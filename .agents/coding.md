# Coding Rules

Behavioral rules in `behavior.md` are mandatory. They override convenience when there is tension between speed and correctness.

- Use Python 3.11.
- Use FastAPI and Pydantic v2 for service APIs and schemas.
- Use Google-style docstrings for public functions, classes, and non-obvious internal helpers.
- Docstrings must explain what the function/class does and why it exists when the intent is not obvious.
- Keep docstrings and module READMEs up to date when behavior changes.
- Keep route handlers thin once logic grows; move business logic into module-level services/helpers.
- Prefer simple, explicit code over speculative abstractions.
- Do not add configurability that is not required by the task.
- Use `shared.schemas` for common response/error contracts.
- Use Alembic for database schema changes.
- Do not modify generated `site/` output.

## Module Documentation

Every implementation module must have a `README.md` describing:

- Purpose.
- Responsibilities.
- API or callable contract.
- Configuration.
- Related ADRs.
- Testing helpers exposed for other modules.

Docs pages under `docs/modules/` should include module READMEs with MkDocs snippets.
