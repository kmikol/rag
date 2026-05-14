{{- define "rag.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "rag.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "rag.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "rag.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "rag.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "rag.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "rag.sharedStorageClaimName" -}}
{{- if .Values.sharedStorage.existingClaim -}}
{{- .Values.sharedStorage.existingClaim -}}
{{- else if .Values.sharedStorage.name -}}
{{- .Values.sharedStorage.name -}}
{{- else -}}
{{- printf "%s-shared-storage" (include "rag.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "rag.validate" -}}
{{- if and .Values.sharedStorage.enabled (not .Values.sharedStorage.create) (not .Values.sharedStorage.existingClaim) -}}
{{- fail "If sharedStorage.enabled is true, either sharedStorage.create must be true or sharedStorage.existingClaim must be provided." -}}
{{- end -}}
{{- end -}}
