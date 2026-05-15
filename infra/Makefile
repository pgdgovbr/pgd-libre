.PHONY: help init fmt validate plan apply bootstrap clean

TF_DIR := terraform

help:
	@echo "PGD Libre — Infra targets"
	@echo "  bootstrap   Cria o bucket de state (única execução, com gcloud autenticado)"
	@echo "  init        terraform init"
	@echo "  fmt         terraform fmt"
	@echo "  validate    terraform validate"
	@echo "  plan        terraform plan"
	@echo "  apply       terraform apply (NÃO usar localmente em prod — só via CI)"
	@echo "  clean       remove .terraform local"

bootstrap:
	./scripts/bootstrap-state-bucket.sh

init:
	cd $(TF_DIR) && terraform init

fmt:
	cd $(TF_DIR) && terraform fmt -recursive

validate:
	cd $(TF_DIR) && terraform validate

plan:
	cd $(TF_DIR) && terraform plan

apply:
	cd $(TF_DIR) && terraform apply

clean:
	rm -rf $(TF_DIR)/.terraform
