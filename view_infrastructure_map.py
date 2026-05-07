#!/usr/bin/env python3
"""
Interactive viewer for infrastructure provider map

Query and explore the infrastructure provider data:
- Search by provider name
- Filter by location
- Compare pricing
- View performance metrics
"""

import json
import sys
from collections import defaultdict

def load_map():
    """Load the infrastructure provider map"""
    try:
        with open('infrastructure_provider_map.json') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: infrastructure_provider_map.json not found")
        print("Run map_infrastructure_providers.py first")
        sys.exit(1)

def list_all_providers(data):
    """List all providers with summary stats"""
    providers = data['providers']
    sorted_providers = sorted(providers.items(), key=lambda x: x[1]['total_models'], reverse=True)

    print("\n" + "="*100)
    print("ALL INFRASTRUCTURE PROVIDERS")
    print("="*100)
    print(f"\nTotal: {len(providers)} providers hosting {data['models_with_endpoints']} models\n")
    print(f"{'#':<4} {'PROVIDER':<30} {'MODELS':<8} {'LOCATION':<10} {'UPTIME':<10} {'LATENCY':<10} {'DATACENTERS'}")
    print("-" * 100)

    for i, (name, pdata) in enumerate(sorted_providers, 1):
        info = pdata['provider_info']
        perf = pdata['performance_stats']

        hq = info.get('headquarters') or 'N/A'
        uptime = f"{perf['avg_uptime']:.1f}%" if perf['avg_uptime'] else 'N/A'
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf['avg_latency_p50'] else 'N/A'
        dcs = ', '.join(info.get('datacenters')) if info.get('datacenters') else 'N/A'

        print(f"{i:<4} {name:<30} {pdata['total_models']:<8} {hq:<10} {uptime:<10} {latency:<10} {dcs}")

def provider_details(data, provider_name):
    """Show detailed information for a specific provider"""
    providers = data['providers']

    # Find provider (case insensitive partial match)
    matches = [p for p in providers.keys() if provider_name.lower() in p.lower()]

    if not matches:
        print(f"No provider found matching '{provider_name}'")
        return

    if len(matches) > 1:
        print(f"Multiple matches found for '{provider_name}':")
        for m in matches:
            print(f"  - {m}")
        print("\nBe more specific or use exact name")
        return

    provider_name = matches[0]
    pdata = providers[provider_name]
    info = pdata['provider_info']
    perf = pdata['performance_stats']
    pr = pdata['pricing_range']

    print("\n" + "="*80)
    print(f"PROVIDER: {provider_name}")
    print("="*80)

    print("\n📍 LOCATION & INFO")
    print(f"  Headquarters: {info.get('headquarters') or 'N/A'}")
    dcs = info.get('datacenters')
    print(f"  Datacenters: {', '.join(dcs) if dcs else 'N/A'}")
    print(f"  Status Page: {info.get('status_page') or 'N/A'}")
    print(f"  Privacy Policy: {info.get('privacy_policy') or 'N/A'}")
    print(f"  Terms of Service: {info.get('terms_of_service') or 'N/A'}")

    print("\n📊 STATISTICS")
    print(f"  Total Models: {pdata['total_models']}")
    print(f"  Tags: {', '.join(pdata['tags'])}")

    print("\n💰 PRICING RANGE")
    print(f"  Prompt: ${pr['min_prompt']:.8f} - ${pr['max_prompt']:.8f} per 1M tokens")
    print(f"  Completion: ${pr['min_completion']:.8f} - ${pr['max_completion']:.8f} per 1M tokens")

    print("\n⚡ PERFORMANCE")
    uptime = f"{perf['avg_uptime']:.2f}%" if perf['avg_uptime'] else 'N/A'
    latency = f"{perf['avg_latency_p50']:.0f}ms" if perf['avg_latency_p50'] else 'N/A'
    throughput = f"{perf['avg_throughput_p50']:.1f} tok/s" if perf['avg_throughput_p50'] else 'N/A'

    print(f"  Average Uptime (24h): {uptime}")
    print(f"  Average Latency (p50): {latency}")
    print(f"  Average Throughput (p50): {throughput}")

    print(f"\n📦 MODELS ({pdata['total_models']})")

    # Group by model creator
    by_creator = defaultdict(list)
    for model in pdata['models']:
        creator = model['model_creator']
        by_creator[creator].append(model)

    for creator in sorted(by_creator.keys()):
        models = by_creator[creator]
        print(f"\n  {creator.upper()} ({len(models)} models):")

        # Show up to 5 models per creator
        for model in sorted(models, key=lambda m: m['pricing']['prompt'])[:5]:
            total_price = model['pricing']['prompt'] + model['pricing']['completion']
            print(f"    • {model['model_id']}")
            print(f"      ${model['pricing']['prompt']:.6f}/1M prompt + ${model['pricing']['completion']:.6f}/1M completion = ${total_price:.6f}/1M total")
            print(f"      Context: {model['context_length']:,} tokens | Uptime: {model['performance']['uptime_24h']:.1f}%" if model['performance']['uptime_24h'] else "N/A")

        if len(models) > 5:
            print(f"    ... and {len(models) - 5} more")

