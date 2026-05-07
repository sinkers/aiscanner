#!/usr/bin/env python3
"""
Fetch models and providers from OpenRouter API
"""

import requests
import json
from collections import defaultdict

API_TOKEN = "REDACTED_OPENROUTER_TOKEN_1"
BASE_URL = "https://openrouter.ai/api/v1"

def fetch_models():
    """Fetch all models from OpenRouter"""
    url = f"{BASE_URL}/models"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def fetch_providers():
    """Fetch all providers from OpenRouter"""
    url = f"{BASE_URL}/providers"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def analyze_models_by_provider(models_data):
    """Analyze how models are organized by provider"""
    models = models_data.get('data', [])

    # Group models by provider
    models_by_provider = defaultdict(list)

    for model in models:
        model_id = model.get('id', '')

        # Option 1: Extract provider from model ID (format: provider/model-name)
        if '/' in model_id:
            provider = model_id.split('/')[0]
            models_by_provider[provider].append(model)

    return models_by_provider

def main():
    print("Fetching models from OpenRouter...")
    models_data = fetch_models()

    print("\nFetching providers from OpenRouter...")
    providers_data = fetch_providers()

    # Save raw data
    with open('openrouter_models.json', 'w') as f:
        json.dump(models_data, f, indent=2)
    print("\n✓ Saved models to: openrouter_models.json")

    with open('openrouter_providers.json', 'w') as f:
        json.dump(providers_data, f, indent=2)
    print("✓ Saved providers to: openrouter_providers.json")

    # Analyze models
    models = models_data.get('data', [])
    print(f"\n📊 Total models found: {len(models)}")

    # Analyze providers
    providers = providers_data.get('data', [])
    print(f"📊 Total providers found: {len(providers)}")

    # Group models by provider
    models_by_provider = analyze_models_by_provider(models_data)

    print(f"\n📊 Unique providers from model IDs: {len(models_by_provider)}")
    print("\nTop 10 providers by model count:")
    sorted_providers = sorted(models_by_provider.items(), key=lambda x: len(x[1]), reverse=True)
    for provider, provider_models in sorted_providers[:10]:
        print(f"  {provider}: {len(provider_models)} models")

    # Show sample model structure
    if models:
        print("\n📝 Sample model structure:")
        sample = models[0]
        print(json.dumps({k: v for k, v in sample.items()}, indent=2))

    # Show sample provider structure
    if providers:
        print("\n📝 Sample provider structure:")
        sample_provider = providers[0]
        print(json.dumps({k: v for k, v in sample_provider.items()}, indent=2))

    # Save models grouped by provider
    models_by_provider_serializable = {
        provider: [model.get('id') for model in models_list]
        for provider, models_list in models_by_provider.items()
    }
    with open('models_by_provider.json', 'w') as f:
        json.dump(models_by_provider_serializable, f, indent=2)
    print("\n✓ Saved grouped models to: models_by_provider.json")

if __name__ == "__main__":
    main()
