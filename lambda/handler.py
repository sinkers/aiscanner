"""
Daily data collector — OpenRouter LLM pricing + GPU rental pricing.

Writes to S3:
  snapshots/YYYY-MM-DD.json             OpenRouter raw archive
  rollups/latest.json                   LLM provider state (UI loads this)
  rollups/providers/{name}.json         per-provider LLM price history
  rollups/models/{model_id}.json        per-model cross-provider history
  rollups/benchmarks.json               Open LLM Leaderboard scores
  snapshots/gpu/YYYY-MM-DD.json         GPU pricing raw archive
  rollups/gpu/latest.json               GPU current state
  rollups/gpu/history/{gpu_name}.json   per-GPU daily price history

Environment variables (set by CDK):
  S3_BUCKET               target bucket
  OPENROUTER_API_TOKEN    bearer token for /endpoints API
  RUNPOD_API_KEY          RunPod GraphQL API key (optional)
  VAST_API_KEY            Vast.ai REST API key (optional)
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timezone
from collections import defaultdict

S3_BUCKET = os.environ["S3_BUCKET"]
API_TOKEN = os.environ["OPENROUTER_API_TOKEN"]
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
VAST_API_KEY = os.environ.get("VAST_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"

s3 = boto3.client("s3")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def http_get(url, token=None):
    headers = {"User-Agent": "dame-pricing-collector/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def http_post(url, body, headers=None):
    """POST JSON body; returns parsed response or None on error."""
    all_headers = {"User-Agent": "dame-pricing-collector/1.0", "Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=all_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error POSTing {url}: {e}")
        return None


def s3_get_json(key):
    try:
        resp = s3.get_object(Bucket=S3_BUCKET, Key=key)
        return json.loads(resp["Body"].read())
    except s3.exceptions.NoSuchKey:
        return None
    except Exception as e:
        print(f"S3 read error {key}: {e}")
        return None


def s3_put_json(key, data, cache_seconds=3600):
    body = json.dumps(data, separators=(",", ":"), default=str).encode()
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType="application/json",
        CacheControl=f"max-age={cache_seconds}",
    )


def safe_key(name):
    """Make a name safe for use as an S3 key segment and URL path component."""
    return re.sub(r"[/\s]", "_", name)


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# Build infrastructure map (mirrors map_infrastructure_providers.py logic)
# ---------------------------------------------------------------------------

def build_infrastructure_map(models, provider_lookup, endpoints_data):
    infra_map = {}

    for model_id, endpoint_data in endpoints_data.items():
        endpoints = endpoint_data.get("data", {}).get("endpoints", [])
        model = next((m for m in models if m["id"] == model_id), None)
        if not model:
            continue

        for endpoint in endpoints:
            provider_name = endpoint["provider_name"]
            tag = endpoint.get("tag", "")
            provider_slug = tag.split("/")[0] if "/" in tag else tag
            provider_info = provider_lookup.get(provider_slug, {})

            if provider_name not in infra_map:
                infra_map[provider_name] = {
                    "provider_info": {
                        "name": provider_name,
                        "slug": provider_slug,
                        "headquarters": provider_info.get("headquarters"),
                        "datacenters": provider_info.get("datacenters", []),
                        "privacy_policy": provider_info.get("privacy_policy_url"),
                        "terms_of_service": provider_info.get("terms_of_service_url"),
                        "status_page": provider_info.get("status_page_url"),
                    },
                    "models": [],
                    "total_models": 0,
                    "tags": set(),
                    "_min_prompt": None,
                    "_max_prompt": 0.0,
                    "_min_completion": None,
                    "_max_completion": 0.0,
                    "_uptime_vals": [],
                    "_latency_vals": [],
                    "_throughput_vals": [],
                }

            p = infra_map[provider_name]
            prompt_price = float(endpoint["pricing"]["prompt"])
            completion_price = float(endpoint["pricing"]["completion"])

            p["_min_prompt"] = prompt_price if p["_min_prompt"] is None else min(p["_min_prompt"], prompt_price)
            p["_max_prompt"] = max(p["_max_prompt"], prompt_price)
            p["_min_completion"] = completion_price if p["_min_completion"] is None else min(p["_min_completion"], completion_price)
            p["_max_completion"] = max(p["_max_completion"], completion_price)

            latency_30m = endpoint.get("latency_last_30m")
            throughput_30m = endpoint.get("throughput_last_30m")

            if endpoint.get("uptime_last_1d") is not None:
                p["_uptime_vals"].append(endpoint["uptime_last_1d"])
            if latency_30m and latency_30m.get("p50"):
                p["_latency_vals"].append(latency_30m["p50"])
            if throughput_30m and throughput_30m.get("p50"):
                p["_throughput_vals"].append(throughput_30m["p50"])

            p["models"].append({
                "model_id": model_id,
                "model_name": model["name"],
                "model_creator": model_id.split("/")[0] if "/" in model_id else "unknown",
                "context_length": endpoint.get("context_length", 0),
                "max_completion_tokens": endpoint.get("max_completion_tokens", 0),
                "pricing": {
                    "prompt": prompt_price,
                    "completion": completion_price,
                    "discount": endpoint["pricing"].get("discount", 0),
                },
                "tag": tag,
                "quantization": endpoint.get("quantization", "unknown"),
                "supported_parameters": endpoint.get("supported_parameters", []),
                "performance": {
                    "uptime_24h": endpoint.get("uptime_last_1d"),
                    "uptime_30m": endpoint.get("uptime_last_30m"),
                    "uptime_5m": endpoint.get("uptime_last_5m"),
                    "latency_30m": latency_30m,
                    "throughput_30m": throughput_30m,
                },
                "supports_implicit_caching": endpoint.get("supports_implicit_caching", False),
                "status": endpoint.get("status", 0),
            })
            p["tags"].add(tag)

    # Finalise aggregates, remove temp accumulator fields
    for p in infra_map.values():
        p["total_models"] = len(p["models"])
        p["tags"] = sorted(p["tags"])
        p["pricing_range"] = {
            "min_prompt": p.pop("_min_prompt") or 0.0,
            "max_prompt": p.pop("_max_prompt"),
            "min_completion": p.pop("_min_completion") or 0.0,
            "max_completion": p.pop("_max_completion"),
        }
        p["performance_stats"] = {
            "avg_uptime": mean(p.pop("_uptime_vals")),
            "avg_latency_p50": mean(p.pop("_latency_vals")),
            "avg_throughput_p50": mean(p.pop("_throughput_vals")),
        }

    return infra_map


# ---------------------------------------------------------------------------
# Rollup updater
# ---------------------------------------------------------------------------

def update_rollups(infra_map, today):
    """Append today's data point to each provider and model rollup file."""
    model_day = defaultdict(list)

    for provider_name, provider_data in infra_map.items():
        models = provider_data["models"]

        # Build today's aggregate for this provider
        latency_vals = [
            m["performance"]["latency_30m"]["p50"]
            for m in models
            if m["performance"].get("latency_30m") and m["performance"]["latency_30m"].get("p50")
        ]
        new_point = {
            "date": today,
            "avg_prompt_price": mean(m["pricing"]["prompt"] for m in models),
            "avg_completion_price": mean(m["pricing"]["completion"] for m in models),
            "model_count": len(models),
            "avg_uptime_24h": mean(m["performance"].get("uptime_24h") for m in models),
            "avg_latency_p50": mean(latency_vals),
        }

        key = f"rollups/providers/{safe_key(provider_name)}.json"
        rollup = s3_get_json(key) or {"provider_name": provider_name, "history": []}
        # Idempotent: remove any existing entry for today before appending
        rollup["history"] = [h for h in rollup["history"] if h["date"] != today]
        rollup["history"].append(new_point)
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(key, rollup)

        # Accumulate per-model data across providers for the model rollups
        for model in models:
            model_day[model["model_id"]].append({
                "provider": provider_name,
                "prompt_price": model["pricing"]["prompt"],
                "completion_price": model["pricing"]["completion"],
                "uptime_24h": model["performance"].get("uptime_24h"),
                "latency_p50": (
                    model["performance"]["latency_30m"]["p50"]
                    if model["performance"].get("latency_30m") and model["performance"]["latency_30m"].get("p50")
                    else None
                ),
            })

    for model_id, providers_today in model_day.items():
        # model_id slashes (e.g. meta-llama/llama-3.1-70b) become S3 path prefixes — that's fine
        # Replace ':' with '_' for URL safety (e.g. model:free → model_free)
        safe_model_id = model_id.replace(":", "_")
        key = f"rollups/models/{safe_model_id}.json"
        rollup = s3_get_json(key) or {"model_id": model_id, "history": []}
        rollup["history"] = [h for h in rollup["history"] if h["date"] != today]
        rollup["history"].append({"date": today, "providers": providers_today})
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(key, rollup)

    print(f"Rollups updated: {len(infra_map)} providers, {len(model_day)} models")


