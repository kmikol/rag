# Tailscale + PostgreSQL on Synology NAS (Docker)

A hardened, production-ready setup that exposes a persistent PostgreSQL database exclusively over your Tailscale tailnet — no open ports, no public internet exposure.

---

## Architecture

```
[Your devices on tailnet]
        │
        ▼  WireGuard (encrypted)
  ┌─────────────┐
  │  tailscale  │  ← sidecar container, owns the network stack
  └──────┬──────┘
         │  network_mode: service:tailscale
  ┌──────▼──────┐
  │  postgres   │  ← no host ports, invisible to internet
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │  ./pg-data/ │  ← owned exclusively by postgres uid
  └─────────────┘
```

The postgres container shares the Tailscale container's network namespace. It has no ports bound on the host and is completely invisible to the public internet.

---

## Prerequisites

- Synology NAS running DSM 7.2+
- **Container Manager** installed from the Package Center
- SSH access enabled (Control Panel → Terminal & SNMP → Enable SSH)
- A Tailscale account

---

## Part 1 — Tailscale Admin Console Setup

### 1.1 Define the `tag:db` Tag in ACL Policy

Go to [tailscale.com/admin/acls](https://login.tailscale.com/admin/acls) and set your policy to:

```json
{
  "tagOwners": {
    "tag:db": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src":    ["autogroup:member"],
      "dst":    ["tag:db:5432"]
    }
  ]
}
```

This does two things:
- Declares `tag:db` as a valid tag owned by admins
- Restricts what the tagged node can receive — only port 5432, only from your tailnet members. The node cannot initiate connections to anything else.

Click **Save**.

### 1.2 Generate an Auth Key

Go to [tailscale.com/admin/settings/keys](https://login.tailscale.com/admin/settings/keys) → **Generate auth key**:

| Setting | Value |
|---|---|
| Description | `nas-postgres` |
| Reusable | No |
| Expiration | 90 days |
| Pre-authorized | ✅ Yes |
| Tags | `tag:db` |

Copy the key (`tskey-auth-...`). You cannot view it again after closing the dialog.

---

## Part 2 — Synology Firewall

Docker containers run on a bridge subnet (`172.16.0.0/12`). The default Synology firewall deny-all rule blocks their outbound traffic, which prevents Tailscale from reaching its control plane.

Go to **Control Panel → Security → Firewall → Edit Rules** and add a new rule **above** the deny-all row:

| Field | Value |
|---|---|
| Ports | All |
| Protocol | All |
| Source IP | `172.16.0.0 / 255.240.0.0` |
| Action | Allow |

Drag it above the bottom deny-all rule. Click **Save**.

---

## Part 3 — Directory Setup

SSH into your NAS and run these commands once:

```bash
# Create the project directory
mkdir -p /volume1/docker/ts-postgres

cd /volume1/docker/ts-postgres

# Tailscale state — will be owned by root (tailscale runs as root)
mkdir -p tailscale-state
sudo chown root:root tailscale-state
sudo chmod 700 tailscale-state

# Postgres data — owned by root initially so the entrypoint can create pgdata/ inside it.
# The entrypoint runs as root, creates pgdata/, chowns it to uid 999, then drops privileges.
# Do NOT pre-create pgdata/ yourself — the entrypoint must create it.
mkdir -p pg-data
sudo chown root:root pg-data
sudo chmod 755 pg-data
```

> **Important:** After postgres has started successfully for the first time (you see "ready to accept connections" in the logs), lock the directory down to uid 999 so nothing else on the host can read it:
>
> ```bash
> sudo chown 999:999 /volume1/docker/ts-postgres/pg-data
> sudo chmod 700 /volume1/docker/ts-postgres/pg-data
> ```
>
> At this point `pgdata/` inside is already owned by `999:999` — postgres set that up itself during init. The parent is now locked down to uid 999 only.

## Part 4 — Configuration Files

### 4.1 `.env`

```bash
nano /volume1/docker/ts-postgres/.env
```

```env
TS_AUTHKEY=tskey-auth-XXXXXXXXXXXXXXXXXXXX

POSTGRES_USER=appuser
POSTGRES_PASSWORD=a-very-long-random-password-here
POSTGRES_DB=appdb
```

Lock down permissions immediately:

```bash
chmod 600 /volume1/docker/ts-postgres/.env
```

### 4.2 `resolv.conf`

Docker's internal DNS resolver (`127.0.0.11`) can fail in userspace networking mode on Synology. Mount a static resolver file to guarantee DNS works:

```bash
echo "nameserver 1.1.1.1
nameserver 8.8.8.8" | sudo tee /volume1/docker/ts-postgres/resolv.conf
```

### 4.3 `docker-compose.yml`

```yaml
services:

  tailscale:
    image: tailscale/tailscale:latest
    hostname: nas-postgres          # This is the name that appears in your tailnet
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
      - TS_EXTRA_ARGS=--advertise-tags=tag:db --netfilter-mode=off
      - TS_STATE_DIR=/var/lib/tailscale
      - TS_USERSPACE=true           # No kernel TUN needed — drops all cap requirements
      - TS_SOCKET=/tmp/tailscaled.sock
    volumes:
      - ./tailscale-state:/var/lib/tailscale
      - ./resolv.conf:/etc/resolv.conf:ro   # Bypass Docker's broken DNS on Synology
    tmpfs:
      - /.cache:mode=0700           # Tailscale needs a writable cache dir
    security_opt:
      - no-new-privileges:true
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "tailscale --socket=/tmp/tailscaled.sock status || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 15s

  postgres:
    image: postgres:16-alpine
    depends_on:
      tailscale:
        condition: service_healthy  # Waits for Tailscale to be fully connected
    network_mode: service:tailscale # Shares Tailscale's network stack — no host ports
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - ./pg-data:/var/lib/postgresql/data  # Only mounts its own data dir
    cap_drop:
      - ALL
    cap_add:
      - CHOWN        # Needed by the entrypoint script on first init
      - FOWNER
      - SETUID
      - SETGID
      - DAC_OVERRIDE # Needed by gosu to drop from root to uid 999
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
```

---

## Part 5 — Deploy

```bash
cd /volume1/docker/ts-postgres
sudo docker compose up -d
```

Watch the logs until Tailscale connects:

```bash
sudo docker compose logs -f tailscale
```

Look for this sequence — it means success:

```
Switching ipn state NeedsLogin -> Running
```

Then check both containers are healthy:

```bash
sudo docker compose ps
```

Both should show `healthy`. The node `nas-postgres` should also appear in [tailscale.com/admin/machines](https://login.tailscale.com/admin/machines).

---

## Part 6 — Connecting to PostgreSQL

From any device on your tailnet:

```bash
psql -h nas-postgres -p 5432 -U appuser -d appdb
```

Or with a connection string:

```
postgresql://appuser:password@nas-postgres:5432/appdb
```

No jump hosts, no SSH tunnels, no VPN config beyond Tailscale — WireGuard handles encryption in transit end-to-end.

---

## Part 7 — Auth Key Rotation

Auth keys expire (default 90 days). When they expire the **running container is unaffected** — Tailscale only needs the key on first registration. The state is persisted in `./tailscale-state/`. However if you ever recreate the container from scratch you will need a valid key.

### Option A — OAuth Client (Recommended, no expiry)

Instead of a regular auth key, use an OAuth client secret. These never expire and Tailscale handles token refresh internally.

1. Go to [tailscale.com/admin/settings/oauth](https://login.tailscale.com/admin/settings/oauth)
2. Create a client with scope **Devices: Write** and tag `tag:db`
3. Copy the client secret (`tskey-client-...`)
4. Use it as `TS_AUTHKEY` in your `.env` — it works as a drop-in replacement

### Option B — Cron Rotation Script

If using a regular auth key, create `/volume1/docker/ts-postgres/refresh-tskey.sh`:

```bash
#!/bin/bash
set -euo pipefail

TAILSCALE_API_KEY="tskey-api-XXXXXXXX"   # API key from tailscale.com/admin/settings/keys
TAILNET="your-tailnet-name.ts.net"        # Found in tailscale.com/admin/dns
ENV_FILE="/volume1/docker/ts-postgres/.env"
COMPOSE_DIR="/volume1/docker/ts-postgres"

NEW_KEY=$(curl -sf -X POST \
  -H "Authorization: Bearer ${TAILSCALE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "devices": {
        "create": {
          "reusable": false,
          "ephemeral": false,
          "preauthorized": true,
          "tags": ["tag:db"]
        }
      }
    },
    "expirySeconds": 7776000
  }' \
  "https://api.tailscale.com/api/v2/tailnet/${TAILNET}/keys" \
  | grep -o '"key":"[^"]*"' | cut -d'"' -f4)

if [ -z "$NEW_KEY" ]; then
  echo "$(date): ERROR — failed to generate new Tailscale key" >&2
  exit 1
fi

sed -i "s|^TS_AUTHKEY=.*|TS_AUTHKEY=${NEW_KEY}|" "$ENV_FILE"
cd "$COMPOSE_DIR"
docker compose restart tailscale

echo "$(date): Tailscale auth key rotated successfully"
```

```bash
chmod 700 /volume1/docker/ts-postgres/refresh-tskey.sh
```

Schedule it in DSM → Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script, run as `root`, every **80 days** (before the 90-day expiry).

---

## Troubleshooting Reference

| Symptom | Cause | Fix |
|---|---|---|
| `not a directory` on state file | Docker created state path as a file | `rm -rf tailscale-state && mkdir tailscale-state` |
| `permission denied` on state file | Wrong ownership | `chown root:root tailscale-state && chmod 700 tailscale-state` |
| `mkdir /.cache: permission denied` | No writable cache | Add `tmpfs: - /.cache:mode=0700` |
| `no DNS fallback candidates remain` | Docker DNS failing | Mount `resolv.conf` as volume |
| `connection attempts aborted` on register | Firewall blocking Docker subnet | Add `172.16.0.0/255.240.0.0` allow rule in DSM firewall |
| `requested tags [tag:db] are invalid` | Tag not defined in ACL policy | Add `tagOwners` block to ACL, generate new key |
| `OCI runtime: namespace path: lstat /proc/.../ns/net` | Tailscale crashed before postgres could attach | Add `healthcheck` + `condition: service_healthy` |
| `mkdir: can't create directory 'pgdata': File exists` | `pgdata/` was pre-created manually | `rm -rf pg-data/pgdata` — let the entrypoint create it |
| `Permission denied` creating `pgdata/` | `pg-data/` owned by uid 999, blocks root entrypoint | `chown root:root pg-data && chmod 755 pg-data`, then lock down to `999:999` after first init |

---

## Potential Improvements

### Security

**1. Run Tailscale as a non-root user**
Currently the tailscale container runs as root. You can run it as uid 1000 by adding `user: "1000:1000"` and adjusting ownership of `tailscale-state` — but you lose the `/var/run` socket path (mitigated by `TS_SOCKET=/tmp/tailscaled.sock`) and the `/.cache` tmpfs must include `uid=1000`. Works fine in practice but adds friction on every rebuild.

**2. Enable `userns-remap` on the Docker daemon**
Add to `/etc/docker/daemon.json`:
```json
{ "userns-remap": "default" }
```
This maps container root (uid 0) to an unprivileged host uid (165536), so a container escape yields nothing on the host. Note that all volume `chown` values must be shifted accordingly: postgres uid 999 becomes host uid 166535, root becomes 165536. Restart Container Manager after changing this.

**3. Drop postgres init-time capabilities after first run**
The `CHOWN`, `FOWNER`, `SETUID`, `SETGID`, `DAC_OVERRIDE` caps are only needed during the very first `initdb`. Once your `pg-data/pgdata/` is populated, remove them from the compose file and redeploy — postgres itself doesn't need them at runtime.

**4. Use Docker secrets instead of `.env`**
Docker Swarm secrets or external secret managers (e.g. Vault) prevent credentials from appearing in `docker inspect` output. For a single-node NAS setup the `.env` with `chmod 600` is a reasonable pragmatic trade-off, but worth knowing the limitation.

**5. Restrict Tailscale ACL further**
Scope the ACL source to specific devices rather than all members:
```json
{
  "action": "accept",
  "src":    ["your-laptop-hostname", "your-workstation-hostname"],
  "dst":    ["tag:db:5432"]
}
```

### Reliability

**6. Postgres connection pooling**
Add a [PgBouncer](https://www.pgbouncer.org/) container between your apps and postgres (also with `network_mode: service:tailscale`) to pool connections and reduce postgres load. Especially useful if multiple clients connect.

**7. Automated backups**
Add a `pg_dump` cron task or a backup sidecar (e.g. `prodrigestivill/postgres-backup-local`) that writes to a separate volume, ideally on a different physical location via Synology's HyperBackup.

**8. Pin image versions**
Replace `tailscale/tailscale:latest` and `postgres:16-alpine` with exact digest-pinned versions (e.g. `postgres:16.3-alpine3.19`) to prevent unexpected breakage on container recreation.

**9. Resource limits**
Add memory and CPU limits to prevent a runaway postgres query from impacting the rest of your NAS:
```yaml
  postgres:
    deploy:
      resources:
        limits:
          memory: 512m
          cpus: "1.0"
```
