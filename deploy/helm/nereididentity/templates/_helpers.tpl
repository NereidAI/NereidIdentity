{{/*
Copyright (C) 2026 YIQISOFT
SPDX-License-Identifier: Apache-2.0

Common labels/name for the identity-plane resources rendered by this umbrella
chart (realm import Secret, admin bootstrap Secret). The subchart resources
keep their own naming; the literal names nereididentity-realm and
nereididentity-admin are referenced from values.yaml, so the release MUST be
installed as "nereididentity".
*/}}
{{- define "nereididentity.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nereididentity.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "nereididentity.labels" -}}
app.kubernetes.io/name: {{ include "nereididentity.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
