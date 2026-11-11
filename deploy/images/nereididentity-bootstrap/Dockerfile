# Copyright (C) 2026 YIQISOFT
# SPDX-License-Identifier: Apache-2.0

# Self-contained image for the post-install/upgrade realm bootstrap hook.
# realm-bootstrap.py is Python-stdlib-only and makes outbound HTTPS calls, so
# the official slim Python image is the only base and no package is installed.
# The build context is the repository root (see the Makefile image target).
FROM docker.io/library/python:3.14-alpine

# Default is the rolling dev channel; the release workflow injects bare
# SemVer (0.0.1) derived from the v-prefixed git tag. GIT_SHA/BUILD_DATE are
# supplied by the caller (Makefile or workflow prep job); no value is
# hardcoded, keeping the tag-sourced version model (treaty section 19.5).
ARG VERSION=0.0.0-dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=""

# One LABEL instruction carrying both the suite's custom labels and the full
# OCI 1.0 annotation set; version/revision/created come only from the ARGs.
LABEL license='SPDX-License-Identifier: Apache-2.0' \
      copyright='Copyright (c) 2026: YIQISOFT' \
      org.opencontainers.image.title='nereididentity-bootstrap' \
      org.opencontainers.image.description='Suite authentication and identity center — Keycloak realm bootstrap hook: SSO, OIDC/LDAP/SAML federation, RBAC and tenant-aware access governance' \
      org.opencontainers.image.vendor='YIQISOFT' \
      org.opencontainers.image.licenses='Apache-2.0' \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source='https://github.com/NereidAI/NereidIdentity' \
      org.opencontainers.image.url='https://github.com/NereidAI/NereidIdentity' \
      org.opencontainers.image.documentation='https://github.com/NereidAI/NereidIdentity#readme' \
      org.opencontainers.image.authors='NereidAI (https://github.com/NereidAI)'

# Run as an unprivileged user: the hook writes nothing to the filesystem.
RUN addgroup -S nereidai && adduser -S -G nereidai nereidai
WORKDIR /scripts
COPY --chown=nereidai:nereidai \
     deploy/helm/nereididentity/files/realm-bootstrap.py \
     /scripts/realm-bootstrap.py
# Scanner-conventional location (Syft/Trivy auto-detect /licenses); the files
# have no extension and .dockerignore does not exclude them.
COPY LICENSE NOTICE /licenses/
USER nereidai

ENTRYPOINT ["python3", "/scripts/realm-bootstrap.py"]
