.PHONY: deploy install synth diff destroy seed invoke serve configure-gpu

OUTPUTS_FILE := cdk-outputs.json

# Read stack outputs — search all stacks for the key (handles multi-stack outputs)
_outputs  = $(shell python3 -c "import json; d=json.load(open('$(OUTPUTS_FILE)')); [print(s[k]) for s in d.values() for k in ['$(1)'] if k in s]" 2>/dev/null)
bucket    = $(shell python3 -c "import json; d=json.load(open('$(OUTPUTS_FILE)')); [print(s['BucketName']) for s in d.values() if 'BucketName' in s]" 2>/dev/null)
cf_url    = $(shell python3 -c "import json; d=json.load(open('$(OUTPUTS_FILE)')); [print(s['CloudFrontURL']) for s in d.values() if 'CloudFrontURL' in s]" 2>/dev/null)
lambda_fn = $(shell python3 -c "import json; d=json.load(open('$(OUTPUTS_FILE)')); [print(s['LambdaName']) for s in d.values() if 'LambdaName' in s]" 2>/dev/null)

## Full deploy: install deps, bootstrap CDK, deploy stack, upload UI
## Use 'make seed' on first-ever deploy to also initialise rollup data.
deploy: install
	@echo "=== Bootstrapping CDK ==="
	cd infra && cdk bootstrap aws://$(shell aws sts get-caller-identity --query Account --output text)/us-east-1 --quiet
	cd infra && cdk bootstrap --quiet
	@echo "=== Deploying stack ==="
	cd infra && cdk deploy --all --require-approval never --outputs-file ../$(OUTPUTS_FILE)
	@echo "=== Uploading UI ==="
	$(MAKE) ui
	@echo ""
	@echo "Site: $$(python3 -c "import json; d=json.load(open('$(OUTPUTS_FILE)')); [print(s['SiteURL']) for s in d.values() if 'SiteURL' in s]")"

## Install CDK Python dependencies
install:
	pip3 install -r infra/requirements.txt -q --break-system-packages

## Preview CloudFormation template
synth:
	cd infra && cdk synth

## Show pending changes
diff:
	cd infra && cdk diff

## Upload HTML files to S3 without touching historical data
ui:
	python3 scripts/bootstrap_s3.py "$(bucket)" --upload-ui --ui-only

## Seed S3 with data on first deploy (skips rollups that already exist)
seed:
	python3 scripts/bootstrap_s3.py "$(bucket)" --upload-ui

## Trigger the Lambda asynchronously (fire-and-forget; check logs in CloudWatch)
invoke:
	aws lambda invoke \
		--function-name "$(lambda_fn)" \
		--invocation-type Event \
		/tmp/pricing-invoke-out.json
	@echo "Lambda triggered (async). Check progress:"
	@echo "  aws logs tail /aws/lambda/$(lambda_fn) --follow"

## Store GPU rental API keys in SSM Parameter Store (run once after deploy)
## Usage: RUNPOD_API_KEY=sk-... VAST_API_KEY=... make configure-gpu
configure-gpu:
	@if [ -z "$(RUNPOD_API_KEY)" ] && [ -z "$(VAST_API_KEY)" ]; then \
		echo "Usage: RUNPOD_API_KEY=<key> VAST_API_KEY=<key> make configure-gpu"; \
		echo "At least one key must be provided."; \
		exit 1; \
	fi
	@if [ -n "$(RUNPOD_API_KEY)" ]; then \
		aws ssm put-parameter \
			--name "/dame/gpu/runpod_api_key" \
			--value "$(RUNPOD_API_KEY)" \
			--type SecureString \
			--overwrite \
			--tier Standard; \
		echo "  stored: /dame/gpu/runpod_api_key"; \
	fi
	@if [ -n "$(VAST_API_KEY)" ]; then \
		aws ssm put-parameter \
			--name "/dame/gpu/vast_api_key" \
			--value "$(VAST_API_KEY)" \
			--type SecureString \
			--overwrite \
			--tier Standard; \
		echo "  stored: /dame/gpu/vast_api_key"; \
	fi
	@echo "Keys stored. Invoke Lambda to collect GPU pricing: make invoke"

## Run local dev server
serve:
	python3 -m http.server 8000

## Destroy the stack (bucket is retained, data is safe)
destroy:
	cd infra && cdk destroy --force
