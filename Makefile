.PHONY: help install synth diff deploy destroy \
        seed ui invoke rebuild-history \
        fetch-openrouter map-infra integrate-research generate-report refresh-all \
        fetch-voice serve view-map view-report \
        configure-gpu configure-gpu-env \
        test test-live

# ── Python package path ─────────────────────────────────────────────────────
PYTHONPATH := src
export PYTHONPATH

OUTPUTS_FILE := cdk-outputs.json

# Read a value from whichever CDK stack contains it
_read = $(shell python3 -c \
    "import json,sys; d=json.load(open('$(OUTPUTS_FILE)')); \
     [print(s['$(1)']) for s in d.values() if '$(1)' in s]" 2>/dev/null)

bucket    := $(call _read,BucketName)
cf_url    := $(call _read,CloudFrontURL)
lambda_fn := $(call _read,LambdaName)

# ── Help ─────────────────────────────────────────────────────────────────────
help:
	@grep -E '^## ' Makefile | sed 's/^## //'

# ── Setup ────────────────────────────────────────────────────────────────────
## install            Install CDK Python dependencies
install:
	pip3 install -r infra/requirements.txt -q --break-system-packages

# ── Infrastructure ───────────────────────────────────────────────────────────
## deploy             Bootstrap CDK, deploy stack, seed S3, print site URL
deploy: install
	@echo "=== Bootstrapping CDK ==="
	cd infra && cdk bootstrap aws://$(shell aws sts get-caller-identity \
	    --query Account --output text)/us-east-1 --quiet
	cd infra && cdk bootstrap --quiet
	@echo "=== Deploying stack ==="
	cd infra && cdk deploy --all --require-approval never \
	    --outputs-file ../$(OUTPUTS_FILE)
	@echo "=== Seeding S3 ==="
	$(MAKE) seed
	@echo ""
	@echo "Site: $(cf_url)"

## synth              Preview CloudFormation template
synth:
	cd infra && cdk synth

## diff               Show pending infrastructure changes
diff:
	cd infra && cdk diff

## destroy            Tear down the stack (S3 bucket is retained)
destroy:
	cd infra && cdk destroy --force

# ── S3 / Deployment ──────────────────────────────────────────────────────────
## ui                 Upload webapp HTML files to S3 only
ui:
	python3 scripts/bootstrap_s3.py "$(bucket)" --upload-ui --ui-only

## seed               Upload data + UI to S3 (skips existing rollup history)
seed:
	python3 scripts/bootstrap_s3.py "$(bucket)" --upload-ui

## invoke             Trigger Lambda async (fire-and-forget)
invoke:
	aws lambda invoke \
	    --function-name "$(lambda_fn)" \
	    --invocation-type Event \
	    /tmp/dame-invoke-out.json
	@echo "Lambda triggered. Tail logs:"
	@echo "  aws logs tail /aws/lambda/$(lambda_fn) --follow"

## rebuild-history    Rebuild all S3 rollup history from daily snapshots
rebuild-history:
	python3 scripts/rebuild_history.py "$(bucket)"

# ── Local Data Pipeline ───────────────────────────────────────────────────────
## fetch-openrouter   Fetch models + providers from OpenRouter API → data/
fetch-openrouter:
	python3 -m llm_providers.openrouter.fetch

## map-infra          Map all infrastructure providers → data/infrastructure_provider_map.json
map-infra:
	python3 -m llm_providers.openrouter.map_infrastructure

## integrate-research Merge data/seeds/provider_research.json into infrastructure map
integrate-research:
	python3 -m llm_providers.openrouter.integrate_research

## generate-report    Generate daily report → data/daily_report.{json,md}
generate-report:
	python3 -m llm_providers.reports.daily_report

## refresh-all        Full local pipeline: fetch → map → integrate → report
refresh-all: fetch-openrouter map-infra integrate-research generate-report
	@echo ""
	@echo "=== Local refresh complete ==="
	@echo "  data/openrouter_models.json"
	@echo "  data/openrouter_providers.json"
	@echo "  data/infrastructure_provider_map.json"
	@echo "  data/daily_report.{json,md}"

## fetch-voice        Fetch voice/video model data from all sources
fetch-voice:
	bash scripts/refresh_voice_video.sh

# ── Local Dev ─────────────────────────────────────────────────────────────────
## test               Run all tests (unit + integration, no network needed)
test:
	python3 -m pytest tests/ -v --tb=short

## test-live          Run tests including live deployment verification (needs network)
test-live:
	python3 -m pytest tests/ -v --tb=short -k "not Live" && \
	python3 -m pytest tests/ -v --tb=short -k "Live"

## serve              Run local dev server at http://localhost:8000/webapp/
serve:
	python3 -m llm_providers.cli.serve

## view-map           Interactive CLI: query infrastructure provider map
view-map:
	python3 -m llm_providers.cli.view_map

## view-report        Interactive CLI: query daily report data
view-report:
	python3 -m llm_providers.cli.view_report

# ── GPU Keys ──────────────────────────────────────────────────────────────────
## configure-gpu      Store GPU API keys in SSM Parameter Store
## Usage: RUNPOD_API_KEY=... VAST_API_KEY=... LAMBDA_LABS_API_KEY=... make configure-gpu
configure-gpu:
	@if [ -z "$(RUNPOD_API_KEY)" ] && [ -z "$(VAST_API_KEY)" ] && \
	    [ -z "$(LAMBDA_LABS_API_KEY)" ]; then \
	    echo "Usage: RUNPOD_API_KEY=<key> VAST_API_KEY=<key> LAMBDA_LABS_API_KEY=<key> make configure-gpu"; \
	    exit 1; \
	fi
	@[ -n "$(RUNPOD_API_KEY)" ] && aws ssm put-parameter \
	    --name "/dame/gpu/runpod_api_key" --value "$(RUNPOD_API_KEY)" \
	    --type SecureString --overwrite --tier Standard \
	    && echo "  stored: /dame/gpu/runpod_api_key" || true
	@[ -n "$(VAST_API_KEY)" ] && aws ssm put-parameter \
	    --name "/dame/gpu/vast_api_key" --value "$(VAST_API_KEY)" \
	    --type SecureString --overwrite --tier Standard \
	    && echo "  stored: /dame/gpu/vast_api_key" || true
	@[ -n "$(LAMBDA_LABS_API_KEY)" ] && aws ssm put-parameter \
	    --name "/dame/gpu/lambda_labs_api_key" --value "$(LAMBDA_LABS_API_KEY)" \
	    --type SecureString --overwrite --tier Standard \
	    && echo "  stored: /dame/gpu/lambda_labs_api_key" || true

## configure-gpu-env  Load GPU API keys from .env into SSM
configure-gpu-env:
	@[ -f .env ] || (echo ".env not found"; exit 1)
	@export $$(grep -v '^#' .env | xargs) && \
	    $(MAKE) configure-gpu \
	        RUNPOD_API_KEY="$$RUNPOD_API_KEY" \
	        VAST_API_KEY="$$VAST_API_KEY" \
	        LAMBDA_LABS_API_KEY="$$LAMBDA_LABS_API_KEY"
