# Internet Exposure Hardening

This guide describes what is required before exposing the RAG API to the public
internet and gives two concrete deployment patterns.

The current application is designed for a private, single-user network. It has a
static bearer token for protected API endpoints, but it does not include a full
internet edge: no browser login flow, no MFA, no built-in rate limiting, no WAF,
no abuse detection, and no public TLS termination. Treat direct publication of
`api-service:8000` as unsafe.

## Required Security Boundary

An internet-facing deployment needs these layers:

1. A public edge that terminates HTTPS.
2. A second authentication layer before traffic reaches `api-service`.
3. The existing `RAG_API_KEY` bearer token for the RAG API itself.
4. Firewall rules so only the edge can reach the application.
5. No public PostgreSQL, Qdrant, Ollama, embedding-service, or ingestion-worker
   ports.
6. Request limits and abuse controls for expensive endpoints.
7. Secret rotation, backups, logging, patching, and recovery procedures.

This is defense in depth. If the edge identity layer is misconfigured, the RAG
bearer token still protects API actions. If the RAG bearer leaks, the identity
layer still prevents anonymous internet traffic from reaching the app.

## Current Gaps to Fix or Compensate For

Before public exposure, account for these current limitations:

- `api-service` uses one shared static bearer token, not per-device or per-user
  sessions.
- There is no built-in login page, MFA, OAuth/OIDC, or token revocation endpoint.
- There is no built-in rate limiting or request body size limit.
- The Dockerfiles currently run as the image default user and are not hardened
  with non-root execution, read-only root filesystems, or dropped capabilities.
- Application secrets are read from environment variables. Docker secrets can be
  used by images that support `_FILE` variables, such as PostgreSQL, but the RAG
  services do not yet read their own secrets from files.
- Migrations are run from the repository checkout, not from the runtime images.

Compensate at the edge first, then harden the images and app configuration as a
follow-up implementation task.

## Do Not Use Basic Auth in Front of This API

HTTP Basic Auth uses the `Authorization` header. The RAG API also expects:

```text
Authorization: Bearer <RAG_API_KEY>
```

One request cannot reliably use both Basic Auth and the RAG bearer token in the
same header. Use an identity layer that authenticates with cookies, mTLS, access
headers, or a forward-auth side channel, leaving the `Authorization` header
available for `RAG_API_KEY`.

## Recommended Path: Cloudflare Tunnel + Access

This is the simplest internet-facing pattern for a homelab or NAS deployment:

- `api-service` has no published host port.
- `cloudflared` creates outbound-only tunnel connections to Cloudflare.
- Cloudflare Access enforces user login, email allowlist, and MFA at the edge.
- API clients still send `Authorization: Bearer <RAG_API_KEY>`.
- Automated clients also send Cloudflare Access service-token headers.

Tradeoff: traffic passes through Cloudflare. That may be unacceptable if the
deployment must remain strictly self-hosted end to end.

### Cloudflare Setup

1. Move the domain or subdomain to Cloudflare DNS.
2. Create a Cloudflare Tunnel.
3. Create a public hostname, for example `rag.example.com`.
4. Route that hostname to `http://api-service:8000`.
5. Create a Cloudflare Access application for `rag.example.com`.
6. Add an Access policy that allows only your account or email address.
7. Require MFA through the configured identity provider.
8. For scripts or mobile clients, create an Access service token and add it to
   the Access policy.

Cloudflare Tunnel does not require inbound ports on the NAS/server. Keep the
host firewall closed except for SSH or other administration paths you actually
need.

### Compose Changes

Remove the public `api-service` port mapping:

```yaml
api-service:
  build:
    context: .
    dockerfile: api_service/Dockerfile
  env_file:
    - ./deploy/env/api-service.env
  expose:
    - "8000"
  volumes:
    - /volume1/rag/watch/papers:/watch/papers
    - /volume1/rag/watch/notes:/watch/notes
    - /volume1/rag/documents:/documents
```

Add `cloudflared` to the same Compose project:

```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  restart: unless-stopped
  command: tunnel --no-autoupdate run --token ${CLOUDFLARED_TUNNEL_TOKEN}
  depends_on:
    api-service:
      condition: service_started
```

Keep `CLOUDFLARED_TUNNEL_TOKEN` outside version control. In a production Compose
deployment, inject it through the NAS/container manager or an ignored root env
file with strict filesystem permissions.

### Calling the API

Interactive browser access first passes through Cloudflare Access. API clients
need both Cloudflare Access credentials and the RAG bearer token:

```bash
curl -fsS -X POST \
  -H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the indexed material say about backups?", "limit":5}' \
  https://rag.example.com/chat
```

Rotate Cloudflare service tokens and `RAG_API_KEY` independently.

## Self-Hosted Path: Caddy + Forward Auth Gateway

Use this path when you do not want Cloudflare in the request path. It requires
more operational work because you must run and maintain your own public edge and
identity gateway.

Recommended shape:

- Public DNS points `rag.example.com` at the server.
- Host firewall opens only TCP `80` and `443` to Caddy.
- Caddy terminates HTTPS and proxies to `api-service`.
- An auth gateway such as Authelia, Authentik, or oauth2-proxy handles login and
  MFA.
- Caddy uses `forward_auth` before `reverse_proxy`.
- `api-service` still requires `Authorization: Bearer <RAG_API_KEY>`.

### Caddy Compose Example

Expose only Caddy:

```yaml
caddy:
  image: caddy:2
  restart: unless-stopped
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
    - /volume1/rag/caddy/data:/data
    - /volume1/rag/caddy/config:/config
  depends_on:
    api-service:
      condition: service_started

api-service:
  build:
    context: .
    dockerfile: api_service/Dockerfile
  env_file:
    - ./deploy/env/api-service.env
  expose:
    - "8000"
```

