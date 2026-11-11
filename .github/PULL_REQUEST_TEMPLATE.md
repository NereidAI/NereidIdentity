<!--
Copyright (C) 2026 YIQISOFT
SPDX-License-Identifier: Apache-2.0

Thank you for contributing to NereidIdentity.
Please keep every section; delete the checklist items that do not apply.
-->

## What this change does

## Why

Link the related issue (e.g. `Closes #123`).

## Verification

- [ ] `make helm-dep` and `make verify` pass locally
- [ ] Rendered manifests reviewed for any Helm template change
- [ ] Realm/bootstrap changes checked against an existing realm (idempotent
      reconciliation; realm import never re-imports)
- [ ] Documentation updated under `docs/` or the chart `README.md`

## Conformance

- [ ] All commits are DCO-signed (`git commit -s`)
- [ ] English-only content; no credentials, real private hostnames or site
      values are committed
- [ ] No `latest` image tags and no push steps added to the Makefile
- [ ] Upstream charts remain pristine dependencies (no forks, no vendoring)
