# Copyright (C) 2026 YIQISOFT
# SPDX-License-Identifier: Apache-2.0

"""Idempotent post-install bootstrap for the NereidAI realm.

Keycloak realm imports cannot grant roles onto the service-account user that
the engine auto-creates for a ``serviceAccountsEnabled`` client, and an
already-imported realm is never overwritten on upgrade. This script therefore
runs after every install/upgrade against the Keycloak Admin REST API and
reconciles the pieces of state the import cannot own:

1. the ``nereidsphere-admin`` client keeps ``fullScopeAllowed=true`` and the
   default ``roles`` client scope (otherwise client-credentials tokens carry
   no ``realm_access``/``resource_access`` claims and Admin API calls 403);
2. its service-account user holds the composite
   ``realm-management/realm-admin`` client role;
3. the single suite-wide human admin user (``admin``) exists, enabled, with
   the realm ``admin``/``user`` roles. It is created once with a generated
   password; an existing user is never updated, so upgrades never rotate the
   password or disturb live sessions;
4. a realm-level ``groups`` client scope carrying the
   ``oidc-group-membership-mapper`` (full paths) exists and is attached as a
   default scope to the SSO client(s), so issued tokens expose group
   membership such as ``/nereidlink/<tenant>/<role>`` in a ``groups`` claim.
   Keycloak 26 ships no built-in groups scope;
5. the NereidAI login theme is active and its native language selector offers
   exactly the configured English and Simplified Chinese locales. Realm import
   declares the same state for fresh installations; this reconciliation is
   required because an existing realm is never re-imported.

It finally self-validates by minting a client-credentials token and calling
``GET admin/realms/<realm>/users``. Standard library only, so it runs inside
the minimal deploy-tools image.

Environment:
    KC_BASE_URL: Keycloak base URL ending in /auth (in-cluster Service URL
        when run from the Helm hook, http://localhost:8090/auth in dev).
    KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD: master bootstrap administrator.
    KC_REALM: target realm, defaults to ``nereidai``.
    KC_ADMIN_CLIENT_ID: service-account client id, defaults to
        ``nereidsphere-admin``.
    KC_ADMIN_CLIENT_SECRET: secret of that client, used only for the final
        self-validation. Required.
    KC_LOGIN_THEME / KC_DEFAULT_LOCALE / KC_SUPPORTED_LOCALES: login theme,
        default locale and comma-separated selector locales; default to
        nereidai / en / en,zh-CN.
    KC_SUITE_ADMIN_PASSWORD: password for the suite-wide human admin user.
        When unset, suite-admin reconciliation is skipped entirely (dev
        compose keeps the seed user from the realm import).
    KC_SUITE_ADMIN_USERNAME / _EMAIL / _FIRST_NAME / _LAST_NAME: identity
        fields for that user, defaulting to admin / admin@nereidai.local /
        Admin / User.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ["KC_BASE_URL"].rstrip("/")
ADMIN_USER = os.environ["KEYCLOAK_ADMIN"]
ADMIN_PASSWORD = os.environ["KEYCLOAK_ADMIN_PASSWORD"]
REALM = os.environ.get("KC_REALM", "nereidai")
ADMIN_CLIENT_ID = os.environ.get("KC_ADMIN_CLIENT_ID", "nereidsphere-admin")
ADMIN_CLIENT_SECRET = os.environ["KC_ADMIN_CLIENT_SECRET"]

MAX_ATTEMPTS = 72
RETRY_SECONDS = 5

# Clients whose tokens must carry the groups claim. nereidsphere is NS's SSO
# RP (mandatory); the product clients are covered so direct-to-NI OIDC mode
# reads the same assignments.
GROUP_CLAIM_CLIENTS = ("nereidsphere", "nereidlink", "nereidhorizon",
                       "nereidforge")
GROUPS_SCOPE = "groups"
LOGIN_THEME = os.environ.get("KC_LOGIN_THEME", "nereidai")
DEFAULT_LOCALE = os.environ.get("KC_DEFAULT_LOCALE", "en")
SUPPORTED_LOCALES = [
    locale.strip()
    for locale in os.environ.get("KC_SUPPORTED_LOCALES", "en,zh-CN").split(",")
    if locale.strip()
]


class BootstrapError(RuntimeError):
    """BootstrapError aborts the hook with a non-zero exit code."""


def request(method, path, token=None, body=None):
    """request performs one Admin/token REST call.

    Returns the decoded JSON body (dict/list) or ``None`` for 204 responses.
    Raises urllib.error.HTTPError/URLError for transport and status failures;
    the caller decides which failures are retryable.
    """
    url = BASE_URL + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if not raw:
            return None
        return json.loads(raw)


def with_retry(description, fn):
    """with_retry runs fn until it succeeds or the bounded attempt budget ends.

    Connection errors, 404 (realm import still in progress) and 5xx are
    retried; every other HTTP status is a fatal configuration error.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 500, 502, 503, 504):
                kind = "not ready yet"
            else:
                detail = exc.read().decode("utf-8", "replace")
                raise BootstrapError(
                    "%s failed: HTTP %d %s" % (description, exc.code, detail)
                ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            kind = str(exc)
        print("%s: %s (attempt %d/%d, retry in %ds)"
              % (description, kind, attempt, MAX_ATTEMPTS, RETRY_SECONDS))
        time.sleep(RETRY_SECONDS)
    raise BootstrapError("%s: timed out waiting for Keycloak" % description)


def master_token():
    """master_token mints an admin token from the master realm password grant."""
    form = urllib.parse.urlencode({
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
        "grant_type": "password",
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + "/realms/master/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["access_token"]


def find_client(token, client_id):
    """find_client returns the internal UUID and representation of a client."""
    query = urllib.parse.urlencode({"clientId": client_id})
    clients = request(
        "GET",
        "/admin/realms/%s/clients?%s" % (REALM, query),
        token=token,
    )
    if not clients:
        raise urllib.error.HTTPError(
            "<lookup>", 404, "client not imported yet", {}, None)
    return clients[0]["id"], clients[0]


def reconcile():
    """reconcile brings client scope flags and the SA role mapping to target.

    Returns the master admin token so subsequent steps reuse it.
    """
    token = with_retry("master login", master_token)

    with_retry("wait for realm " + REALM,
               lambda: request("GET", "/admin/realms/%s" % REALM, token=token))

    client_uuid, client = with_retry(
        "lookup " + ADMIN_CLIENT_ID, lambda: find_client(token, ADMIN_CLIENT_ID))

    if not client.get("fullScopeAllowed"):
        client["fullScopeAllowed"] = True
        with_retry("enable full scope on " + ADMIN_CLIENT_ID, lambda: request(
            "PUT", "/admin/realms/%s/clients/%s" % (REALM, client_uuid),
            token=token, body=client))
        print("fullScopeAllowed enabled on", ADMIN_CLIENT_ID)

    scopes = with_retry(
        "list client scopes",
        lambda: request("GET", "/admin/realms/%s/client-scopes" % REALM,
                        token=token))
    roles_scope = next((s for s in scopes if s["name"] == "roles"), None)
    if roles_scope is None:
        raise BootstrapError("built-in 'roles' client scope not found")
    with_retry(
        "attach roles default scope",
        lambda: request(
            "PUT",
            "/admin/realms/%s/clients/%s/default-client-scopes/%s"
            % (REALM, client_uuid, roles_scope["id"]),
            token=token))

    service_user = with_retry(
        "lookup service-account user",
        lambda: request(
            "GET",
            "/admin/realms/%s/clients/%s/service-account-user"
            % (REALM, client_uuid),
            token=token))
    user_uuid = service_user["id"]

    rm_uuid = with_retry(
        "lookup realm-management client",
        lambda: find_client(token, "realm-management"))[0]
    realm_admin_role = with_retry(
        "lookup realm-admin role",
        lambda: request(
            "GET",
            "/admin/realms/%s/clients/%s/roles/realm-admin"
            % (REALM, rm_uuid),
            token=token))

    existing = with_retry(
        "read current role mapping",
        lambda: request(
            "GET",
            "/admin/realms/%s/users/%s/role-mappings/clients/%s"
            % (REALM, user_uuid, rm_uuid),
            token=token)) or []
    if not any(r.get("name") == "realm-admin" for r in existing):
        with_retry(
            "grant realm-admin to service account",
            lambda: request(
                "POST",
                "/admin/realms/%s/users/%s/role-mappings/clients/%s"
                % (REALM, user_uuid, rm_uuid),
                token=token, body=[realm_admin_role]))
        print("realm-management/realm-admin granted to service account",
              service_user["username"])
    else:
        print("realm-management/realm-admin already granted")

    return token


def ensure_login_settings(token):
    """ensure_login_settings activates the suite theme and bilingual selector.

    Only these four realm fields are changed; the rest of the live realm
    representation is sent back untouched. The default locale must be one of
    the selectable locales, otherwise Keycloak cannot resolve it consistently.
    """
    if not SUPPORTED_LOCALES:
        raise BootstrapError("KC_SUPPORTED_LOCALES must not be empty")
    if DEFAULT_LOCALE not in SUPPORTED_LOCALES:
        raise BootstrapError(
            "default locale %s is not in supported locales %s"
            % (DEFAULT_LOCALE, ",".join(SUPPORTED_LOCALES)))

    desired = {
        "loginTheme": LOGIN_THEME,
        "internationalizationEnabled": True,
        "supportedLocales": SUPPORTED_LOCALES,
        "defaultLocale": DEFAULT_LOCALE,
    }
    realm = with_retry(
        "read login settings",
        lambda: request("GET", "/admin/realms/%s" % REALM, token=token))
    changes = {key: value for key, value in desired.items()
               if realm.get(key) != value}
    if not changes:
        print("login theme and bilingual locales already configured")
        return

    realm.update(desired)
    with_retry(
        "configure login theme and bilingual locales",
        lambda: request("PUT", "/admin/realms/%s" % REALM,
                        token=token, body=realm))
    print("login settings reconciled:", ", ".join(sorted(changes)))


def ensure_group_claim_scope(token):
    """ensure_group_claim_scope creates the 'groups' client scope with the
    oidc-group-membership-mapper (full paths) and attaches it as a default
    scope to the SSO clients, so access/id tokens and userinfo expose realm
    group membership as a 'groups' claim (e.g. /nereidlink/<tenant>/<role>).
    Idempotent: existing scope/mapper/bindings are left untouched. Keycloak
    26 has no built-in groups client scope.
    """
    scopes = with_retry(
        "list client scopes",
        lambda: request("GET", "/admin/realms/%s/client-scopes" % REALM,
                        token=token))
    scope = next((s for s in scopes if s["name"] == GROUPS_SCOPE), None)
    if scope is None:
        with_retry(
            "create groups client scope",
            lambda: request(
                "POST", "/admin/realms/%s/client-scopes" % REALM, token=token,
                body={"name": GROUPS_SCOPE,
                      "protocol": "openid-connect",
                      "attributes": {"include.in.token.scope": "true",
                                     "display.on.consent.screen": "false"}}))
        scopes = with_retry(
            "relist client scopes",
            lambda: request("GET", "/admin/realms/%s/client-scopes" % REALM,
                            token=token))
        scope = next(s for s in scopes if s["name"] == GROUPS_SCOPE)
        print("created client scope:", GROUPS_SCOPE)

    mappers = with_retry(
        "list groups scope mappers",
        lambda: request(
            "GET",
            "/admin/realms/%s/client-scopes/%s/protocol-mappers/models"
            % (REALM, scope["id"]), token=token)) or []
    if any(m.get("protocolMapper") == "oidc-group-membership-mapper"
           for m in mappers):
        print("group-membership mapper already present on", GROUPS_SCOPE)
    else:
        with_retry(
            "add group-membership mapper",
            lambda: request(
                "POST",
                "/admin/realms/%s/client-scopes/%s/protocol-mappers/models"
                % (REALM, scope["id"]), token=token,
                body={"name": "groups",
                      "protocol": "openid-connect",
                      "protocolMapper": "oidc-group-membership-mapper",
                      "config": {"claim.name": "groups",
                                 "full.path": "true",
                                 "id.token.claim": "true",
                                 "access.token.claim": "true",
                                 "userinfo.token.claim": "true"}}))
        print("added oidc-group-membership-mapper to", GROUPS_SCOPE)

    for client_id in GROUP_CLAIM_CLIENTS:
        query = urllib.parse.urlencode({"clientId": client_id})
        clients = with_retry(
            "lookup " + client_id,
            lambda q=query: request(
                "GET", "/admin/realms/%s/clients?%s" % (REALM, q),
                token=token))
        if not clients:
            print("skip missing client:", client_id)
            continue
        client_uuid = clients[0]["id"]

        defaults = with_retry(
            "list default scopes of " + client_id,
            lambda: request(
                "GET",
                "/admin/realms/%s/clients/%s/default-client-scopes"
                % (REALM, client_uuid), token=token))
        if any(s["id"] == scope["id"] for s in defaults):
            print("groups scope already attached to", client_id)
            continue
        with_retry(
            "attach groups scope to " + client_id,
            lambda: request(
                "PUT",
                "/admin/realms/%s/clients/%s/default-client-scopes/%s"
                % (REALM, client_uuid, scope["id"]), token=token))
        print("groups scope attached to", client_id)


def find_user_by_username(token, username):
    """find_user_by_username returns the user representation or None."""
    query = urllib.parse.urlencode({"username": username, "exact": "true"})
    users = with_retry(
        "lookup user " + username,
        lambda: request(
            "GET", "/admin/realms/%s/users?%s" % (REALM, query),
            token=token))
    return users[0] if users else None


def ensure_suite_admin(token):
    """ensure_suite_admin creates the shared human admin once and binds roles.

    The user is created with a non-temporary password; if it already exists,
    neither its password nor any other field is touched. The realm ``admin``
    and ``user`` roles are reconciled idempotently. No-op when
    KC_SUITE_ADMIN_PASSWORD is unset (dev compose keeps the imported seed
    user).
    """
    password = os.environ.get("KC_SUITE_ADMIN_PASSWORD")
    if not password:
        print("suite admin reconciliation skipped "
              "(KC_SUITE_ADMIN_PASSWORD unset)")
        return

    username = os.environ.get("KC_SUITE_ADMIN_USERNAME", "admin")
    email = os.environ.get("KC_SUITE_ADMIN_EMAIL", "admin@nereidai.local")

    user = find_user_by_username(token, username)
    if user is None:
        body = {
            "username": username,
            "email": email,
            "firstName": os.environ.get("KC_SUITE_ADMIN_FIRST_NAME", "Admin"),
            "lastName": os.environ.get("KC_SUITE_ADMIN_LAST_NAME", "User"),
            "enabled": True,
            "emailVerified": True,
            "credentials": [{
                "type": "password",
                "value": password,
                "temporary": False,
            }],
        }
        with_retry(
            "create suite admin " + username,
            lambda: request("POST", "/admin/realms/%s/users" % REALM,
                            token=token, body=body))
        user = with_retry(
            "reread created suite admin",
            lambda: find_user_by_username(token, username))
        print("suite admin user created:", username)
    else:
        print("suite admin user already exists; password left untouched")

    desired = []
    for role_name in ("admin", "user"):
        role = with_retry(
            "lookup realm role " + role_name,
            lambda rn=role_name: request(
                "GET", "/admin/realms/%s/roles/%s" % (REALM, rn),
                token=token))
        desired.append(role)

    current = with_retry(
        "read suite admin role mapping",
        lambda: request(
            "GET", "/admin/realms/%s/users/%s/role-mappings/realm"
            % (REALM, user["id"]), token=token)) or []
    have = {r["name"] for r in current}
    missing = [r for r in desired if r["name"] not in have]
    if missing:
        with_retry(
            "bind realm roles to suite admin",
            lambda: request(
                "POST", "/admin/realms/%s/users/%s/role-mappings/realm"
                % (REALM, user["id"]), token=token, body=missing))
        print("realm roles granted to %s: %s"
              % (username, ", ".join(sorted(r["name"] for r in missing))))
    else:
        print("suite admin realm roles already bound")


def self_validate():
    """self_validate proves the service account can administer the realm."""
    form = urllib.parse.urlencode({
        "client_id": ADMIN_CLIENT_ID,
        "client_secret": ADMIN_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode("utf-8")

    def mint():
        req = urllib.request.Request(
            BASE_URL + "/realms/%s/protocol/openid-connect/token" % REALM,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["access_token"]

    sa_token = with_retry("client-credentials token", mint)

    def list_users():
        return request("GET", "/admin/realms/%s/users" % REALM, token=sa_token)

    users = with_retry("list realm users as service account", list_users)
    print("self-validation OK: service account listed %d user(s)" % len(users))


def main():
    """main is the hook entry point; non-zero exit fails the Helm hook Job."""
    token = reconcile()
    ensure_login_settings(token)
    ensure_group_claim_scope(token)
    ensure_suite_admin(token)
    self_validate()
    print("bootstrap complete")


if __name__ == "__main__":
    try:
        main()
    except BootstrapError as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(1)
