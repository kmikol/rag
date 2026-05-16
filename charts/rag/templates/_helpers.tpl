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

{{- define "rag.databaseHost" -}}
{{- if .Values.postgresql.enabled -}}
{{- printf "%s-postgresql" (include "rag.fullname" .) -}}
{{- else -}}
{{- required "database.host is required when postgresql.enabled is false" .Values.database.host -}}
{{- end -}}
{{- end -}}

{{- define "rag.databaseSecretName" -}}
{{- required "database.existingSecret is required" .Values.database.existingSecret -}}
{{- end -}}

{{- define "rag.embeddingSettingsEnv" -}}
- name: EMBEDDING_BACKEND
  value: {{ .Values.embedding.backend | quote }}
- name: EMBEDDING_MODEL_NAME
  value: {{ .Values.embedding.modelName | quote }}
- name: EMBEDDING_DIMENSION
  value: {{ .Values.embedding.dimension | quote }}
- name: EMBEDDING_ENDPOINT_URL
  value: {{ .Values.embedding.endpointUrl | quote }}
- name: EMBEDDING_TIMEOUT_SECONDS
  value: {{ .Values.embedding.timeoutSeconds | quote }}
- name: EMBEDDING_KEEP_ALIVE
  value: {{ .Values.embedding.keepAlive | quote }}
{{- end -}}

{{- define "rag.embeddingSecretEnv" -}}
{{- with .Values.embedding.apiKey.existingSecret }}
- name: EMBEDDING_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ . }}
      key: {{ $.Values.embedding.apiKey.secretKey }}
{{- end }}
{{- end -}}

{{- define "rag.llmEnv" -}}
- name: LLM_PROVIDER
  value: {{ .Values.llm.provider | quote }}
- name: LLM_CHAT_COMPLETIONS_URL
  value: {{ .Values.llm.chatCompletionsUrl | quote }}
- name: LLM_ENDPOINT_URL
  value: {{ .Values.llm.endpointUrl | quote }}
- name: LLM_MODEL
  value: {{ .Values.llm.model | quote }}
- name: LLM_TIMEOUT_SECONDS
  value: {{ .Values.llm.timeoutSeconds | quote }}
{{- with .Values.llm.temperature }}
- name: LLM_TEMPERATURE
  value: {{ . | quote }}
{{- end }}
{{- with .Values.llm.maxTokens }}
- name: LLM_MAX_TOKENS
  value: {{ . | quote }}
{{- end }}
{{- with .Values.llm.apiKey.existingSecret }}
- name: LLM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ . }}
      key: {{ $.Values.llm.apiKey.secretKey }}
{{- end }}
{{- end -}}

{{- define "rag.validate" -}}
{{- if and .Values.sharedStorage.enabled (not .Values.sharedStorage.create) (not .Values.sharedStorage.existingClaim) -}}
{{- fail "If sharedStorage.enabled is true, either sharedStorage.create must be true or sharedStorage.existingClaim must be provided." -}}
{{- end -}}
{{- end -}}
