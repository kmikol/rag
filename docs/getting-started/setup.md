# Setup

Implementation has not started yet. The setup path will be filled in as services are added.

## Documentation Setup

Install the documentation dependencies:

```bash
python -m pip install -r docs/docs-requirements.txt
```

Serve the documentation locally:

```bash
make docs.serve.local
```

## Planned Runtime Prerequisites

- Docker or Docker-compatible runtime.
- Access to the private Tailscale/LAN network.
- NAS-hosted PostgreSQL.
- Qdrant Docker service, defaulting to NAS placement.
- Ollama on the model host.
- Configured watch roots containing supported documents.
