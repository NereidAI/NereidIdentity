<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# NereidIdentity Pitfalls

Root causes found while building/operating the identity plane, in the
Symptom / Root cause / Permanent rule form. Read before touching the chart,
realm import or admin automation.

## 1. Service-account admin token gets 403 from the Admin API

- **Symptom:** `nereidsphere-admin` exchanges client-credentials successfully
  but `GET /auth/admin/realms/nereidai/users` returns 403; the token carries
  no `realm_access`/`resource_access` claims.
- **Root cause (two independent requirements):**
  1. A client with `fullScopeAllowed=false` gets no role claims in its
     client-credentials token, even after roles are bound to the
     service-account user. The `roles` default client scope must also be
     attached.
  2. A realm import **cannot grant roles onto the service-account user
     Keycloak auto-creates** for a `serviceAccountsEnabled` client. Declaring
     a `service-account-<client>` user with roles in the import JSON is
     silently ignored.
- **Permanent rule:** the admin client ships with `fullScopeAllowed=true`
  and default scope `["roles"]`; the idempotent post-install/upgrade hook
  (`files/realm-bootstrap.py`, Helm Job + compose `bootstrap` profile) is the
  only owner of the `realm-management/realm-admin` binding and self-validates
  via a client-credentials `GET users`. Never move that grant "back" into the
  realm JSON.

## 2. Keycloak CrashLoops on a fresh install: connection refused to the DB

- **Symptom:** new cluster install — Keycloak Pod restarts with
  `Connection to keycloak-db-rw:5432 refused` before the CNPG Cluster is
  ready, and keeps CrashLoopBackOff until the pod is force-deleted.
- **Root cause:** Keycloak starts as soon as the Service exists; the CNPG
  database accepts connections only after initdb completes.
- **Permanent rule:** the keycloak subchart `dbchecker` init container is
  enabled in chart values (busybox `nc` gate on `keycloak-db-rw:5432`).
  Do not remove it to "speed up" installs.

## 3. Existing realms are never re-imported

- **Symptom:** changed `identity.clients.*` values, upgraded the release,
  live realm unchanged (old secret, old client flags).
- **Root cause:** Keycloak `--import-realm` imports only when the realm does
  not exist; it is not a reconciliation mechanism.
- **Permanent rule:** realm/secret rotation on a live deployment goes through
  the Keycloak Admin API/UI or an explicit re-import (drop/recreate realm);
  Helm values own only the first-import state plus what the bootstrap hook
  reconciles. The chart README "Realm lifecycle" section states this.

## 4. ROPC must stay disabled; NS integration assumes browser login

- **Symptom:** a server-side password-grant client fails
  (`unauthorized_client` / grant disabled) against the `nereidai` realm.
- **Root cause:** every realm client ships with
  `directAccessGrantsEnabled=false` per the SSO standard (MFA/passkey and
  brokered IdPs are incompatible with ROPC).
- **Permanent rule:** login is authorization-code + PKCE browser flow (NS is
  the only relying party; products use NS tickets). Do not re-enable the
  password grant "temporarily" for debugging — use a realm client with a
  registered redirect or the master admin password grant on the master
  realm for API checks.

## 5. Concurrent group creation logs `sibling_names` 23505

- **Symptom:** the Keycloak log shows
  `duplicate key value violates unique constraint "sibling_names"` on
  `insert into KEYCLOAK_GROUP`, possibly together with `HHH100503: On
  release of batch it still contained JDBC statements`. A sequential
  duplicate create answers `409 Sibling group named ... already exists`;
  the 500 only appears when two check-then-create transactions overlap
  (multiple NS replicas + duplicate admin-UI requests).
- **Root cause:** Keycloak's group creation is check-then-insert, not
  atomic; nothing is corrupted, and the desired group exists after the
  racing pair settles. The failure lives in the **writer** (NS admin
  console): it treated 409/500-duplicate as fatal instead of adopting the
  group the competing transaction created, so the same missing segment was
  retried and could collide again.
- **Permanent rule:** NS `EnsureGroupExists` (1) serializes hierarchy
  creation in-process and (2) on 409 or a 500 whose body names
  `sibling_names`/`duplicate key`/`already exists`, re-reads the group list
  with bounded retries and adopts the existing ID — never fails the
  assignment. NI itself needs no change; these ERROR lines are noise when
  no client is failing.

## 6. A non-null `clientScopes` in the import JSON suppresses all built-in scopes

- **Symptom:** on a fresh import the realm has only the custom `groups`
  scope plus `offline_access`; Keycloak logs
  `Referenced client scope 'roles' doesn't exist. Ignoring` for
  `roles`/`web-origins`/`profile`/`email`, and the bootstrap hook aborts
  with `built-in 'roles' client scope not found`. Client default-scope
  references in the same JSON are silently dropped.
- **Root cause:** `RealmManager.importRealm` (Keycloak 26.1) seeds the
  built-in default client scopes only when
  `RealmRepresentation.getClientScopes() == null`. An empty array `[]` and a
  populated array are equally non-null, so declaring just the custom
  `groups` scope disables the whole built-in set. `offline_access` is
  created on a separate code path, which is why it survives.
- **Permanent rule:** the realm JSON must not carry a top-level
  `clientScopes` key, and client `defaultClientScopes` arrays list only
  built-in scopes (no `groups`). Keycloak then seeds every built-in scope
  with zero import warnings, and the custom `groups` scope — its mapper
  plus its per-client default-scope attachments — is owned exclusively by
  the idempotent bootstrap hook (`ensure_group_claim_scope`). Never re-add
  inline scope declarations or `groups` references to "make the JSON
  self-contained" — they would break or noisy-fail every fresh install,
  including the compose dev stack and new customer sites.
