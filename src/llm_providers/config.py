"""Central configuration: paths, API settings, environment variables."""

import os
from pathlib import Path

# Repository root (three levels up: src/llm_providers/config.py → repo root)
REPO_ROOT = Path(__file__).parent.parent.parent

DATA_DIR = REPO_ROOT / "data"
SEEDS_DIR = DATA_DIR / "seeds"
WEBAPP_DIR = REPO_ROOT / "webapp"

# OpenRouter API
OPENROUTER_API_TOKEN = os.environ.get(
    "OPENROUTER_API_TOKEN",
    "REDACTED_OPENROUTER_TOKEN_1",
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Data file paths
MODELS_FILE = DATA_DIR / "openrouter_models.json"
PROVIDERS_FILE = DATA_DIR / "openrouter_providers.json"
INFRA_MAP_FILE = DATA_DIR / "infrastructure_provider_map.json"
MODELS_BY_PROVIDER_FILE = DATA_DIR / "models_by_provider.json"
PROVIDER_RESEARCH_FILE = SEEDS_DIR / "provider_research.json"
DAILY_REPORT_JSON = DATA_DIR / "daily_report.json"
DAILY_REPORT_MD = DATA_DIR / "daily_report.md"
PROGRESS_FILE = DATA_DIR / "mapping_progress.json"
