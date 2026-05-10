.PHONY: deploy install synth diff destroy seed invoke serve

OUTPUTS_FILE := cdk-outputs.json

# Read stack outputs (only valid after deploy)
bucket    = $(shell python3 -c "import json; print(list(json.load(open('$(OUTPUTS_FILE)')).values())[0]['BucketName'])" 2>/dev/null)
cf_url    = $(shell python3 -c "import json; print(list(json.load(open('$(OUTPUTS_FILE)')).values())[0]['CloudFrontURL'])" 2>/dev/null)
lambda_fn = $(shell python3 -c "import json; print(list(json.load(open('$(OUTPUTS_FILE)')).values())[0]['LambdaName'])" 2>/dev/null)

## Full deploy: install deps, bootstrap CDK, deploy stack, seed S3
deploy: install
	@echo "=== Bootstrapping CDK ==="
	cd infra && cdk bootstrap --quiet
	@echo "=== Deploying stack ==="
	cd infra && cdk deploy --require-approval never --outputs-file ../$(OUTPUTS_FILE)
	@echo "=== Seeding S3 ==="
	$(MAKE) seed
	@echo ""
	@echo "Site: $$(python3 -c "import json; print(list(json.load(open('$(OUTPUTS_FILE)')).values())[0]['CloudFrontURL'])")"

## Install CDK Python dependencies
install:
	pip3 install -r infra/requirements.txt -q --break-system-packages

## Preview CloudFormation template
synth:
	cd infra && cdk synth

## Show pending changes
diff:
	cd infra && cdk diff

## Upload index.html and current data to S3 (re-seed without full redeploy)
seed:
	python3 scripts/bootstrap_s3.py "$(bucket)" --upload-ui

## Manually trigger the Lambda and tail logs
invoke:
	aws lambda invoke \
		--function-name "$(lambda_fn)" \
		--log-type Tail \
		--query 'LogResult' \
		--output text \
		/tmp/pricing-invoke-out.json \
	| base64 -d
	@echo "--- response ---"
	@cat /tmp/pricing-invoke-out.json

## Run local dev server
serve:
	python3 -m http.server 8000

## Destroy the stack (bucket is retained, data is safe)
destroy:
	cd infra && cdk destroy --force
