---
name: Feature request
about: Propose an improvement to the identity plane, realm declaration or SSO contract
title: "feat: "
labels: enhancement
---

<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

## Problem statement

The use case or limitation motivating the request. Identity-plane scope only:
product business logic belongs in the relevant product repository.

## Proposed change

Describe the desired behavior and, where relevant, the affected surface
(Helm values, realm JSON, bootstrap reconciliation, documentation).

## Alternatives considered

Other approaches already evaluated, if any.

## Compatibility

- [ ] The change keeps the OIDC contract in `docs/sso-integration-standard.md`
      intact, or the required contract change is described
- [ ] Existing realms are reconciled idempotently (realm import never
      re-imports an existing realm)
