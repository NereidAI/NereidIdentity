<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# Agent Prompt Template — Product SSO Integration (NS ticket default, direct OIDC optional)

Use one copy per product (NereidLink, NereidHorizon, NereidForge). Replace
the `{{PLACEHOLDERS}}`. Implement BOTH modes; the suite default is `ns`.
Read `NereidIdentity/docs/sso-integration-standard.md` (v2) and
`NereidIdentity/docs/external-idp-guide.md` first — the wire contract in
standard §4 is normative; do not invent deviations.

```text
Task: Add suite SSO to {{PRODUCT}} with two selectable modes:
- sso.mode=ns   (DEFAULT, standard §4): no OIDC config in the product;
  unauthenticated browser entry redirects to NereidSphere, which mints a
  30-second single-use, audience-bound ticket; the product exchanges it
  server-to-server and mints its EXISTING local session.
- sso.mode=oidc (OPTIONAL, standard §6): the product is a confidential OIDC
  RP against NereidIdentity, authorization-code + PKCE.
- sso.mode=local or disabled: today's local/break-glass auth, unchanged.

Product parameters:
- Product id / X-NS-Client-Id: {{PRODUCT_ID}}            (e.g. nereidlink)
- Ticket callback route (public): {{NS_CALLBACK_PATH}}   (default /auth/ns-callback)
- Post-login SPA route/deep link: {{FRONTEND_ROUTE}}
- OIDC client_id: {{CLIENT_ID}}
- OIDC callback path: {{OIDC_CALLBACK_PATH}}             (e.g. /v1/auth/oidc/callback)
- Stack anchors / existing auth seams: {{STACK_ANCHORS}}
- Dev NS base URL: {{DEV_NS_URL}}   Dev NI issuer: http://localhost:8090/realms/nereidai

Mode ns — exact behavior (standard §4):
1. Config block: sso.mode; sso.ns.base_url, product_id, client_secret (Secret
   only, masked in API, never logged), callback_path. Startup MUST succeed
   unconfigured/with NS down; expose SSO status to the login UI.
2. Unauthenticated BROWSER request to a protected route → 302 to
   {base_url}/auth/enter/{product_id}?to=<current relative path>. API/XHR
   requests get 401 (no redirect). `to` is rebuilt from the request; do not
   trust a client-provided absolute URL.
3. Public GET {{NS_CALLBACK_PATH}}?ticket=…&to=… :
   - POST {base_url}/api/v1/auth/ticket/verify, HTTPS server-to-server,
     headers X-NS-Client-Id: {product_id}, X-NS-Client-Secret: {secret},
     body {"ticket": "..."}. Validate the NS server certificate (private
     internal-ca via the platform CA injection, not image rebuild).
   - 200 → identity{ sub, email, name, preferred_username, roles[] }, to.
   - 400 TICKET_INVALID/TICKET_EXPIRED/TICKET_AUDIENCE → redirect back to the
     NS enter URL (fresh ticket); 401 UNAUTHORIZED is a deployment error:
     log (no secrets) and show a configuration error page, do not loop.
4. On success JIT-provision/update the local user keyed by sub, map suite
   roles user/operator/admin to {{PRODUCT}} built-in roles via a configurable
   role_map with default-role/reject policy, attach the configured
   tenant/org, and mint the product's NORMAL session (so REST auth, refresh,
   WebSocket and audit all keep working unchanged). Validate `to` as a
   same-origin relative path before the final 302.
5. Logout: clear local session, then redirect to NS logout
   ({base_url}/api/v1/auth/logout) so NI end-session runs.
6. NEVER trust X-User-* headers or identity claims from browsers; identity
   only enters via the server-side ticket exchange. No IdP tokens are ever
   handled in this mode. Rotating the shared secret requires no code.

Mode oidc — only when deployed direct-to-NI (standard §6):
7. Authorization-code + PKCE (S256), discovery, JWKS verification
   (iss/aud/nonce/exp), state cookie, refresh, RP-initiated logout;
   maintained OIDC library, no ROPC, no hand-rolled JWT validation.
8. Config: enabled, issuer (NI realm URL), client_id, client_secret,
   redirect_url, frontend_base_url, scopes (openid profile email roles),
   roles_claim (default realm_access.roles), role_map, jit tenant/default
   role, state_ttl. Exact redirect URI; same-origin deep-link allowlist.
9. First-login JIT reuses the SAME local provisioning/role-mapping/session
   code as mode ns — one identity-onboarding path, two front doors.

Product-specific anchors to reuse (do not rebuild what exists):
- NereidLink: callback is a sibling of internal/oidc Complete — exchange the
  ticket instead of code/JWKS, then call identity.UpsertExternalUser +
  rbac.EnsureMembership + IssuePairForUser; deliver via the existing
  /auth/callback#session= SPA path; WS ?access_token and local HS256
  pipeline unchanged; OIDC mode = existing ADR-0021 path, just align config
  shape; wire into gatewayapi authorize seam and isExemptPath.
- NereidHorizon: callback (Express route in PUBLIC_PATHS, bypass requireCsrf
  for this GET) verifies the ticket, synthesizes the SAME session record as
  /api/login (including Exchange baseURL/auth/orgId from exchangeConfig for
  the mapped role), sets nereid_sid + nereid_csrf cookies, then 302; map
  suite roles to platform vs partner and decide partner org binding.
- NereidForge: callback verifies ticket then issues the normal pair via
  LocalSigner.sign; frontend authStore and ?token= WS unchanged. In mode ns
  (and oidc) the auth.enabled=false dev bypass MUST be force-disabled and
  X-Tenant-Id accepted only from provisioned identity, never raw headers.

Surfaces:
- Backend: mode/status endpoint consumed by the login page (hide SSO entry
  unless enabled; distinct error for NS-unreachable vs rejected ticket),
  admin config surface following the product's standard settings pattern
  (platform-admin only; secret "leave blank to keep" masking).
- Frontend: login page SSO entry, callback handling route, settings section
  (mode select, NS base url/product id/secret in mode ns; issuer/client/
  scopes/roles_claim/role_map/JIT in mode oidc; Test connection).
- i18n/help: ALL user-facing strings through t(...), add BOTH locales and
  run the repo i18n checker; bilingual help docs with help ids registered
  and the help checker run.
- Contracts/docs: update OpenAPI/protocol docs in the same change (must
  parse), add/update an ADR for the dual-mode decision, update FEATURES and
  the pitfalls/lessons doc per repo rules.

Do NOT: call NI/Keycloak admin APIs; register clients yourself (NI owns
that); embed secrets in images/charts/git; trust browser-supplied identity
headers; weaken or remove local auth and local administrator recovery;
implement direct customer-IdP federation in a suite install (standalone
mode-3 delivery only, documented in external-idp-guide.md §5).

Verification (use the product repo's documented commands; do not invent
tooling):
- format/lint/vet/typecheck/unit tests for: enter redirect, verify success +
  every TICKET_* code, bad secret 401, audience rejection, to-allowlist,
  replay rejected, JIT/role map, session mint, logout redirect; oidc mode
  PKCE/callback/JWKS failure cases. Then full build.
- frontend tsc --noEmit, lint, build, i18n/help checks where present.
- Smoke mode ns against a running NS (dev) + NI compose: protect a page,
  follow the redirect chain through NI login (admin/admin), land authed in
  the product; open a second product with one login; replay the callback URL
  → rejected and recoverable; wrong secret → config error, no loop; stop NS
  → startup fine and status shows error; break-glass local admin still logs
  in. Keep test processes singleton and clean up.

Report: design summary (one shared onboarding path), files changed, new
endpoints, config/Secret/values impact, mode matrix with verification
output, deviations from the standard with reasons.
```
