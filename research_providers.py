#!/usr/bin/env python3
"""
Research providers to find:
- Main company homepage
- Contact details
- Headquarters location (verify/fill in missing)
"""

import json
import time

# Template for manual research results
RESEARCH_TEMPLATE = {
    "homepage": "",
    "contact_email": "",
    "support_url": "",
    "headquarters_verified": "",
    "headquarters_city": "",
    "company_description": "",
    "founded_year": "",
    "last_updated": ""
}

def load_data():
    with open('infrastructure_provider_map.json') as f:
        return json.load(f)

def save_research_progress(research_data):
    with open('provider_research.json', 'w') as f:
        json.dump(research_data, f, indent=2)
    print(f"✅ Saved research data for {len(research_data)} providers")

def main():
    data = load_data()
    providers = data['providers']

    # Sort by model count (prioritize important ones)
    sorted_providers = sorted(providers.items(), key=lambda x: x[1]['total_models'], reverse=True)

    # Load existing research if any
    try:
        with open('provider_research.json') as f:
            research = json.load(f)
    except FileNotFoundError:
        research = {}

    print("Provider Research Script")
    print("="*80)
    print(f"Total providers: {len(providers)}")
    print(f"Already researched: {len(research)}")
    print(f"Remaining: {len(providers) - len(research)}")
    print()

    # Show what needs research
    print("Top 20 providers needing research:")
    print("-"*80)
    for i, (name, pdata) in enumerate(sorted_providers[:20], 1):
        status = "✓" if name in research else " "
        info = pdata['provider_info']
        hq = info.get('headquarters') or '???'
        print(f"[{status}] {i:2d}. {name:25s} ({pdata['total_models']:2d} models) | HQ: {hq}")

    print()
    print("Search queries to use for each provider:")
    print("-"*80)
    for i, (name, pdata) in enumerate(sorted_providers[:5], 1):
        slug = pdata['provider_info'].get('slug', '')
        print(f"\n{i}. {name} ({slug})")
        print(f"   Google: \"{name} AI platform official website\"")
        print(f"   Google: \"{name} {slug} company headquarters\"")
        print(f"   Google: \"{name} contact support email\"")

if __name__ == "__main__":
    main()
