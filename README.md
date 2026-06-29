# AI Scanner

**Compare pricing, performance, and availability across AI infrastructure** — LLM hosting providers, voice/video AI services, and GPU rental markets, all in one place.

Live site: **https://d2urbiy71pvy0i.cloudfront.net**

## What This Does

The AI market is fragmented across hundreds of providers with different pricing, capabilities, and performance characteristics. AI Scanner aggregates data from multiple sources and presents it in a unified, searchable interface so you can make informed decisions about where to run your AI workloads.

## Features

### LLM Infrastructure Map

Compare infrastructure providers hosting AI models on OpenRouter — who hosts what, where they are, and at what price.

- **Provider table** — sortable and filterable by name, location, model count, pricing
- **Geography view** — providers grouped by country
- **Performance leaders** — top providers ranked by uptime and latency
- **Pricing comparison** — find the cheapest provider for any model
- **Model comparisons** — side-by-side pricing across providers for models hosted by 2+ providers, with price history charts
- **Benchmark scores** — Open LLM Leaderboard v2 data integrated into model views
- **Provider detail modals** — company info, location, pricing ranges, performance stats, and history charts

### Voice & Video AI Services

Compare STT, TTS, and video generation services across providers.

- **Multi-provider catalog** — Deepgram, ElevenLabs, OpenAI, Google, Groq, Fireworks, AssemblyAI, fal.ai, HuggingFace open-source models
- **Filter by capability** — streaming, real-time, free tier, voice cloning
- **Pricing breakdowns** — per-minute (STT), per-character (TTS), per-second (video), with streaming vs batch rates
- **Self-hosting info** — hardware requirements (VRAM, RAM, CPU-only) for open-source models
- **Trial credit calculator** — see how far free credits go at each provider's rates

### GPU Rental Pricing

Compare GPU rental costs across cloud providers.

- **Multi-provider comparison** — RunPod, Vast.ai, Lambda Labs, TensorDock, Vultr, Azure, AWS, Oracle Cloud, Google Cloud, CoreWeave, FluidStack, DataCrunch, Jarvis Labs, Thunder Compute, Nova Cloud
- **Pricing tiers** — spot, on-demand, and reserved pricing side by side
- **Filter by GPU model** — search for specific GPUs (A100, H100, RTX 4090, etc.)
- **Price trends** — historical pricing charts

## Quick Start

### View the Live Site

Visit the CloudFront URL above. Updated daily by a scheduled Lambda. No setup required.

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set your API token
export OPENROUTER_API_TOKEN=your-token-here

# Refresh all data
make refresh-all

# Start local dev server
make serve
# Open http://localhost:8000/webapp/
```

See `make help` for all available targets.

## Data Pipeline

Four-stage pipeline, all run via `make`:

```
1. FETCH     make fetch-openrouter     Fetch models + providers from OpenRouter API
2. MAP       make map-infra            Map infrastructure providers (~2 min)
3. ENRICH    make integrate-research   Merge hand-curated company research
4. REPORT    make generate-report      Generate daily report (JSON + Markdown)
```

Voice/video data has its own fetcher:

```
make fetch-voice       Fetch voice/video models from all providers
```

Run `make refresh-all` to execute the full LLM pipeline end to end.

### Progress Tracking

The infrastructure mapper saves a checkpoint every 10 models. If interrupted, re-run `make map-infra` — it resumes from the last checkpoint.

## AWS Deployment

The project runs as a **scheduled Lambda + static S3 site**, deployed with CDK.

```
EventBridge (daily 00:00 UTC)
    └── Lambda (collector, ~90s, 512MB)
            ├── Fetches all model endpoints from OpenRouter API
            ├── snapshots/YYYY-MM-DD.json     daily archive
            ├── rollups/latest.json            current state (UI loads this)
            ├── rollups/providers/{name}.json   per-provider history
            └── rollups/models/{id}.json        per-model history
                        ↓
                S3 bucket (private, OAC)
                        ↓
                CloudFront (HTTPS, cached)
                        ↓
                    Browser
```

### Deploy

```bash
make deploy      # Full deploy: CDK + seed S3
make ui          # Upload webapp HTML only
make seed        # Upload data + UI without redeploying
make invoke      # Manually trigger the Lambda
make destroy     # Tear down the stack (bucket is retained)
```

Requires AWS credentials and Node.js (for CDK CLI). Run `./deploy/deploy.sh` for a from-scratch deploy.

## Data Sources

| Source | What it provides | Update frequency |
|---|---|---|
| [OpenRouter API](https://openrouter.ai) | LLM models, providers, endpoints, pricing, performance | Daily (Lambda) |
| [Deepgram API](https://deepgram.com) | STT/TTS models and pricing | On demand |
| [ElevenLabs API](https://elevenlabs.io) | TTS/STS models, voice catalog, pricing | On demand |
| [OpenAI API](https://openai.com) | TTS/STT models and pricing | On demand |
| [Groq API](https://groq.com) | STT models and pricing | On demand |
| [fal.ai API](https://fal.ai) | Image/video generation models and pricing | On demand |
| [HuggingFace](https://huggingface.co) | Open-source model metadata, downloads, hardware reqs | On demand |
| [Open LLM Leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard) | Benchmark scores | On demand |
| GPU provider APIs | Spot/on-demand/reserved GPU pricing | On demand |

## Technical Notes

**Pricing format**: Stored as dollars per token; displayed as dollars per 1M tokens (multiply by 1,000,000).

**API URL encoding**: Model IDs in OpenRouter endpoint URLs must not be URL-encoded (`/api/v1/models/openai/gpt-4/endpoints`, not `openai%2Fgpt-4`).

**Missing data**: Shows "Unknown" or "N/A" rather than guessed values. ~21% of providers lack location data; this is expected.

## Troubleshooting

**Browser shows old data** — CloudFront caches HTML for 5 minutes. Hard refresh (Cmd+Shift+R) or use incognito.

**Lambda 401 Unauthorized** — The `OPENROUTER_API_TOKEN` environment variable may have expired. Update it and redeploy.

**`make deploy` fails at CDK bootstrap** — Ensure `aws configure` is set with permissions for IAM roles and S3 buckets.
