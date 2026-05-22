"""Fetch models and providers from the OpenRouter API."""

import json
from collections import defaultdict

import requests

from llm_providers import config


def fetch_models() -> dict:
    """Fetch all models from OpenRouter."""
    url = f"{config.OPENROUTER_BASE_URL}/models"
    response = requests.get(url, headers={"Authorization": f"Bearer {config.OPENROUTER_API_TOKEN}"})
    response.raise_for_status()
    return response.json()


def fetch_providers() -> dict:
    """Fetch all infrastructure providers from OpenRouter."""
    url = f"{config.OPENROUTER_BASE_URL}/providers"
    response = requests.get(url, headers={"Authorization": f"Bearer {config.OPENROUTER_API_TOKEN}"})
    response.raise_for_status()
    return response.json()


def group_models_by_creator(models_data: dict) -> dict[str, list]:
    """Group models by their creator slug (first segment of model ID)."""
    by_creator: dict[str, list] = defaultdict(list)
    for model in models_data.get("data", []):
        model_id = model.get("id", "")
        if "/" in model_id:
            by_creator[model_id.split("/")[0]].append(model)
    return dict(by_creator)


def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching models from OpenRouter...")
    models_data = fetch_models()
    config.MODELS_FILE.write_text(json.dumps(models_data, indent=2))
    print(f"✓ Saved {len(models_data.get('data', []))} models → {config.MODELS_FILE}")

    print("\nFetching providers from OpenRouter...")
    providers_data = fetch_providers()
    config.PROVIDERS_FILE.write_text(json.dumps(providers_data, indent=2))
    print(f"✓ Saved {len(providers_data.get('data', []))} providers → {config.PROVIDERS_FILE}")

    by_creator = group_models_by_creator(models_data)
    models_by_creator_ids = {k: [m.get("id") for m in v] for k, v in by_creator.items()}
    config.MODELS_BY_PROVIDER_FILE.write_text(json.dumps(models_by_creator_ids, indent=2))
    print(f"✓ Saved grouped models → {config.MODELS_BY_PROVIDER_FILE}")

    print(f"\nTop 10 model creators by count:")
    for creator, models in sorted(by_creator.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        print(f"  {creator}: {len(models)} models")


if __name__ == "__main__":
    main()
