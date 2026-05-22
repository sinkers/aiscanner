# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenRouter Infrastructure Provider Mapper — maps infrastructure providers hosting models on OpenRouter, showing who hosts what, where they are, pricing, and real-time performance metrics.

**Critical Distinction**: OpenRouter has TWO types of "providers":
1. **Model Creator** — Company that trained the model (e.g., `anthropic` in `anthropic/claude-3.5-sonnet`)
2. **Infrastructure Provider** — Company that hosts/serves the model (e.g., Azure, AWS Bedrock, DeepInfra)

This project focuses on #2 (infrastructure providers). One model can be hosted by multiple infrastructure providers with different pricing and performance.

## Directory Structure

```
llm-providers/
├── README.md               # Project overview (only doc at root)
├── CLAUDE.md               # This file
├── Makefile                # All common tasks (run `make help`)
├── requirements.txt        # Python dependencies
├── .env                    # Secrets (gitignored)
│
├── src/llm_providers/      # Python package (PYTHONPATH=src)
│   ├── config.py           # Central config: API token, all data paths
│   ├── openrouter/
│   │   ├── fetch.py        # Fetch models + providers from API
│   │   ├── map_infrastructure.py  # Map infrastructure providers
│   │   └── integrate_research.py # Merge seed research into map
│   ├── reports/
│   │   └── daily_report.py # Generate daily markdown + JSON report
│   └── cli/
│       ├── serve.py        # Local dev server (serves from repo root)
│       ├── view_map.py     # Query infrastructure map
│       ├── view_report.py  # Query daily report
│       └── view_audio.py   # Audio model pricing viewer
│
├── webapp/                 # Web UI
│   ├── index.html          # Main dashboard
│   ├── llm.html            # LLM models view
│   ├── voice.html          # Voice/Video services
│   ├── gpu.html            # GPU rental pricing
│   └── fix_pricing.js      # Pricing data helper
│
├── data/                   # All data files (gitignored except seeds/)
│   ├── seeds/              # Hand-curated data (committed to git)
│   │   └── provider_research.json
│   ├── openrouter_models.json
│   ├── openrouter_providers.json
│   ├── infrastructure_provider_map.json
│   ├── daily_report.json
│   └── daily_report.md
│
├── deploy/                 # Deploy scripts
│   ├── deploy.sh           # Full deploy (calls make deploy)
│   └── refresh_all_data.sh # Refresh all data locally
│
├── docs/                   # Documentation
│   ├── quick-start.md
│   ├── data-sources.md
│   ├── web-ui-guide.md
│   └── pricing-guide.md
│
├── scripts/                # S3/utility scripts
│   ├── bootstrap_s3.py     # Seed S3 with initial data
│   ├── rebuild_history.py  # Rebuild S3 rollup history
│   ├── fetch_benchmarks.py
│   ├── fetch_huggingface_models.py
│   ├── fetch_voice_providers.py
│   ├── fetch_fal_models.py
│   ├── merge_voice_video_data.py
│   └── refresh_voice_video.sh
│
├── lambda/                 # AWS Lambda handler (CDK-managed)
│   └── handler.py
│
└── infra/                  # AWS CDK infrastructure
    ├── app.py
    └── stack.py
```

## Architecture

### Data Pipeline (4 stages, all run via `make`)

```
1. FETCH  (make fetch-openrouter)
   └─ src/llm_providers/openrouter/fetch.py
      ├─ GET /api/v1/models → data/openrouter_models.json
      └─ GET /api/v1/providers → data/openrouter_providers.json

2. MAP    (make map-infra)   ⭐ Core stage
   └─ src/llm_providers/openrouter/map_infrastructure.py
      ├─ For each model: GET /api/v1/models/{id}/endpoints
      ├─ Aggregates pricing, performance, location per provider
      ├─ Progress checkpoint: data/mapping_progress.json (resumes if interrupted)
      └─ Output: data/infrastructure_provider_map.json

3. ENRICH (make integrate-research)
   └─ src/llm_providers/openrouter/integrate_research.py
      ├─ Reads: data/seeds/provider_research.json (hand-curated)
      └─ Merges: homepage, contact_email, support_url, city, description

4. REPORT (make generate-report)
   └─ src/llm_providers/reports/daily_report.py
      ├─ Tracks TTS, STT, video, image generation features
      ├─ Outputs: data/daily_report.md + data/daily_report.json
      └─ Run 'make refresh-all' to execute all 4 stages
```

### Web UI

```
webapp/index.html     — Main dashboard (requires web server for CORS)
webapp/index_standalone.html — Embedded JSON version (gitignored, regenerate as needed)
```

Run locally: `make serve` → http://localhost:8000/webapp/

## Critical Technical Details

### API Endpoint Gotcha: URL Encoding