Caddy stores certificates and account keys in `/data`, so that directory must be
persistent and backed up.

### Caddyfile Skeleton

Replace the `forward_auth` upstream and URI with the exact endpoint documented
by your auth gateway:

```caddyfile
rag.example.com {
  request_body {
    max_size 1MB
  }

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "no-referrer"
    Content-Security-Policy "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    -Server
  }

  forward_auth auth-gateway:9091 {
    uri /api/authz/forward-auth
    copy_headers Remote-User Remote-Email Remote-Groups
  }

  reverse_proxy api-service:8000 {
    health_uri /health
    health_interval 30s
    health_timeout 5s
  }
}
```

Caddy automatically provisions and renews certificates for qualifying public
hostnames. Make sure DNS points to the server before starting it.

Do not add `preload` to the HSTS header until every subdomain under the domain
is permanently HTTPS-only and you understand the recovery implications.

## Firewall Rules

For the Cloudflare Tunnel path:

- Do not publish `api-service` to the host.
- Do not open inbound `80` or `443` unless another service needs them.
- Allow outbound HTTPS from `cloudflared`.
- Restrict SSH or NAS administration to trusted IPs or a private VPN.

For the self-hosted Caddy path:

- Allow inbound TCP `80` and `443` only.
- Do not expose `8000`, `8001`, `8002`, `5432`, `6333`, or `11434`.
- Bind administrative ports to localhost or a private interface.
- Keep PostgreSQL and Qdrant on Docker-internal networks or private LAN
  addresses only.

## Rate Limits and Abuse Controls

Chat, search, and ingestion can consume CPU, memory, disk, model-provider quota,
and model-host time. Add limits at the edge:

- Maximum request body size.
- Per-IP or per-identity request rate limits.
- Low limits for `/chat`, `/search`, and `/ingest`.
- Higher or disabled limits only for trusted private administration paths.
- Alerts for repeated `401`, `403`, `429`, and `5xx` responses.

Cloudflare Access/WAF can provide these controls in the Cloudflare path. For the
self-hosted path, use the auth gateway, firewall tooling, reverse-proxy modules,
or a host IDS such as CrowdSec or fail2ban.

## Secrets and Rotation

Generate long random secrets:

```bash
openssl rand -base64 48
```

Rotate:

- `RAG_API_KEY`
- PostgreSQL password
- Cloudflare tunnel token or Caddy auth-gateway secrets
- Cloudflare Access service tokens, if used
- External model-provider API keys, if used

Keep deployment env files out of Git and restrict permissions:

```bash
chmod 600 deploy/env/*.env
```

For PostgreSQL, prefer the image-supported `POSTGRES_PASSWORD_FILE` convention
with Docker secrets or your NAS secret manager. For RAG service secrets, use the
deployment platform's secret injection until the app supports `*_FILE` settings.

## Container Hardening

Before treating the stack as internet-facing production, harden the runtime
images and Compose service definitions:

- Run application containers as a non-root user.
- Drop Linux capabilities with `cap_drop: ["ALL"]`.
- Add `security_opt: ["no-new-privileges:true"]`.
- Use `read_only: true` where possible.
- Add `tmpfs: ["/tmp"]` when read-only roots need temporary files.
- Mount watch roots read-write only where deletion through the API is required.
- Mount managed document storage only into services that need it.
- Pin image versions and update them on a schedule.

Do this as code changes and test the ingestion/delete flows afterward. The
worker writes managed copies and may delete source files during reconciliation,
so read-only mounts must be applied carefully.

## Logging and Monitoring

At minimum, collect:

- Reverse-proxy access logs.
- Edge-auth allow/deny logs.
- `api-service`, `embedding-service`, and `ingestion-worker` logs.
- PostgreSQL and Qdrant container health.
- Disk usage for PostgreSQL, Qdrant, watch roots, and managed documents.
- Backup success/failure.

Alert on:

- Repeated authentication failures.
- Sudden spikes on `/chat`, `/search`, or `/ingest`.
- Provider quota errors or unexpected external-provider traffic.
- PostgreSQL, Qdrant, or model-host unavailability.
- Disk nearing capacity.

## Backup and Recovery

Before exposing the system, prove restore works:

1. Restore PostgreSQL into a clean database.
2. Restore Qdrant storage or recreate the collection and reingest.
3. Restore managed documents.
4. Start services against the restored state.
5. Run `/documents`, `/search`, and a known `/chat` query.

Backups are part of security. A compromised or buggy internet-facing deployment
can delete source files through the intended API if the attacker obtains both
edge access and `RAG_API_KEY`.

## Internet-Readiness Checklist

Do not expose the deployment until all items are true:

- `api-service` is not directly published to the internet.
- HTTPS is enforced at the edge.
- A second auth layer with MFA protects every path.
- `RAG_API_KEY` is long, random, and not reused elsewhere.
- PostgreSQL, Qdrant, Ollama, embedding-service, and ingestion-worker are not
  public.
- Request body and rate limits exist for expensive endpoints.
- Logs are collected and reviewed.
- Backups are automated and restore-tested.
- Secrets are stored outside Git and have a rotation procedure.
- Images and host packages have an update procedure.
- You have tested access from a clean external network, not just from inside the
  LAN.

## References

- [OWASP API Security Top 10 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)
- [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Caddy `forward_auth`](https://caddyserver.com/docs/caddyfile/directives/forward_auth)
- [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)
- [MDN `X-Content-Type-Options`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options)
