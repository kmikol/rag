# Documentation Rules

Documentation is part of the implementation.

Update docs when behavior changes:

- Module behavior changes require the module `README.md` to be updated.
- Public functions/classes should have current Google-style docstrings.
- Service API changes require module README and schema docs updates.
- New docs pages require `docs/mkdocs.yml` navigation updates.
- Run `mkdocs build -f docs/mkdocs.yml --strict` after documentation changes.

## ADR Policy

Accepted ADRs are historical records and must not be edited to fit new implementation work.

If implementation conflicts with an accepted ADR:

1. Stop and identify the conflict.
2. Consult the owner/user before changing direction.
3. Draft a new ADR that supersedes the old one.
4. Link the superseding ADR from indexes and relevant docs.
5. Proceed only after the owner accepts the new decision.

Small typo fixes in ADRs are acceptable. Decision, rationale, consequence, and implication changes require a superseding ADR.
