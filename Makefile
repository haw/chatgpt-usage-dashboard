.PHONY: build up down test logs clear-data tf aws tf-bootstrap

build:
	docker compose build

up:
	docker compose up -d dashboard

down:
	docker compose down

test:
	docker compose run --rm --no-deps test

logs:
	docker compose logs -f dashboard

# Terraform / AWS CLI in the tools container, e.g.
#   make tf ARGS="plan -var-file=envs/prod.tfvars"
#   make aws ARGS="sts get-caller-identity"
tf:
	docker compose run --rm terraform terraform $(ARGS)

aws:
	docker compose run --rm terraform aws $(ARGS)

# One-time: create this project's Terraform state bucket and write envs/$(ENV).backend.hcl.
# Safe to re-run (no changes once the bucket exists).
ENV ?= prod
tf-bootstrap:
	docker compose run --rm terraform sh -ec '\
		terraform -chdir=bootstrap init -input=false && \
		terraform -chdir=bootstrap apply -var environment=$(ENV) && \
		terraform -chdir=bootstrap output -raw backend_config > envs/$(ENV).backend.hcl && \
		echo "Wrote infra/terraform/envs/$(ENV).backend.hcl"'

# Deletes only the local ./data contents using the current host user's permissions.
clear-data:
	@if [ -L "$(CURDIR)/data" ] || [ ! -d "$(CURDIR)/data" ]; then echo "Refusing to clear: ./data is missing or is a symlink." >&2; exit 1; fi
	@read -r -p "Delete saved files under local ./data? S3 data is untouched. [y/N] " answer; \
	case "$$answer" in \
		y|Y) find "$(CURDIR)/data" -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf -- {} + && echo "Local saved data cleared." ;; \
		*) echo "Cancelled." ;; \
	esac
