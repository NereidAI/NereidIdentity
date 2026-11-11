<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# NereidIdentity

Suite-wide identity plane for NereidAI — the shared, replaceable OIDC/OAuth2
provider behind single sign-on for NereidSphere, NereidLink, NereidHorizon
and NereidForge.

The current engine is **Keycloak 26** with a dedicated PostgreSQL. Keycloak is
an implementation detail, not an architecture dependency: another OIDC engine
can replace it and NereidSphere (the only mandatory OIDC relying party) only
changes its connection settings (`issuer`, `client_id`, `client_secret`,
`redirect`, `scopes`). In the default suite integration, products do not
speak OIDC at all — they trust NS through one-time ticket handoff. Products
deployed standalone-from-NS may still register direct OIDC clients here.
Realms, clients and the admin service-account grant are provisioned
declaratively in this repo; products never call the admin API.

See [`docs/sso-integration-standard.md`](docs/sso-integration-standard.md)
for the suite SSO contract (NS ticket default, direct-OIDC option, brokered
customer IdPs), [`docs/oidc-contract.md`](docs/oidc-contract.md) for the
engine contract, and [`docs/pitfalls.md`](docs/pitfalls.md) for Keycloak
operational gotchas.

## Layout

```text
realm/nereidai-realm.json       Canonical development realm (NS + 3 product OIDC clients, admin SA; dev secrets)
deploy/compose/                 Developer Keycloak + PostgreSQL stack (+ bootstrap profile)
deploy/helm/nereididentity/     Umbrella Helm chart and NereidAI bilingual login theme
docs/                           SSO standard, engine contract, external-IdP guide, agent prompts
```

## Development

Prerequisites: Docker with pull access to the public registries
(`quay.io`, Docker Hub and GHCR). Air-gapped hosts use node-level registry
mirroring; see the NereidOverview mirror guide for the containerd
configuration.

```bash
make dev-up
# grant the admin service-account role the realm import cannot bind
# (idempotent; rerun whenever realm clients change):
make dev-bootstrap
```

Stop the stack with `make dev-down`; `make dev-logs` follows its logs and
`make dev-rebuild` pulls fresh images and recreates it. See `make help` for
all targets.

The Keycloak and PostgreSQL images come directly from public registries. The
one-shot bootstrap step runs the suite-owned
`ghcr.io/nereidai/nereididentity-bootstrap:0.0.0-dev` image, which has three
local sourcing options:

- once the GHCR package is public, Compose pulls it automatically;
- on a restricted network, or while the package is still private, build it
  locally first: on a non-tag checkout `make image` loads exactly the
  `0.0.0-dev` tag (plus the two traceability tags) into the Docker daemon,
  and Compose uses that local copy without pulling;
- or set `BOOTSTRAP_IMAGE` in your `compose.env` to a registry mirror you can
  reach (all override variables are documented in
  `deploy/compose/.env.example`). The bind mount in the compose file layers
  the working copy of `realm-bootstrap.py` over the image, so script edits
  need no rebuild.

- Admin console: <http://localhost:8090> (`admin/admin`, dev only)
- Issuer: `http://localhost:8090/realms/nereidai` (dev Keycloak serves no
  `/auth` relative path; the central deployment uses `/auth`)
- Seed users: `admin/admin` (realm admin), `user/user`
- Client secrets are the well-known `changeme*` development values
- The NereidAI login page defaults to English and offers English/简体中文
  switching from its language menu; the same theme source is used by Helm

Point NS/product development configs at `http://localhost:8090/realms/nereidai`.
Keep overrides (ports, images, credentials) outside Git in
`../.deployment/deploy-values/nereididentity/compose.env`; `make dev-*` uses
that file when present. Start from `deploy/compose/.env.example`, keep the
directory at mode `0700` and the environment file at mode `0600`. Direct Compose
commands can pass the same file with `--env-file`.

## Central deployment (k3s)

```bash
# Operator-supplied site values (never committed); copy the example into the
# workspace deployment directory and fill every required secret:
install -d -m 700 ../.deployment/deploy-values/nereididentity
cp -n deploy/helm/nereididentity/values-k3s-example.yaml \
  ../.deployment/deploy-values/nereididentity/values.yaml
chmod 600 ../.deployment/deploy-values/nereididentity/values.yaml
make helm-dep
make install VALUES=../.deployment/deploy-values/nereididentity/values.yaml
```

`make install` runs `helm upgrade --install` as release
`nereididentity` in the `nereididentity` namespace with `--skip-crds`
(the CloudNativePG CRDs are a cluster-wide prerequisite this chart never
owns). The release name is fixed: the chart mounts fixed-name Secrets.

`helm dependency update` fetches the pristine upstream `keycloakx` and
`cloudnative-pg` charts from their public repositories; the product
repository is the single source of truth and no suite chart bundle or chart
museum is required. Prerequisites on the cluster: cert-manager with the
`internal-ca` ClusterIssuer and the `nfs-csi` StorageClass. Nodes pull
images directly from public registries; an authenticated mirror is a
node-level containerd setting and, if it needs credentials, pull Secrets are
supplied through `keycloak.imagePullSecrets` and
`bootstrap.imagePullSecrets`.

Every suite product runs in its **own namespace**, named after the product
itself (`nereididentity`, `nereidsphere`, `nereidlink`, …); this convention
also applies to lab/POC installs. See the NereidOverview deployment guide for
the deployment topology.

Issuer: `https://sso.example.org/auth/realms/nereidai`. Realm clients:
`nereidsphere` (NS login, mandatory), `nereidlink`, `nereidhorizon`,
`nereidforge` (used only when a product runs direct-to-NI OIDC), all
authorization-code + PKCE, ROPC disabled. The `nereidsphere-admin`
service-account client backs the NS admin console (Keycloak Admin API); a
post-install/upgrade Helm hook idempotently binds its realm-admin role and
self-validates the grant. Customer identity systems connect via Keycloak
identity brokering, never directly to NS or products.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, the DCO
sign-off requirement and the pre-commit gate. Vulnerabilities are reported
privately per [SECURITY.md](SECURITY.md); community interaction follows the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE). The
required notices are in [NOTICE](NOTICE), and the third-party components this
project deploys (Keycloak, CloudNativePG/PostgreSQL, CPython, busybox and the
upstream Helm charts) are listed with their licenses in
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
