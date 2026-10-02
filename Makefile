.PHONY: build up down collect test logs clear-data

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

# Deletes only the local ./data contents through a root container so container-owned files can be removed.
clear-data:
	@if [ -L "$(CURDIR)/data" ] || [ ! -d "$(CURDIR)/data" ]; then echo "Refusing to clear: ./data is missing or is a symlink." >&2; exit 1; fi
	@read -r -p "Delete saved files under local ./data? S3 data is untouched. [y/N] " answer; \
	case "$$answer" in \
		y|Y) docker compose run --rm --no-deps --user 0 --entrypoint sh dashboard -c 'find /app/data -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf -- {} +' && echo "Local saved data cleared." ;; \
		*) echo "Cancelled." ;; \
	esac
