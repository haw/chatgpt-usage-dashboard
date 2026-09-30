.PHONY: build up down collect test logs

build:
	docker compose build

up:
	docker compose up -d dashboard

down:
	docker compose down

collect:
	docker compose run --rm collector collect --days 7

test:
	docker compose run --rm --no-deps test

logs:
	docker compose logs -f dashboard
