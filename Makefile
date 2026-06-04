.PHONY: build up down logs test shell db-init

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	pytest tests/ --cov=detection --cov=api --cov-report=term -v

shell:
	docker compose exec api bash
