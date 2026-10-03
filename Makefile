.PHONY: build up down test logs clear-data tf aws tf-build aws-configure aws-whoami tf-shell tf-bootstrap tf-init tf-plan tf-apply tf-output tf-fmt tf-check tf-first-image

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

# --- Terraform / AWS CLI (infra/terraform), always inside the tools container ---------------
# ENV picks envs/<ENV>.tfvars and envs/<ENV>.backend.hcl; ARGS is appended to the command, e.g.
#   make tf-plan
#   make tf-apply ARGS="-target=aws_ecr_repository.api"
#   make -s tf-output ARGS="-raw ecr_repository"
#   make tf ARGS="state list"            # any other terraform subcommand
#   make aws ARGS="sts get-caller-identity"
ENV ?= prod
TF_RUN = docker compose run --rm terraform

tf-build:
	docker compose build terraform

# One-time: store the access key in the container's credentials volume.
aws-configure:
	$(TF_RUN) aws configure

aws-whoami:
	$(TF_RUN) aws sts get-caller-identity

# A shell in the container (terraform, aws, jq, openssl) for anything interactive.
tf-shell:
	$(TF_RUN) bash

tf:
	$(TF_RUN) terraform $(ARGS)

aws:
	$(TF_RUN) aws $(ARGS)

# One-time: create this project's Terraform state bucket and write envs/$(ENV).backend.hcl.
# Safe to re-run (no changes once the bucket exists).
tf-bootstrap:
	$(TF_RUN) sh -ec '\
		terraform -chdir=bootstrap init -input=false && \
		terraform -chdir=bootstrap apply -var environment=$(ENV) && \
		terraform -chdir=bootstrap output -raw backend_config > envs/$(ENV).backend.hcl && \
		echo "Wrote infra/terraform/envs/$(ENV).backend.hcl"'

tf-init:
	$(TF_RUN) terraform init -backend-config=envs/$(ENV).backend.hcl $(ARGS)

tf-plan:
	$(TF_RUN) terraform plan -var-file=envs/$(ENV).tfvars $(ARGS)

tf-apply:
	$(TF_RUN) terraform apply -var-file=envs/$(ENV).tfvars $(ARGS)

tf-output:
	$(TF_RUN) terraform output $(ARGS)

tf-fmt:
	$(TF_RUN) terraform fmt -recursive

# What CI checks; needs no AWS credentials.
tf-check:
	$(TF_RUN) sh -ec 'terraform fmt -check -recursive && terraform init -backend=false -input=false >/dev/null && terraform validate'

# One-time, before the first full apply: the ECS service needs an image to start, so create
# only the ECR repository and push the API image built on the host. CI pushes from then on.
tf-first-image:
	$(TF_RUN) terraform apply -var-file=envs/$(ENV).tfvars -target=aws_ecr_repository.api
	REPO=$$($(TF_RUN) terraform output -raw ecr_repository) && \
	$(TF_RUN) aws ecr get-login-password | docker login --username AWS --password-stdin $${REPO%%/*} && \
	docker build -t $$REPO:latest . && \
	docker push $$REPO:latest

# Deletes only the local ./data contents using the current host user's permissions.
clear-data:
	@if [ -L "$(CURDIR)/data" ] || [ ! -d "$(CURDIR)/data" ]; then echo "Refusing to clear: ./data is missing or is a symlink." >&2; exit 1; fi
	@read -r -p "Delete saved files under local ./data? S3 data is untouched. [y/N] " answer; \
	case "$$answer" in \
		y|Y) find "$(CURDIR)/data" -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf -- {} + && echo "Local saved data cleared." ;; \
		*) echo "Cancelled." ;; \
	esac
