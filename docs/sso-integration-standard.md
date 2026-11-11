<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# NereidAI SSO Integration Standard

Version 2 — 2026-10-14. Owner: NereidIdentity. This document is the single
source of truth for single sign-on across the suite (NereidSphere,
NereidLink, NereidHorizon, NereidForge). Product agents implement this
standard; they do not invent proprietary auth handshakes.

Version 2 supersedes version 1 (every-product-an-OIDC-RP). The default is now
**NS-federated login via one-time tickets**; per-product direct OIDC remains
an allowed option; customer IdPs are always brokered behind NereidIdentity.

## 1. Core Principle

```
                        ┌─────────────────────────────┐
Browser ── OIDC ──► NS ──► NereidIdentity (Keycloak)  │
 only NS talks        │  ├── built-in accounts       │
 OIDC to NI           │  └── brokered customer IdP    │
                      │      (OIDC or SAML 2.0)       │
                      └──────────────┬──────────────┘
                                     │ one-time ticket (mode 1, default)
                                     ▼
                     Products (Link / Horizon / Forge)
```

1. **NereidSphere (NS) is the only suite component that speaks OIDC to
   NereidIdentity (NI).** NS is a confidential relying party using
   authorization-code + PKCE; it holds the suite session.
2. **NS only ever points at NI.** It has no configuration for customer IdPs.
   Customer-managed identity systems (Entra ID, Okta, Auth0, Authing, AD FS,
   …) are connected **behind NI** using Keycloak Identity Brokering. Adding,
   swapping or removing a brokered IdP changes nothing in NS or the products
   — no config change, no restart.
3. **Products do not configure OIDC in the default mode.** They trust NS via
   the ticket exchange in §4 and mint their own local sessions.
4. **Authorization stays product-local.** NI/NS provide identity
   (sub/email/name/roles); RBAC, tenancy and feature permissions remain
   entirely inside each product.
5. **ROPC (`grant_type=password`) is forbidden everywhere.** It is deprecated
   by OAuth 2.0 best practice (RFC 9700), blocks MFA/passkey, and cannot work
   against brokered IdPs.

## 2. Integration Modes

Each product selects its mode independently in deployment configuration;
mixed deployments are first-class (for example Link direct, the rest
NS-federated).

| Mode | Who logs into the browser | Product OIDC config | Suite SSO | Account governance |
|---|---|---|---|---|
| **1. NS-federated (default)** | NS ↔ NI only | None — product trusts NS tickets | Yes | Full (accounts live in NI) |
| **2. Direct-to-NI OIDC** (optional, per product) | Product ↔ NI directly | issuer/client/secret of NI | Yes (NI SSO session) | Full (accounts live in NI; NS console still manages/disable them) |
| **3. Direct-to-customer IdP** | Product ↔ customer IdP | Customer-issued, **NI bypassed** | No | None — outside the suite |

Rules:

- In any **suite deployment**, a product MUST use mode 1 or mode 2. It MUST
  NOT federate directly with a customer IdP: doing so removes suite SSO,
  unified logout and NS account governance (disable/reset/roles) and turns
  the product into a standalone deployment.
- **Mode 3 exists only for single-product standalone deliveries** sold
  without the suite. It is documented for completeness (see
  `external-idp-guide.md` §5); the suite installers never configure it.
- Customer SSO in a suite deployment is **always** a NI broker. Both mode 1
  and mode 2 products see it with zero change: NI presents the same issuer,
  clients and claims either way.
- Mode selection is deployment configuration, not code. The product binary
  supports every mode allowed for that product.

### What NS can govern, per mode

| Capability | Mode 1 | Mode 2 | Mode 3 |
|---|---|---|---|
| Suite SSO (one login for all products) | Yes | Yes (NI session) | No |
| NS account CRUD / password reset / roles | Yes | Yes (via NI Admin API) | No |
| Disabling a user takes effect | Immediately (next ticket/login) | At next product login/token refresh | Never |
| NS sees the product's live sessions | No (product-local session) | No | No |
| Unified logout | Product logout → NS logout → NI end-session | Best-effort RP-initiated per product | No |

Products always own their local session after handoff; NS never proxies
per-request API traffic in mode 1 and never holds product sessions.

## 3. NS ↔ NI Session (modes 1 and 2 share it)

1. NS performs **authorization-code + PKCE (S256)** against NI's OIDC
   discovery document, with `state` and `nonce`, and verifies the ID token via
   JWKS (issuer/audience/nonce/expiry). Baseline scopes:
   `openid profile email roles` (`roles` is a Keycloak client scope carrying
   `realm_access.roles`).
2. NS establishes its own server-side session with the browser (sealed
   HttpOnly `ns_session` cookie, refresh, idle/absolute timeouts); browser
   JavaScript never sees IdP tokens.
3. NS supports RP-initiated logout against NI's `end_session_endpoint` and
   then clears the NS session.
4. A **break-glass local administrator** remains available when NI is
   unreachable or SSO is disabled (`auth.mode: local`, account from
   deployment values/Secret). It is an emergency path only, never the default
   in production.
