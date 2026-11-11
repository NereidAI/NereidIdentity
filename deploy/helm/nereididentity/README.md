<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# nereididentity Helm chart

Umbrella chart for the NereidAI suite identity plane: a dedicated PostgreSQL
(CloudNativePG) plus Keycloak 26, with the `nereidai` realm imported
declaratively at startup. The realm contains the NS login client, the
optional per-product direct-OIDC clients, and the `nereidsphere-admin`
service-account client used by the NS admin console. See
`../../../docs/sso-integration-standard.md` for how NS/products consume it
(ticket-based SSO is the default; product OIDC clients serve direct mode
only).

## Prerequisites

- Helm 3; `helm dependency update` fetches the pristine upstream
  `keycloakx` and `cloudnative-pg` charts from their public repositories
  (or install from a clone that already ran it)
- `cert-manager` with the `internal-ca` ClusterIssuer
- `nfs-csi` StorageClass (or override `postgresql.cluster.storage.storageClass`)
- Public registry access for image pulls; on an authenticated node mirror,
  supply pull Secret names through `keycloak.imagePullSecrets` and
  `bootstrap.imagePullSecrets` (no pull secret is rendered by default)

## Install

Use the root `Makefile` (treaty section 15.8 standard interface):

```bash
install -d -m 700 ../.deployment/deploy-values/nereididentity
cp -n deploy/helm/nereididentity/values-k3s-example.yaml \
  ../.deployment/deploy-values/nereididentity/values.yaml
chmod 600 ../.deployment/deploy-values/nereididentity/values.yaml
# Edit every REPLACE-* secret in the copied file, then run from the repo root.
make helm-dep
make install VALUES=../.deployment/deploy-values/nereididentity/values.yaml
```

`make install` runs `helm upgrade --install` with `--create-namespace` and
`--skip-crds`. To use Helm directly, apply the same flags plus
`-f <your-values.yaml>` to this chart directory.

The release name must be `nereididentity`: the Keycloak subchart mounts the
fixed-name Secrets `nereididentity-realm` and `nereididentity-admin`. The
namespace convention is one namespace per suite product, named after the
product itself (`nereididentity` here; `nereidsphere`, `nereidlink`, … for the
others). This is fixed and not overridden, even for lab/POC installs.

`--skip-crds` is required whenever the CNPG CRDs already exist cluster-wide.

## What gets deployed

| Resource | Owner | Notes |
|---|---|---|
| `cloudnative-pg` operator + `keycloak-db` Cluster | upstream cloudnative-pg chart (alias `postgresql`) + this chart's `cnpg-cluster.yaml` | Services `keycloak-db-rw/-r/-ro:5432`, Secret `pg-keycloak-credentials` |
| `nereididentity-keycloak` StatefulSet + Ingress | keycloak subchart | `https://sso.example.org/auth`, TLS Secret `keycloak-tls` |
| Secret `nereididentity-admin` | this chart | master admin bootstrap (`KEYCLOAK_ADMIN*`) |
| Secret `nereididentity-realm` | this chart | realm JSON rendered from `identity.clients.*`, plus `admin-client-secret` and `suite-admin-password` for the hook |
| ConfigMap `nereididentity-theme` | this chart | NereidAI login theme with English/简体中文 messages, projected into Keycloak's theme directory |
| `dbchecker` init container | keycloak subchart | blocks Keycloak until `keycloak-db-rw:5432` accepts TCP, preventing the startup CrashLoop |
| Job `nereididentity-bootstrap` | this chart | post-install/upgrade hook from `ghcr.io/nereidai/nereididentity-bootstrap`: grants the SA role the import cannot bind, creates the shared suite admin user, attaches the `groups` claim scope, and self-validates |

Issuer URL: `https://sso.example.org/auth/realms/nereidai`.

## Realm lifecycle

Keycloak starts with `--import-realm` and mounts the rendered realm JSON at
`/opt/keycloak/data/import`. Import is idempotent: a realm that already exists
is left untouched. Rotating a client secret after first import must therefore
go through the Keycloak Admin REST API/UI or a deliberate re-import; changing
Helm values alone does not update a live realm.

The realm import creates the `nereidsphere-admin` service-account user but
cannot grant roles onto it. The `nereididentity-bootstrap` post-install/
post-upgrade Job (`files/realm-bootstrap.py`, also used by the compose
`bootstrap` profile) idempotently ensures `fullScopeAllowed=true` with the
default `roles` scope, grants `realm-management/realm-admin`, and proves the
result by listing realm users with a client-credentials token. Hook logs are
the first diagnostic when the NS admin console receives 403.

### Suite admin user

All products share a single human administrator (`identity.suiteAdmin`,
default username `admin`) with the realm `admin` role; every product login
resolves to the same SSO identity. The hook creates this user once: if it
already exists, neither its password nor any other field is touched, so
`helm upgrade` never invalidates sessions.

With `password: ""` (default) the chart generates a 32-character password on
first install, reuses the stored value on every later render, and keeps it in
the `nereididentity-realm` Secret:

```bash
kubectl -n nereididentity get secret nereididentity-realm \
  -o jsonpath='{.data.suite-admin-password}' | base64 -d; echo
```

Password rotation goes through the NS admin console / Keycloak Admin REST API
(or deleting and recreating the user); it is never driven by Helm values.
This user carries the suite `admin` role but no Keycloak console
administration role — realm administration stays with the
`nereidsphere-admin` service account.

### Bilingual login theme

The realm uses the `nereidai` login theme, which inherits Keycloak's stock
authentication flows and translations while overriding NereidAI branding and
locale labels. The native language menu switches between **English** and
**简体中文**; `identity.login.defaultLocale` controls the initial language
(default `en`) and `identity.login.supportedLocales` controls the two entries.
The same files under `files/theme/nereidai/` serve Helm and compose.

Fresh imports declare the theme and locale settings. On upgrades, the
bootstrap hook reconciles them through the Admin REST API because Keycloak
never re-imports an existing realm. A chart revision also rolls the Keycloak
Pod so production theme caches cannot serve stale resources.

### Groups claim

Every SSO client gets a realm-level `groups` client scope (Keycloak 26 has no
built-in one) with an `oidc-group-membership-mapper` emitting **full paths**
into the access token, ID token and userinfo as the `groups` claim. NS writes
per-user, per-product tenant/role assignments as groups shaped
`/nereid{product}/{tenant}/{role}` (e.g.
`/nereidlink/<tenant-uuid>/admins`); the import declares the scope for fresh
realms and the bootstrap hook reconciles it on every upgrade for realms
already imported.

## Switching the OIDC engine

Keycloak is one implementation of `../../../docs/oidc-contract.md`. An
alternative engine replaces the `keycloak` dependency, the realm import and
the bootstrap hook; only NS changes its OIDC connection settings, and
ticket-mode products stay unchanged.
