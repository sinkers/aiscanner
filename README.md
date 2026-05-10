# OpenRouter Infrastructure Provider Map

**Complete mapping of all infrastructure providers hosting AI models on OpenRouter** — who hosts what, where they are, pricing over time, and real-time performance metrics.

Live site: **https://d2urbiy71pvy0i.cloudfront.net**

## What This Does

OpenRouter aggregates hundreds of AI models from dozens of infrastructure providers worldwide. Each model can be hosted by multiple providers with different pricing, latency, reliability, and location. This project maps it all and tracks pricing history daily.

The key distinction: OpenRouter has two types of "providers":
1. **Model Creator** — company that trained the model (`anthropic` in `anthropic/claude-3.5-sonnet`)
2. **Infrastructure Provider** — company that hosts/serves the model (Azure, DeepInfra, Together, etc.)

This project focuses on #2.

## Quick Start

### View the Live Site

```
https://d2urbiy71pvy0i.cloudfront.net
```

Updated daily by a scheduled Lambda. No setup required.

### Run Locally

```bash
python3 -m http.server 8000
open http://localhost:8000
```

Falls back to `infrastructure_provider_map.json` when `rollups/latest.json` is not available.

## Web Interface

### 5 Views

| Tab | What it shows |
|---|---|
| **All Providers** | Sortable/filterable table of all providers |
| **By Geography** | Providers grouped by country |
| **Performance Leaders** | Top 15 by uptime and latency |
| **Pricing Comparison** | Free models and cheapest paid options |
| **Model Comparisons** | All models with 2+ providers — side-by-side pricing and history charts |

### Model Comparisons Tab

The key tab for cost optimisation:

- Every model available from more than one provider, sorted by provider count
- Each row shows cheapest price and the spread between cheapest and most expensive
- Expand any model to see a **full provider pricing table** (prompt/1M, completion/1M, total, uptime, latency) sorted cheapest first
- **Price history chart** — one line per provider, tracks combined price/1M over time (builds up from the daily Lambda runs)

### Provider Details Modal

Click any provider name to see company description, location, links, pricing ranges, performance stats, and a pricing history chart for that provider.

## AWS Deployment

The project runs as a **scheduled Lambda + static S3 site**, deployed with CDK.

```
EventBridge (daily 00:00 UTC)
    └── Lambda (collector, ~90s, 512MB)
            ├── Fetches all model endpoints from OpenRouter API
            ├── snapshots/YYYY-MM-DD.json   raw daily archive
            ├── rollups/latest.json          current state (UI loads this)
            ├── rollups/providers/{name}.json  per-provider history
            └── rollups/models/{id}.json       per-model cross-provider history
                        ↓
                S3 bucket (private)
                        ↓
                CloudFront distribution
                        ↓
                    Browser
```

### Deploy from Scratch

Requires AWS credentials and Node.js (for CDK CLI).

```bash
./deploy.sh
```

This bootstraps CDK, deploys the stack, seeds S3 with existing data, and uploads the UI. Prints the CloudFront URL when done.

### Makefile Targets

```bash
make deploy      # Full deploy: CDK + seed S3 with existing data
make diff        # Preview pending infrastructure changes
make seed        # Re-upload data and index.html without redeploying
make invoke      # Manually trigger the Lambda and tail logs
make serve       # Local dev server on port 8000
make destroy     # Tear down the stack (bucket is retained)
```

### Infrastructure

| Resource | Details |
|---|---|
| S3 bucket | `dame-openrouter-pricing-{account-id}` — private, served via CloudFront OAC |
| CloudFront | HTTPS, 1h cache on rollups, 5min cache on `index.html` |
| Lambda | Python 3.12, 512MB, 15min timeout |
| EventBridge | `cron(0 0 * * ? *)` — daily at midnight UTC |

### S3 Layout

```
snapshots/YYYY-MM-DD.json       raw daily snapshot (~1MB each, 24h cache)
rollups/latest.json             current provider map (UI primary source)
rollups/providers/{name}.json   per-provider pricing history
rollups/models/{id}.json        per-model cross-provider pricing history
index.html                      the UI
```