5. Account administration (built-in accounts only) uses the
   `nereidsphere-admin` service-account client (client-credentials,
   realm-management/realm-admin, provisioned by the NI chart). NS never uses
   the Keycloak master admin password. Accounts federated from a brokered
   IdP are read-only in the NS console (lifecycle owned by the customer IdP).

## 4. Mode 1 — Ticket Exchange Contract

This is the mandatory wire contract between NS and every mode-1 product. The
reference implementation already exists in NS (`/auth/enter/{product}`,
`/api/v1/auth/ticket/verify`); products implement only their side.

### 4.1 Flow

```
1. Browser → Product (any protected URL, no session)
2. Product  → 302 {ns_base_url}/auth/enter/{product_id}?to={relative path}
3. NS: no NS session → NI login (auth-code+PKCE) → NS session
   NS: valid session → mint ticket → 302 {product_callback}?ticket=…&to=…
4. Browser → Product callback (public route)
5. Product backend → POST {ns_base_url}/api/v1/auth/ticket/verify
       headers: X-NS-Client-Id: {product_id}
                X-NS-Client-Secret: {shared secret}
       body:    {"ticket": "…"}
6. NS → 200 {"identity": {…}, "to": "…"}   (or a TICKET_* error)
7. Product: JIT-provision/update local user, mint product session,
   redirect browser to the validated relative `to` path.
```

Entry from the NS portal uses the same step-3 URL, so the product side is
identical whether the user starts at the portal or at a product deep link.

### 4.2 NS endpoints (stable contract)

- `GET /auth/enter/{product_id}?to=<relative path>` — browser endpoint.
  Requires an NS session; otherwise starts the OIDC login and returns here.
  Redirects (302) to the product's registered callback with `ticket` and
  `to`. Unknown product → 404; non-relative `to` → 400.
- `POST /api/v1/auth/ticket/verify` — server-to-server only. Authentication:
  headers `X-NS-Client-Id` (the product id from the NS product catalogue) and
  `X-NS-Client-Secret` (constant-time compared). Request body
  `{"ticket":"..."}`.

Success response (HTTP 200):

```json
{
  "identity": {
    "sub": "f3a2…",
    "email": "alice@example.com",
    "name": "Alice Wang",
    "preferred_username": "alice",
    "roles": ["user", "operator"]
  },
  "to": "/devices/42"
}
```

Errors use the standard envelope `{"error":{"code","message"}}`:

| HTTP | code | Meaning |
|---|---|---|
| 401 | `UNAUTHORIZED` | Bad/missing product credentials |
| 400 | `BAD_REQUEST` | Missing ticket |
| 400 | `TICKET_INVALID` | Unknown or already consumed ticket |
| 400 | `TICKET_EXPIRED` | Past the 30-second lifetime |
| 400 | `TICKET_AUDIENCE` | Ticket minted for another product |

### 4.3 Ticket properties (non-negotiable)

1. **Single-use.** A successful or failed exchange burns the ticket; replays
   return `TICKET_INVALID`.
2. **Short-lived:** 30 seconds from issue.
3. **Audience-bound:** only the product id named at issue may consume it.
4. **Carries exactly one identity snapshot** (the claims above) and the `to`
   deep link; it never carries IdP tokens, refresh tokens or secrets.
5. **Unforgeable:** high-entropy random identifier (256-bit) or an
   authenticated sealed token (NS HMAC/AEAD). For NS multi-replica
   deployments tickets MUST validate on any replica: either seal the ticket
   statelessly with the NS session key (plus a short-lived replay cache) or
   use a shared store; an in-memory-only store is limited to documented
   single-replica deployments.
6. Transport between product backend and NS is HTTPS (cluster-internal or
   ingress), never through the browser.

### 4.4 Product-side requirements

1. Configuration block:

   ```yaml
   sso:
     mode: ns                 # ns | oidc | local
     ns:
       base_url: https://nereidsphere.example.org
       product_id: nereidlink
       client_secret: <32-byte random, from Secret>
       callback_path: /auth/ns-callback
   ```

2. One **public** callback route at `callback_path`; every other protected
   route requires the product session. Unauthenticated browser requests are
   redirected to `{base_url}/auth/enter/{product_id}?to=<current relative
   path>` (API/XHR requests return 401 instead of redirecting).
3. The callback extracts `ticket`/`to`, calls verify server to server, and
   only then establishes the session. The browser-supplied ticket is the
   only input; the product MUST NOT trust any `X-User-*` header or identity
   claim arriving directly from a browser.
4. Validate `to` as a same-origin relative path before redirecting (open
   redirect protection); default to the product home on any failure.
5. JIT-provision the local user keyed by `identity.sub` with
   `identity.email`/`preferred_username`/`name`; map suite roles
   (`user`/`operator`/`admin`) onto product roles per §5; update on every
   login. Disable/delete follows a subsequent login without the role.
6. After the session is minted, all existing product mechanisms (local
   session/JWT/cookie, WebSocket auth, CSRF, audit log) work unchanged; SSO
   users appear in the same audit trail and permission system as local users.
