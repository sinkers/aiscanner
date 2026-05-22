"""Interactive CLI to query and explore the infrastructure provider map."""

import json
import sys
from collections import defaultdict

from llm_providers import config


def load_map() -> dict:
    if not config.INFRA_MAP_FILE.exists():
        print(f"Error: {config.INFRA_MAP_FILE} not found")
        print("Run 'make map-infra' first")
        sys.exit(1)
    return json.loads(config.INFRA_MAP_FILE.read_text())


def list_all_providers(data: dict) -> None:
    providers = data["providers"]
    sorted_providers = sorted(providers.items(), key=lambda x: x[1]["total_models"], reverse=True)

    print(f"\n{'='*100}\nALL INFRASTRUCTURE PROVIDERS\n{'='*100}")
    print(f"\nTotal: {len(providers)} providers\n")
    print(f"{'#':<4} {'PROVIDER':<30} {'MODELS':<8} {'LOCATION':<10} {'UPTIME':<10} {'LATENCY':<10} {'DATACENTERS'}")
    print("-" * 100)

    for i, (name, pd) in enumerate(sorted_providers, 1):
        info = pd["provider_info"]
        perf = pd["performance_stats"]
        hq = info.get("headquarters") or "N/A"
        uptime = f"{perf['avg_uptime']:.1f}%" if perf["avg_uptime"] else "N/A"
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf["avg_latency_p50"] else "N/A"
        dcs = ", ".join(info.get("datacenters") or []) or "N/A"
        print(f"{i:<4} {name:<30} {pd['total_models']:<8} {hq:<10} {uptime:<10} {latency:<10} {dcs}")


def provider_details(data: dict, provider_name: str) -> None:
    providers = data["providers"]
    matches = [p for p in providers if provider_name.lower() in p.lower()]

    if not matches:
        print(f"No provider matching '{provider_name}'")
        return
    if len(matches) > 1:
        print(f"Multiple matches: {', '.join(matches)}")
        return

    name = matches[0]
    pd = providers[name]
    info = pd["provider_info"]
    perf = pd["performance_stats"]
    pr = pd["pricing_range"]

    print(f"\n{'='*80}\nPROVIDER: {name}\n{'='*80}")
    print(f"\n  HQ: {info.get('headquarters') or 'N/A'}")
    dcs = info.get("datacenters")
    print(f"  Datacenters: {', '.join(dcs) if dcs else 'N/A'}")
    for label, key in (("Status Page", "status_page"), ("Privacy", "privacy_policy"), ("Terms", "terms_of_service")):
        print(f"  {label}: {info.get(key) or 'N/A'}")

    print(f"\n  Total Models: {pd['total_models']}")
    print(f"  Tags: {', '.join(pd['tags'])}")

    print(f"\n  Prompt price range:     ${pr['min_prompt']:.8f} – ${pr['max_prompt']:.8f}")
    print(f"  Completion price range: ${pr['min_completion']:.8f} – ${pr['max_completion']:.8f}")

    uptime = f"{perf['avg_uptime']:.2f}%" if perf["avg_uptime"] else "N/A"
    latency = f"{perf['avg_latency_p50']:.0f}ms" if perf["avg_latency_p50"] else "N/A"
    throughput = f"{perf['avg_throughput_p50']:.1f} tok/s" if perf["avg_throughput_p50"] else "N/A"
    print(f"\n  Avg uptime (24h): {uptime}")
    print(f"  Avg latency (p50): {latency}")
    print(f"  Avg throughput (p50): {throughput}")

    print(f"\n  Models ({pd['total_models']}):")
    by_creator: dict[str, list] = defaultdict(list)
    for m in pd["models"]:
        by_creator[m["model_creator"]].append(m)

    for creator in sorted(by_creator):
        models = by_creator[creator]
        print(f"\n    {creator.upper()} ({len(models)} models):")
        for m in sorted(models, key=lambda x: x["pricing"]["prompt"])[:5]:
            total = m["pricing"]["prompt"] + m["pricing"]["completion"]
            uptime_m = m["performance"]["uptime_24h"]
            uptime_str = f"{uptime_m:.1f}%" if uptime_m else "N/A"
            print(f"      • {m['model_id']}")
            print(f"        ${m['pricing']['prompt']:.6f} prompt + ${m['pricing']['completion']:.6f} completion = ${total:.6f} | uptime: {uptime_str}")
        if len(models) > 5:
            print(f"      ... and {len(models) - 5} more")