# ---------------------------------------------------------------------------
# Open LLM Leaderboard benchmarks
# ---------------------------------------------------------------------------

HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=open-llm-leaderboard%2Fcontents"
    "&config=default&split=train&length=100&offset={offset}"
)

# Exact column names as returned by the HuggingFace datasets-server API
_COL_AVG     = "Average \u2b06\ufe0f"   # "Average ⬆️"
_COL_PARAMS  = "#Params (B)"


def fetch_benchmarks():
    """
    Fetch all rows from the Open LLM Leaderboard v2 dataset via the
    HuggingFace datasets-server API (no auth required) and return a
    processed, rank-ordered list of models.
    """
    models = []
    offset = 0
    total = None

    while True:
        data = http_get(HF_ROWS_URL.format(offset=offset))
        if not data:
            print(f"  benchmark fetch stopped at offset {offset}")
            break

        if total is None:
            total = data.get("num_rows_total", 0)
            print(f"  fetching {total} benchmark rows...")

        rows = data.get("rows", [])
        if not rows:
            break

        for item in rows:
            r = item.get("row", {})
            avg = r.get(_COL_AVG)
            raw_id = r.get("Model", "").strip()
            # Model field may be HTML — extract href path as canonical ID
            m = re.search(r'href="https://huggingface\.co/([^"]+)"', raw_id)
            hf_id = m.group(1) if m else re.sub(r"<[^>]+>", "", raw_id).strip()
            if not hf_id or avg is None:
                continue
            models.append({
                "id":       hf_id,
                "avg":      round(float(avg), 2),
                "ifeval":   round(float(r.get("IFEval")   or 0), 2),
                "bbh":      round(float(r.get("BBH")      or 0), 2),
                "math":     round(float(r.get("MATH Lvl 5") or 0), 2),
                "gpqa":     round(float(r.get("GPQA")     or 0), 2),
                "musr":     round(float(r.get("MUSR")     or 0), 2),
                "mmlu_pro": round(float(r.get("MMLU-PRO") or 0), 2),
            })

        offset += len(rows)
        if offset >= (total or 0):
            break

    # Sort highest score first and assign ranks
    models.sort(key=lambda m: m["avg"], reverse=True)
    for i, m in enumerate(models):
        m["rank"] = i + 1

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": len(models),
        "models": models,
    }


