# One-command workflows. Everything runs in containers — no local Python/Node/Postgres needed.
.PHONY: up down logs ps test reset help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

up: ## Build + start the full stack (API :8000/docs, Grafana :3000, Prometheus :9090)
	docker compose up --build -d
	@echo "API ready at http://localhost:8000/docs once healthchecks pass (~30s)."

down: ## Stop the stack (keeps the Postgres volume)
	docker compose down

reset: ## Stop the stack and delete all data (fresh DB)
	docker compose down -v

logs: ## Tail logs from every service
	docker compose logs -f

ps: ## Show service status / healthchecks
	docker compose ps

test: ## Run the backend test suite (lint + types + pytest with coverage)
	cd backend && ruff check . && mypy app && pytest --cov=app
