.DEFAULT_GOAL := help
SHELL := /bin/bash

CYAN   := \033[36m
GREEN  := \033[32m
RESET  := \033[0m

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
