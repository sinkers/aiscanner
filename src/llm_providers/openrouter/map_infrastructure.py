"""Map all infrastructure providers hosting models on OpenRouter.

Fetches the /endpoints API for every model, aggregates pricing, performance,
and location per infrastructure provider, then writes infrastructure_provider_map.json.
Supports resume-on-interrupt via a progress checkpoint file.
"""

import json
import time
from collections import defaultdict
from datetime import datetime

import requests

from llm_providers import config


def load_progress() -> dict:
    """Load checkpoint from a previous run, or return a fresh state."""
    if config.PROGRESS_FILE.exists():
        return json.loads(config.PROGRESS_FILE.read_text())
    return {"last_model_index": 0, "endpoints_data": {}, "failed_models": []}


def save_progress(progress: dict) -> None:
    config.PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def fetch_model_endpoints(model_id: str) -> dict | None:
    """Return raw endpoints payload for one model, or None on error/404."""
    try:
        url = f"{config.OPENROUTER_BASE_URL}/models/{model_id}/endpoints"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {config.OPENROUTER_API_TOKEN}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            print(f"      Error {response.status_code}")
    except Exception as exc:
        print(f"      Exception: {exc}")
    return None


def fetch_all_endpoints(models: list, progress: dict) -> tuple[dict, list]:
    """Fetch endpoints for all models, resuming from checkpoint."""
    start_index = progress["last_model_index"]
    endpoints_data: dict = progress["endpoints_data"]
    failed_models: list = progress["failed_models"]
    total = len(models)

    print(f"\nFetching endpoints for {total} models (starting from index {start_index})...\n")

    for i in range(start_index, total):
        model_id = models[i]["id"]
        pct = (i + 1) / total * 100
        print(f"[{i + 1}/{total}] ({pct:.1f}%) {model_id}...", end="", flush=True)

        if model_id in endpoints_data:
            print(" (cached)")
            continue

        data = fetch_model_endpoints(model_id)
        if data:
            endpoints = data.get("data", {}).get("endpoints", [])
            endpoints_data[model_id] = data
            print(f" ✓ ({len(endpoints)} providers)")
        else:
            failed_models.append(model_id)
            print(" ✗")

        if (i + 1) % 10 == 0:
            progress.update(
                last_model_index=i + 1,
                endpoints_data=endpoints_data,
                failed_models=failed_models,
            )
            save_progress(progress)

        time.sleep(0.15)

    progress.update(
        last_model_index=total,
        endpoints_data=endpoints_data,
        failed_models=failed_models,
    )
    save_progress(progress)
    return endpoints_data, failed_models


def build_infrastructure_map(
    models: list, providers: list, endpoints_data: dict
) -> dict:
    """Aggregate per-provider stats from per-model endpoint data."""
    provider_lookup = {p["slug"]: p for p in providers}

    infra_map: dict = defaultdict(lambda: {
        "provider_info": {},
        "models": [],
        "total_models": 0,
        "tags": set(),
        "pricing_range": {
            "min_prompt": float("inf"),
            "max_prompt": 0.0,
            "min_completion": float("inf"),
            "max_completion": 0.0,
        },
        "performance_stats": {
            "avg_uptime": [],
            "avg_latency_p50": [],
            "avg_throughput_p50": [],
        },
    })

    models_by_id = {m["id"]: m for m in models}

    for model_id, endpoint_data in endpoints_data.items():
        model = models_by_id.get(model_id)
        if not model:
            continue

        for endpoint in endpoint_data.get("data", {}).get("endpoints", []):
            provider_name = endpoint["provider_name"]
            tag = endpoint["tag"]
            provider_slug = tag.split("/")[0] if "/" in tag else tag
            provider_info_raw = provider_lookup.get(provider_slug, {})

            entry = infra_map[provider_name]

            if not entry["provider_info"]:
                entry["provider_info"] = {
                    "name": provider_name,
                    "slug": provider_slug,
                    "headquarters": provider_info_raw.get("headquarters"),
                    "datacenters": provider_info_raw.get("datacenters", []),
                    "privacy_policy": provider_info_raw.get("privacy_policy_url"),
                    "terms_of_service": provider_info_raw.get("terms_of_service_url"),
                    "status_page": provider_info_raw.get("status_page_url"),
                }

            entry["models"].append({
                "model_id": model_id,
                "model_name": model["name"],
                "model_creator": model_id.split("/")[0] if "/" in model_id else "unknown",
                "context_length": endpoint["context_length"],
                "max_completion_tokens": endpoint["max_completion_tokens"],
                "pricing": {
                    "prompt": float(endpoint["pricing"]["prompt"]),
                    "completion": float(endpoint["pricing"]["completion"]),
                    "discount": endpoint["pricing"].get("discount", 0),
                },
                "tag": tag,
                "quantization": endpoint.get("quantization", "unknown"),
                "supported_parameters": endpoint.get("supported_parameters", []),
                "performance": {
                    "uptime_24h": endpoint.get("uptime_last_1d"),
                    "uptime_30m": endpoint.get("uptime_last_30m"),
                    "uptime_5m": endpoint.get("uptime_last_5m"),
                    "latency_30m": endpoint.get("latency_last_30m"),
                    "throughput_30m": endpoint.get("throughput_last_30m"),
                },
                "supports_implicit_caching": endpoint.get("supports_implicit_caching", False),
                "status": endpoint.get("status", 0),
            })

            entry["tags"].add(tag)

            pr = entry["pricing_range"]
            prompt = float(endpoint["pricing"]["prompt"])
            completion = float(endpoint["pricing"]["completion"])
            pr["min_prompt"] = min(pr["min_prompt"], prompt)
            pr["max_prompt"] = max(pr["max_prompt"], prompt)
            pr["min_completion"] = min(pr["min_completion"], completion)
            pr["max_completion"] = max(pr["max_completion"], completion)

            perf = entry["performance_stats"]
            if endpoint.get("uptime_last_1d"):
                perf["avg_uptime"].append(endpoint["uptime_last_1d"])
            latency = endpoint.get("latency_last_30m")
            if latency and latency.get("p50"):
                perf["avg_latency_p50"].append(latency["p50"])
            throughput = endpoint.get("throughput_last_30m")
            if throughput and throughput.get("p50"):
                perf["avg_throughput_p50"].append(throughput["p50"])

    # Finalise aggregates
    for data in infra_map.values():
        data["total_models"] = len(data["models"])
        data["tags"] = list(data["tags"])
        perf = data["performance_stats"]
        for key in ("avg_uptime", "avg_latency_p50", "avg_throughput_p50"):
            vals = perf[key]
            perf[key] = sum(vals) / len(vals) if vals else None

    return dict(infra_map)


