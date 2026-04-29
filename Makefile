.DEFAULT_GOAL := help
SHELL := /bin/bash

CYAN   := \033[36m
GREEN  := \033[32m
RESET  := \033[0m

TEST_COMPOSE := docker compose -f docker-compose.test.yml
E2E_COMPOSE := docker compose -f docker-compose.e2e.yml

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "$(CYAN)Personal RAG System$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  $(GREEN)%-22s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ═══════════════════════════════════════════════════════════════
# DOCS
# ═══════════════════════════════════════════════════════════════

.PHONY: docs.serve.local docs.serve.online docs.build

docs.serve.local: ## Serve docs locally with live reload (http://localhost:8001)
	mkdocs serve -f docs/mkdocs.yml --dev-addr 127.0.0.1:8001

docs.build: ## Build docs into ./site
	mkdocs build -f docs/mkdocs.yml

docs.serve.online: ## Build and deploy docs to GitHub Pages (gh-pages branch)
	mkdocs gh-deploy -f docs/mkdocs.yml --force

# ═══════════════════════════════════════════════════════════════
# DEVELOPMENT
# ═══════════════════════════════════════════════════════════════

.PHONY: build up down lint lint.fix format typecheck pre-commit.install pre-commit.run db.upgrade db.downgrade db.revision test test.unit test.integration test.e2e test.smoke

build: ## Build local Docker images
	docker compose build

up: ## Start the local Docker Compose stack
	docker compose up

down: ## Stop the local Docker Compose stack
	docker compose down

lint: ## Check code style with ruff (linting + formatting, no changes)
	ruff check .
	ruff format --check .

lint.fix: ## Auto-fix ruff lint issues and format code
	ruff check --fix .
	ruff format .

format: ## Format code with ruff
	ruff format .

typecheck: ## Run mypy static type checker
	python -m mypy api_service embedding_service ingestion_worker shared tests \
		--ignore-missing-imports --no-strict-optional

pre-commit.install: ## Install pre-commit hooks
	pre-commit install

pre-commit.run: ## Run pre-commit hooks against all files
	pre-commit run --all-files

db.upgrade: ## Apply database migrations
	alembic upgrade head

db.downgrade: ## Roll back one database migration
	alembic downgrade -1

db.revision: ## Create a new database migration (MESSAGE="...")
	alembic revision -m "$${MESSAGE:?Set MESSAGE='description'}"

test: ## Run lint, type checking, unit, integration, and smoke tests
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test.unit
	$(MAKE) test.integration
	$(MAKE) test.smoke

test.unit: ## Run unit tests locally
	PYTHONPATH=. python -m pytest \
		api_service/tests/unit/ \
		embedding_service/tests/unit/ \
		ingestion_worker/tests/unit/ \
		shared/tests/unit/ \
		-v

test.integration: ## Run integration tests in Docker
	$(TEST_COMPOSE) run --build --rm test pytest \
		api_service/tests/integration/ \
		embedding_service/tests/integration/ \
		ingestion_worker/tests/integration/ \
		shared/tests/integration/ \
		-v; \
	EXIT=$$?; \
	$(TEST_COMPOSE) down -v; \
	exit $$EXIT

test.e2e: ## Run provider-backed end-to-end RAG tests in Docker
	@test -n "$$GEMINI_API_KEY_E2E_TEST" || (echo "GEMINI_API_KEY_E2E_TEST is required for test.e2e"; exit 2)
	$(E2E_COMPOSE) run --build --rm test; \
	EXIT=$$?; \
	$(E2E_COMPOSE) down -v; \
	exit $$EXIT

test.smoke: ## Run smoke tests locally
	PYTHONPATH=. python -m pytest tests/smoke/ -v
