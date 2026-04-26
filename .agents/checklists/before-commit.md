# Checklist: Before Commit

- Module README updated if behavior changed.
- Google-style docstrings updated for changed public functions/classes.
- Tests updated in the owning module.
- Every changed line traces to the user's request.
- No unrelated refactors, formatting churn, or adjacent cleanups included.
- `make lint` passes.
- `make typecheck` passes.
- Relevant tests pass.
- `make test.smoke` passes for docs/config/build changes.
- No generated `site/`, caches, local env files, or secrets are staged.
- `git status --short --branch` reviewed.
