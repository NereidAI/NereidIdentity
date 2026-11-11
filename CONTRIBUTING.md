<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

# Contributing to NereidIdentity

Thanks for taking the time to contribute. NereidIdentity is the suite-wide
identity plane for NereidAI: it owns the OIDC/OAuth2 provider deployment, the
canonical realm declaration and the written SSO contract. It deliberately
contains no product business logic — changes that belong in a consumer
product will be redirected to that repository.

## Ground rules

- All repository content (code, comments, commits, documentation) is written
  in English.
- Every commit must carry a Developer Certificate of Origin sign-off:

  ```bash
  git commit -s
  ```

  This adds the `Signed-off-by` trailer; by adding it you certify the DCO at
  <https://developercertificate.org/>.
- Never commit credentials, real hostnames of private infrastructure, or site
  values. Tracked configuration carries placeholders only; site-specific
  values live outside the repository (see `values-k3s-example.yaml`).
- Every hand-written file carries an SPDX header
  (`SPDX-License-Identifier: Apache-2.0`) in the language's comment form:
  hash comments for YAML/Makefile/Dockerfiles, HTML comments for Markdown,
  placed after any YAML frontmatter. Exceptions by convention: the legal texts
  `LICENSE`, `NOTICE` and `THIRD_PARTY_NOTICES`; JSON files and the generated
  Helm `Chart.lock`, which do not allow comments; and `AGENTS.md`, whose
  presence in the public tree is a maintainer decision.

## Workflow

1. Open an issue first for anything beyond a small fix, so the design can be
   discussed before code is written.
2. Branch from `main` and open a pull request targeting `main`.
3. Keep commits focused, with a conventional prefix
   (`feat:`, `fix:`, `docs:`, `build:`, `ci:`, `refactor:`).
4. Update the affected documentation under `docs/` or the chart `README.md`
   when behavior or configuration changes.

## Local verification

The root `Makefile` is the single entry point. Before marking a pull request
ready, run the same gate CI runs:

```bash
make helm-dep   # fetch pristine upstream chart dependencies
make verify     # realm JSON validity, version drift guard, helm lint + render
```

For the developer Keycloak/PostgreSQL stack use `make dev-up` /
`make dev-down`; see the README for the bootstrap profile.

## Image and chart constraints

- The Makefile builds images locally only; it never pushes. Publication is
  owned exclusively by the tag-triggered GitHub Actions workflows.
- Deployment manifests reference the bare version tag only — never `latest`.
- Upstream Helm charts are used as pristine dependencies; do not fork or
  vendor them into this repository.
- `VERSION`-derived versions and release tags are changed only through the
  documented release flow, not ad hoc in pull requests.
- The bootstrap Dockerfile must keep the full OCI annotation set plus the
  custom `license`/`copyright` labels in a single `LABEL` instruction, with
  `version`/`revision`/`created` sourced only from build arguments, and must
  copy `LICENSE` and `NOTICE` into `/licenses/`. Verify changes with
  `make image` followed by `docker inspect` on the resulting image.

## Security

Do not open public issues for vulnerabilities. Follow the private reporting
process in [SECURITY.md](SECURITY.md).
