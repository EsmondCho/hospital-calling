.DEFAULT_GOAL := help

COMPOSE := docker compose

# ── One-shot ────────────────────────────────────────────────────────────────
up: ## Build + start everything (postgres, redis, django, celery, backoffice)
	$(COMPOSE) up --build

up-d: ## Same as `up` but detached (background)
	$(COMPOSE) up --build -d

down: ## Stop everything
	$(COMPOSE) down

clean: ## Stop everything and delete the database volume (fresh seed next time)
	$(COMPOSE) down -v

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

# ── Run a single service (deps start automatically) ──────────────────────────
django: ## Start the API server only (port 8002) — runs migrations + seed
	$(COMPOSE) up --build django

celery: ## Start the Celery worker + beat only
	$(COMPOSE) up --build celery-worker celery-beat

backoffice: ## Start the Next.js backoffice only (port 3000)
	$(COMPOSE) up --build backoffice

# ── Django helpers ────────────────────────────────────────────────────────────
migrate: ## Apply migrations (also loads the demo seed)
	$(COMPOSE) run --rm django python manage.py migrate

seed-reset: ## Wipe the DB volume and re-seed from scratch
	$(COMPOSE) down -v
	$(COMPOSE) up --build -d django
	@echo "Re-seeding... watch `make logs` for completion."

shell: ## Django shell
	$(COMPOSE) run --rm django python manage.py shell

createsuperuser: ## Create a Django /admin/ superuser
	$(COMPOSE) run --rm django python manage.py createsuperuser

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: up up-d down clean logs django celery backoffice migrate seed-reset shell createsuperuser help