# ---------------------------------------------------------------------------
# GPU pricing collection (RunPod + Vast.ai)
# ---------------------------------------------------------------------------

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
VAST_API_URL = "https://console.vast.ai/api/v0"

_RUNPOD_QUERY = """
{
  gpuTypes {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    securePrice
    communityPrice
    secureSpotPrice
    communitySpotPrice
    lowestPrice(input: {gpuCount: 1}) {
      minimumBidPrice
      uninterruptablePrice
    }
  }
}
"""


def fetch_runpod_gpus():
    """Fetch GPU types and pricing from RunPod GraphQL API."""
    if not RUNPOD_API_KEY:
        return []
    data = http_post(
        RUNPOD_GRAPHQL_URL,
        {"query": _RUNPOD_QUERY},
        headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
    )
    if not data:
        return []
    if "errors" in data:
        print(f"RunPod API errors: {data['errors']}")
        return []
    results = []
    for gpu in data.get("data", {}).get("gpuTypes", []):
        lp = gpu.get("lowestPrice") or {}
        results.append({
            "id": gpu.get("id"),
            "name": gpu.get("displayName"),
            "vram_gb": gpu.get("memoryInGb"),
            "secure_cloud_available": gpu.get("secureCloud", False),
            "community_cloud_available": gpu.get("communityCloud", False),
            "pricing": {
                "secure_on_demand":    gpu.get("securePrice"),
                "community_on_demand": gpu.get("communityPrice"),
                "secure_spot":         gpu.get("secureSpotPrice"),
                "community_spot":      gpu.get("communitySpotPrice"),
                "minimum_bid":         lp.get("minimumBidPrice"),
                "uninterruptable":     lp.get("uninterruptablePrice"),
            },
        })
    return results


