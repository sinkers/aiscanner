#!/usr/bin/env python3
"""
Complete guide to filtering OpenRouter models by provider

Demonstrates all the options available for showing models served by a provider.
"""

import json
import requests
from collections import defaultdict

API_TOKEN = "REDACTED_OPENROUTER_TOKEN_1"
BASE_URL = "https://openrouter.ai/api/v1"

def load_data():
    with open('openrouter_models.json') as f:
        return json.load(f)['data']

def option1_filter_by_model_creator(models, creator_slug):
    """
    OPTION 1: Filter by model creator (company that trained the model)
    Extract from model ID prefix
    """
    print("\n" + "="*80)
    print(f"OPTION 1: Filter by Model Creator '{creator_slug}'")
    print("="*80)
    print("Use this when you want: All models created/trained by a company\n")

    filtered = [m for m in models if m['id'].startswith(f"{creator_slug}/")]

    print(f"Found {len(filtered)} models created by '{creator_slug}':\n")
    for model in filtered[:5]:
        print(f"  {model['id']}")
        print(f"    {model['name']}")
        print(f"    Context: {model['context_length']:,} tokens")
        print()

    if len(filtered) > 5:
        print(f"  ... and {len(filtered) - 5} more\n")

    return filtered

def option2_filter_by_infrastructure_provider(models, infra_provider):
    """
    OPTION 2: Filter by infrastructure provider (company that hosts/serves the model)
    Check endpoints for each model
    """
    print("\n" + "="*80)
    print(f"OPTION 2: Filter by Infrastructure Provider '{infra_provider}'")
    print("="*80)
    print("Use this when you want: All models available through a specific hosting provider\n")
    print(f"Checking which models are served by {infra_provider}...")
    print("(This requires fetching endpoints for each model - checking first 50)\n")

    matching_models = []
    checked = 0

    for model in models[:50]:
        checked += 1
        endpoint_path = model.get('links', {}).get('details', '')
        if not endpoint_path:
            continue

        try:
            url = f"https://openrouter.ai{endpoint_path}"
            headers = {"Authorization": f"Bearer {API_TOKEN}"}
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                endpoints = data.get('data', {}).get('endpoints', [])

                for ep in endpoints:
                    if ep['provider_name'] == infra_provider:
                        matching_models.append({
                            'model': model,
                            'endpoint': ep
                        })
                        break
        except:
            pass

    print(f"Checked {checked} models, found {len(matching_models)} served by '{infra_provider}':\n")

    for item in matching_models[:5]:
        model = item['model']
        ep = item['endpoint']
        print(f"  {model['id']}")
        print(f"    Pricing: ${ep['pricing']['prompt']}/1M prompt, ${ep['pricing']['completion']}/1M completion")
        uptime = ep.get('uptime_last_1d')
        if uptime:
            print(f"    Uptime: {uptime:.1f}%")
        print()

    if len(matching_models) > 5:
        print(f"  ... and {len(matching_models) - 5} more\n")

    return matching_models

def option3_compare_providers_for_model(model_id):
    """
    OPTION 3: For a specific model, compare all infrastructure providers that serve it
    """
    print("\n" + "="*80)
    print(f"OPTION 3: Compare Infrastructure Providers for '{model_id}'")
    print("="*80)
    print("Use this when you want: The best provider for a specific model\n")

    # First find the model
    models = load_data()
    model = next((m for m in models if m['id'] == model_id), None)

    if not model:
        print(f"Model '{model_id}' not found")
        return None

    endpoint_path = model.get('links', {}).get('details', '')
    if not endpoint_path:
        print(f"No endpoints available for this model")
        return None

    try:
        url = f"https://openrouter.ai{endpoint_path}"
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Failed to fetch endpoints: {response.status_code}")
            return None

        data = response.json()
        endpoints = data.get('data', {}).get('endpoints', [])

        print(f"Model: {model['name']}")
        print(f"Available through {len(endpoints)} infrastructure provider(s):\n")

        for i, ep in enumerate(endpoints, 1):
            print(f"{i}. {ep['provider_name']}")
            print(f"   Tag: {ep['tag']}")
            print(f"   Pricing: ${ep['pricing']['prompt']}/1M prompt, ${ep['pricing']['completion']}/1M completion")
            uptime = ep.get('uptime_last_1d')
            if uptime:
                print(f"   Uptime (24h): {uptime:.1f}%")
            latency = ep.get('latency_last_30m', {})
            if latency and latency.get('p50'):
                print(f"   Latency p50: {latency['p50']}ms, p99: {latency.get('p99', 'N/A')}ms")
            print()

        return endpoints
    except Exception as e:
        print(f"Error: {e}")
        return None

