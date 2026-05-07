#!/usr/bin/env python3
"""
Integrate research data into the infrastructure provider map
"""

import json
from datetime import datetime

def integrate_research():
    # Load existing infrastructure map
    with open('infrastructure_provider_map.json') as f:
        infra_data = json.load(f)

    # Load research data
    try:
        with open('provider_research.json') as f:
            research = json.load(f)
    except FileNotFoundError:
        print("❌ provider_research.json not found")
        print("   The research agent needs to complete first")
        return

    print("Integrating Research Data")
    print("="*80)
    print(f"Infrastructure providers: {len(infra_data['providers'])}")
    print(f"Research entries: {len(research)}")
    print()

    updated_count = 0
    added_fields = {
        'homepage': 0,
        'contact_email': 0,
        'support_url': 0,
        'headquarters_city': 0,
        'headquarters_verified': 0,
        'company_description': 0
    }

    # Integrate research into provider info
    for provider_name, provider_data in infra_data['providers'].items():
        if provider_name in research:
            research_data = research[provider_name]
            info = provider_data['provider_info']

            # Add homepage
            if research_data.get('homepage'):
                info['homepage'] = research_data['homepage']
                added_fields['homepage'] += 1

            # Add contact email
            if research_data.get('contact_email'):
                info['contact_email'] = research_data['contact_email']
                added_fields['contact_email'] += 1

            # Add support URL
            if research_data.get('support_url'):
                info['support_url'] = research_data['support_url']
                added_fields['support_url'] += 1

            # Add headquarters city
            if research_data.get('headquarters_city'):
                info['headquarters_city'] = research_data['headquarters_city']
                added_fields['headquarters_city'] += 1

            # Update headquarters country if researched
            if research_data.get('headquarters_country'):
                # Only update if we didn't have it before, or if it's verified
                if not info.get('headquarters') or research_data.get('headquarters_verified'):
                    info['headquarters'] = research_data['headquarters_country']
                    added_fields['headquarters_verified'] += 1

            # Add company description
            if research_data.get('company_description'):
                info['company_description'] = research_data['company_description']
                added_fields['company_description'] += 1

            updated_count += 1

    # Update metadata
    infra_data['last_enriched'] = datetime.now().isoformat()
    infra_data['research_source'] = 'Web search via Claude Code'

    # Save updated infrastructure map
    with open('infrastructure_provider_map.json', 'w') as f:
        json.dump(infra_data, f, indent=2)

    print(f"✅ Updated {updated_count} providers")
    print()
    print("Fields added:")
    for field, count in added_fields.items():
        print(f"  {field}: {count}")
    print()
    print("Updated: infrastructure_provider_map.json")

def preview_research():
    """Preview what we found"""
    try:
        with open('provider_research.json') as f:
            research = json.load(f)
    except FileNotFoundError:
        print("No research data yet")
        return

    print("\n" + "="*80)
    print("RESEARCH PREVIEW")
    print("="*80)

    for provider, data in list(research.items())[:5]:
        print(f"\n{provider}:")
        for key, value in data.items():
            if value:
                print(f"  {key}: {value}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        preview_research()
    else:
        integrate_research()
