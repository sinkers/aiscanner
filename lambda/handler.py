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

==============================================================================
HISTORICAL DATA PROTECTION — DO NOT REMOVE OR MODIFY THESE INVARIANTS
==============================================================================
The following rules preserve the integrity of all historical pricing data:

1. DAILY SNAPSHOTS ARE WRITE-ONCE.
   snapshots/YYYY-MM-DD.json and snapshots/gpu/YYYY-MM-DD.json are written
   once per day and must NEVER be overwritten. They are the raw archive.

2. ROLLUP HISTORIES ARE APPEND-ONLY.
   The `history` arrays in rollups/providers/*.json, rollups/models/*.json,
   and rollups/gpu/history/*.json are append-only. Only the entry for TODAY
   may be replaced (idempotent re-run protection). Past dates must never be
   modified or deleted.

3. NEVER TRUNCATE HISTORY ARRAYS.
   Do not slice, cap, or trim history arrays regardless of length.

4. GUARD AGAINST EMPTY FETCHES.
   Before writing any rollup, verify the upstream fetch returned data. An
   empty or failed fetch must abort the write — never overwrite good data
   with an empty result.

The S3 bucket has versioning enabled as a safety net. If you must recover a
file, use `aws s3api list-object-versions` to find and restore a prior version.
==============================================================================
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
BASE_URL = "https://openrouter.ai/api/v1"

s3 = boto3.client("s3")


def _ssm_get(name):
    """Read a SecureString from SSM Parameter Store; return '' on any error."""
    try:
        ssm = boto3.client("ssm")
        resp = ssm.get_parameter(Name=name, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception:
        return ""


def _load_gpu_keys():
    """
    GPU API keys are optional. Resolution order:
      1. Environment variable (set at deploy time, fine for dev)
      2. SSM Parameter Store  (set once post-deploy, no redeploy needed)
    """
    runpod = os.environ.get("RUNPOD_API_KEY", "")
    vast   = os.environ.get("VAST_API_KEY", "")
    if not runpod:
        runpod = _ssm_get("/dame/gpu/runpod_api_key")
    if not vast:
        vast = _ssm_get("/dame/gpu/vast_api_key")
    return runpod, vast


RUNPOD_API_KEY, VAST_API_KEY = _load_gpu_keys()


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
    """
    Fetch GPU offers from Vast.ai and aggregate by GPU type.

    Auth is optional — the API returns public listings without a key, but an
    API key may surface additional/cheaper offers.  We always try with the key
    first (if set) and fall back to unauthenticated so data is collected even
    when the key is absent.

    Offers are split by is_bid flag:
      is_bid=True  → spot / interruptible (can be outbid and evicted)
      is_bid=False → on-demand / stable  (reserved until you stop it)
    """
    url = VAST_API_URL + "/bundles/"
    if VAST_API_KEY:
        url += f"?api_key={VAST_API_KEY}"

    raw = http_get(url)

    # API returns {"offers": [...]}; guard against both shapes
    if isinstance(raw, dict):
        offers_list = raw.get("offers", [])
    elif isinstance(raw, list):
        offers_list = raw
    else:
        print(f"Unexpected Vast.ai response type: {type(raw)}")
        return []

    if not offers_list:
        print("Vast.ai returned no offers")
        return []

    print(f"  Vast.ai: {len(offers_list)} offers received")

    gpu_groups = {}
    for offer in offers_list:
        name = offer.get("gpu_name") or "Unknown"
        if name not in gpu_groups:
            gpu_groups[name] = {
                "vram_gb": (offer.get("gpu_ram") or 0) / 1024,
                "spot_offers":   [],   # is_bid=True — interruptible
                "demand_offers": [],   # is_bid=False — stable on-demand
            }

        price    = offer.get("dph_total")
        is_bid   = offer.get("is_bid", False)
        rentable = offer.get("rentable", False)
        entry = {
            "id":            offer.get("id"),
            "price_per_hour": price,
            "rentable":      rentable,
            "reliability":   offer.get("reliability2", 0),
            "num_gpus":      offer.get("num_gpus", 1),
            "cuda_vers":     offer.get("cuda_max_good"),
            "dlperf":        offer.get("dlperf"),
        }

        if is_bid:
            gpu_groups[name]["spot_offers"].append(entry)
        else:
            gpu_groups[name]["demand_offers"].append(entry)

    def _stats(offers):
        prices = [o["price_per_hour"] for o in offers if o["price_per_hour"]]
        if not prices:
            return None, None
        return min(prices), sum(prices) / len(prices)

    results = []
    for gpu_name, gdata in gpu_groups.items():
        spot    = gdata["spot_offers"]
        demand  = gdata["demand_offers"]
        all_off = spot + demand

        spot_min,   spot_avg   = _stats(spot)
        demand_min, demand_avg = _stats(demand)

        rentable_demand = [o for o in demand if o["rentable"] and o["price_per_hour"]]
        rent_min, rent_avg = _stats(rentable_demand)

        all_prices = [o["price_per_hour"] for o in all_off if o["price_per_hour"]]
        if not all_prices:
            continue

        pricing = {
            "min": min(all_prices),
            "max": max(all_prices),
            "avg": sum(all_prices) / len(all_prices),
        }
        if spot_min   is not None: pricing["spot_min"]   = spot_min
        if spot_avg   is not None: pricing["spot_avg"]   = spot_avg
        if demand_min is not None: pricing["demand_min"] = demand_min
        if demand_avg is not None: pricing["demand_avg"] = demand_avg
        if rent_min   is not None: pricing["rentable_min"] = rent_min
        if rent_avg   is not None: pricing["rentable_avg"] = rent_avg

        results.append({
            "name":            gpu_name,
            "vram_gb":         gdata["vram_gb"],
            "total_offers":    len(all_off),
            "spot_offers":     len(spot),
            "demand_offers":   len(demand),
            "rentable_offers": len(rentable_demand),
            "pricing":         pricing,
            "sample_offers":   (rentable_demand or all_off)[:5],
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
        combined.update({field: val for field, val in {
            "vast_min":             p.get("min"),
            "vast_max":             p.get("max"),
            "vast_avg":             p.get("avg"),
            "vast_spot_min":        p.get("spot_min"),
            "vast_spot_avg":        p.get("spot_avg"),
            "vast_demand_min":      p.get("demand_min"),
            "vast_demand_avg":      p.get("demand_avg"),
            "vast_rentable_min":    p.get("rentable_min"),
            "vast_rentable_offers": gpu.get("rentable_offers"),
        }.items() if val is not None})
        rollup["history"].append(combined)
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(key, rollup, cache_seconds=86400)

    runpod_count = len(gpu_snapshot.get("runpod", {}).get("gpus", []))
    vast_count = len(gpu_snapshot.get("vast", {}).get("gpus", []))
    print(f"GPU rollups updated: {runpod_count} RunPod + {vast_count} Vast.ai GPU types")


# ---------------------------------------------------------------------------
# Daily Report Generation (Advanced Features)
# ---------------------------------------------------------------------------

def categorize_models_by_features(models):
    """Categorize models by advanced features (TTS, STT, video, image gen)."""
    features = {
        'stt': [],
        'tts': [],
        'stt_tts': [],
        'video_input': [],
        'image_gen': [],
    }

    for model in models:
        model_id = model['id']
        arch = model.get('architecture', {})
        input_mods = arch.get('input_modalities', [])
        output_mods = arch.get('output_modalities', [])

        has_audio_in = 'audio' in input_mods
        has_audio_out = 'audio' in output_mods
        has_video_in = 'video' in input_mods
        has_image_out = 'image' in output_mods

        model_info = {
            'id': model_id,
            'name': model['name'],
            'modality': arch.get('modality', 'unknown'),
            'pricing': model.get('pricing', {}),
        }

        if has_audio_in and has_audio_out:
            features['stt_tts'].append(model_info)
        elif has_audio_in:
            features['stt'].append(model_info)
        elif has_audio_out:
            features['tts'].append(model_info)

        if has_video_in:
            features['video_input'].append(model_info)
        if has_image_out:
            features['image_gen'].append(model_info)

    return features


def calculate_pricing_stats(models):
    """Calculate pricing statistics for a set of models."""
    if not models:
        return {'min': 0, 'max': 0, 'avg': 0, 'free_count': 0, 'paid_count': 0}

    prices = []
    free_count = 0

    for model in models:
        pricing = model.get('pricing', {})
        prompt = float(pricing.get('prompt', 0))
        completion = float(pricing.get('completion', 0))
        total = prompt + completion

        if total < 0:  # Skip placeholder prices
            continue
        if total == 0:
            free_count += 1
        else:
            prices.append(total)

    if not prices:
        return {'min': 0, 'max': 0, 'avg': 0, 'free_count': free_count, 'paid_count': 0}

    return {
        'min': min(prices) * 1_000_000,
        'max': max(prices) * 1_000_000,
        'avg': (sum(prices) / len(prices)) * 1_000_000,
        'free_count': free_count,
        'paid_count': len(prices),
    }


def analyze_providers_by_features(infra_map, feature_models):
    """Analyze which providers support which features."""
    feature_model_ids = {
        feature: set(m['id'] for m in models)
        for feature, models in feature_models.items()
    }

    provider_features = {}
    for provider_name, provider_data in infra_map.items():
        feature_counts = {k: 0 for k in feature_model_ids.keys()}

        for model in provider_data.get('models', []):
            model_id = model.get('model_id', '')
            for feature, model_ids in feature_model_ids.items():
                if model_id in model_ids:
                    feature_counts[feature] += 1

        provider_features[provider_name] = {
            'feature_counts': feature_counts,
            'total_advanced': sum(feature_counts.values()),
        }

    return provider_features


def generate_daily_report(models, infra_map):
    """Generate daily report with advanced features analysis."""
    feature_models = categorize_models_by_features(models)

    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'overall_stats': {
            'total_models': len(models),
            'total_providers': len(infra_map),
            'advanced_feature_models': len(set(
                m['id'] for feature in feature_models.values() for m in feature
            )),
        },
        'feature_stats': {},
        'provider_rankings': [],
    }

    # Calculate stats for each feature
    for feature_name, feature_model_list in feature_models.items():
        report['feature_stats'][feature_name] = {
            'count': len(feature_model_list),
            'pricing': calculate_pricing_stats(feature_model_list),
            'model_ids': [m['id'] for m in feature_model_list],
        }

    # Analyze providers
    provider_features = analyze_providers_by_features(infra_map, feature_models)
    providers_with_features = [
        {'name': name, **data}
        for name, data in provider_features.items()
        if data['total_advanced'] > 0
    ]
    providers_with_features.sort(key=lambda x: x['total_advanced'], reverse=True)
    report['provider_rankings'] = providers_with_features[:20]

    report['overall_stats']['providers_with_features'] = len(providers_with_features)

    return report


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
    vast_gpus   = fetch_vastai_gpus()

    if runpod_gpus or vast_gpus:
        gpu_snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runpod": {"total_gpus": len(runpod_gpus), "gpus": runpod_gpus},
            "vast":   {"total_gpu_types": len(vast_gpus), "gpus": vast_gpus},
        }

        # If a provider returned nothing because its API key is not configured,
        # carry forward the last known data so we don't wipe historical entries
        # from the live dashboard while the key is absent.
        if not runpod_gpus or not vast_gpus:
            prev = s3_get_json("rollups/gpu/latest.json") or {}
            if not runpod_gpus and prev.get("runpod", {}).get("gpus"):
                gpu_snapshot["runpod"] = prev["runpod"]
                print(f"  RunPod key not set — keeping {len(prev['runpod']['gpus'])} existing GPU entries")
            if not vast_gpus and prev.get("vast", {}).get("gpus"):
                gpu_snapshot["vast"] = prev["vast"]
                print(f"  Vast.ai returned nothing — keeping {len(prev['vast']['gpus'])} existing GPU entries")

        s3_put_json(f"snapshots/gpu/{today}.json", gpu_snapshot, cache_seconds=86400)
        s3_put_json("rollups/gpu/latest.json", gpu_snapshot, cache_seconds=3600)
        update_gpu_rollups(gpu_snapshot, today)
        rp_count   = len(gpu_snapshot["runpod"]["gpus"])
        vast_count = len(gpu_snapshot["vast"]["gpus"])
        print(f"GPU pricing saved: {rp_count} RunPod + {vast_count} Vast.ai GPU types")
    else:
        print("No GPU data available — configure RUNPOD_API_KEY / VAST_API_KEY via SSM or env")

    # Daily report with advanced features (TTS, STT, video, image gen)
    print("Generating daily report with advanced features...")
    daily_report = generate_daily_report(models, infra_map)
    s3_put_json("rollups/daily_report.json", daily_report, cache_seconds=3600)
    print(f"Daily report saved: {daily_report['overall_stats']['advanced_feature_models']} models with advanced features")

    print("Done.")
    return {"statusCode": 200, "date": today}
