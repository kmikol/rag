# Database Migrations

Alembic migrations live in `migrations/versions`.

The migration environment reads `POSTGRES_URL` from the environment. If it is not set, it falls back to the development URL in `alembic.ini`.

Useful commands:

```bash
alembic revision -m "describe change"
alembic upgrade head
alembic downgrade -1
```