7. Product logout clears the local session and redirects the browser to the
   browser-followable (GET) NS logout URL, which clears the NS session and
   performs NI end-session. NS publishes this URL for products (default
   `/auth/logout`; the existing POST `/api/v1/auth/logout` stays for the
   portal's fetch-based logout).
8. The shared secret lives in the product's Secret store and in NS product
   configuration only; it is masked in APIs, never logged, and rotated by
   updating both sides.
9. Tickets failing with `TICKET_*` redirect the browser back to the NS entry
   URL to obtain a fresh ticket; they never render a stack trace.

## 5. Identity Claims, Roles and JIT

- Stable identity: `sub`. Display fields: `preferred_username`, `name`,
  `email`. Roles: coarse suite vocabulary `user`, `operator`, `admin`.
- Tokens also carry a standard `groups` claim (full paths, leading `/`) in
  the access token, ID token and userinfo. NS stores per-user, per-product
  tenant/role assignments as realm groups shaped
  `/nereid{product}/{tenant}/{role}` (e.g.
  `/nereidlink/<tenant-uuid>/admins`); products filter by their `/nereid*`
  prefix. The default `/user` group may also appear.
- In mode 1 the identity JSON above is authoritative. In mode 2 roles come
  from the NI token (`realm_access.roles` with Keycloak; a mapper emits the
  same vocabulary when the user is brokered from an external IdP).
- Each product maps the three suite roles onto its own fine-grained
  permissions; products do not invent suite role names. Unknown roles fall
  back to the configured default role or reject, per product setting.
- Every product login resolves to the same realm identity. NI bootstraps one
  shared human administrator (username `admin`, realm role `admin`) so the
  same account works across all products; its generated password lives in the
  identity-plane Secret and is never pushed to products.
- JIT links the local user to `sub`; mode-2 products additionally key by
  issuer. Tenant/org assignment at JIT time is product-local configuration
  (the identity plane invents no tenant semantics).

## 6. Mode 2 — Direct OIDC RP Requirements

A mode-2 product is a standard confidential OIDC relying party against **NI**:

1. OIDC Discovery for all endpoints; JWKS verification of the ID token
   (iss/aud/nonce/exp); authorization-code + PKCE (S256); `state` cookie;
   refresh tokens; RP-initiated logout. Use a maintained library — no
   hand-rolled JWT validation. No ROPC.
2. Configuration block: `enabled/issuer/client_id/client_secret/
   redirect_url/frontend_base_url/scopes/roles_claim/role_map/jit
   defaults/state_ttl`. `issuer` is the NI realm URL, e.g.
   `https://sso.example.org/auth/realms/nereidai`; `roles_claim` defaults to
   `realm_access.roles`.
3. Exact redirect URIs registered in NI (no wildcards in production);
   post-login deep links validated against a same-origin allowlist.
4. Startup MUST succeed with SSO unconfigured or NI unreachable; SSO status
   (configured/enabled/last error) is exposed to the login UI. Local
   break-glass administrator always works.
5. Client secret encrypted/masked, never embedded in images/charts/git.
6. NereidLink already conforms (ADR-0021); other products implement the same
   shape when deployed in mode 2.

## 7. Clients and Redirects (NI realm)

Declared in `../realm/nereidai-realm.json` (dev) and the Helm values
(production). The product clients exist for mode 2 (and mixed deployments);
mode 1 does not use them.

| client_id | Type | Used by |
|---|---|---|
| `nereidsphere` | confidential, auth-code+PKCE | NS login (always) |
| `nereidlink` | confidential, auth-code+PKCE | NereidLink mode 2 |
| `nereidhorizon` | confidential, auth-code+PKCE | NereidHorizon mode 2 |
| `nereidforge` | confidential, auth-code+PKCE | NereidForge mode 2 |
| `nereidsphere-admin` | service account, client-credentials | NS admin console ↔ NI Admin API |

Fixed callback paths: NS `/auth/callback`; Link `/v1/auth/oidc/callback`;
Horizon `/auth/callback`; Forge `/auth/callback`. Mode-1 product callbacks
(`sso.callback_path`, default `/auth/ns-callback`) are product routes, not NI
clients, and need no NI registration.

## 8. Transport and Trust

- All browser and service traffic is HTTPS behind the suite ingress; NI
  honors `X-Forwarded-*` so issuer URLs are https.
- Internal clusters use the private `internal-ca`; services trust it via the
  platform CA injection mechanism (e.g. `SSL_CERT_FILE`), never image
  rebuilds.
- Mode-1 product↔NS verify calls use server-side HTTPS only; the product
  validates the NS CA and presents no browser-reachable identity channel.
- Fully air-gapped operation is mandatory for built-in/brokered
  deployments: no call-home, no external runtime dependency.

## 9. What Version 2 Replaces

- The version-1 requirement that every product be a direct OIDC RP: still
  supported per product (mode 2), no longer the default.
- Any design where NS points directly at a customer IdP: forbidden — customer
  federation is owned by NI brokering, which keeps NS configuration and all
  products stable.
- NS ROPC login: replaced by authorization-code + PKCE against NI.
- The NS ticket mechanism is **retained and promoted** to the default
  product integration; it is made multi-replica-safe (stateless sealed
  tickets).
