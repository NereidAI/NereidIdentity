<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# External IdP Integration Guide

Operational guide for connecting customer-managed identity systems
(Entra ID, Okta, Auth0, Authing, AD FS, Shibboleth, …) to a NereidAI suite
deployment. Product-side requirements are in
[`sso-integration-standard.md`](sso-integration-standard.md); this guide
covers the **one supported path** — brokering behind NereidIdentity — plus
the standalone-delivery exception.

## 1. Rule: customer IdPs are always brokered

In a suite deployment the customer IdP is connected to NI (Keycloak) using
**Identity Brokering**, never to NS or a product directly:

```
Browser ── OIDC/SAML ──► NI Keycloak ──► NS ── ticket ──► Products
                          ▲ broker
                   Customer IdP (OIDC or SAML 2.0)
```

Consequences:

- NS is configured once, against NI only. Its issuer never changes.
- Mode-1 products need no change at all; mode-2 products keep their NI
  clients. Adding, swapping or disabling the customer IdP requires no product
  or NS config change and no restart.
- OIDC **and SAML 2.0** customer systems are supported by the same mechanism.
- Federated account lifecycle is owned by the customer (password, MFA,
  lockout, deprovisioning). Keycloak stores only a federated link; the NS
  admin console shows such users read-only.
- Mapping the customer's groups/claims onto the suite roles
  (`user`/`operator`/`admin`) happens in NI broker mappers, in one place, so
  every product receives the same roles.

## 2. What to request from the customer

### OIDC IdP

- Issuer / discovery URL (must be reachable from the cluster; provide egress
  proxy or an air-gapped mirror if required — the suite makes no outbound
  calls itself except broker login flows).
- A confidential client registration: `client_id` + `client_secret`,
  authorization-code flow.
- Redirect/reply URL to register at the customer IdP:
  `https://sso.<suite-domain>/auth/realms/nereidai/broker/<alias>/endpoint`
  (`<alias>` chosen during setup, e.g. `entra`, `okta`).
- Claims: subject (`sub`), email, display name/preferred username, and a
  groups/roles attribute whose values map to suite roles.

### SAML 2.0 IdP

- IdP metadata XML URL or file (entity ID, SSO endpoints, signing certificate).
- ACS URL:
  `https://sso.<suite-domain>/auth/realms/nereidai/broker/<alias>/endpoint`
- NameID format (persistent or email), group/role attribute in the assertion.

## 3. Broker setup

Either use the NI admin console (realm `nereidai` → Identity Providers →
Add provider) or the Keycloak Admin REST API, executed with the master admin
or an equivalent realm-administration account (this is an **operator action on
NI**; NS and products are not involved):

```
POST /auth/admin/realms/nereidai/identity-provider/instances
GET  /auth/admin/realms/nereidai/identity-provider/instances
DELETE /auth/admin/realms/nereidai/identity-provider/instances/{alias}
```

Provider body: `providerId` (`oidc` or `saml`), `alias`, `enabled`,
`config` (client id/secret or metadata URL, `useJwksUrl`,
`validateSignature`, sync mode).

Mandatory configuration:

1. **Mappers:** customer group/claim → Keycloak realm role, one mapper per
   suite role (`user`/`operator`/`admin`). Keep the vocabulary exactly as in
   the SSO standard §5; never map customer groups straight to product-local
   roles.
2. **First login flow:** use Keycloak's first broker login with automatic
   provisioning and a uniqueness strategy (email verified, or IdP-subject).
   Review whether duplicate emails across IdPs are allowed for the
   deployment.
3. **Signature validation:** require signed assertions/claims and validate
   the IdP certificate/JWKS; plan certificate rotation.
4. **Lockout propagation:** verify that a disabled/locked customer account
   fails the brokered login (the IdP must re-authenticate; do not grant
   long-lived Keycloak offline sessions for federated users).

Optional:

- Multiple IdPs may be attached at once; Keycloak shows a chooser or accepts
  `kc_idp_hint=<alias>` on the login URL (NS can deep-link per deployment).
- Hide the built-in username/password form on the login screen when the
  deployment is IdP-only (keep the Keycloak master admin reachable).

## 4. Validation

1. NS login redirects to NI; NI offers (or auto-redirects to) the customer
   login; after customer consent/authentication the browser returns to NS
   with an NS session.
2. Federated user appears in the NS portal; ticket entry into every mode-1
   product succeeds, the product JIT-creates the local user and assigns the
   roles mapped at the broker.
3. A mode-2 product (e.g. NereidLink) login receives the same mapped roles
   from `realm_access.roles`.
4. Group change at the customer IdP is reflected on the next login; a
   disabled customer account cannot log in anywhere.
5. Disabling the broker instance restores built-in-account login without any
   NS/product change; break-glass local administrators still work.

## 5. Standalone delivery exception (mode 3)

When a **single product** is delivered without the suite (no NS, no shared
NI), that product may be configured as a standard OIDC relying party directly
against the customer IdP. This is explicitly outside suite governance
(documented in the SSO standard §2):

- No suite SSO, no NS portal, no NS account administration.
- No unified logout and no cross-product disable; user lifecycle is fully
  owned by the customer.
- The customer registers one confidential client for that product, using the
  product's own callback path (Link `/v1/auth/oidc/callback`, Horizon/Forge
  `/auth/callback`).
- Configure the product's OIDC block (discovery issuer, client id/secret,
  `roles_claim`/`role_map`, JIT tenant/default role); requirements are the
  mode-2 RP requirements in the standard §6 applied to the customer issuer.
- The product keeps its local break-glass administrator.

Claim mapping for common vendors (mode 3 reference; the same mapping can be
expressed as broker mappers in the standard path):

#### Entra ID (Azure AD)

Tokens carry `groups` as group **object IDs**. Create three groups
(NereidAI Users / Operators / Admins) and map object IDs:

```yaml
roles_claim: groups
role_map:
  "11111111-1111-1111-1111-111111111111": user
  "22222222-2222-2222-2222-222222222222": operator
  "33333333-3333-3333-3333-333333333333": admin
```

For many groups, emit app roles in a `roles` claim instead and point
`roles_claim` at `roles`.

#### Okta

```yaml
roles_claim: groups
role_map:
  nereidai-user: user
  nereidai-operator: operator
  nereidai-admin: admin
```

#### Authing / generic OIDC

```yaml
roles_claim: groups
role_map: { user: user, operator: operator, admin: admin }
```

Products accept dotted claim paths for nested claims
(e.g. `realm_access.roles`).

## 6. Rollback and emergency

- A broken federation must never lock operators out: the NI master admin and
  the NS break-glass local administrator remain available; built-in accounts
  still log in when the broker is disabled.
- Disabling the IdP instance in NI restores built-in-only login instantly;
  no downstream change.
- Rotate the customer client secret (OIDC) or signing certificate (SAML) in
  NI only; NS and products are unaffected.
- JIT users created from federated logins are keyed by IdP+subject;
  re-enabling the same IdP relinks them. Removing the IdP leaves local
  product users in place (products decide deactivation policy per
  deployment).
