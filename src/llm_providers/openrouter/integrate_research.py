"""Merge hand-curated provider research into the infrastructure map."""

import json
import sys
from datetime import datetime

from llm_providers import config


def integrate_research() -> None:
    infra_data = json.loads(config.INFRA_MAP_FILE.read_text())

    if not config.PROVIDER_RESEARCH_FILE.exists():
        print(f"❌ {config.PROVIDER_RESEARCH_FILE} not found")
        sys.exit(1)

    research = json.loads(config.PROVIDER_RESEARCH_FILE.read_text())

    print(f"Integrating Research Data\n{'='*80}")
    print(f"Infrastructure providers: {len(infra_data['providers'])}")
    print(f"Research entries: {len(research)}\n")

    added_fields: dict[str, int] = {
        "homepage": 0,
        "contact_email": 0,
        "support_url": 0,
        "headquarters_city": 0,
        "headquarters_verified": 0,
        "company_description": 0,
    }
    updated_count = 0

    for provider_name, provider_data in infra_data["providers"].items():
        if provider_name not in research:
            continue

        info = provider_data["provider_info"]
        rd = research[provider_name]

        for field in ("homepage", "contact_email", "support_url", "headquarters_city", "company_description"):
            if rd.get(field):
                info[field] = rd[field]
                added_fields[field] += 1

        if rd.get("headquarters_country"):
            if not info.get("headquarters") or rd.get("headquarters_verified"):
                info["headquarters"] = rd["headquarters_country"]
                added_fields["headquarters_verified"] += 1

        updated_count += 1

    infra_data["last_enriched"] = datetime.now().isoformat()
    infra_data["research_source"] = "Web search via Claude Code"

    config.INFRA_MAP_FILE.write_text(json.dumps(infra_data, indent=2))

    print(f"✅ Updated {updated_count} providers")
    print("\nFields added:")
    for field, count in added_fields.items():
        print(f"  {field}: {count}")
    print(f"\nUpdated: {config.INFRA_MAP_FILE}")


def preview_research() -> None:
    if not config.PROVIDER_RESEARCH_FILE.exists():
        print("No research data yet")
        return

    research = json.loads(config.PROVIDER_RESEARCH_FILE.read_text())
    print(f"\n{'='*80}\nRESEARCH PREVIEW\n{'='*80}")
    for provider, data in list(research.items())[:5]:
        print(f"\n{provider}:")
        for key, value in data.items():
            if value:
                print(f"  {key}: {value}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        preview_research()
    else:
        integrate_research()


if __name__ == "__main__":
    main()