def compare_providers_for_model(data: dict, model_id: str) -> None:
    hosting = [
        {"provider": name, "model": m, "location": pd["provider_info"].get("headquarters", "N/A")}
        for name, pd in data["providers"].items()
        for m in pd["models"]
        if m["model_id"] == model_id
    ]

    if not hosting:
        print(f"\nNo providers hosting '{model_id}'")
        return

    hosting.sort(key=lambda x: x["model"]["pricing"]["prompt"] + x["model"]["pricing"]["completion"])

    print(f"\n{'='*100}\nPROVIDERS HOSTING: {model_id}\n{'='*100}")
    print(f"\nFound {len(hosting)} provider(s)\n")
    print(f"{'RANK':<6} {'PROVIDER':<25} {'LOCATION':<10} {'PRICE/1M':<15} {'UPTIME':<10} {'LATENCY'}")
    print("-" * 100)

    for i, h in enumerate(hosting, 1):
        m = h["model"]
        total = m["pricing"]["prompt"] + m["pricing"]["completion"]
        uptime = f"{m['performance']['uptime_24h']:.1f}%" if m["performance"]["uptime_24h"] else "N/A"
        lp = m["performance"]["latency_30m"]
        latency = f"{lp['p50']:.0f}ms" if lp and lp.get("p50") else "N/A"
        print(f"{i:<6} {h['provider']:<25} {h['location']:<10} ${total:.6f}      {uptime:<10} {latency}")


def filter_by_location(data: dict, location: str) -> None:
    matching = [
        (name, pd) for name, pd in data["providers"].items()
        if location.upper() in (pd["provider_info"].get("headquarters") or "").upper()
    ]

    if not matching:
        print(f"\nNo providers in '{location}'. Available locations:")
        locs: dict[str, int] = defaultdict(int)
        for pd in data["providers"].values():
            hq = pd["provider_info"].get("headquarters")
            if hq:
                locs[hq] += 1
        for loc, cnt in sorted(locs.items()):
            print(f"  {loc}: {cnt} providers")
        return

    matching.sort(key=lambda x: x[1]["total_models"], reverse=True)
    print(f"\n{'='*80}\nPROVIDERS IN: {location.upper()}\n{'='*80}\nFound {len(matching)} providers\n")

    for name, pd in matching:
        perf = pd["performance_stats"]
        uptime = f"{perf['avg_uptime']:.1f}%" if perf["avg_uptime"] else "N/A"
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf["avg_latency_p50"] else "N/A"
        dcs = pd["provider_info"].get("datacenters")
        print(f"{name}")
        print(f"  Models: {pd['total_models']} | Uptime: {uptime} | Latency: {latency}")
        print(f"  Datacenters: {', '.join(dcs) if dcs else 'N/A'}\n")


def cheapest_models(data: dict, limit: int = 20) -> None:
    offerings = [
        {
            "provider": name,
            "model_id": m["model_id"],
            "total_price": m["pricing"]["prompt"] + m["pricing"]["completion"],
        }
        for name, pd in data["providers"].items()
        for m in pd["models"]
    ]
    offerings.sort(key=lambda x: x["total_price"])

    print(f"\n{'='*100}\nCHEAPEST MODELS (Top {limit})\n{'='*100}")
    print(f"\n{'RANK':<6} {'MODEL':<45} {'PROVIDER':<25} {'TOTAL/1M'}")
    print("-" * 100)
    for i, o in enumerate(offerings[:limit], 1):
        print(f"{i:<6} {o['model_id']:<45} {o['provider']:<25} ${o['total_price']:.8f}")


def main() -> None:
    usage = (
        "Usage:\n"
        "  python3 -m llm_providers.cli.view_map list\n"
        "  python3 -m llm_providers.cli.view_map provider <name>\n"
        "  python3 -m llm_providers.cli.view_map model <model_id>\n"
        "  python3 -m llm_providers.cli.view_map location <country>\n"
        "  python3 -m llm_providers.cli.view_map cheapest [limit]\n"
    )

    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)

    data = load_map()
    cmd = sys.argv[1].lower()

    if cmd == "list":
        list_all_providers(data)
    elif cmd == "provider" and len(sys.argv) > 2:
        provider_details(data, sys.argv[2])
    elif cmd == "model" and len(sys.argv) > 2:
        compare_providers_for_model(data, sys.argv[2])
    elif cmd == "location" and len(sys.argv) > 2:
        filter_by_location(data, sys.argv[2])
    elif cmd == "cheapest":
        cheapest_models(data, int(sys.argv[2]) if len(sys.argv) > 2 else 20)
    else:
        print(f"Unknown command: {cmd}\n{usage}")
        sys.exit(1)


if __name__ == "__main__":
    main()
