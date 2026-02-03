# Manga-ARR Makefile
# Convenient commands for common operations

.PHONY: help setup start stop restart logs build clean test db-migrate db-upgrade db-downgrade

help: ## Show this help message
	@echo "Manga-ARR - Available commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Initial setup (copy .env and create directories)
	@echo "Setting up Manga-ARR..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✓ Created .env file - PLEASE CONFIGURE IT BEFORE STARTING!"; \
	else \
		echo "✓ .env already exists"; \
	fi
	@mkdir -p downloads manga/kindle
	@echo "✓ Created directories"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit .env with your configuration"
	@echo "  2. Run: make start"

start: ## Start all services
	@echo "Starting Manga-ARR..."
	docker-compose up -d
	@echo ""
	@echo "✓ Services started!"
	@echo "  API:         http://localhost:7878"
	@echo "  API Docs:    http://localhost:7878/docs"
	@echo "  Calibre-Web: http://localhost:8083"
	@echo ""
	@echo "Check logs with: make logs"

stop: ## Stop all services
	@echo "Stopping Manga-ARR..."
	docker-compose down
	@echo "✓ Services stopped"

restart: ## Restart all services
	@echo "Restarting Manga-ARR..."
	docker-compose restart
	@echo "✓ Services restarted"

logs: ## Show logs from all services
	docker-compose logs -f

logs-backend: ## Show logs from backend only
	docker-compose logs -f backend

logs-converter: ## Show logs from KCC converter only
	docker-compose logs -f kcc-converter

logs-db: ## Show logs from database only
	docker-compose logs -f postgres

build: ## Rebuild all Docker images
	@echo "Building Docker images..."
	docker-compose build
	@echo "✓ Build complete"

rebuild: ## Rebuild and restart all services
	@echo "Rebuilding Manga-ARR..."
	docker-compose down
	docker-compose build
	docker-compose up -d
	@echo "✓ Rebuild complete"

status: ## Show status of all services
	docker-compose ps

clean: ## Stop and remove containers (keeps volumes)
	@echo "Cleaning up containers..."
	docker-compose down
	@echo "✓ Containers removed (volumes preserved)"

clean-all: ## ⚠️  Remove everything including volumes (DATA LOSS!)
	@echo "⚠️  WARNING: This will delete ALL data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		rm -rf downloads/* manga/*; \
		echo "✓ All data removed"; \
	else \
		echo "Cancelled"; \
	fi

shell-backend: ## Open shell in backend container
	docker-compose exec backend bash

shell-db: ## Open psql shell in database
	docker-compose exec postgres psql -U manga manga_arr

test-scraper: ## Test scraper connection
	@curl -s http://localhost:7878/api/v1/system/test/scraper | python3 -m json.tool

test-smtp: ## Test SMTP connection
	@curl -s http://localhost:7878/api/v1/system/test/smtp | python3 -m json.tool

test-kcc: ## Test KCC installation
	@curl -s http://localhost:7878/api/v1/system/test/kcc | python3 -m json.tool

api-status: ## Get API status
	@curl -s http://localhost:7878/api/v1/system/status | python3 -m json.tool

api-stats: ## Get detailed statistics
	@curl -s http://localhost:7878/api/v1/system/stats | python3 -m json.tool

queue: ## Show download queue
	@curl -s http://localhost:7878/api/v1/queue/ | python3 -m json.tool

db-backup: ## Backup database
	@echo "Creating database backup..."
	@mkdir -p backups
	@docker-compose exec -T postgres pg_dump -U manga manga_arr > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✓ Backup created in backups/"

db-restore: ## Restore database from backup (Usage: make db-restore FILE=backups/backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "Error: Please specify backup file"; \
		echo "Usage: make db-restore FILE=backups/backup_20240101_120000.sql"; \
		exit 1; \
	fi
	@echo "Restoring database from $(FILE)..."
	@docker-compose exec -T postgres psql -U manga manga_arr < $(FILE)
	@echo "✓ Database restored"

update: ## Update Manga-ARR to latest version
	@echo "Updating Manga-ARR..."
	git pull
	docker-compose down
	docker-compose build
	docker-compose up -d
	@echo "✓ Update complete"

install: setup start ## Complete installation (setup + start)
	@echo ""
	@echo "🎉 Manga-ARR is installed and running!"
	@echo ""
	@echo "Next: Open http://localhost:7878/docs and add your first manga"