def option4_list_all_infrastructure_providers():
    """
    OPTION 4: Get a complete list of all infrastructure providers
    """
    print("\n" + "="*80)
    print("OPTION 4: List All Infrastructure Providers")
    print("="*80)
    print("Use this when you want: See all available hosting providers\n")

    # Fetch providers API
    url = f"{BASE_URL}/providers"
    headers = {"Authorization": f"Bearer {API_TOKEN}"}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            providers = response.json().get('data', [])

            print(f"Found {len(providers)} infrastructure providers:\n")

            # Group by headquarters
            by_hq = defaultdict(list)
            for p in providers:
                hq = p.get('headquarters', 'Unknown')
                by_hq[hq].append(p)

            for hq in sorted(by_hq.keys()):
                print(f"\n{hq}:")
                for p in by_hq[hq]:
                    print(f"  - {p['name']} (slug: {p['slug']})")

            return providers
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    print("="*80)
    print("OPENROUTER: OPTIONS TO SHOW MODELS BY PROVIDER")
    print("="*80)

    models = load_data()

    # Demo each option
    option1_filter_by_model_creator(models, 'anthropic')
    option2_filter_by_infrastructure_provider(models, 'Amazon Bedrock')
    option3_compare_providers_for_model('meta-llama/llama-3.1-70b-instruct')
    option4_list_all_infrastructure_providers()

    # Final summary
    print("\n" + "="*80)
    print("SUMMARY: WHICH OPTION TO USE?")
    print("="*80)
    print("""
┌────────────────────────────────────────────────────────────────────────┐
│ YOUR GOAL                          │ USE THIS OPTION                   │
├────────────────────────────────────────────────────────────────────────┤
│ Get all Anthropic models           │ Option 1: Filter by model creator │
│                                    │ models.filter(startsWith('anthropic/'))│
├────────────────────────────────────────────────────────────────────────┤
│ Get models available via Azure     │ Option 2: Filter by infra provider│
│                                    │ Check endpoints for each model    │
├────────────────────────────────────────────────────────────────────────┤
│ Choose best provider for GPT-4     │ Option 3: Compare providers       │
│                                    │ Fetch model endpoints & compare   │
├────────────────────────────────────────────────────────────────────────┤
│ See all hosting providers          │ Option 4: List providers          │
│                                    │ GET /api/v1/providers             │
└────────────────────────────────────────────────────────────────────────┘

KEY CONCEPTS:

1. MODEL CREATOR (from model ID prefix)
   - The company/org that trained the model
   - Example: "anthropic" in "anthropic/claude-3.5-sonnet"
   - Simple to filter: just check model ID prefix

2. INFRASTRUCTURE PROVIDER (from endpoints API)
   - The company/service that hosts/serves the model
   - Example: OpenAI, Azure, AWS Bedrock, Google, etc.
   - More complex: requires fetching endpoints for each model
   - ONE MODEL can be served by MULTIPLE infrastructure providers
   - Each provider may have different pricing, latency, and uptime

3. WHY MULTIPLE INFRASTRUCTURE PROVIDERS?
   - OpenRouter aggregates models from multiple sources
   - Same model (e.g., Claude) available through Anthropic, AWS Bedrock, Google
   - You can choose based on: price, speed, reliability, or your existing cloud setup

RECOMMENDED WORKFLOW:

1. If you want models by creator:
   → Use Option 1 (simple prefix filter)

2. If you want models by infrastructure provider:
   → Use Option 2 (requires API calls but gives you exact results)

3. If you want to optimize for a specific model:
   → Use Option 3 (compare all providers for that model)

4. If you want to see what's available:
   → Use Option 4 (list all providers)
""")

if __name__ == "__main__":
    main()
