# Terraform + AWS CLI for working on infra/terraform without installing either on the host.
#   docker compose run --rm terraform terraform plan -var-file=envs/prod.tfvars
#   docker compose run --rm terraform aws sts get-caller-identity
FROM hashicorp/terraform:1.13.4

# aws-cli v2 (Alpine community package), plus the small tools the README's commands use.
RUN apk add --no-cache aws-cli bash curl jq openssl

# The official image's entrypoint is `terraform`; clear it so both `terraform ...` and `aws ...` can be run.
ENTRYPOINT []
CMD ["terraform", "version"]
