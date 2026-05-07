#!/usr/bin/env python3
"""
Map all infrastructure providers hosting models on OpenRouter

This script fetches detailed information about:
- Which infrastructure providers host which models
- Pricing for each provider/model combination
- Performance metrics (latency, throughput, uptime)
- Geographic location of providers
- Provider capabilities and features
"""

import requests
import json
import time
from collections import defaultdict
from datetime import datetime
import os

API_TOKEN = "REDACTED_OPENROUTER_TOKEN_1"
BASE_URL = "https://openrouter.ai/api/v1"

# Progress tracking
PROGRESS_FILE = "mapping_progress.json"
OUTPUT_FILE = "infrastructure_provider_map.json"

def load_progress():
    """Load progress from previous run"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {
        'last_model_index': 0,
        'endpoints_data': {},
        'failed_models': []
    }

def save_progress(progress):
    """Save progress to resume later"""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def fetch_model_endpoints(model_id):
    """Fetch endpoints for a specific model"""
    try:
        # Don't encode - API expects raw model ID in path
        url = f"{BASE_URL}/models/{model_id}/endpoints"
        headers = {"Authorization": f"Bearer {API_TOKEN}"}

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None  # Model doesn't have endpoints yet
        else:
            print(f"      Error {response.status_code}")
            return None
    except Exception as e:
        print(f"      Exception: {e}")
        return None

def fetch_all_endpoints(models, progress):
    """Fetch endpoints for all models with progress tracking"""
    start_index = progress['last_model_index']
    endpoints_data = progress['endpoints_data']
    failed_models = progress['failed_models']

    total = len(models)
    print(f"\nFetching endpoints for {total} models...")
    print(f"Starting from index {start_index}\n")

    for i in range(start_index, total):
        model = models[i]
        model_id = model['id']

        # Progress indicator
        pct = ((i + 1) / total) * 100
        print(f"[{i+1}/{total}] ({pct:.1f}%) {model_id}...", end='', flush=True)

        # Check if we already have this data
        if model_id in endpoints_data:
            print(" (cached)")
            continue

        # Fetch endpoints
        endpoint_data = fetch_model_endpoints(model_id)

        if endpoint_data:
            endpoints = endpoint_data.get('data', {}).get('endpoints', [])
            endpoints_data[model_id] = endpoint_data
            print(f" ✓ ({len(endpoints)} providers)")
        else:
            failed_models.append(model_id)
            print(" ✗")

        # Update progress every 10 models
        if (i + 1) % 10 == 0:
            progress['last_model_index'] = i + 1
            progress['endpoints_data'] = endpoints_data
            progress['failed_models'] = failed_models
            save_progress(progress)

        # Rate limiting - be nice to the API
        time.sleep(0.15)

    # Final save
    progress['last_model_index'] = total
    progress['endpoints_data'] = endpoints_data
    progress['failed_models'] = failed_models
    save_progress(progress)

    return endpoints_data, failed_models

def build_infrastructure_map(models_data, providers_data, endpoints_data):
    """Build comprehensive infrastructure provider map"""

    # Create provider lookup
    provider_lookup = {p['slug']: p for p in providers_data}

    # Infrastructure provider map
    infra_map = defaultdict(lambda: {
        'provider_info': {},
        'models': [],
        'total_models': 0,
        'tags': set(),
        'pricing_range': {'min_prompt': float('inf'), 'max_prompt': 0, 'min_completion': float('inf'), 'max_completion': 0},
        'performance_stats': {
            'avg_uptime': [],
            'avg_latency_p50': [],
            'avg_throughput_p50': []
        }
    })

    # Process each model's endpoints
    for model_id, endpoint_data in endpoints_data.items():
        endpoints = endpoint_data.get('data', {}).get('endpoints', [])

        # Find the model details
        model = next((m for m in models_data if m['id'] == model_id), None)
        if not model:
            continue

        for endpoint in endpoints:
            provider_name = endpoint['provider_name']
            tag = endpoint['tag']

            # Get provider info from providers API
            provider_slug = tag.split('/')[0] if '/' in tag else tag
            provider_info = provider_lookup.get(provider_slug, {})

            # Initialize provider if first time
            if not infra_map[provider_name]['provider_info']:
                infra_map[provider_name]['provider_info'] = {
                    'name': provider_name,
                    'slug': provider_slug,
                    'headquarters': provider_info.get('headquarters'),
                    'datacenters': provider_info.get('datacenters', []),
                    'privacy_policy': provider_info.get('privacy_policy_url'),
                    'terms_of_service': provider_info.get('terms_of_service_url'),
                    'status_page': provider_info.get('status_page_url')
                }

            # Add model info
            model_entry = {
                'model_id': model_id,
                'model_name': model['name'],
                'model_creator': model_id.split('/')[0] if '/' in model_id else 'unknown',
                'context_length': endpoint['context_length'],
                'max_completion_tokens': endpoint['max_completion_tokens'],
                'pricing': {
                    'prompt': float(endpoint['pricing']['prompt']),
                    'completion': float(endpoint['pricing']['completion']),
                    'discount': endpoint['pricing'].get('discount', 0)
                },
                'tag': tag,
                'quantization': endpoint.get('quantization', 'unknown'),
                'supported_parameters': endpoint.get('supported_parameters', []),
                'performance': {
                    'uptime_24h': endpoint.get('uptime_last_1d'),
                    'uptime_30m': endpoint.get('uptime_last_30m'),
                    'uptime_5m': endpoint.get('uptime_last_5m'),
                    'latency_30m': endpoint.get('latency_last_30m'),
                    'throughput_30m': endpoint.get('throughput_last_30m')
                },
                'supports_implicit_caching': endpoint.get('supports_implicit_caching', False),
                'status': endpoint.get('status', 0)
            }

            infra_map[provider_name]['models'].append(model_entry)
            infra_map[provider_name]['tags'].add(tag)

            # Update pricing range
            pricing = endpoint['pricing']
            pr = infra_map[provider_name]['pricing_range']
            pr['min_prompt'] = min(pr['min_prompt'], float(pricing['prompt']))
            pr['max_prompt'] = max(pr['max_prompt'], float(pricing['prompt']))
            pr['min_completion'] = min(pr['min_completion'], float(pricing['completion']))
            pr['max_completion'] = max(pr['max_completion'], float(pricing['completion']))

            # Update performance stats
            perf = infra_map[provider_name]['performance_stats']
            if endpoint.get('uptime_last_1d'):
                perf['avg_uptime'].append(endpoint['uptime_last_1d'])

            latency_30m = endpoint.get('latency_last_30m')
            if latency_30m and latency_30m.get('p50'):
                perf['avg_latency_p50'].append(latency_30m['p50'])

            throughput_30m = endpoint.get('throughput_last_30m')
            if throughput_30m and throughput_30m.get('p50'):
                perf['avg_throughput_p50'].append(throughput_30m['p50'])

    # Calculate totals and averages
    for provider_name, data in infra_map.items():
        data['total_models'] = len(data['models'])
        data['tags'] = list(data['tags'])

        # Calculate averages
        perf = data['performance_stats']
        if perf['avg_uptime']:
            perf['avg_uptime'] = sum(perf['avg_uptime']) / len(perf['avg_uptime'])
        else:
            perf['avg_uptime'] = None

        if perf['avg_latency_p50']:
            perf['avg_latency_p50'] = sum(perf['avg_latency_p50']) / len(perf['avg_latency_p50'])
        else:
            perf['avg_latency_p50'] = None

        if perf['avg_throughput_p50']:
            perf['avg_throughput_p50'] = sum(perf['avg_throughput_p50']) / len(perf['avg_throughput_p50'])
        else:
            perf['avg_throughput_p50'] = None

    return dict(infra_map)

def generate_summary_report(infra_map):
    """Generate human-readable summary report"""

    print("\n" + "="*80)
    print("INFRASTRUCTURE PROVIDER MAP SUMMARY")
    print("="*80)

    # Sort providers by model count
    sorted_providers = sorted(infra_map.items(), key=lambda x: x[1]['total_models'], reverse=True)

    print(f"\nTotal Infrastructure Providers: {len(sorted_providers)}")
    print(f"\n{'RANK':<6} {'PROVIDER':<25} {'MODELS':<8} {'HQ':<6} {'AVG UPTIME':<12} {'AVG LATENCY'}")
    print("-" * 80)

    for i, (provider_name, data) in enumerate(sorted_providers, 1):
        info = data['provider_info']
        perf = data['performance_stats']

        hq = info.get('headquarters') or 'N/A'
        uptime = f"{perf['avg_uptime']:.1f}%" if perf['avg_uptime'] else 'N/A'
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf['avg_latency_p50'] else 'N/A'

        print(f"{i:<6} {provider_name:<25} {data['total_models']:<8} {hq:<6} {uptime:<12} {latency}")

    # Geographic distribution
    print("\n" + "="*80)
    print("GEOGRAPHIC DISTRIBUTION")
    print("="*80)

    by_location = defaultdict(list)
    for provider_name, data in infra_map.items():
        hq = data['provider_info'].get('headquarters') or 'Unknown'
        by_location[hq].append(provider_name)

    for location in sorted(by_location.keys()):
        providers = by_location[location]
        print(f"\n{location}: {len(providers)} providers")
        for p in sorted(providers)[:5]:
            model_count = infra_map[p]['total_models']
            print(f"  - {p} ({model_count} models)")
        if len(providers) > 5:
            print(f"  ... and {len(providers) - 5} more")

    # Pricing analysis
    print("\n" + "="*80)
    print("PRICING ANALYSIS (Top 10 by model count)")
    print("="*80)
    print(f"\n{'PROVIDER':<25} {'MODELS':<8} {'PROMPT PRICE RANGE':<30} {'COMPLETION PRICE RANGE'}")
    print("-" * 90)

    for provider_name, data in sorted_providers[:10]:
        pr = data['pricing_range']
        prompt_range = f"${pr['min_prompt']:.6f} - ${pr['max_prompt']:.6f}"
        completion_range = f"${pr['min_completion']:.6f} - ${pr['max_completion']:.6f}"

        print(f"{provider_name:<25} {data['total_models']:<8} {prompt_range:<30} {completion_range}")

def main():
    print("="*80)
    print("INFRASTRUCTURE PROVIDER MAPPING")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load existing data
    print("\nLoading models and providers...")
    with open('openrouter_models.json') as f:
        models = json.load(f)['data']

    with open('openrouter_providers.json') as f:
        providers = json.load(f)['data']

    print(f"✓ Loaded {len(models)} models")
    print(f"✓ Loaded {len(providers)} providers")

    # Load or create progress
    progress = load_progress()

    if progress['last_model_index'] > 0:
        print(f"\n⚠️  Resuming from previous run (index {progress['last_model_index']})")
        print(f"   Already processed: {len(progress['endpoints_data'])} models")
        print(f"   Failed: {len(progress['failed_models'])} models")

    # Fetch all endpoints
    print("\n" + "="*80)
    endpoints_data, failed_models = fetch_all_endpoints(models, progress)

    print("\n" + "="*80)
    print(f"✓ Completed endpoint fetching")
    print(f"  Successfully fetched: {len(endpoints_data)} models")
    print(f"  Failed/No endpoints: {len(failed_models)} models")

    # Build infrastructure map
    print("\nBuilding infrastructure provider map...")
    infra_map = build_infrastructure_map(models, providers, endpoints_data)

    # Save detailed map
    output = {
        'generated_at': datetime.now().isoformat(),
        'total_models': len(models),
        'models_with_endpoints': len(endpoints_data),
        'total_providers': len(infra_map),
        'providers': infra_map,
        'failed_models': failed_models
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✓ Saved infrastructure map to: {OUTPUT_FILE}")

    # Generate summary report
    generate_summary_report(infra_map)

    print("\n" + "="*80)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # Cleanup progress file on successful completion
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("\n✓ Cleaned up progress file")

if __name__ == "__main__":
    main()