**WRONG** (causes 404s):
```python
encoded = model_id.replace('/', '%2F')  # openai%2Fgpt-4
url = f"/api/v1/models/{encoded}/endpoints"  # ❌
```

**CORRECT**:
```python
url = f"/api/v1/models/{model_id}/endpoints"  # ✅ Raw ID in path
```

### Pricing Display Conversion

**Storage** (JSON): Dollars per token
```json
{"prompt": "0.0000004", "completion": "0.0000006"}
```
**Display** (UI): Dollars per 1M tokens — multiply stored value by 1,000,000.

### Data Paths

All paths are defined in `src/llm_providers/config.py`. Never hardcode paths in modules — use `config.INFRA_MAP_FILE`, `config.MODELS_FILE`, etc.

### Running the Package

```bash
export PYTHONPATH=src   # or use make targets which set this automatically
python3 -m llm_providers.openrouter.fetch
```

## Common Commands

```bash
make help                  # List all targets

# Full local data refresh
make refresh-all           # fetch → map → enrich → report

# Individual stages
make fetch-openrouter      # Fetch models + providers from API
make map-infra             # Map infrastructure providers (~2 min)
make integrate-research    # Merge seed research data
make generate-report       # Generate daily report

# Query data locally
make view-map              # Interactive map viewer
make view-report           # Interactive report viewer

# Local dev server
make serve                 # http://localhost:8000/webapp/

# Deploy
make deploy                # Full CDK deploy + S3 seed
make ui                    # Upload webapp HTML to S3 only
make seed                  # Upload data + UI to S3
make invoke                # Trigger Lambda (collect fresh data)

# GPU pricing API keys
make configure-gpu-env     # Load GPU keys from .env into SSM
```

## API Token

Set `OPENROUTER_API_TOKEN` in `.env` or export it in your shell. Falls back to a hardcoded token in `src/llm_providers/config.py` — update that token if API calls fail with 401.

## Important Patterns

### Progress Tracking (Resume on Failure)

`map_infrastructure.py` saves a checkpoint every 10 models to `data/mapping_progress.json`. If interrupted, just re-run `make map-infra` — it resumes from the last checkpoint.

### Handling Missing Data

- Show "N/A" or "Unknown" for missing fields — never guess or infer
- 14 providers (21%) have no location data — this is expected
- 49 providers (73%) have no datacenter data — this is expected

### Standalone HTML Generation

`webapp/index_standalone.html` is gitignored — regenerate it when needed:

```python
import json, re
from pathlib import Path

repo = Path(__file__).parent  # adjust if running from elsewhere
data = json.loads((repo / "data/infrastructure_provider_map.json").read_text())
html = (repo / "webapp/index.html").read_text()

# Replace the fetch() call with embedded data
html = html.replace(
    '''async function loadData() {
            try {
                const response = await fetch('infrastructure_provider_map.json');
                infraData = await response.json();
                initializeUI();
            } catch (error) {
                console.error('Error loading data:', error);
                document.getElementById('providers-table-container').innerHTML =
                    '<div class="no-results">Error loading data. Make sure infrastructure_provider_map.json exists in the same directory.<br><br>If opening directly as a file, use index_standalone.html instead or run a web server.</div>';
            }
        }''',
    '''async function loadData() {
            // Data embedded in standalone version
            infraData = ''' + json.dumps(data) + ''';
            initializeUI();
        }'''
)
(repo / "webapp/index_standalone.html").write_text(html)
```

### Browser Caching Issues

When updating data and the browser shows old data:
1. Kill old server: `pkill -f "http.server"`
2. Start on a new port: `python3 -m http.server 7777`
3. Hard refresh: Cmd+Shift+R (Mac) / Ctrl+Shift+R
4. Best: open in a new incognito window

## Development Workflow

```bash
# 1. Edit source in src/llm_providers/ or webapp/

# 2. If you changed the data pipeline, refresh data
make refresh-all

# 3. Test locally
make serve
open "http://localhost:8000/webapp/index.html"

# 4. Deploy
make deploy   # full deploy
make ui       # webapp HTML only
```

## Data Files

| File | Location | In Git | Notes |
|------|----------|--------|-------|
| `infrastructure_provider_map.json` | `data/` | No | Generated by `make map-infra` |
| `openrouter_models.json` | `data/` | No | Fetched by `make fetch-openrouter` |
| `openrouter_providers.json` | `data/` | No | Fetched by `make fetch-openrouter` |
| `daily_report.json` | `data/` | No | Generated by `make generate-report` |
| `daily_report.md` | `data/` | No | Generated by `make generate-report` |
| `provider_research.json` | `data/seeds/` | **Yes** | Hand-curated company info |
| `voice_video_models.json` | `data/` | No | Fetched by `make fetch-voice` |
