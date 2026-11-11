<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# Agent Prompt — NereidSphere Portal, OIDC RP + Ticket Hub + Admin Console

Copy the block below to the NereidSphere agent. The current working tree is a
large uncommitted rewrite whose ticket/gateway/session machinery is being
**promoted** to the suite-default SSO path; ROPC must be replaced, not added to.

```text
Task: Evolve NereidSphere into the suite SSO hub defined by
NereidIdentity/docs/sso-integration-standard.md (read it first, v2) and
NereidIdentity/docs/external-idp-guide.md. NS is (1) the ONLY suite component
that speaks OIDC to NereidIdentity (NI/Keycloak), (2) the ticket issuer for
mode-1 products and (3) the built-in-account administration console.

Architecture rules (non-negotiable):
1. NS only ever points at NI: auth.mode=local|oidc; oidc block contains
   issuer/client_id/client_secret of the NI realm (no customer-IdP fields).
   Customer IdPs are brokered behind NI; NS stays unchanged when one is added.
 2. ROPC (password grant) and the self-owned credential login exchange are
    REMOVED for oidc mode: authorization-code + PKCE (S256) with discovery and
    JWKS (coreos/go-oidc/v3 + golang.org/x/oauth2 already in go.mod). The
    browser is redirected to NI's branded login; NS does not render an OIDC
    username/password form.
 3. Admin console: built-in account CRUD goes through NI Admin REST using the
    nereidsphere-admin service-account client (client_credentials; config
    issuer/client_id/admin_client_id/admin_client_secret) scoped to oidc
    built-in mode; it never contains the Keycloak master password. Brokered
    users are shown read-only (no reset/disable actions rendered for
    federated accounts).
 4. The ticket hub REMAINS and is the default mode-1 product integration (the
    contract is fixed — do not change endpoint paths, headers, envelope or
    identity JSON): GET /auth/enter/{product}?to=, 302 to product
    sso_callback_path with ticket/to, POST /api/v1/auth/ticket/verify with
    X-NS-Client-Id / X-NS-Client-Secret -> {identity,to}. Keep 30s single-use
    audience-bound; make tickets multi-replica-safe: seal the full ticket
    (aud/to/identity/exp/jti) statelessly with the existing AES-GCM session
    key seam, plus a bounded jti replay cache (or documented single-replica
    fallback). Inbound X-User-* headers continue to be stripped on gateway
    routes. The forward-auth endpoint /api/v1/auth/verify stays.
 5. Products are selected per-product mode: registry entry carries
    mode=ns|oidc (mode 1/2). Mode-1 entries require sso_secret;
    mode-2 entries carry declarative oidc metadata (client_id,
    oidc_redirect_paths). Direct-to-customer-IdP (mode 3) is standalone
    delivery only and MUST NOT appear in suite installs. Registry stays
    declarative values (v1, no database); the portal launch URL is always
    /auth/enter/{id} in mode 1.
 6. local break-glass: auth.mode=local is supported, accounts from
    deployment Secret/values, emergency-only, clearly labeled in UI/docs;
    oidc mode with NI down shows a clear login-unavailable page; startup never
    hard-fails when NI is unreachable (readyz reflects issuer status).
 7. CSRF: all state-changing browser endpoints under oidc/local get a
    double-submit cookie + X-Csrf-Token or equivalent; OPTIONS bypass only for
    CORS preflight.

Backend tasks:
A. Add GET /auth/login → start auth-code+PKCE (state+nonce+returnTo cookies
   short TTL, S256), GET /auth/callback → exchange, JWKS verify
   (iss/aud/nonce/exp), build sealed ns_session (reuse Codec/Resolver/claims
   parsing incl. realm_access.roles; scopes openid profile email roles),
   transparent refresh and RP-initiated logout against end_session_endpoint.
   Delete POST /api/v1/auth/login ROPC path in oidc mode (local mode keeps a
   dedicated login endpoint gated by config, not the same exchange). Add a
   browser-followable GET /auth/logout (clear session, RP-initiated NI
   end-session redirect) used by mode-1 product logout chains; keep POST
   /api/v1/auth/logout for portal fetch logout.
B. Stateless sealed tickets per rule 4, replacing the in-memory TicketStore;
   verify contract compatibility (same errors: UNAUTHORIZED/BAD_REQUEST/
   TICKET_INVALID/TICKET_AUDIENCE/TICKET_EXPIRED). Add unit tests covering
   issue/consume/replay/audience/expiry across two independently constructed
   verifiers simulating replicas.
B2. Verify WebSocket passthrough through /p/{id}/ proxy — either confirm with
   an automated/upstream-doc-supported test or document v1 limit; tickets
   already cover Link WS via the local pair the product mints after verify.
B3. Remove dead config (e.g. oidc.redirect_path placeholder for ROPC) and
   the stale dist/keycloak-7.0.1.tgz; align internal/auth file/package docs.
C. Admin API (suite admin role only, standard error envelope, config-secret
   handling): users list/get/create/update/enable-disable/reset password/
   assign suite roles; brokered/federated users read-only with
   federation>identity-provider shown; connection/read-only status (auth.mode,
   issuer reachable via readyz, per-product mode/status). Never use master
   admin; never log client secrets; masking in any response.
C2. Remove the old keycloak.* bootstrap section; identity admin uses the
   nereidsphere-admin client_credentials grant. Chart: render the admin
   client secret from values into the config Secret; operators supply it
   (matches NI chart adminClient.secret).
D. Redirect allowlist unchanged: relative paths or exact configured product
   origins; to relative only; constant-time secret compare (exists).

Frontend (web/, React 18 + antd 5 + react-router 6):
E. /login renders a single "Sign in with SSO" entry → GET /auth/login, plus
   break-glass local form only when auth.mode=local (or explicit
   breakGlass.enabled); remove the username/password form for oidc mode.
F. Add Identity/SSO admin area: user management (built-in users CRUDS+roles;
   federated users shown as managed externally), and a connection status page
   (mode, issuer, products mode/status, brokered IdP alias if available).
G. i18n: t(...) everywhere; add keys to locales/en.ts and zh.ts in the same
   change; run the repo i18n/help-doc checkers; bilingual help for the new
   pages with help ids registered.

Docs/inventory:
H. Rewrite docs/sso-flow.md for auth-code+PKCE + stateless ticket flow;
   update docs/gateway.md (keep /p/ and forward-auth); update
   docs/oidc-integration.md (NS↔NI only, broker transparent, admin SA);
   README quickstart (dev NI compose issuer
   http://localhost:8090/realms/nereidai — note dev Keycloak serves no
   /auth relative path; chart/prod issuer includes /auth); AGENTS.md scope
   sections (NS = suite RP + ticket hub + built-in account console; no IdP
   admin/master-password; customer IdP only via NI broker).
I. Record delivered behavior in the repo feature inventory and a pitfall
   entry "ROPC disabled realm breaks password-grant NS; auth-code required"
   plus "fullScopeAllowed/roles scope required for client-credentials admin
   token" per root treaty §9 pitfalls rule.

Verification (repo AGENTS.md is authoritative):
- gofmt, go vet ./..., go test ./... (PKCE flow, claims, stateless ticket
  cross-verifier/replay, redirect allowlist, admin authorization, topology
  gating); make build.
- web/: npx tsc --noEmit, lint, build, i18n/help checks.
- Smoke against NI dev compose: run the bootstrap profile
  (docker compose --profile bootstrap run --rm bootstrap) to grant the SA
  role; auth-code login as admin/admin & user/user; portal enter → ticket →
  a local stub product verifies and establishes its own session; admin
  console CRUD works; broker IdP added in NI appears as read-only federation;
  NI down → startup OK, login page states unavailable, break-glass local
  works; rotate sso_secret in config → old secret 401; ticket replay 400.
  Clean up test processes per repo rules.

Report: files changed/deleted, stateless ticket design, CSRF design,
break-glass configuration, deviations from the standard with reasons, full
verification output, and the exact operator values for auth.mode=oidc against
NI (dev & k3s) plus for auth.mode=local.
```
