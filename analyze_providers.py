#!/usr/bin/env python3
"""
Comprehensive analysis of OpenRouter models and providers
Shows the difference between:
1. Model provider (from model ID) - the company that created the model
2. Infrastructure providers (from endpoints) - the companies that serve/host the model
"""

import requests
import json
from collections import defaultdict
import time

API_TOKEN = "REDACTED_OPENROUTER_TOKEN_1"
BASE_URL = "https://openrouter.ai/api/v1"

def fetch_model_endpoints(model_id):
    """Fetch endpoints for a specific model"""
    # URL encode the model_id
    encoded_id = model_id.replace('/', '%2F').replace(':', '%3A')
    url = f"{BASE_URL}/models/{encoded_id}/endpoints"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching endpoints for {model_id}: {e}")
        return None

def analyze_all_endpoints(models, limit=None):
    """
    Fetch endpoints for all models (or a limited sample)
    This takes a while, so we'll limit it by default
    """
    print(f"\nFetching endpoints for models (limit={limit or 'all'})...")

    endpoints_data = {}
    models_to_check = models[:limit] if limit else models

    for i, model in enumerate(models_to_check, 1):
        model_id = model['id']
        print(f"  [{i}/{len(models_to_check)}] {model_id}...", end='', flush=True)

        endpoints = fetch_model_endpoints(model_id)
        if endpoints:
            endpoints_data[model_id] = endpoints
            provider_count = len(endpoints.get('data', {}).get('endpoints', []))
            print(f" ✓ ({provider_count} providers)")
        else:
            print(" ✗ (failed)")

        # Rate limiting
        if i < len(models_to_check):
            time.sleep(0.1)

    return endpoints_data

def main():
    # Load previously fetched data
    print("Loading models and providers data...")
    with open('openrouter_models.json') as f:
        models = json.load(f)['data']

    with open('openrouter_providers.json') as f:
        providers = json.load(f)['data']

    print(f"Loaded {len(models)} models and {len(providers)} providers")

    # Fetch sample endpoints (let's check 20 models from different model providers)
    sample_models = []
    model_providers_seen = set()

    for model in models:
        if '/' in model['id']:
            model_provider = model['id'].split('/')[0]
            if model_provider not in model_providers_seen:
                sample_models.append(model)
                model_providers_seen.add(model_provider)
                if len(sample_models) >= 20:
                    break

    # Fetch endpoints for sample
    endpoints_data = analyze_all_endpoints(sample_models, limit=20)

    # Save raw endpoints data
    with open('sample_endpoints.json', 'w') as f:
        json.dump(endpoints_data, f, indent=2)
    print(f"\n✓ Saved endpoints data to: sample_endpoints.json")

    # Analyze the data
    print("\n" + "="*80)
    print("ANALYSIS: TWO TYPES OF PROVIDERS")
    print("="*80)

    print("""
There are TWO different concepts of "provider" in OpenRouter:

1. MODEL PROVIDER (from model ID):
   - The company/organization that created/trained the model
   - Example: "anthropic" in "anthropic/claude-3.5-sonnet"
   - This is in the model ID before the slash

2. INFRASTRUCTURE PROVIDER (from endpoints):
   - The company/service that hosts/serves the model
   - Example: A model might be served by OpenAI, Azure, AWS Bedrock, etc.
   - Found in the "endpoints" API for each model
   - One model can have MULTIPLE infrastructure providers
""")

    # Show examples
    print("\n" + "="*80)
    print("EXAMPLES OF MULTI-PROVIDER MODELS")
    print("="*80)

    for model_id, endpoint_data in list(endpoints_data.items())[:10]:
        endpoints = endpoint_data.get('data', {}).get('endpoints', [])
        if len(endpoints) > 1:
            model_provider = model_id.split('/')[0] if '/' in model_id else 'unknown'
            infra_providers = [ep['provider_name'] for ep in endpoints]

            print(f"\nModel: {model_id}")
            print(f"  Model Provider: {model_provider}")
            print(f"  Infrastructure Providers: {', '.join(infra_providers)}")

            # Show pricing and performance differences
            for ep in endpoints:
                print(f"\n  {ep['provider_name']} endpoint:")
                print(f"    Pricing: ${ep['pricing']['prompt']}/1M prompt, ${ep['pricing']['completion']}/1M completion")
                print(f"    Uptime (24h): {ep['uptime_last_1d']:.2f}%")
                if ep['latency_last_30m']:
                    print(f"    Latency p50: {ep['latency_last_30m']['p50']}ms")

    # Create infrastructure provider index
    print("\n" + "="*80)
    print("INFRASTRUCTURE PROVIDER INDEX")
    print("="*80)

    infra_provider_models = defaultdict(set)

    for model_id, endpoint_data in endpoints_data.items():
        endpoints = endpoint_data.get('data', {}).get('endpoints', [])
        for ep in endpoints:
            provider_name = ep['provider_name']
            infra_provider_models[provider_name].add(model_id)

    print("\nInfrastructure providers found (in sample):")
    for provider in sorted(infra_provider_models.keys()):
        model_count = len(infra_provider_models[provider])
        print(f"  {provider}: {model_count} models")

    # Save infrastructure provider mapping
    infra_mapping = {
        provider: list(models)
        for provider, models in infra_provider_models.items()
    }
    with open('infra_provider_mapping.json', 'w') as f:
        json.dump(infra_mapping, f, indent=2)
    print("\n✓ Saved infrastructure provider mapping to: infra_provider_mapping.json")

    # Summary
    print("\n" + "="*80)
    print("OPTIONS TO FILTER MODELS BY PROVIDER")
    print("="*80)
    print("""
OPTION A: Filter by Model Provider (model creator)
----------
Use the model ID prefix to filter by the company that created the model.

Example: Get all Anthropic models
  models.filter(m => m.id.startsWith('anthropic/'))

Result: anthropic/claude-3.5-sonnet, anthropic/claude-opus-4, etc.

OPTION B: Filter by Infrastructure Provider (hosting provider)
----------
Check the /models/{model_id}/endpoints API to see which infrastructure
providers serve each model.

Steps:
  1. Fetch all models
  2. For each model, fetch /models/{model_id}/endpoints
  3. Filter endpoints by provider_name field

Example: Get all models served by Azure
  For each model:
    - Fetch endpoints
    - Check if any endpoint has provider_name == "Azure"

Result: Could include openai/gpt-4, anthropic/claude-3.5-sonnet, etc.
        (any model that Azure hosts)

WHICH OPTION TO USE?
--------------------
- Use Option A if you want models by their creator (e.g., "all Anthropic models")
- Use Option B if you want models by infrastructure provider (e.g., "all models I can access through Azure")

Option B is more complex but gives you:
  - Performance metrics per provider
  - Pricing differences per provider
  - Ability to choose fastest/cheapest endpoint for a model
""")

if __name__ == "__main__":
    main()
