# Copyright (C) 2026 YIQISOFT
# SPDX-License-Identifier: Apache-2.0

# Standard entry point for NereidIdentity (treaty section 15.8, §19).
#
# The identity plane itself runs upstream Keycloak and CloudNativePG images at
# their true public coordinates; the only suite-owned image is
# nereididentity-bootstrap, which packages the stdlib-only realm bootstrap
# hook. This Makefile builds/packages locally only and never pushes; GHCR
# publication belongs to the workflows (§19.2): the tag-triggered release
# plus the rolling 0.0.0-dev dev-channel publish, both using the three-tag
# scheme with no latest tag. Local hub copies are the operator's own manual
# tag/push decision or go through NereidOverview harbor-sync.sh.

# Optional local build acceleration (treaty §19.3): copy local.mk.example to
# local.mk (git-ignored). A missing file means a pristine upstream build.
-include local.mk

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

DOCKER ?= docker

REGISTRY   ?= ghcr.io/nereidai
# No VERSION file: the git tag is the single version source (treaty §19). On
# an exact v* tag checkout use its bare SemVer (v0.0.1 -> 0.0.1); any other
# checkout builds the rolling dev channel 0.0.0-dev. CI may inject VERSION.
VERSION    ?= $(shell ref=$$(git describe --tags --exact-match 2>/dev/null) && echo "$${ref#v}" || echo 0.0.0-dev)
TAG        ?= $(VERSION)
# Traceability tags (treaty §19.2): UTC timestamp and short git revision.
GIT_SHA    ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_TS   := $(shell date -u +%Y%m%d-%H%M)
# RFC 3339 UTC for the OCI image.created label; distinct from the compact
# BUILD_TS used in traceability image tags.
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
# Local make builds stay native/single-arch (treaty §19.2.1): the amd64+arm64
# multi-arch index is a publication-time property produced by the tag-triggered
# release workflow, not by this Makefile.
NATIVE_ARCH := $(shell uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')
PLATFORMS  ?= linux/$(NATIVE_ARCH)
IMAGE_NAME ?= nereididentity-bootstrap
IMAGE      ?= $(REGISTRY)/$(IMAGE_NAME):$(TAG)
DOCKERFILE ?= deploy/images/$(IMAGE_NAME)/Dockerfile
RELEASE    ?= nereididentity
NAMESPACE  ?= nereididentity
CHART_DIR  ?= deploy/helm/nereididentity
COMPOSE_DIR ?= deploy/compose
DEPLOYMENT_ROOT ?= $(abspath $(CURDIR)/../.deployment)
ENV_FILE ?= $(DEPLOYMENT_ROOT)/deploy-values/nereididentity/compose.env
COMPOSE_ENV = $(if $(wildcard $(ENV_FILE)),--env-file "$(ENV_FILE)")
# Operator-supplied site values; never committed. Required by install.
VALUES     ?=

# The committed example values are placeholder-only and are the default
# render input for the non-cluster verification gate.
TEMPLATE_VALUES ?= $(CHART_DIR)/values-k3s-example.yaml

.DEFAULT_GOAL := help
.PHONY: help

help: ## List available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: lint
lint: ## Validate the realm JSON declaration
	python3 -m json.tool realm/nereidai-realm.json >/dev/null

.PHONY: helm-dep
helm-dep: ## Update chart dependencies from the upstream chart repositories
	helm dependency update $(CHART_DIR)

.PHONY: helm-lint
helm-lint: ## Lint the chart with defaults and the committed example values
	helm lint $(CHART_DIR)
	helm lint $(CHART_DIR) -f $(CHART_DIR)/values-k3s-example.yaml

.PHONY: helm-template
helm-template: ## Render the chart (example values by default; VALUES= for site values)
	helm template $(RELEASE) $(CHART_DIR) \
	  -f $(if $(VALUES),$(VALUES),$(TEMPLATE_VALUES)) >/dev/null
	@echo "rendered $(RELEASE) from $(if $(VALUES),$(VALUES),$(TEMPLATE_VALUES))"

.PHONY: helm-package
helm-package: helm-version-check ## Package the chart into dist/charts/ (offline redistribution only)
	mkdir -p dist/charts
	helm package $(CHART_DIR) -d dist/charts

.PHONY: image
image: ## Build the bootstrap hook image for the local Docker daemon (three tags, no push)
	$(DOCKER) buildx build --load --platform $(PLATFORMS) \
		--build-arg VERSION=$(VERSION) \
		--build-arg GIT_SHA=$(GIT_SHA) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		-f $(DOCKERFILE) \
		-t $(REGISTRY)/$(IMAGE_NAME):$(TAG) \
		-t $(REGISTRY)/$(IMAGE_NAME):$(TAG)-$(BUILD_TS) \
		-t $(REGISTRY)/$(IMAGE_NAME):$(TAG)-$(GIT_SHA) .

.PHONY: helm-version-check
helm-version-check: ## On an exact-tag checkout, fail when chart version/appVersion or the bootstrap image tag drift from the tag-derived VERSION
	@if ! git describe --tags --exact-match >/dev/null 2>&1; then \
	  echo "skipping chart version sync: not an exact-tag checkout (dev channel $(VERSION))"; \
	  exit 0; \
	fi; \
	chart_ver=$$(sed -n 's/^version: //p' $(CHART_DIR)/Chart.yaml); \
	test -n "$$chart_ver" || { echo "no chart version found in $(CHART_DIR)/Chart.yaml"; exit 1; }; \
	test "$$chart_ver" = "$(VERSION)" || \
	  { echo "Chart.yaml version '$$chart_ver' != tag-derived VERSION '$(VERSION)'"; exit 1; }; \
	app_ver=$$(sed -n 's/^appVersion: //p' $(CHART_DIR)/Chart.yaml | tr -d '"'); \
	test "$$app_ver" = "$(VERSION)" || \
	  { echo "Chart.yaml appVersion '$$app_ver' != tag-derived VERSION '$(VERSION)'"; exit 1; }; \
	image_tag=$$(python3 -c 'import yaml; print(yaml.safe_load(open("$(CHART_DIR)/values.yaml"))["bootstrap"]["image"]["tag"])'); \
	test "$$image_tag" = "$(VERSION)" || \
	  { echo "bootstrap image tag '$$image_tag' != VERSION '$(VERSION)'"; exit 1; }; \
	echo "chart version $$chart_ver, appVersion $$app_ver and bootstrap image tag $$image_tag match tag-derived VERSION"

.PHONY: verify
verify: lint helm-version-check helm-lint helm-template ## Pre-commit gate: declarations, version sync, chart lint and render

.PHONY: install
install: ## Helm install/upgrade; requires explicit VALUES=<site-values.yaml>
	@test -n "$(VALUES)" || { echo "VALUES=<site-values.yaml> is required"; exit 1; }
	helm upgrade --install $(RELEASE) $(CHART_DIR) \
	  --namespace $(NAMESPACE) --create-namespace --skip-crds -f $(VALUES)

.PHONY: uninstall
uninstall: ## Helm uninstall the release from NAMESPACE
	helm uninstall $(RELEASE) --namespace $(NAMESPACE)

.PHONY: dev-up
dev-up: ## Start the local Keycloak + PostgreSQL compose stack
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) up -d

.PHONY: dev-bootstrap
dev-bootstrap: ## Run the idempotent realm bootstrap once (SA role grant, suite admin, self-check)
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) \
		--profile bootstrap run --rm bootstrap

.PHONY: dev-down
dev-down: ## Stop the local compose stack
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) down

.PHONY: dev-logs
dev-logs: ## Follow logs of the local compose stack
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) logs -f

.PHONY: dev-rebuild
dev-rebuild: ## Recreate the compose stack, pulling current upstream images
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) pull
	$(DOCKER) compose -f $(COMPOSE_DIR)/docker-compose.yml $(COMPOSE_ENV) up -d --force-recreate

.PHONY: clean
clean: ## Remove local packaging output (never touches images or clusters)
	rm -rf dist
