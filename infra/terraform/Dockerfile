# Terraform + AWS CLI for working on infra/terraform without installing either on the host.
#   docker compose run --rm terraform terraform plan -var-file=envs/prod.tfvars
#   docker compose run --rm terraform aws sts get-caller-identity
FROM hashicorp/terraform:1.13.4

# aws-cli v2 (Alpine community package), plus the small tools the README's commands use.
RUN apk add --no-cache aws-cli bash curl jq openssl

# Home of the user compose runs as. /home/tf/.aws is where the named volume holding the AWS credentials
# is mounted; a new volume takes its ownership from this directory.
ARG UID=1000
ARG GID=1000
RUN mkdir -p /home/tf/.aws && chown -R ${UID}:${GID} /home/tf && chmod 700 /home/tf/.aws

# The official image's entrypoint is `terraform`; clear it so both `terraform ...` and `aws ...` can be run.
ENTRYPOINT []
CMD ["terraform", "version"]
