<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# NereidAI OIDC / OAuth2 Contract

> Superseded in scope by [`sso-integration-standard.md`](sso-integration-standard.md)
> (product integration requirements and deployment topologies) and
> [`external-idp-guide.md`](external-idp-guide.md) (customer IdP onboarding).
> This page keeps the short engine contract.

NereidIdentity publishes the identity service consumed by every NereidAI
product. The contract is engine-agnostic: Keycloak is the current
implementation; any OIDC/OAuth2-compliant engine satisfying this contract can
replace it with configuration-only changes in the products.

## Required engine capabilities

1. OIDC Discovery 1.0 (`/.well-known/openid-configuration`).
2. Authorization Code flow with PKCE, refresh tokens and RP-initiated
   logout.
3. Confidential clients with client-secret authentication; exact redirect URI
   matching; one client-credentials service account with realm administration
   for the NS admin console.
4. ID token / access token JWT verifiable via published JWKS, with a
    configurable claim carrying coarse roles (`realm_access.roles` on
    Keycloak; mapper-produced for federated users) and a standard `groups`
    claim carrying full realm-group paths for NS-managed assignments.
5. Suite roles `user` / `operator` / `admin`; fine-grained authorization is
   product-local.
6. HTTPS behind the suite ingress with forwarded-protocol header support, so
   issuer URLs are https.
7. Resource Owner Password Credentials (ROPC) is **not used** (clients ship
   with `directAccessGrantsEnabled=false`).
8. **Identity brokering**: federate external OIDC and SAML 2.0 providers with
   group/claim-to-role mappers, so customer IdPs connect behind NI and never
   to NS/products directly.
9. **Admin REST API**: realm user CRUD, role assignment and identity-provider
   instance management, usable by a client-credentials service account.
10. Realm provisioning by declarative import (clients/roles) plus an
    idempotent post-install bootstrap for state the import cannot own (the
    `nereidsphere-admin` service-account role binding, and the single shared
    suite `admin` user with its realm roles).

## Clients (built-in realm)

Only the NS client is mandatory in a suite deployment: NS is the sole OIDC
relying party in the default (ticket) integration. The per-product clients
exist for products deployed in mode 2 (direct-to-NI OIDC, see the SSO
standard §2/§6).

| client_id | Type | Purpose |
|---|---|---|
| `nereidsphere` | confidential, auth-code+PKCE | NS portal login (always) |
| `nereidlink` | confidential, auth-code+PKCE | NereidLink mode 2 |
| `nereidhorizon` | confidential, auth-code+PKCE | NereidHorizon mode 2 |
| `nereidforge` | confidential, auth-code+PKCE | NereidForge mode 2 |
| `nereidsphere-admin` | service account, client-credentials | NS admin console ↔ Admin API (realm-admin; bound by the chart bootstrap hook) |

The admin client requires `fullScopeAllowed=true` plus the default `roles`
client scope; without both, client-credentials tokens omit
`realm_access`/`resource_access` and the Admin API returns 403. The realm
import cannot grant onto the auto-created service-account user, so the
umbrella chart ships an idempotent post-install/upgrade hook that binds
`realm-management/realm-admin` and self-validates the result.

Secrets: development `changeme*` values in `realm/nereidai-realm.json`;
production values rendered from Helm `identity.clients.*` into the import
Secret. The identity plane never pushes secrets into product namespaces.
