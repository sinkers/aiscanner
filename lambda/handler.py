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

GPU API keys (optional — set via SSM /dame/gpu/* or env var fallback):
  RUNPOD_API_KEY          RunPod GraphQL API key
  VAST_API_KEY            Vast.ai REST API key
  LAMBDA_LABS_API_KEY     Lambda Labs REST API key

No-auth providers (always collected):
  TensorDock, Vultr, Azure, Oracle, AWS, Nova Cloud, DataCrunch/Verda,
  Google Cloud (static), CoreWeave (static), FluidStack (static),
  Jarvis Labs (static), Paperspace (static), SaladCloud (static),
  Crusoe (static), Hyperstack (static), Nebius (static),
  DigitalOcean (static), OVHcloud (static), Hetzner (static),
  Scaleway (static), Alibaba Cloud (static)

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

import base64
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
      2. SSM Parameter Store  (set once post-deploy with make configure-gpu)
    """
    _key_map = {
        "runpod":          ("RUNPOD_API_KEY",          "/dame/gpu/runpod_api_key"),
        "vast":            ("VAST_API_KEY",             "/dame/gpu/vast_api_key"),
        "lambda_labs":     ("LAMBDA_LABS_API_KEY",      "/dame/gpu/lambda_labs_api_key"),
        "thunder_compute": ("THUNDER_COMPUTE_API_KEY",  "/dame/gpu/thunder_compute_api_key"),
    }
    result = {}
    for provider, (env_var, ssm_path) in _key_map.items():
        result[provider] = os.environ.get(env_var, "") or _ssm_get(ssm_path)
    return result


_GPU_KEYS = _load_gpu_keys()
RUNPOD_API_KEY          = _GPU_KEYS["runpod"]
VAST_API_KEY            = _GPU_KEYS["vast"]
LAMBDA_LABS_API_KEY     = _GPU_KEYS["lambda_labs"]
THUNDER_COMPUTE_API_KEY = _GPU_KEYS["thunder_compute"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def http_get(url, token=None, basic_auth=None):
    headers = {"User-Agent": "dame-pricing-collector/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif basic_auth:
        # basic_auth is the API key — username is empty (Lambda Labs style)
        creds = base64.b64encode(f"{basic_auth}:".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
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
# GPU name normalisation
# ---------------------------------------------------------------------------
# Different providers name the same GPU differently. This function maps all
# variants to a canonical name so cross-provider comparison works.

# Regex patterns applied in order to strip noise before lookup
_GPU_NAME_STRIP_PATTERNS = [
    (re.compile(r"\s*\d+GB$", re.IGNORECASE), ""),           # trailing "80GB"
    (re.compile(r"\s+SXM[45]?$", re.IGNORECASE), " SXM"),    # SXM4/SXM5 → SXM
    (re.compile(r"\s+SXM[56]?$", re.IGNORECASE), " SXM"),    # SXM6 → SXM
    (re.compile(r"\s+PCIE$", re.IGNORECASE), " PCIe"),        # PCIE → PCIe
]

# Explicit name mappings: raw name → canonical name
_GPU_NAME_MAP = {
    # H100 variants
    "HGX H100":               "H100 SXM",
    "H100 HGX":               "H100 SXM",
    "H100 SXM5":              "H100 SXM",
    "H100 (Tensor)":          "H100 SXM",
    "H100":                   "H100 SXM",
    "H100 NVL":               "H100 NVL",
    # H200 variants
    "HGX H200":               "H200 SXM",
    "H200 HGX":               "H200 SXM",
    "H200 SXM5":              "H200 SXM",
    "H200":                   "H200 SXM",
    "H200 NVL":               "H200 NVL",
    # B200 variants
    "HGX B200":               "B200 SXM",
    "B200 SXM6":              "B200 SXM",
    "B200":                   "B200 SXM",
    # B300 variants
    "HGX B300":               "B300 SXM",
    "B300 SXM6":              "B300 SXM",
    "B300":                   "B300 SXM",
    # GB200/GB300
    "GB200 NVL72":            "GB200 NVL72",
    "GB300 SXM6":             "GB300 SXM",
    # A100 variants
    "A100 SXM4":              "A100 SXM",
    "A100 SXM":               "A100 SXM",
    "A100 NVLink":            "A100 SXM",
    "A100 PCIE":              "A100 PCIe",
    "A100 PCIe":              "A100 PCIe",
    "A100 80G":               "A100 80GB",
    "A100 (E3)":              "A100",
    "A100 (E4)":              "A100",
    # A6000 variants
    "RTX A6000":              "A6000",
    "A6000":                  "A6000",
    # L40S
    "L40S":                   "L40S",
    # L40
    "L40":                    "L40",
    # V100 variants
    "Tesla V100":             "V100",
    "V100":                   "V100",
    "V100 SXM2":              "V100 SXM",
    "Tesla V100 (V2)":        "V100",
    "Tesla V100 (X7)":        "V100",
    # RTX PRO 6000 variants
    "RTX PRO 6000 Blackwell": "RTX PRO 6000",
    "RTX PRO 6000 WK":        "RTX PRO 6000",
    "RTX PRO 6000 WS":        "RTX PRO 6000",
    "RTX PRO 6000 S":         "RTX PRO 6000",
    "RTX PRO 6000 MaxQ":      "RTX PRO 6000",
    "RTX PRO 6000 SE":        "RTX PRO 6000",
    "RTX PRO 6000 CC":        "RTX PRO 6000",
    "RTX Pro 6000":           "RTX PRO 6000",
    # GH200
    "GH200":                  "GH200",
    # MI300X
    "MI300X":                 "MI300X",
}


def normalize_gpu_name(raw_name):
    """Normalize a GPU name to a canonical form for cross-provider comparison.

    Strips 'NVIDIA ' / 'AMD ' prefixes, removes trailing VRAM suffixes,
    normalises SXM/PCIe variants, then applies the explicit mapping table.
    """
    name = raw_name.strip()

    # Strip vendor prefixes
    for prefix in ("NVIDIA ", "AMD "):
        if name.startswith(prefix):
            name = name[len(prefix):]

    # Strip trailing VRAM (e.g. "80GB", "48GB") and SXM version numbers
    for pattern, repl in _GPU_NAME_STRIP_PATTERNS:
        name = pattern.sub(repl, name)

    # Explicit mapping
    if name in _GPU_NAME_MAP:
        return _GPU_NAME_MAP[name]

    return name


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


# ---------------------------------------------------------------------------
# GPU pricing collection — Lambda Labs
# ---------------------------------------------------------------------------

LAMBDA_LABS_API_URL = "https://cloud.lambdalabs.com/api/v1"


def fetch_lambdalabs_gpus():
    """Fetch instance types and pricing from Lambda Labs REST API."""
    if not LAMBDA_LABS_API_KEY:
        return []
    data = http_get(f"{LAMBDA_LABS_API_URL}/instance-types", basic_auth=LAMBDA_LABS_API_KEY)
    if not data:
        return []

    results = []
    for instance_name, info in data.get("data", {}).items():
        itype = info.get("instance_type", {})
        if itype.get("gpu_description", "") in ("N/A", "", None):
            continue  # skip CPU-only instances
        specs = itype.get("specs", {})
        price_cents = itype.get("price_cents_per_hour", 0)
        gpu_count = specs.get("gpus", 1) or 1
        price_per_gpu = price_cents / 100 / gpu_count  # $/hr per GPU

        # Extract GPU name and VRAM from gpu_description
        # e.g. "1x H100 SXM5 (80 GB)" → name "H100 SXM5", vram 80
        gpu_desc = itype.get("gpu_description", "")
        vram = 0
        m = re.search(r"\((\d+)\s*GB", gpu_desc)
        if m:
            vram = int(m.group(1))
        # Strip leading count prefix "Nx " if present
        gpu_name_clean = re.sub(r"^\d+x\s+", "", gpu_desc).split("(")[0].strip()
        display_name = gpu_name_clean or instance_name

        regions = [r["name"] for r in info.get("regions_with_capacity_available", [])]

        results.append({
            "name":         display_name,
            "instance_id":  instance_name,
            "vram_gb":      vram,
            "gpu_count":    gpu_count,
            "regions":      regions,
            "in_stock":     len(regions) > 0,
            "pricing": {
                # Lambda Labs is on-demand only (no spot)
                "min":        price_per_gpu,
                "avg":        price_per_gpu,
                "demand_min": price_per_gpu,
                "demand_avg": price_per_gpu,
                "instance_price": price_cents / 100,  # full instance $/hr
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Lambda Labs: {len(results)} instance types")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — TensorDock
# ---------------------------------------------------------------------------

TENSORDOCK_HOSTNODES_URL = "https://marketplace.tensordock.com/api/v0/client/deploy/hostnodes"


def fetch_tensordock_gpus():
    """Fetch available GPU host nodes from TensorDock marketplace (no auth)."""
    data = http_get(TENSORDOCK_HOSTNODES_URL)
    if not data:
        return []

    hostnodes = data.get("hostnodes", {})
    gpu_groups = {}

    for node_id, node in hostnodes.items():
        specs = node.get("specs", {})
        gpu_specs = specs.get("gpu", {})
        for gpu_slug, gpu_info in gpu_specs.items():
            if not isinstance(gpu_info, dict):
                continue
            price = gpu_info.get("price")
            if price is None:
                continue
            vram = gpu_info.get("vram", 0)
            # Normalise slug to readable name: "geforcertx4090-pcie-24gb" → "GeForce RTX 4090"
            clean = gpu_slug.upper()
            # Trim trailing vram/pcie/nvlink suffixes that duplicate info
            clean = re.sub(r"-?\d+GB$", "", clean, flags=re.IGNORECASE)
            clean = re.sub(r"-(PCIE|NVLINK|SXM\d*)$", "", clean, flags=re.IGNORECASE)
            clean = clean.replace("-", " ").strip()

            if clean not in gpu_groups:
                gpu_groups[clean] = {"vram_gb": vram, "prices": []}
            gpu_groups[clean]["prices"].append(float(price))

    results = []
    for name, gdata in gpu_groups.items():
        prices = gdata["prices"]
        if not prices:
            continue
        avg_price = sum(prices) / len(prices)
        results.append({
            "name":        name,
            "vram_gb":     gdata["vram_gb"],
            "total_offers": len(prices),
            "pricing": {
                # TensorDock is on-demand only
                "min":        min(prices),
                "avg":        avg_price,
                "max":        max(prices),
                "demand_min": min(prices),
                "demand_avg": avg_price,
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  TensorDock: {len(results)} GPU types from {len(hostnodes)} nodes")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Vultr
# ---------------------------------------------------------------------------

VULTR_PLANS_URL = "https://api.vultr.com/v2/plans?type=vcg&per_page=500"


def fetch_vultr_gpus():
    """Fetch GPU instance plans from Vultr public API (no auth)."""
    all_plans = []
    url = VULTR_PLANS_URL
    page = 0
    while url and page < 10:
        data = http_get(url)
        if not data:
            break
        all_plans.extend(data.get("plans", []))
        next_link = (data.get("meta") or {}).get("links", {}).get("next", "")
        url = next_link or None
        page += 1

    if not all_plans:
        return []

    # Group by GPU model
    gpu_groups = {}
    for plan in all_plans:
        gpu_type = plan.get("gpu_type", "Unknown")
        # "NVIDIA_A16" → "A16", "AMD_MI300X" → "AMD MI300X"
        clean = gpu_type.replace("NVIDIA_", "").replace("AMD_", "AMD ").replace("_", " ")
        vram_per_gpu = plan.get("gpu_vram_gb", 0)
        gpu_count = plan.get("gpu_count", 1) or 1
        total_vram = vram_per_gpu * gpu_count
        hourly = plan.get("hourly_cost", 0) or 0
        price_per_gpu = hourly / gpu_count if gpu_count else hourly

        if clean not in gpu_groups:
            gpu_groups[clean] = {"vram_gb": total_vram, "prices_per_gpu": []}
        gpu_groups[clean]["prices_per_gpu"].append(price_per_gpu)

    results = []
    for name, gdata in gpu_groups.items():
        prices = gdata["prices_per_gpu"]
        if not prices:
            continue
        avg_price = sum(prices) / len(prices)
        results.append({
            "name":        f"{name}",
            "vram_gb":     gdata["vram_gb"],
            "total_offers": len(prices),
            "pricing": {
                # Vultr plans are on-demand only
                "min":        min(prices),
                "avg":        avg_price,
                "max":        max(prices),
                "demand_min": min(prices),
                "demand_avg": avg_price,
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Vultr: {len(results)} GPU types from {len(all_plans)} plans")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Azure
# ---------------------------------------------------------------------------

AZURE_PRICING_URL = "https://prices.azure.com/api/retail/prices"

# Filter: GPU VM families (NC, ND, NV, NG) in eastus, on-demand Linux prices
_AZURE_FILTER = (
    "armRegionName eq 'eastus' and "
    "(startswith(armSkuName,'Standard_NC') or "
    "startswith(armSkuName,'Standard_ND') or "
    "startswith(armSkuName,'Standard_NV') or "
    "startswith(armSkuName,'Standard_NG')) and "
    "priceType eq 'Consumption'"
)


def _azure_gpu_name(sku_name):
    """Best-effort extraction of GPU model from an Azure VM SKU name."""
    patterns = [
        (r"H200",   "H200"),
        (r"H100",   "H100"),
        (r"A100",   "A100"),
        (r"A10\b",  "A10"),
        (r"T4\b",   "T4"),
        (r"V100",   "V100"),
        (r"K80",    "K80"),
        (r"M60",    "M60"),
        (r"V620",   "AMD Radeon V620"),
        (r"RTX4000","RTX 4000"),
    ]
    for pat, name in patterns:
        if re.search(pat, sku_name, re.IGNORECASE):
            return name
    # Fall back to series letter (NC → NC-series, ND → ND-series)
    m = re.match(r"Standard_(N[CDVG])", sku_name)
    return f"{m.group(1)}-series" if m else sku_name


def fetch_azure_gpus():
    """Fetch Azure GPU VM on-demand + spot prices for eastus (no auth)."""
    items = []
    url = f"{AZURE_PRICING_URL}?$filter={urllib.request.quote(_AZURE_FILTER)}"
    page = 0
    while url and page < 25:
        data = http_get(url)
        if not data:
            break
        batch = data.get("Items", [])
        items.extend(batch)
        url = data.get("NextPageLink")
        page += 1

    if not items:
        print("  Azure: no pricing items returned")
        return []

    gpu_groups = {}
    for item in items:
        sku   = item.get("armSkuName", "")
        price = item.get("retailPrice", 0)
        meter = item.get("meterName", "")
        if not price or not sku:
            continue
        # Skip Windows, Reserved, Low Priority
        if any(t in meter for t in ("Windows", "Low Priority", "Spot Priority")):
            continue

        gpu_name = _azure_gpu_name(sku)
        is_spot  = "Spot" in meter

        if gpu_name not in gpu_groups:
            gpu_groups[gpu_name] = {"spot": [], "demand": []}
        if is_spot:
            gpu_groups[gpu_name]["spot"].append(price)
        else:
            gpu_groups[gpu_name]["demand"].append(price)

    results = []
    for gpu_name, gdata in gpu_groups.items():
        spot_p   = gdata["spot"]
        demand_p = gdata["demand"]
        all_p    = spot_p + demand_p
        if not all_p:
            continue

        pricing = {
            "min": min(all_p),
            "max": max(all_p),
            "avg": sum(all_p) / len(all_p),
        }
        if spot_p:
            pricing["spot_min"] = min(spot_p)
            pricing["spot_avg"] = sum(spot_p) / len(spot_p)
        if demand_p:
            pricing["demand_min"] = min(demand_p)
            pricing["demand_avg"] = sum(demand_p) / len(demand_p)

        results.append({
            "name":         gpu_name,
            "vram_gb":      0,   # Azure pricing API doesn't expose VRAM specs
            "total_offers": len(all_p),
            "spot_offers":  len(spot_p),
            "demand_offers": len(demand_p),
            "pricing":      pricing,
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Azure: {len(results)} GPU types from {len(items)} pricing records")
    return results


def _write_provider_rollup(provider_key, gpu_list, today, prefix_fields):
    """
    Generic helper: update per-GPU history files for a provider.

    provider_key   - snake_case provider name (e.g. "lambda_labs")
    gpu_list       - list of GPU dicts from the fetcher
    today          - ISO date string
    prefix_fields  - dict mapping storage field name → pricing dict key
                     e.g. {"ll_min": "min", "ll_demand_min": "demand_min"}
    """
    for gpu in gpu_list:
        name = gpu.get("name", "")
        if not name:
            continue
        s3_key = f"rollups/gpu/history/{provider_key}/{safe_key(name)}.json"
        rollup = s3_get_json(s3_key) or {"gpu_name": name, "provider": provider_key, "history": []}
        rollup["history"] = [h for h in rollup["history"] if h["date"] != today]
        p = gpu.get("pricing", {})
        entry = {"date": today}
        for field, pricing_key in prefix_fields.items():
            val = p.get(pricing_key)
            if val is not None:
                entry[field] = val
        rollup["history"].append(entry)
        rollup["history"].sort(key=lambda x: x["date"])
        s3_put_json(s3_key, rollup, cache_seconds=86400)


# ---------------------------------------------------------------------------
# GPU pricing collection — Oracle Cloud Infrastructure
# ---------------------------------------------------------------------------

OCI_PRICING_URL = "https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD&lang=en"

# Display name → clean GPU name mapping (OCI API has inconsistent naming)
_OCI_GPU_NAME_MAP = {
    "L40S":         "L40S",
    "H100T":        "H100 (Tensor)",
    "H100":         "H100",
    "H200":         "H200",
    "B200":         "B200",
    "B300":         "B300",
    "GB200":        "GB200",
    "GB300":        "GB300",
    "MI300X":       "AMD MI300X",
    "MI355X":       "AMD MI355X",
    "A100":         "A100",
    "A10":          "A10",
    "RTX PRO 6000": "RTX Pro 6000",
    "X7":           "Tesla V100 (X7)",
    "V2":           "Tesla V100 (V2)",
    "E3":           "A100 (E3)",
    "E4":           "A100 (E4)",
}


def _oci_gpu_name(display_name):
    """Extract clean GPU name from OCI product display name."""
    for key, name in _OCI_GPU_NAME_MAP.items():
        if key in display_name:
            return name
    # Fallback: strip prefix and clean up
    cleaned = re.sub(r"^(OCI\s*[-–]\s*|Oracle Cloud Infrastructure\s*[-–]\s*|Compute\s*[-–]\s*|GPU\s*[-–]\s*)+", "", display_name, flags=re.IGNORECASE).strip()
    return cleaned or display_name


def fetch_oracle_gpus():
    """Fetch OCI GPU pricing — public API, no auth, per GPU per hour."""
    data = http_get(OCI_PRICING_URL)
    if not data:
        return []

    items = data.get("items", [])
    results = []
    seen = set()

    for item in items:
        name = item.get("displayName", "")
        metric = item.get("metricName", "")

        # Only include GPU compute items priced per-GPU-per-hour
        if "GPU Per Hour" not in metric:
            continue
        # Skip VMware, Cloud@Customer, Roving Edge
        if any(x in name for x in ("VMware", "Cloud@Customer", "Roving Edge", "Commit")):
            continue

        gpu_name = _oci_gpu_name(name)
        if gpu_name in seen:
            continue
        seen.add(gpu_name)

        price = None
        for loc in item.get("currencyCodeLocalizations", []):
            for p in loc.get("prices", []):
                if p.get("model") == "PAY_AS_YOU_GO":
                    price = float(p["value"])
                    break
            if price is not None:
                break

        if price is None:
            continue

        results.append({
            "name":        gpu_name,
            "vram_gb":     0,   # OCI pricing API doesn't expose VRAM
            "total_offers": 1,
            "pricing": {
                "min":        price,
                "avg":        price,
                "demand_min": price,
                "demand_avg": price,
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Oracle Cloud: {len(results)} GPU types")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — AWS EC2 (on-demand, via boto3 Pricing API)
# ---------------------------------------------------------------------------

# GPU instance families in AWS: p, g, trn (Trainium), inf (Inferentia)
# We focus on p and g families for actual GPU compute
_AWS_GPU_FAMILIES = ("p2.", "p3.", "p4.", "p5.", "p6.", "g4.", "g5.", "g6.", "g6e.")

_AWS_INSTANCE_GPU_MAP = {
    # p2 — Tesla K80
    "p2.xlarge": ("Tesla K80", 12, 1), "p2.8xlarge": ("Tesla K80", 12, 8), "p2.16xlarge": ("Tesla K80", 12, 16),
    # p3 — Tesla V100
    "p3.2xlarge": ("Tesla V100 16GB", 16, 1), "p3.8xlarge": ("Tesla V100 16GB", 16, 4),
    "p3.16xlarge": ("Tesla V100 16GB", 16, 8), "p3dn.24xlarge": ("Tesla V100 32GB", 32, 8),
    # p4 — A100
    "p4d.24xlarge": ("A100 40GB", 40, 8), "p4de.24xlarge": ("A100 80GB", 80, 8),
    # p5 — H100
    "p5.48xlarge": ("H100 80GB", 80, 8),
    # p5e — H200
    "p5e.48xlarge": ("H200 141GB", 141, 8),
    # p6 — B200
    "p6-b200.48xlarge": ("B200 180GB", 180, 8),
    # g4dn — T4
    "g4dn.xlarge": ("T4 16GB", 16, 1), "g4dn.2xlarge": ("T4 16GB", 16, 1),
    "g4dn.4xlarge": ("T4 16GB", 16, 1), "g4dn.8xlarge": ("T4 16GB", 16, 1),
    "g4dn.12xlarge": ("T4 16GB", 16, 4), "g4dn.16xlarge": ("T4 16GB", 16, 1),
    "g4dn.metal": ("T4 16GB", 16, 8),
    # g5 — A10G
    "g5.xlarge": ("A10G 24GB", 24, 1), "g5.2xlarge": ("A10G 24GB", 24, 1),
    "g5.4xlarge": ("A10G 24GB", 24, 1), "g5.8xlarge": ("A10G 24GB", 24, 1),
    "g5.12xlarge": ("A10G 24GB", 24, 4), "g5.16xlarge": ("A10G 24GB", 24, 1),
    "g5.24xlarge": ("A10G 24GB", 24, 4), "g5.48xlarge": ("A10G 24GB", 24, 8),
    # g6 — L4
    "g6.xlarge": ("L4 24GB", 24, 1), "g6.2xlarge": ("L4 24GB", 24, 1),
    "g6.4xlarge": ("L4 24GB", 24, 1), "g6.8xlarge": ("L4 24GB", 24, 1),
    "g6.12xlarge": ("L4 24GB", 24, 4), "g6.16xlarge": ("L4 24GB", 24, 1),
    "g6.24xlarge": ("L4 24GB", 24, 4), "g6.48xlarge": ("L4 24GB", 24, 8),
    # g6e — L40S
    "g6e.xlarge": ("L40S 48GB", 48, 1), "g6e.2xlarge": ("L40S 48GB", 48, 1),
    "g6e.4xlarge": ("L40S 48GB", 48, 1), "g6e.8xlarge": ("L40S 48GB", 48, 1),
    "g6e.12xlarge": ("L40S 48GB", 48, 4), "g6e.16xlarge": ("L40S 48GB", 48, 1),
    "g6e.24xlarge": ("L40S 48GB", 48, 4), "g6e.48xlarge": ("L40S 48GB", 48, 8),
}


def fetch_aws_gpus():
    """
    Fetch AWS EC2 GPU on-demand pricing via the boto3 Pricing API.
    Requires pricing:GetProducts permission on the Lambda role.
    Returns per-GPU hourly price for key GPU instance families.
    """
    try:
        pricing_client = boto3.client("pricing", region_name="us-east-1")
    except Exception as e:
        print(f"  AWS pricing client error: {e}")
        return []

    instance_prices = {}  # instance_type → on-demand $/hr
    paginator = pricing_client.get_paginator("get_products")

    try:
        pages = paginator.paginate(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "operatingSystem",    "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy",            "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw",     "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus",     "Value": "Used"},
                {"Type": "TERM_MATCH", "Field": "location",           "Value": "US East (N. Virginia)"},
            ],
        )
        for page in pages:
            for price_str in page["PriceList"]:
                try:
                    item = json.loads(price_str)
                    attrs = item.get("product", {}).get("attributes", {})
                    itype = attrs.get("instanceType", "")
                    if not any(itype.startswith(f) for f in _AWS_GPU_FAMILIES):
                        continue
                    # Extract on-demand USD price
                    terms = item.get("terms", {}).get("OnDemand", {})
                    for term in terms.values():
                        for dim in term.get("priceDimensions", {}).values():
                            usd = float(dim.get("pricePerUnit", {}).get("USD", 0))
                            if usd > 0:
                                instance_prices[itype] = usd
                except Exception:
                    continue

    except Exception as e:
        print(f"  AWS pricing fetch error: {e}")
        return []

    if not instance_prices:
        print("  AWS: no GPU pricing returned (check pricing:GetProducts IAM permission)")
        return []

    # Aggregate per GPU model using the instance map
    gpu_groups = {}
    for itype, instance_price in instance_prices.items():
        gpu_info = _AWS_INSTANCE_GPU_MAP.get(itype)
        if not gpu_info:
            continue
        gpu_name, vram, gpu_count = gpu_info
        price_per_gpu = instance_price / gpu_count

        if gpu_name not in gpu_groups:
            gpu_groups[gpu_name] = {"vram_gb": vram, "prices": []}
        gpu_groups[gpu_name]["prices"].append(price_per_gpu)

    results = []
    for gpu_name, gdata in gpu_groups.items():
        prices = gdata["prices"]
        if not prices:
            continue
        results.append({
            "name":        gpu_name,
            "vram_gb":     gdata["vram_gb"],
            "total_offers": len(prices),
            "pricing": {
                "min":        min(prices),
                "avg":        sum(prices) / len(prices),
                "max":        max(prices),
                "demand_min": min(prices),
                "demand_avg": sum(prices) / len(prices),
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  AWS: {len(results)} GPU types from {len(instance_prices)} instance prices")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Thunder Compute
# ---------------------------------------------------------------------------

THUNDER_COMPUTE_API_URL = "https://api.thundercompute.com:8443"


def fetch_thunder_compute_gpus():
    """Fetch GPU specs and pricing from Thunder Compute API.

    Merges /specs (GPU types, VRAM, multi-GPU configs) with /pricing
    (hourly rates). Groups by GPU type, reporting per-GPU price for
    the cheapest mode (prototyping < production).
    """
    if not THUNDER_COMPUTE_API_KEY:
        return []

    specs_data = http_get(f"{THUNDER_COMPUTE_API_URL}/specs", token=THUNDER_COMPUTE_API_KEY)
    price_data = http_get(f"{THUNDER_COMPUTE_API_URL}/pricing", token=THUNDER_COMPUTE_API_KEY)

    if not specs_data or not price_data:
        print("  Thunder Compute: API returned no data")
        return []

    specs = specs_data.get("specs", {})
    pricing = price_data.get("pricing", {})

    # Group specs by base GPU type (e.g. "h100", "a100xl", "l40s")
    gpu_groups = {}
    for key, spec in specs.items():
        display = spec.get("displayName", key)
        vram = spec.get("vramGB", 0)
        gpu_count = spec.get("gpuCount", 1)
        mode = spec.get("mode", "")

        # Extract base type: "h100_x2_production" → "h100"
        base = key.split("_x")[0] if "_x" in key else key.rsplit("_", 1)[0]

        if base not in gpu_groups:
            gpu_groups[base] = {
                "display": display,
                "vram": vram,
            }

        # Per-GPU price for single-GPU configs
        price = pricing.get(key, 0)
        if gpu_count == 1 and price > 0:
            existing = gpu_groups[base].get("prices", {})
            existing[mode] = price
            gpu_groups[base]["prices"] = existing

    # Also check pricing keys not in specs (e.g. l40s)
    for pkey, price in pricing.items():
        if price <= 0 or pkey in ("additional_vcpus", "disk_gb",
                                   "ephemeral_disk_gb", "snapshot_gb"):
            continue
        base = pkey.split("_x")[0] if "_x" in pkey else pkey.rsplit("_", 1)[0]
        if base not in gpu_groups and not pkey.endswith("_native"):
            # Infer name from key
            name_map = {
                "l40s": ("NVIDIA L40S", 48),
                "l40": ("NVIDIA L40", 48),
                "h100": ("NVIDIA H100", 80),
                "a100xl": ("NVIDIA A100 (80GB)", 80),
                "a6000": ("RTX A6000", 48),
            }
            if base in name_map:
                display, vram = name_map[base]
                gpu_groups[base] = {"display": display, "vram": vram, "prices": {}}

        if base in gpu_groups and "_x" not in pkey:
            mode = "prototyping" if "prototyping" in pkey else (
                "production" if "production" in pkey or "native" in pkey else "default")
            existing = gpu_groups[base].get("prices", {})
            if mode not in existing:
                existing[mode] = price
                gpu_groups[base]["prices"] = existing

    results = []
    for base, gdata in gpu_groups.items():
        prices = gdata.get("prices", {})
        if not prices:
            continue
        # Per-GPU hourly: cheapest is prototyping, most expensive is production
        proto_price = prices.get("prototyping") or prices.get("default")
        prod_price = prices.get("production") or prices.get("native")
        positive = [p for p in prices.values() if p > 0]
        cheapest = min(positive) if positive else 0

        results.append({
            "name": gdata["display"],
            "vram_gb": gdata["vram"],
            "pricing": {
                "min":        cheapest,
                "avg":        cheapest,
                "demand_min": proto_price or cheapest,
                "demand_avg": prod_price or cheapest,
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Thunder Compute: {len(results)} GPU types")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Nova Cloud
# ---------------------------------------------------------------------------

NOVA_CLOUD_API_URL = "https://api.nova-cloud.ai"

# Display name map for Nova Cloud's short GPU type codes
_NOVA_GPU_NAMES = {
    "4090":    "RTX 4090",
    "5090":    "RTX 5090",
    "pro6000": "RTX PRO 6000",
    "a100":    "A100",
    "h100":    "H100",
    "l40s":    "L40S",
}


def fetch_nova_cloud_gpus():
    """Fetch GPU offers from Nova Cloud (no auth required).

    Uses /search for live availability + pricing, and /pricing as fallback
    for GPU types that are listed but have no current offers.
    """
    search_data = http_get(f"{NOVA_CLOUD_API_URL}/search")
    price_data = http_get(f"{NOVA_CLOUD_API_URL}/pricing")

    if not search_data and not price_data:
        print("  Nova Cloud: API returned no data")
        return []

    # Group /search offers by GPU type (single-GPU only for per-GPU pricing)
    gpu_groups = {}
    for offer in (search_data or []):
        gpu_type = offer.get("gpu_type", "")
        gpu_count = offer.get("gpu_count", 1)
        if gpu_count != 1:
            continue

        if gpu_type not in gpu_groups:
            gpu_groups[gpu_type] = {
                "vram_gb": round((offer.get("gpu_ram_mb") or 0) / 1024),
                "demand_prices": [],
                "spot_prices": [],
                "available": 0,
                "total": 0,
                "locations": set(),
            }

        g = gpu_groups[gpu_type]
        price = offer.get("gpu_price_hourly", 0)
        if price > 0:
            g["demand_prices"].append(price)
        spot = offer.get("interruptible_rate", 0)
        if spot > 0:
            g["spot_prices"].append(spot)
        g["total"] += 1
        if offer.get("available"):
            g["available"] += 1
        loc = offer.get("location", "")
        if loc:
            g["locations"].add(loc)

    # Add any GPU types from /pricing not in /search (listed but no current offers)
    if price_data and isinstance(price_data, dict):
        for gpu_type, price in price_data.get("gpus", {}).items():
            if gpu_type not in gpu_groups and price > 0:
                gpu_groups[gpu_type] = {
                    "vram_gb": 0,
                    "demand_prices": [price],
                    "spot_prices": [],
                    "available": 0,
                    "total": 0,
                    "locations": set(),
                }

    results = []
    for gpu_type, gdata in gpu_groups.items():
        demand = gdata["demand_prices"]
        spot = gdata["spot_prices"]
        display_name = _NOVA_GPU_NAMES.get(gpu_type, gpu_type.upper())

        results.append({
            "name": display_name,
            "vram_gb": gdata["vram_gb"],
            "available": gdata["available"] > 0,
            "available_count": gdata["available"],
            "total_offers": gdata["total"],
            "locations": sorted(gdata["locations"]),
            "pricing": {
                "min":        min(spot + demand) if (spot + demand) else 0,
                "avg":        sum(demand) / len(demand) if demand else 0,
                "demand_min": min(demand) if demand else None,
                "demand_avg": sum(demand) / len(demand) if demand else None,
                "spot_min":   min(spot) if spot else None,
                "spot_avg":   sum(spot) / len(spot) if spot else None,
            },
        })

    results.sort(key=lambda x: x["name"])
    print(f"  Nova Cloud: {len(results)} GPU types ({sum(1 for r in results if r['available'])} available)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Google Cloud (static catalog, no auth)
# ---------------------------------------------------------------------------

# Google Cloud GPU pricing (us-central1, on-demand + spot)
# Source: https://cloud.google.com/compute/vm-instance-pricing
_GOOGLE_CLOUD_GPUS = [
    {"name": "NVIDIA H100 80GB",  "vram_gb": 80,  "demand": 10.90, "spot": 3.67},
    {"name": "NVIDIA A100 80GB",  "vram_gb": 80,  "demand": 5.07,  "spot": 1.52},
    {"name": "NVIDIA A100 40GB",  "vram_gb": 40,  "demand": 3.67,  "spot": 1.10},
    {"name": "NVIDIA L4",         "vram_gb": 24,  "demand": 0.81,  "spot": 0.24},
    {"name": "NVIDIA T4",         "vram_gb": 16,  "demand": 0.35,  "spot": 0.11},
    {"name": "NVIDIA V100",       "vram_gb": 16,  "demand": 2.48,  "spot": 0.74},
    {"name": "NVIDIA P100",       "vram_gb": 16,  "demand": 1.46,  "spot": 0.44},
    {"name": "NVIDIA P4",         "vram_gb": 8,   "demand": 0.60,  "spot": 0.18},
    {"name": "NVIDIA K80",        "vram_gb": 12,  "demand": 0.45,  "spot": 0.13},
    {"name": "NVIDIA H200 141GB", "vram_gb": 141, "demand": 16.11, "spot": 4.83},
]


def fetch_google_cloud_gpus():
    """Return Google Cloud GPU pricing from static catalog.

    Google Cloud Compute Engine requires OAuth for their API, so we maintain
    a static pricing catalog from their published pricing page. Prices are
    per-GPU per-hour for us-central1.
    """
    results = []
    for gpu in _GOOGLE_CLOUD_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["spot"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
                "spot_min":   gpu["spot"],
                "spot_avg":   gpu["spot"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Google Cloud: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — CoreWeave (static catalog, no public API)
# ---------------------------------------------------------------------------

# CoreWeave GPU pricing (per-GPU per-hour)
# Source: https://www.coreweave.com/pricing
# Note: CoreWeave sells in multi-GPU packs; prices below are per-GPU
_COREWEAVE_GPUS = [
    {"name": "NVIDIA GB200 NVL72",      "vram_gb": 186, "demand": 10.50, "spot": None},
    {"name": "NVIDIA HGX B200",         "vram_gb": 180, "demand": 8.60,  "spot": 4.26},
    {"name": "NVIDIA HGX B300",         "vram_gb": 270, "demand": None,  "spot": 4.48},
    {"name": "RTX PRO 6000 Blackwell",  "vram_gb": 96,  "demand": 2.50,  "spot": 1.39},
    {"name": "NVIDIA HGX H100",         "vram_gb": 80,  "demand": 6.16,  "spot": 2.46},
    {"name": "NVIDIA HGX H200",         "vram_gb": 141, "demand": 6.31,  "spot": 2.62},
    {"name": "NVIDIA GH200",            "vram_gb": 96,  "demand": 6.50,  "spot": None},
    {"name": "NVIDIA L40",              "vram_gb": 48,  "demand": 1.25,  "spot": 0.78},
    {"name": "NVIDIA L40S",             "vram_gb": 48,  "demand": 2.25,  "spot": 0.99},
    {"name": "NVIDIA A100 80GB",        "vram_gb": 80,  "demand": 2.70,  "spot": 1.21},
]


def fetch_coreweave_gpus():
    """Return CoreWeave GPU pricing from static catalog.

    CoreWeave has no public pricing API. Prices maintained from their
    published pricing page; per-GPU rates derived from multi-GPU packs.
    """
    results = []
    for gpu in _COREWEAVE_GPUS:
        demand = gpu["demand"]
        spot = gpu["spot"]
        all_prices = [p for p in (demand, spot) if p is not None]
        if not all_prices:
            continue

        pricing = {
            "min": min(all_prices),
            "avg": max(all_prices),
        }
        if demand is not None:
            pricing["demand_min"] = demand
            pricing["demand_avg"] = demand
        if spot is not None:
            pricing["spot_min"] = spot
            pricing["spot_avg"] = spot

        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": pricing,
        })

    results.sort(key=lambda x: x["name"])
    print(f"  CoreWeave: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — FluidStack (static catalog, API offline)
# ---------------------------------------------------------------------------

# FluidStack GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.fluidstack.io/pricing (API at api.fluidstack.io is offline)
_FLUIDSTACK_GPUS = [
    {"name": "NVIDIA H100 SXM",  "vram_gb": 80,  "demand": 2.25},
    {"name": "NVIDIA H100 PCIe", "vram_gb": 80,  "demand": 2.05},
    {"name": "NVIDIA A100 80GB", "vram_gb": 80,  "demand": 1.30},
    {"name": "NVIDIA A100 40GB", "vram_gb": 40,  "demand": 0.80},
    {"name": "NVIDIA L40S",      "vram_gb": 48,  "demand": 1.20},
]


def fetch_fluidstack_gpus():
    """Return FluidStack GPU pricing from static catalog.

    FluidStack's API (api.fluidstack.io) is currently offline. Prices
    maintained from their published pricing page. On-demand only.
    """
    results = []
    for gpu in _FLUIDSTACK_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  FluidStack: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — DataCrunch / Verda (public API, no auth)
# ---------------------------------------------------------------------------

DATACRUNCH_API_URL = "https://api.datacrunch.io/v1/instance-types"


def fetch_datacrunch_gpus():
    """Fetch GPU instance types and pricing from DataCrunch/Verda API (no auth).

    The DataCrunch API returns all instance types including multi-GPU configs.
    We filter to single-GPU entries for per-GPU pricing, then aggregate by
    GPU model for min/avg/spot prices.
    """
    data = http_get(DATACRUNCH_API_URL)
    if not data or not isinstance(data, list):
        print("  DataCrunch: API returned no data")
        return []

    gpu_groups = {}
    for instance in data:
        if not isinstance(instance, dict):
            continue
        gpu_info = instance.get("gpu") or {}
        num_gpus = gpu_info.get("number_of_gpus", 1)
        if num_gpus != 1:
            continue  # skip multi-GPU for per-GPU pricing

        model = instance.get("model") or ""
        name = instance.get("name") or model
        gpu_mem = instance.get("gpu_memory") or {}
        vram = gpu_mem.get("size_in_gigabytes", 0)

        price_str = instance.get("price_per_hour", "0")
        spot_str = instance.get("spot_price", "0")
        try:
            price = float(price_str)
            spot = float(spot_str)
        except (ValueError, TypeError):
            continue

        if model not in gpu_groups:
            gpu_groups[model] = {
                "name": name,
                "vram_gb": vram,
                "demand_prices": [],
                "spot_prices": [],
            }

        if price > 0:
            gpu_groups[model]["demand_prices"].append(price)
        if spot > 0:
            gpu_groups[model]["spot_prices"].append(spot)

    results = []
    for model, gdata in gpu_groups.items():
        demand = gdata["demand_prices"]
        spot = gdata["spot_prices"]
        all_prices = demand + spot
        if not all_prices:
            continue

        pricing = {
            "min": min(all_prices),
            "avg": sum(demand) / len(demand) if demand else min(all_prices),
            "max": max(all_prices),
        }
        if demand:
            pricing["demand_min"] = min(demand)
            pricing["demand_avg"] = sum(demand) / len(demand)
        if spot:
            pricing["spot_min"] = min(spot)
            pricing["spot_avg"] = sum(spot) / len(spot)

        results.append({
            "name": gdata["name"],
            "vram_gb": gdata["vram_gb"],
            "pricing": pricing,
        })

    results.sort(key=lambda x: x["name"])
    print(f"  DataCrunch: {len(results)} GPU types from API")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Jarvis Labs (static catalog, API unavailable)
# ---------------------------------------------------------------------------

# Jarvis Labs GPU pricing (per-GPU per-hour, on-demand)
# Source: https://jarvislabs.ai/pricing
_JARVISLABS_GPUS = [
    {"name": "NVIDIA H200 SXM",          "vram_gb": 141, "demand": 3.99},
    {"name": "NVIDIA H100 SXM",          "vram_gb": 80,  "demand": 2.69},
    {"name": "RTX PRO 6000 Blackwell",   "vram_gb": 96,  "demand": 1.89},
    {"name": "NVIDIA A100 80GB",         "vram_gb": 80,  "demand": 1.49},
    {"name": "NVIDIA A100 40GB",         "vram_gb": 40,  "demand": 0.89},
    {"name": "NVIDIA A30",               "vram_gb": 24,  "demand": 0.41},
    {"name": "NVIDIA L4",                "vram_gb": 24,  "demand": 0.44},
]


def fetch_jarvislabs_gpus():
    """Return Jarvis Labs GPU pricing from static catalog.

    Jarvis Labs API is behind auth and currently unreachable. Prices
    maintained from their published pricing page. On-demand only.
    """
    results = []
    for gpu in _JARVISLABS_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Jarvis Labs: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Paperspace (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Paperspace GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.paperspace.com/pricing
# Note: Paperspace is now part of DigitalOcean
_PAPERSPACE_GPUS = [
    {"name": "NVIDIA H100",     "vram_gb": 80,  "demand": 5.95},
    {"name": "NVIDIA A100 80G", "vram_gb": 80,  "demand": 3.18},
    {"name": "NVIDIA A6000",    "vram_gb": 48,  "demand": 1.89},
    {"name": "NVIDIA A5000",    "vram_gb": 24,  "demand": 1.38},
    {"name": "NVIDIA A4000",    "vram_gb": 16,  "demand": 0.76},
    {"name": "NVIDIA V100",     "vram_gb": 16,  "demand": 2.30},
    {"name": "NVIDIA P6000",    "vram_gb": 24,  "demand": 1.10},
    {"name": "NVIDIA RTX5000",  "vram_gb": 16,  "demand": 0.82},
    {"name": "NVIDIA P5000",    "vram_gb": 16,  "demand": 0.78},
    {"name": "NVIDIA RTX4000",  "vram_gb": 8,   "demand": 0.56},
    {"name": "NVIDIA P4000",    "vram_gb": 8,   "demand": 0.51},
    {"name": "NVIDIA M4000",    "vram_gb": 8,   "demand": 0.45},
]


def fetch_paperspace_gpus():
    """Return Paperspace GPU pricing from static catalog.

    Paperspace (now part of DigitalOcean) requires auth for their API.
    Prices maintained from their published pricing page. On-demand only.
    """
    results = []
    for gpu in _PAPERSPACE_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Paperspace: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Salad (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# SaladCloud GPU pricing (per-GPU per-hour, on-demand)
# Source: https://salad.com/pricing
# Note: Distributed GPU cloud using consumer GPUs; very low prices
_SALAD_GPUS = [
    {"name": "NVIDIA RTX 3070",    "vram_gb": 8,  "demand": 0.040},
    {"name": "NVIDIA RTX 3080",    "vram_gb": 10, "demand": 0.060},
    {"name": "NVIDIA RTX 3090",    "vram_gb": 24, "demand": 0.090},
    {"name": "NVIDIA RTX 4070",    "vram_gb": 12, "demand": 0.050},
    {"name": "NVIDIA RTX 4080",    "vram_gb": 16, "demand": 0.120},
    {"name": "NVIDIA RTX 4090",    "vram_gb": 24, "demand": 0.160},
    {"name": "NVIDIA RTX 5060",    "vram_gb": 12, "demand": 0.065},
    {"name": "NVIDIA RTX 5070 Ti", "vram_gb": 16, "demand": 0.100},
    {"name": "NVIDIA RTX 5080",    "vram_gb": 16, "demand": 0.180},
    {"name": "NVIDIA RTX 5090",    "vram_gb": 32, "demand": 0.250},
    {"name": "NVIDIA RTX A5000",   "vram_gb": 24, "demand": 0.090},
]


def fetch_salad_gpus():
    """Return SaladCloud GPU pricing from static catalog.

    SaladCloud is a distributed GPU cloud using consumer hardware.
    API requires auth. Prices from their published pricing page.
    On-demand only; no spot tier (already lowest-cost via distributed model).
    """
    results = []
    for gpu in _SALAD_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Salad: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Crusoe (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Crusoe Cloud GPU pricing (per-GPU per-hour)
# Source: https://crusoe.ai/cloud/pricing
_CRUSOE_GPUS = [
    {"name": "NVIDIA L40S",        "vram_gb": 48,  "demand": 1.50, "spot": None},
    {"name": "NVIDIA A100 PCIe",   "vram_gb": 80,  "demand": 2.00, "spot": None},
    {"name": "NVIDIA A100 SXM",    "vram_gb": 80,  "demand": 2.30, "spot": None},
    {"name": "AMD MI300X",         "vram_gb": 192, "demand": 3.45, "spot": None},
    {"name": "NVIDIA H100 HGX",    "vram_gb": 80,  "demand": 3.90, "spot": None},
    {"name": "NVIDIA H200 HGX",    "vram_gb": 141, "demand": 4.29, "spot": None},
]


def fetch_crusoe_gpus():
    """Return Crusoe Cloud GPU pricing from static catalog.

    Crusoe (clean energy GPU cloud) requires auth for their API.
    Prices maintained from their published pricing page. On-demand only;
    spot pricing available but discounts vary (30-70%), not listed statically.
    """
    results = []
    for gpu in _CRUSOE_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Crusoe: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Hyperstack (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Hyperstack GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.hyperstack.cloud/gpu-pricing
_HYPERSTACK_GPUS = [
    {"name": "NVIDIA A4000",           "vram_gb": 16,  "demand": 0.15},
    {"name": "NVIDIA A6000",           "vram_gb": 48,  "demand": 0.50},
    {"name": "NVIDIA L40",             "vram_gb": 48,  "demand": 1.00},
    {"name": "NVIDIA A100 80GB",       "vram_gb": 80,  "demand": 1.35},
    {"name": "NVIDIA A100 NVLink",     "vram_gb": 80,  "demand": 1.40},
    {"name": "NVIDIA A100 SXM",        "vram_gb": 80,  "demand": 1.60},
    {"name": "RTX PRO 6000 Blackwell", "vram_gb": 96,  "demand": 1.80},
    {"name": "NVIDIA H100",            "vram_gb": 80,  "demand": 1.90},
    {"name": "NVIDIA H100 NVLink",     "vram_gb": 80,  "demand": 1.95},
    {"name": "NVIDIA H100 SXM",        "vram_gb": 80,  "demand": 2.40},
    {"name": "NVIDIA H200 SXM",        "vram_gb": 141, "demand": 3.50},
]


def fetch_hyperstack_gpus():
    """Return Hyperstack GPU pricing from static catalog.

    Hyperstack requires auth for their API. Prices maintained from their
    published GPU pricing page. On-demand only.
    """
    results = []
    for gpu in _HYPERSTACK_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Hyperstack: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Nebius (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Nebius AI GPU pricing (per-GPU per-hour, on-demand)
# Source: https://nebius.com/prices
_NEBIUS_GPUS = [
    {"name": "NVIDIA L40S",            "vram_gb": 48,  "demand": 1.55},
    {"name": "RTX PRO 6000 Blackwell", "vram_gb": 96,  "demand": 1.80},
    {"name": "NVIDIA H100 SXM",        "vram_gb": 80,  "demand": 2.55},
    {"name": "NVIDIA H200 SXM",        "vram_gb": 141, "demand": 4.50},
    {"name": "NVIDIA B200 SXM",        "vram_gb": 192, "demand": 5.50},
    {"name": "NVIDIA B300 SXM",        "vram_gb": 288, "demand": 7.85},
]


def fetch_nebius_gpus():
    """Return Nebius AI GPU pricing from static catalog.

    Nebius requires auth for their API. Prices maintained from their
    published pricing page. On-demand only; spot available at 50-80%
    discount but varies dynamically.
    """
    results = []
    for gpu in _NEBIUS_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Nebius: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — DigitalOcean (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# DigitalOcean GPU Droplets pricing (per-GPU per-hour, on-demand)
# Source: https://www.digitalocean.com/pricing/gpu-droplets
_DIGITALOCEAN_GPUS = [
    {"name": "NVIDIA L40S",   "vram_gb": 48,  "demand": 0.76},
    {"name": "AMD MI300X",    "vram_gb": 192, "demand": 3.41},
    {"name": "NVIDIA H100",   "vram_gb": 80,  "demand": 4.24},
    {"name": "NVIDIA H200",   "vram_gb": 141, "demand": 7.99},
]


def fetch_digitalocean_gpus():
    """Return DigitalOcean GPU Droplets pricing from static catalog.

    DigitalOcean requires auth for their API. Prices maintained from
    their published GPU Droplets pricing page. On-demand only.
    """
    results = []
    for gpu in _DIGITALOCEAN_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  DigitalOcean: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — OVHcloud (static catalog, no auth needed)
# ---------------------------------------------------------------------------

# OVHcloud GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.ovhcloud.com/en/public-cloud/prices/
# Note: Prices converted from EUR to USD at ~1.10 rate
_OVH_GPUS = [
    {"name": "NVIDIA L4",          "vram_gb": 24,  "demand": 0.50},
    {"name": "NVIDIA L40S",        "vram_gb": 48,  "demand": 0.75},
    {"name": "NVIDIA A100 PCIe",   "vram_gb": 80,  "demand": 1.43},
    {"name": "NVIDIA H100 PCIe",   "vram_gb": 80,  "demand": 1.67},
    {"name": "NVIDIA H100 SXM",    "vram_gb": 80,  "demand": 2.04},
    {"name": "NVIDIA H200 SXM",    "vram_gb": 141, "demand": 3.30},
]


def fetch_ovh_gpus():
    """Return OVHcloud GPU pricing from static catalog.

    OVHcloud pricing page is public but requires instance configuration
    to see exact rates. Prices here are approximate EUR->USD conversions
    from their published European datacenter rates. On-demand only.
    """
    results = []
    for gpu in _OVH_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  OVHcloud: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Hetzner (static catalog, no auth needed)
# ---------------------------------------------------------------------------

# Hetzner GPU server pricing (per-GPU per-hour, on-demand)
# Source: https://www.hetzner.com/dedicated-rootserver/
# Note: Prices converted from EUR monthly to USD hourly (~730 hrs/month, EUR*1.10)
_HETZNER_GPUS = [
    {"name": "NVIDIA RTX 4000 SFF Ada",    "vram_gb": 20,  "demand": 0.28},
    {"name": "RTX PRO 6000 Blackwell",     "vram_gb": 96,  "demand": 1.34},
]


def fetch_hetzner_gpus():
    """Return Hetzner GPU pricing from static catalog.

    Hetzner offers dedicated GPU servers with monthly billing (capped hourly).
    Prices converted from EUR/month to USD/hour. Limited GPU selection.
    """
    results = []
    for gpu in _HETZNER_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Hetzner: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Scaleway (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Scaleway GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.scaleway.com/en/gpu-instances/
_SCALEWAY_GPUS = [
    {"name": "NVIDIA L4",          "vram_gb": 24,  "demand": 0.90},
    {"name": "NVIDIA L40S",        "vram_gb": 48,  "demand": 1.68},
    {"name": "NVIDIA H100 PCIe",   "vram_gb": 80,  "demand": 3.27},
    {"name": "NVIDIA H100 SXM",    "vram_gb": 80,  "demand": 3.61},
    {"name": "NVIDIA B300 SXM",    "vram_gb": 262, "demand": 8.55},
]


def fetch_scaleway_gpus():
    """Return Scaleway GPU pricing from static catalog.

    Scaleway requires auth for their API. Prices maintained from their
    published GPU instances page. On-demand only; available in Paris
    and Warsaw regions.
    """
    results = []
    for gpu in _SCALEWAY_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Scaleway: {len(results)} GPU types (static catalog)")
    return results


# ---------------------------------------------------------------------------
# GPU pricing collection — Alibaba Cloud (static catalog, API requires auth)
# ---------------------------------------------------------------------------

# Alibaba Cloud GPU pricing (per-GPU per-hour, on-demand)
# Source: https://www.alibabacloud.com/product/gpu
# Note: Prices are approximate US region rates
_ALIBABA_GPUS = [
    {"name": "NVIDIA T4",          "vram_gb": 16,  "demand": 0.45},
    {"name": "NVIDIA V100",        "vram_gb": 16,  "demand": 2.55},
    {"name": "NVIDIA A100 80GB",   "vram_gb": 80,  "demand": 3.67},
    {"name": "NVIDIA L40S",        "vram_gb": 48,  "demand": 1.75},
]


def fetch_alibaba_gpus():
    """Return Alibaba Cloud GPU pricing from static catalog.

    Alibaba Cloud requires auth for their API. Prices approximate from
    their published pricing (US region). On-demand only.
    """
    results = []
    for gpu in _ALIBABA_GPUS:
        results.append({
            "name": gpu["name"],
            "vram_gb": gpu["vram_gb"],
            "pricing": {
                "min":        gpu["demand"],
                "avg":        gpu["demand"],
                "demand_min": gpu["demand"],
                "demand_avg": gpu["demand"],
            },
        })
    results.sort(key=lambda x: x["name"])
    print(f"  Alibaba Cloud: {len(results)} GPU types (static catalog)")
    return results


def update_gpu_rollups(gpu_snapshot, today):
    """Append today's prices to per-GPU history files for all providers."""

    # RunPod — legacy path (no provider prefix) kept for backward compat
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

    # Vast.ai — own history path (like other providers)
    _write_provider_rollup("vast", gpu_snapshot.get("vast", {}).get("gpus", []), today, {
        "min":          "min",
        "max":          "max",
        "avg":          "avg",
        "spot_min":     "spot_min",
        "spot_avg":     "spot_avg",
        "demand_min":   "demand_min",
        "demand_avg":   "demand_avg",
        "rentable_min": "rentable_min",
        "rentable_avg": "rentable_avg",
    })

    # Lambda Labs — on-demand only, per-GPU pricing
    _write_provider_rollup("lambda_labs", gpu_snapshot.get("lambda_labs", {}).get("gpus", []), today, {
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "instance_price": "instance_price",
    })

    # TensorDock — on-demand only
    _write_provider_rollup("tensordock", gpu_snapshot.get("tensordock", {}).get("gpus", []), today, {
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "min":        "min",
        "avg":        "avg",
        "max":        "max",
    })

    # Vultr — on-demand only
    _write_provider_rollup("vultr", gpu_snapshot.get("vultr", {}).get("gpus", []), today, {
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "min":        "min",
        "avg":        "avg",
        "max":        "max",
    })

    # Azure — spot + on-demand
    _write_provider_rollup("azure", gpu_snapshot.get("azure", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "max":        "max",
        "spot_min":   "spot_min",
        "spot_avg":   "spot_avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Oracle Cloud — on-demand only
    _write_provider_rollup("oracle", gpu_snapshot.get("oracle", {}).get("gpus", []), today, {
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # AWS EC2 — on-demand only (spot not yet implemented)
    _write_provider_rollup("aws", gpu_snapshot.get("aws", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "max":        "max",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Thunder Compute — on-demand pricing (prototyping vs production tiers)
    _write_provider_rollup("thunder_compute", gpu_snapshot.get("thunder_compute", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Nova Cloud — on-demand + spot (interruptible) pricing
    _write_provider_rollup("nova_cloud", gpu_snapshot.get("nova_cloud", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "spot_min":   "spot_min",
        "spot_avg":   "spot_avg",
    })

    # Google Cloud — on-demand + spot
    _write_provider_rollup("google_cloud", gpu_snapshot.get("google_cloud", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "spot_min":   "spot_min",
        "spot_avg":   "spot_avg",
    })

    # CoreWeave — on-demand + spot
    _write_provider_rollup("coreweave", gpu_snapshot.get("coreweave", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "spot_min":   "spot_min",
        "spot_avg":   "spot_avg",
    })

    # FluidStack — on-demand only
    _write_provider_rollup("fluidstack", gpu_snapshot.get("fluidstack", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # DataCrunch/Verda — on-demand + spot
    _write_provider_rollup("datacrunch", gpu_snapshot.get("datacrunch", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "max":        "max",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
        "spot_min":   "spot_min",
        "spot_avg":   "spot_avg",
    })

    # Jarvis Labs — on-demand only
    _write_provider_rollup("jarvis_labs", gpu_snapshot.get("jarvis_labs", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Paperspace — on-demand only
    _write_provider_rollup("paperspace", gpu_snapshot.get("paperspace", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # SaladCloud — on-demand only
    _write_provider_rollup("salad", gpu_snapshot.get("salad", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Crusoe — on-demand only
    _write_provider_rollup("crusoe", gpu_snapshot.get("crusoe", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Hyperstack — on-demand only
    _write_provider_rollup("hyperstack", gpu_snapshot.get("hyperstack", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Nebius — on-demand only
    _write_provider_rollup("nebius", gpu_snapshot.get("nebius", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # DigitalOcean — on-demand only
    _write_provider_rollup("digitalocean", gpu_snapshot.get("digitalocean", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # OVHcloud — on-demand only
    _write_provider_rollup("ovh", gpu_snapshot.get("ovh", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Hetzner — on-demand only
    _write_provider_rollup("hetzner", gpu_snapshot.get("hetzner", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Scaleway — on-demand only
    _write_provider_rollup("scaleway", gpu_snapshot.get("scaleway", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    # Alibaba Cloud — on-demand only
    _write_provider_rollup("alibaba", gpu_snapshot.get("alibaba", {}).get("gpus", []), today, {
        "min":        "min",
        "avg":        "avg",
        "demand_min": "demand_min",
        "demand_avg": "demand_avg",
    })

    _all_providers = (
        "runpod", "vast", "lambda_labs", "tensordock", "vultr", "azure",
        "oracle", "aws", "thunder_compute", "nova_cloud",
        "google_cloud", "coreweave", "fluidstack", "datacrunch", "jarvis_labs",
        "paperspace", "salad", "crusoe", "hyperstack", "nebius",
        "digitalocean", "ovh", "hetzner", "scaleway", "alibaba",
    )
    counts = {
        k: len(gpu_snapshot.get(k, {}).get("gpus", []))
        for k in _all_providers
    }
    print(f"GPU rollups updated: {counts}")


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

    # GPU rental pricing (all providers)
    print("Fetching GPU rental pricing...")
    runpod_gpus          = fetch_runpod_gpus()
    vast_gpus            = fetch_vastai_gpus()
    lambdalabs_gpus      = fetch_lambdalabs_gpus()
    tensordock_gpus      = fetch_tensordock_gpus()
    vultr_gpus           = fetch_vultr_gpus()
    azure_gpus           = fetch_azure_gpus()
    oracle_gpus          = fetch_oracle_gpus()
    aws_gpus             = fetch_aws_gpus()
    thunder_compute_gpus = fetch_thunder_compute_gpus()
    nova_cloud_gpus      = fetch_nova_cloud_gpus()
    google_cloud_gpus    = fetch_google_cloud_gpus()
    coreweave_gpus       = fetch_coreweave_gpus()
    fluidstack_gpus      = fetch_fluidstack_gpus()
    datacrunch_gpus      = fetch_datacrunch_gpus()
    jarvis_labs_gpus     = fetch_jarvislabs_gpus()
    paperspace_gpus      = fetch_paperspace_gpus()
    salad_gpus           = fetch_salad_gpus()
    crusoe_gpus          = fetch_crusoe_gpus()
    hyperstack_gpus      = fetch_hyperstack_gpus()
    nebius_gpus          = fetch_nebius_gpus()
    digitalocean_gpus    = fetch_digitalocean_gpus()
    ovh_gpus             = fetch_ovh_gpus()
    hetzner_gpus         = fetch_hetzner_gpus()
    scaleway_gpus        = fetch_scaleway_gpus()
    alibaba_gpus         = fetch_alibaba_gpus()

    # Build snapshot — always write if at least one provider has data
    _provider_results = {
        "runpod":          runpod_gpus,
        "vast":            vast_gpus,
        "lambda_labs":     lambdalabs_gpus,
        "tensordock":      tensordock_gpus,
        "vultr":           vultr_gpus,
        "azure":           azure_gpus,
        "oracle":          oracle_gpus,
        "aws":             aws_gpus,
        "thunder_compute": thunder_compute_gpus,
        "nova_cloud":      nova_cloud_gpus,
        "google_cloud":    google_cloud_gpus,
        "coreweave":       coreweave_gpus,
        "fluidstack":      fluidstack_gpus,
        "datacrunch":      datacrunch_gpus,
        "jarvis_labs":     jarvis_labs_gpus,
        "paperspace":      paperspace_gpus,
        "salad":           salad_gpus,
        "crusoe":          crusoe_gpus,
        "hyperstack":      hyperstack_gpus,
        "nebius":          nebius_gpus,
        "digitalocean":    digitalocean_gpus,
        "ovh":             ovh_gpus,
        "hetzner":         hetzner_gpus,
        "scaleway":        scaleway_gpus,
        "alibaba":         alibaba_gpus,
    }

    # Normalise GPU names across all providers for cross-provider comparison
    for provider_key, gpus in _provider_results.items():
        for gpu in gpus:
            gpu["name"] = normalize_gpu_name(gpu["name"])

    any_data = any(gpus for gpus in _provider_results.values())

    if any_data:
        gpu_snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runpod":          {"name": "RunPod",           "total_gpus": len(runpod_gpus),          "gpus": runpod_gpus},
            "vast":            {"name": "Vast.ai",          "total_gpus": len(vast_gpus),            "gpus": vast_gpus},
            "lambda_labs":     {"name": "Lambda Labs",      "total_gpus": len(lambdalabs_gpus),      "gpus": lambdalabs_gpus},
            "tensordock":      {"name": "TensorDock",       "total_gpus": len(tensordock_gpus),      "gpus": tensordock_gpus},
            "vultr":           {"name": "Vultr",            "total_gpus": len(vultr_gpus),           "gpus": vultr_gpus},
            "azure":           {"name": "Azure",            "total_gpus": len(azure_gpus),           "gpus": azure_gpus},
            "oracle":          {"name": "Oracle Cloud",     "total_gpus": len(oracle_gpus),          "gpus": oracle_gpus},
            "aws":             {"name": "AWS EC2",          "total_gpus": len(aws_gpus),             "gpus": aws_gpus},
            "thunder_compute": {"name": "Thunder Compute",  "total_gpus": len(thunder_compute_gpus), "gpus": thunder_compute_gpus},
            "nova_cloud":      {"name": "Nova Cloud",       "total_gpus": len(nova_cloud_gpus),      "gpus": nova_cloud_gpus},
            "google_cloud":    {"name": "Google Cloud",     "total_gpus": len(google_cloud_gpus),    "gpus": google_cloud_gpus},
            "coreweave":       {"name": "CoreWeave",        "total_gpus": len(coreweave_gpus),       "gpus": coreweave_gpus},
            "fluidstack":      {"name": "FluidStack",       "total_gpus": len(fluidstack_gpus),      "gpus": fluidstack_gpus},
            "datacrunch":      {"name": "DataCrunch",       "total_gpus": len(datacrunch_gpus),      "gpus": datacrunch_gpus},
            "jarvis_labs":     {"name": "Jarvis Labs",      "total_gpus": len(jarvis_labs_gpus),     "gpus": jarvis_labs_gpus},
            "paperspace":      {"name": "Paperspace",       "total_gpus": len(paperspace_gpus),      "gpus": paperspace_gpus},
            "salad":           {"name": "SaladCloud",       "total_gpus": len(salad_gpus),           "gpus": salad_gpus},
            "crusoe":          {"name": "Crusoe",           "total_gpus": len(crusoe_gpus),          "gpus": crusoe_gpus},
            "hyperstack":      {"name": "Hyperstack",       "total_gpus": len(hyperstack_gpus),      "gpus": hyperstack_gpus},
            "nebius":          {"name": "Nebius",           "total_gpus": len(nebius_gpus),           "gpus": nebius_gpus},
            "digitalocean":    {"name": "DigitalOcean",     "total_gpus": len(digitalocean_gpus),    "gpus": digitalocean_gpus},
            "ovh":             {"name": "OVHcloud",         "total_gpus": len(ovh_gpus),             "gpus": ovh_gpus},
            "hetzner":         {"name": "Hetzner",          "total_gpus": len(hetzner_gpus),         "gpus": hetzner_gpus},
            "scaleway":        {"name": "Scaleway",         "total_gpus": len(scaleway_gpus),        "gpus": scaleway_gpus},
            "alibaba":         {"name": "Alibaba Cloud",    "total_gpus": len(alibaba_gpus),         "gpus": alibaba_gpus},
        }

        # Carry forward last known data for any provider that returned nothing
        # (key absent, API down, etc.) so the dashboard never goes blank.
        prev = None
        for provider_key, gpus in _provider_results.items():
            if not gpus:
                if prev is None:
                    prev = s3_get_json("rollups/gpu/latest.json") or {}
                prev_provider = prev.get(provider_key, {})
                if prev_provider.get("gpus"):
                    gpu_snapshot[provider_key] = prev_provider
                    print(f"  {provider_key}: no new data — carrying forward "
                          f"{len(prev_provider['gpus'])} existing entries")

        s3_put_json(f"snapshots/gpu/{today}.json", gpu_snapshot, cache_seconds=86400)
        s3_put_json("rollups/gpu/latest.json", gpu_snapshot, cache_seconds=3600)
        update_gpu_rollups(gpu_snapshot, today)
        counts = {k: len(v["gpus"]) for k, v in gpu_snapshot.items() if isinstance(v, dict) and "gpus" in v}
        print(f"GPU pricing saved: {counts}")
    else:
        print("No GPU data available — check API keys in SSM (/dame/gpu/*)")

    # Daily report with advanced features (TTS, STT, video, image gen)
    print("Generating daily report with advanced features...")
    daily_report = generate_daily_report(models, infra_map)
    s3_put_json("rollups/daily_report.json", daily_report, cache_seconds=3600)
    print(f"Daily report saved: {daily_report['overall_stats']['advanced_feature_models']} models with advanced features")

    print("Done.")
    return {"statusCode": 200, "date": today}