## Local Data Pipeline

To refresh data locally (e.g. to seed a new deployment):

```bash
# 1. Fetch base catalogues (rarely changes)
python3 fetch_openrouter.py

# 2. Map all infrastructure providers (~90 seconds)
python3 map_infrastructure_providers.py

# 3. Optionally enrich with company research
python3 integrate_research.py

# 4. Upload to S3
make seed
```

`map_infrastructure_providers.py` saves progress every 10 models to `mapping_progress.json` and resumes on re-run if interrupted.

## Key Files

### Infrastructure (AWS)
- **`lambda/handler.py`** — Lambda function: fetches endpoints, writes snapshot + rollups
- **`infra/stack.py`** — CDK stack: S3, CloudFront, Lambda, EventBridge
- **`infra/app.py`** — CDK app entry point
- **`scripts/bootstrap_s3.py`** — Seeds S3 from existing `infrastructure_provider_map.json`
- **`Makefile`** — Common operations
- **`deploy.sh`** — One-command deploy

### Data Pipeline
- **`map_infrastructure_providers.py`** — Core mapper (fetches all endpoint data)
- **`fetch_openrouter.py`** — Fetches models and providers catalogues
- **`integrate_research.py`** — Merges `provider_research.json` enrichment data
- **`view_infrastructure_map.py`** — CLI query tool

### Data Files
- **`infrastructure_provider_map.json`** — Current provider map (local source of truth)
- **`provider_research.json`** — Company info: homepage, contact, description

### Web UI
- **`index.html`** — Full UI (Chart.js, all views, provider modal with history charts)
- **`index_standalone.html`** — Standalone version with data embedded (no server needed)

## CLI Query Tool

```bash
python3 view_infrastructure_map.py list
python3 view_infrastructure_map.py provider "DeepInfra"
python3 view_infrastructure_map.py model "meta-llama/llama-3.1-70b-instruct"
python3 view_infrastructure_map.py location US
python3 view_infrastructure_map.py cheapest 20
```

## Technical Notes

### API URL Encoding

Model IDs in endpoint URLs must **not** be URL-encoded:
```
✅  /api/v1/models/openai/gpt-4/endpoints
❌  /api/v1/models/openai%2Fgpt-4/endpoints  (404)
```

### Pricing Format

Stored as dollars per token; displayed as dollars per 1M tokens (multiply × 1,000,000).

### Rollup File Keys

Provider names with spaces/slashes have them replaced with `_` (e.g. `Azure AI Studio` → `Azure_AI_Studio.json`). Model IDs with `:` have them replaced with `_` (e.g. `model:free` → `model_free.json`); `/` in model IDs becomes a path prefix in S3 (e.g. `meta-llama/llama-3.1-70b-instruct.json`).

## Data Quality

| Data | Reliability | Source |
|---|---|---|
| Pricing | Real-time | OpenRouter API |
| Performance (uptime, latency) | Real-time, last 24h/30m | OpenRouter API |
| Model availability | Accurate | OpenRouter API |
| Provider headquarters | ~79% coverage | OpenRouter API |
| Company info (homepage, description) | ~88% coverage | `provider_research.json` |

Philosophy: show "Unknown" rather than guessed data.

## Troubleshooting

**Browser shows old data after `make seed`**
CloudFront caches `index.html` for 5 minutes. Hard refresh with Cmd+Shift+R or open in incognito.

**Lambda 401 Unauthorized**
The OpenRouter token in `infra/stack.py` (env var `OPENROUTER_API_TOKEN`) may have expired. Update it and run `make deploy`.

**`make deploy` fails at CDK bootstrap**
Ensure `aws configure` is set and you have permissions to create IAM roles and S3 buckets.

---

**Data Source**: OpenRouter API (https://openrouter.ai)  
**Updated**: Daily at 00:00 UTC by scheduled Lambda
