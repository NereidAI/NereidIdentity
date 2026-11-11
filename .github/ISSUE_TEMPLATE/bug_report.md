---
name: Bug report
about: Report a defect in the identity plane, chart, realm import or bootstrap hook
title: "bug: "
labels: bug
---

<!-- Copyright (C) 2026 YIQISOFT; SPDX-License-Identifier: Apache-2.0 -->

## Summary

A clear, short description of the defect.

## Reproduction

1. Steps or the exact `helm` / `docker compose` commands used
2. Values or configuration involved (redact every secret and real hostname)
3. What happened, including the relevant logs

## Expected behavior

What should have happened instead.

## Environment

- NereidIdentity release/tag or commit:
- Deployment: k3s/Helm (release revision) or docker compose
- Keycloak engine version:
- Node architecture(s): amd64 / arm64
- Registry path: public registries / node mirror

## Checklist

- [ ] No credentials, tokens or private hostnames are included
- [ ] `make verify` passes on the reported commit