def compare_providers_for_model(data, model_id):
    """Compare all providers hosting a specific model"""
    providers = data['providers']

    # Find all providers hosting this model
    hosting = []
    for provider_name, pdata in providers.items():
        for model in pdata['models']:
            if model['model_id'] == model_id:
                hosting.append({
                    'provider': provider_name,
                    'model': model,
                    'location': pdata['provider_info'].get('headquarters', 'N/A')
                })

    if not hosting:
        print(f"\nNo providers found hosting '{model_id}'")
        print("\nAvailable models (showing first 20):")
        all_models = set()
        for pdata in providers.values():
            for model in pdata['models']:
                all_models.add(model['model_id'])
        for mid in sorted(list(all_models))[:20]:
            print(f"  - {mid}")
        return

    print("\n" + "="*100)
    print(f"PROVIDERS HOSTING: {model_id}")
    print("="*100)
    print(f"\nFound {len(hosting)} provider(s)\n")

    # Sort by total price
    hosting.sort(key=lambda x: x['model']['pricing']['prompt'] + x['model']['pricing']['completion'])

    print(f"{'RANK':<6} {'PROVIDER':<25} {'LOCATION':<10} {'PRICE/1M':<15} {'UPTIME':<10} {'LATENCY'}")
    print("-" * 100)

    for i, h in enumerate(hosting, 1):
        model = h['model']
        total_price = model['pricing']['prompt'] + model['pricing']['completion']
        uptime = f"{model['performance']['uptime_24h']:.1f}%" if model['performance']['uptime_24h'] else 'N/A'
        latency_30m = model['performance']['latency_30m']
        latency = f"{latency_30m['p50']:.0f}ms" if latency_30m and latency_30m.get('p50') else 'N/A'

        price_str = f"${total_price:.6f}"

        print(f"{i:<6} {h['provider']:<25} {h['location']:<10} {price_str:<15} {uptime:<10} {latency}")

    # Detailed breakdown
    print(f"\n{'PROVIDER':<25} {'PROMPT/1M':<15} {'COMPLETION/1M':<15} {'CONTEXT':<12} {'LATENCY (p50/p90/p99)'}")
    print("-" * 100)

    for h in hosting:
        model = h['model']
        prompt = f"${model['pricing']['prompt']:.6f}"
        completion = f"${model['pricing']['completion']:.6f}"
        context = f"{model['context_length']:,}"
        latency_30m = model['performance']['latency_30m']

        if latency_30m and latency_30m.get('p50'):
            latency_detail = f"{latency_30m['p50']:.0f} / {latency_30m.get('p90', 0):.0f} / {latency_30m.get('p99', 0):.0f} ms"
        else:
            latency_detail = 'N/A'

        print(f"{h['provider']:<25} {prompt:<15} {completion:<15} {context:<12} {latency_detail}")