def fetch_vastai_gpus():
    """Fetch GPU offers from Vast.ai and aggregate by GPU type."""
    if not VAST_API_KEY:
        return []
    data = http_get(f"{VAST_API_URL}/bundles/?api_key={VAST_API_KEY}")
    if not isinstance(data, list):
        print(f"Unexpected Vast.ai response: {type(data)}")
        return []

    gpu_groups = {}
    for offer in data:
        name = offer.get("gpu_name", "Unknown")
        if name not in gpu_groups:
            gpu_groups[name] = {
                "vram_gb": (offer.get("gpu_ram") or 0) / 1024,
                "offers": [],
            }
        gpu_groups[name]["offers"].append({
            "id": offer.get("id"),
            "price_per_hour": offer.get("dph_total"),
            "rentable": offer.get("rentable", False),
            "reliability": offer.get("reliability2", 0),
            "num_gpus": offer.get("num_gpus", 1),
            "cuda_vers": offer.get("cuda_max_good"),
            "dlperf": offer.get("dlperf"),
        })

    results = []
    for gpu_name, gdata in gpu_groups.items():
        offers = gdata["offers"]
        rentable = [o for o in offers if o["rentable"]]
        all_prices = [o["price_per_hour"] for o in offers if o["price_per_hour"]]
        rent_prices = [o["price_per_hour"] for o in rentable if o["price_per_hour"]]
        if not all_prices:
            continue
        results.append({
            "name": gpu_name,
            "vram_gb": gdata["vram_gb"],
            "total_offers": len(offers),
            "rentable_offers": len(rentable),
            "pricing": {
                "min": min(all_prices),
                "max": max(all_prices),
                "avg": sum(all_prices) / len(all_prices),
                "rentable_min": min(rent_prices) if rent_prices else None,
                "rentable_avg": sum(rent_prices) / len(rent_prices) if rent_prices else None,
            },
            "sample_offers": rentable[:5],
        })
    results.sort(key=lambda x: x["name"])
    return results


