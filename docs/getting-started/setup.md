# Setup

The project is intended to be developed from inside the devcontainer.

## Devcontainer Setup

Open the repository in VS Code and choose **Reopen in Container**. The devcontainer uses Python 3.11, installs dependencies from `requirements.txt`, and enables Docker access for Compose-based integration tests.

After the container starts, verify the toolchain:

```bash
make lint
make typecheck
make test.unit
```

Install pre-commit hooks:

```bash
make pre-commit.install
```

The hooks fail on lint, formatting, or type-checking issues. They do not auto-fix changes during commit.

## Environment Files

Configuration is environment-variable driven.

- `config/env/*.env` contains safe service-specific local development defaults and is committed.
- `config/env/*.env.example` documents the same keys for new environments.
- `.env.example` documents optional root-level Compose interpolation values.

Do not put personal secrets in committed env defaults. Override values in your shell, Compose environment, ignored `.env.local`, or deployment-specific env files.

## Documentation Setup

Serve the documentation locally:

```bash
make docs.serve.local
```

## Runtime Deployment Prerequisites (Kubernetes-first)

- Kubernetes cluster with Helm (primary runtime target).
- Access to the private Tailscale/LAN network.
- PostgreSQL reachable from the cluster (often external to the chart).
- Qdrant deployed by the chart with durable storage, or an equivalent managed deployment.
- Ollama on the model host.
- Configured watch roots containing supported documents.