def print_summary(infra_map: dict) -> None:
    sorted_providers = sorted(
        infra_map.items(), key=lambda x: x[1]["total_models"], reverse=True
    )
    print(f"\n{'='*80}\nINFRASTRUCTURE PROVIDER MAP SUMMARY\n{'='*80}")
    print(f"\nTotal providers: {len(sorted_providers)}\n")
    print(f"{'RANK':<6} {'PROVIDER':<25} {'MODELS':<8} {'HQ':<6} {'AVG UPTIME':<12} {'AVG LATENCY'}")
    print("-" * 70)
    for i, (name, data) in enumerate(sorted_providers, 1):
        info = data["provider_info"]
        perf = data["performance_stats"]
        hq = info.get("headquarters") or "N/A"
        uptime = f"{perf['avg_uptime']:.1f}%" if perf["avg_uptime"] else "N/A"
        latency = f"{perf['avg_latency_p50']:.0f}ms" if perf["avg_latency_p50"] else "N/A"
        print(f"{i:<6} {name:<25} {data['total_models']:<8} {hq:<6} {uptime:<12} {latency}")


def main() -> None:
    print(f"{'='*80}\nINFRASTRUCTURE PROVIDER MAPPING\n{'='*80}")
    print(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}")

    models = json.loads(config.MODELS_FILE.read_text())["data"]
    providers = json.loads(config.PROVIDERS_FILE.read_text())["data"]
    print(f"✓ Loaded {len(models)} models, {len(providers)} providers")

    progress = load_progress()
    if progress["last_model_index"] > 0:
        print(f"\n⚠  Resuming from index {progress['last_model_index']}")

    endpoints_data, failed_models = fetch_all_endpoints(models, progress)
    print(f"\n✓ Fetched endpoints: {len(endpoints_data)} ok, {len(failed_models)} failed")

    print("\nBuilding infrastructure map...")
    infra_map = build_infrastructure_map(models, providers, endpoints_data)

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_models": len(models),
        "models_with_endpoints": len(endpoints_data),
        "total_providers": len(infra_map),
        "providers": infra_map,
        "failed_models": failed_models,
    }
    config.INFRA_MAP_FILE.write_text(json.dumps(output, indent=2))
    print(f"✓ Saved infrastructure map → {config.INFRA_MAP_FILE}")

    print_summary(infra_map)

    print(f"\n{'='*80}\nCompleted: {datetime.now():%Y-%m-%d %H:%M:%S}\n{'='*80}")

    if config.PROGRESS_FILE.exists():
        config.PROGRESS_FILE.unlink()
        print("✓ Cleaned up progress file")


if __name__ == "__main__":
    main()