def update_gpu_rollups(gpu_snapshot, today):
    """Append today's prices to per-GPU history files."""
    # RunPod GPU history
    for gpu in gpu_snapshot.get("runpod", {}).get("gpus", []):
        name = gpu.get("name", "")
        if not name:
            continue
        key = f"rollups/gpu/history/{safe_key(name)}.json"
        rollup = s3_get_json(key) or {"gpu_name": name, "history": []}
        rollup["history"] = [h for h in rollup["history"] if h["date"] != today]
        p = gpu.get("pricing", {})
        rollup["history"].append({
            "date": today,
            "provider": "runpod",
            "secure_on_demand":    p.get("secure_on_demand"),
            "community_on_demand": p.get("community_on_demand"),
            "secure_spot":         p.get("secure_spot"),
            "community_spot":      p.get("community_spot"),
        })
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(key, rollup, cache_seconds=86400)

    # Vast.ai GPU history
    for gpu in gpu_snapshot.get("vast", {}).get("gpus", []):
        name = gpu.get("name", "")
        if not name:
            continue
        key = f"rollups/gpu/history/{safe_key(name)}.json"
        rollup = s3_get_json(key) or {"gpu_name": name, "history": []}
        # Merge: keep existing runpod entry for today if present, add vast entry
        existing_today = [h for h in rollup["history"] if h["date"] == today]
        rollup["history"] = [h for h in rollup["history"] if h["date"] != today]
        p = gpu.get("pricing", {})
        # If there was already a runpod entry today, merge both into a combined record
        combined = existing_today[0] if existing_today else {"date": today}
        combined.update({
            "vast_min":             p.get("min"),
            "vast_avg":             p.get("avg"),
            "vast_rentable_min":    p.get("rentable_min"),
            "vast_rentable_offers": gpu.get("rentable_offers"),
        })
        rollup["history"].append(combined)
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(key, rollup, cache_seconds=86400)

    runpod_count = len(gpu_snapshot.get("runpod", {}).get("gpus", []))
    vast_count = len(gpu_snapshot.get("vast", {}).get("gpus", []))
    print(f"GPU rollups updated: {runpod_count} RunPod + {vast_count} Vast.ai GPU types")


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    today = datetime.now(timezone.utc).date().isoformat()
    print(f"Daily collection starting — {today}")

    # Fetch models and providers catalogues
    models_resp = http_get(f"{BASE_URL}/models")
    providers_resp = http_get(f"{BASE_URL}/providers")

    if not models_resp:
        raise RuntimeError("Failed to fetch models list from OpenRouter")

    models = models_resp["data"]
    providers_list = (providers_resp or {}).get("data", [])
    provider_lookup = {p["slug"]: p for p in providers_list}
    print(f"Loaded {len(models)} models, {len(providers_list)} providers")

    # Fetch per-model endpoints (rate-limited to be polite)
    endpoints_data = {}
    for i, model in enumerate(models):
        model_id = model["id"]
        result = http_get(f"{BASE_URL}/models/{model_id}/endpoints", token=API_TOKEN)
        if result:
            endpoints_data[model_id] = result
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(models)} fetched ({len(endpoints_data)} with endpoints)")
        time.sleep(0.15)

    print(f"Endpoints fetched: {len(endpoints_data)}/{len(models)}")

    infra_map = build_infrastructure_map(models, provider_lookup, endpoints_data)

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_models": len(models),
        "models_with_endpoints": len(endpoints_data),
        "total_providers": len(infra_map),
        "providers": infra_map,
    }

    # Raw archive — kept forever, cached for 24 h
    s3_put_json(f"snapshots/{today}.json", snapshot, cache_seconds=86400)
    print(f"Snapshot saved: snapshots/{today}.json")

    # latest.json — what the UI loads, 1 h cache
    s3_put_json("rollups/latest.json", snapshot)
    print("Updated: rollups/latest.json")

    update_rollups(infra_map, today)

    # Benchmark scores (Open LLM Leaderboard)
    print("Fetching Open LLM Leaderboard benchmarks...")
    benchmarks = fetch_benchmarks()
    if benchmarks and benchmarks["total"] > 0:
        s3_put_json("rollups/benchmarks.json", benchmarks, cache_seconds=86400)
        print(f"Benchmarks saved: {benchmarks['total']} models ranked")
    else:
        print("Warning: benchmark fetch returned no data")

    # GPU rental pricing (RunPod + Vast.ai)
    print("Fetching GPU rental pricing...")
    runpod_gpus = fetch_runpod_gpus()
    vast_gpus = fetch_vastai_gpus()
    if runpod_gpus or vast_gpus:
        gpu_snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runpod": {"total_gpus": len(runpod_gpus), "gpus": runpod_gpus},
            "vast":   {"total_gpu_types": len(vast_gpus), "gpus": vast_gpus},
        }
        s3_put_json(f"snapshots/gpu/{today}.json", gpu_snapshot, cache_seconds=86400)
        s3_put_json("rollups/gpu/latest.json", gpu_snapshot, cache_seconds=3600)
        update_gpu_rollups(gpu_snapshot, today)
        print(f"GPU pricing saved: {len(runpod_gpus)} RunPod + {len(vast_gpus)} Vast.ai")
    else:
        print("GPU API keys not configured — skipping GPU pricing collection")

    print("Done.")
    return {"statusCode": 200, "date": today}