def filter_by_location(data, location):
    """Filter providers by headquarters location"""
    providers = data['providers']

    matching = []
    for name, pdata in providers.items():
        hq = pdata['provider_info'].get('headquarters')
        if hq and location.upper() in hq.upper():
            matching.append((name, pdata))

    if not matching:
        print(f"\nNo providers found in '{location}'")
        print("\nAvailable locations:")
        locations = set()
        for pdata in providers.values():
            hq = pdata['provider_info'].get('headquarters')
            if hq:
                locations.add(hq)
        for loc in sorted(locations):
            count = sum(1 for p in providers.values() if p['provider_info'].get('headquarters') == loc)
            print(f"  {loc}: {count} providers")
        return

    matching.sort(key=lambda x: x[1]['total_models'], reverse=True)

    print("\n" + "="*80)
    print(f"PROVIDERS IN: {location.upper()}")
    print("="*80)
    print(f"\nFound {len(matching)} provider(s)\n")

    for name, pdata in matching:
        perf = pdata['performance_stats']
        uptime = f"{perf['avg_uptime']:.1f}%" if perf['avg_uptime'] else 'N/A'
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf['avg_latency_p50'] else 'N/A'

        print(f"{name}")
        print(f"  Models: {pdata['total_models']} | Uptime: {uptime} | Latency: {latency}")
        dcs = pdata['provider_info'].get('datacenters')
        print(f"  Datacenters: {', '.join(dcs) if dcs else 'N/A'}")
        print()

def cheapest_models(data, limit=20):
    """Find the cheapest models across all providers"""
    providers = data['providers']

    all_offerings = []
    for provider_name, pdata in providers.items():
        for model in pdata['models']:
            total_price = model['pricing']['prompt'] + model['pricing']['completion']
            all_offerings.append({
                'provider': provider_name,
                'model_id': model['model_id'],
                'model_name': model['model_name'],
                'total_price': total_price,
                'prompt_price': model['pricing']['prompt'],
                'completion_price': model['pricing']['completion'],
                'context': model['context_length']
            })

    # Sort by total price
    all_offerings.sort(key=lambda x: x['total_price'])

    print("\n" + "="*100)
    print(f"CHEAPEST MODELS (Top {limit})")
    print("="*100)
    print(f"\n{'RANK':<6} {'MODEL':<45} {'PROVIDER':<25} {'TOTAL/1M':<15}")
    print("-" * 100)

    for i, offer in enumerate(all_offerings[:limit], 1):
        print(f"{i:<6} {offer['model_id']:<45} {offer['provider']:<25} ${offer['total_price']:.8f}")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 view_infrastructure_map.py list                     # List all providers")
        print("  python3 view_infrastructure_map.py provider <name>          # Provider details")
        print("  python3 view_infrastructure_map.py model <model_id>         # Compare providers for model")
        print("  python3 view_infrastructure_map.py location <country>       # Filter by location")
        print("  python3 view_infrastructure_map.py cheapest [limit]         # Cheapest models")
        print("\nExamples:")
        print("  python3 view_infrastructure_map.py list")
        print("  python3 view_infrastructure_map.py provider 'DeepInfra'")
        print("  python3 view_infrastructure_map.py model 'meta-llama/llama-3.1-70b-instruct'")
        print("  python3 view_infrastructure_map.py location US")
        print("  python3 view_infrastructure_map.py cheapest 50")
        sys.exit(1)

    data = load_map()

    command = sys.argv[1].lower()

    if command == 'list':
        list_all_providers(data)
    elif command == 'provider' and len(sys.argv) > 2:
        provider_details(data, sys.argv[2])
    elif command == 'model' and len(sys.argv) > 2:
        compare_providers_for_model(data, sys.argv[2])
    elif command == 'location' and len(sys.argv) > 2:
        filter_by_location(data, sys.argv[2])
    elif command == 'cheapest':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        cheapest_models(data, limit)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
