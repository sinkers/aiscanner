#!/usr/bin/env python3
"""
Show different options for filtering OpenRouter models by provider
"""

import json
from collections import defaultdict

def load_data():
    """Load the fetched data"""
    with open('openrouter_models.json') as f:
        models = json.load(f)['data']

    with open('openrouter_providers.json') as f:
        providers = json.load(f)['data']

    return models, providers

def option1_parse_model_id(models):
    """
    Option 1: Parse provider from model ID
    Model IDs follow format: provider/model-name or provider/model-name:variant
    """
    print("\n" + "="*80)
    print("OPTION 1: Parse provider from model ID")
    print("="*80)

    models_by_provider = defaultdict(list)

    for model in models:
        model_id = model['id']
        if '/' in model_id:
            provider = model_id.split('/')[0]
            models_by_provider[provider].append(model)

    print(f"\nFound {len(models_by_provider)} unique providers")
    print("\nProviders and model counts:")
    for provider in sorted(models_by_provider.keys()):
        print(f"  {provider}: {len(models_by_provider[provider])} models")

    return models_by_provider

def option2_keyword_search(models, keyword):
    """
    Option 2: Search by keyword in model ID or name
    """
    print("\n" + "="*80)
    print(f"OPTION 2: Keyword search for '{keyword}'")
    print("="*80)

    matching_models = []
    keyword_lower = keyword.lower()

    for model in models:
        if keyword_lower in model['id'].lower() or keyword_lower in model['name'].lower():
            matching_models.append(model)

    print(f"\nFound {len(matching_models)} models matching '{keyword}':")
    for model in matching_models[:10]:  # Show first 10
        print(f"  - {model['id']}: {model['name']}")

    if len(matching_models) > 10:
        print(f"  ... and {len(matching_models) - 10} more")

    return matching_models

def option3_filter_by_provider_list(models, provider_slug):
    """
    Option 3: Filter by exact provider slug from model ID
    """
    print("\n" + "="*80)
    print(f"OPTION 3: Filter by exact provider slug '{provider_slug}'")
    print("="*80)

    provider_models = [
        model for model in models
        if model['id'].startswith(f"{provider_slug}/")
    ]

    print(f"\nFound {len(provider_models)} models for provider '{provider_slug}':")
    for model in provider_models:
        pricing = model['pricing']
        price_str = f"${pricing['prompt']}/1M prompt, ${pricing['completion']}/1M completion"
        if pricing['prompt'] == '0' and pricing['completion'] == '0':
            price_str = "FREE"
        print(f"  - {model['id']}")
        print(f"    Name: {model['name']}")
        print(f"    Context: {model['context_length']:,} tokens")
        print(f"    Pricing: {price_str}")
        print()

    return provider_models

def option4_provider_cross_reference(models, providers):
    """
    Option 4: Cross-reference with providers API
    """
    print("\n" + "="*80)
    print("OPTION 4: Cross-reference model providers with provider list")
    print("="*80)

    # Get provider slugs from providers API
    provider_slugs = {p['slug'] for p in providers}

    # Get provider slugs from model IDs
    model_provider_slugs = set()
    for model in models:
        if '/' in model['id']:
            provider = model['id'].split('/')[0]
            model_provider_slugs.add(provider)

    print(f"\nProviders in providers API: {len(provider_slugs)}")
    print(f"Provider slugs from model IDs: {len(model_provider_slugs)}")

    # Find matches and mismatches
    matched = model_provider_slugs & provider_slugs
    only_in_models = model_provider_slugs - provider_slugs
    only_in_providers = provider_slugs - model_provider_slugs

    print(f"\nMatched providers: {len(matched)}")
    print(f"Provider slugs only in model IDs: {len(only_in_models)}")
    if only_in_models:
        print(f"  Examples: {', '.join(sorted(list(only_in_models))[:5])}")

    print(f"\nProvider slugs only in providers API: {len(only_in_providers)}")
    if only_in_providers:
        print(f"  Examples: {', '.join(sorted(list(only_in_providers))[:5])}")

    # Create a mapping of provider slug to provider info
    provider_map = {p['slug']: p for p in providers}

    return matched, provider_map

def generate_provider_summary(models, providers):
    """
    Generate a comprehensive summary
    """
    print("\n" + "="*80)
    print("COMPREHENSIVE PROVIDER SUMMARY")
    print("="*80)

    provider_map = {p['slug']: p for p in providers}
    models_by_provider = defaultdict(list)

    for model in models:
        if '/' in model['id']:
            provider = model['id'].split('/')[0]
            models_by_provider[provider].append(model)

    # Sort providers by model count
    sorted_providers = sorted(models_by_provider.items(), key=lambda x: len(x[1]), reverse=True)

    print(f"\nTotal providers with models: {len(sorted_providers)}")
    print("\nTop providers by model count:\n")

    for i, (provider, provider_models) in enumerate(sorted_providers[:15], 1):
        provider_info = provider_map.get(provider, {})
        name = provider_info.get('name', provider)
        hq = provider_info.get('headquarters', 'Unknown')

        # Count free models
        free_count = sum(1 for m in provider_models if m['pricing']['prompt'] == '0' and m['pricing']['completion'] == '0')

        print(f"{i:2d}. {name} ({provider})")
        print(f"    Models: {len(provider_models)} | Free: {free_count} | HQ: {hq}")

    # Save detailed summary
    summary = []
    for provider, provider_models in sorted_providers:
        provider_info = provider_map.get(provider, {})
        summary.append({
            'slug': provider,
            'name': provider_info.get('name', provider),
            'headquarters': provider_info.get('headquarters'),
            'model_count': len(provider_models),
            'models': [
                {
                    'id': m['id'],
                    'name': m['name'],
                    'context_length': m['context_length'],
                    'pricing': m['pricing']
                }
                for m in provider_models
            ]
        })

    with open('provider_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print("\n✓ Saved detailed summary to: provider_summary.json")

def main():
    print("Loading data...")
    models, providers = load_data()

    # Show all options
    option1_parse_model_id(models)
    option2_keyword_search(models, "anthropic")
    option3_filter_by_provider_list(models, "anthropic")
    option4_provider_cross_reference(models, providers)
    generate_provider_summary(models, providers)

    print("\n" + "="*80)
    print("SUMMARY: OPTIONS TO SHOW MODELS BY PROVIDER")
    print("="*80)
    print("""
1. Parse model ID: Extract provider from model ID format (provider/model-name)
   - Most reliable method
   - Provider slug is always the part before the first '/'

2. Keyword search: Search for provider name in model ID or model name
   - Good for fuzzy matching
   - May return false positives

3. Exact provider filter: Filter by exact provider slug
   - Best for programmatic filtering
   - Example: models.filter(m => m.id.startsWith('anthropic/'))

4. Cross-reference with providers API: Match model providers with provider details
   - Provides additional context (name, HQ, datacenter locations)
   - Some providers in models may not be in providers API (and vice versa)

RECOMMENDED APPROACH:
- Use Option 1 or 3 for reliable filtering
- Model ID format is: <provider-slug>/<model-name>[:<variant>]
- Provider slug in model ID is the authoritative provider identifier
""")

if __name__ == "__main__":
    main()
