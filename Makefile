.PHONY: up down logs test lint format shell

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f app

test:
	docker compose exec app pytest tests/ -v

lint:
	docker compose exec app ruff check app/
	docker compose exec app mypy app/

format:
	docker compose exec app ruff format app/

shell:
	docker compose exec app bash