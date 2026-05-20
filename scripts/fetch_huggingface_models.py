#!/usr/bin/env python3
"""
Fetch top models from HuggingFace Hub API by pipeline type.

No auth required (but rate-limited to 500 req/5 min without token).
Set HF_TOKEN env var for higher limits.

Pipeline tags: automatic-speech-recognition, text-to-speech, text-to-image, text-to-video
"""

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "https://huggingface.co/api"
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Pipeline tags and how many top models to fetch per category
PIPELINE_CONFIGS = {
    "automatic-speech-recognition": {"category": "stt", "top_n": 100},
    "text-to-speech": {"category": "tts", "top_n": 100},
    "text-to-image": {"category": "image_generation", "top_n": 100},
    "text-to-video": {"category": "video_generation", "top_n": 50},
}


def fetch_models_list(pipeline_tag, limit=100, offset=0):
    """Fetch models list sorted by downloads."""
    params = {
        "pipeline_tag": pipeline_tag,
        "sort": "downloads",
        "direction": "-1",
        "limit": str(limit),
        "full": "true",
    }
    if offset > 0:
        params["offset"] = str(offset)

    url = f"{BASE_URL}/models?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    if HF_TOKEN:
        req.add_header("Authorization", f"Bearer {HF_TOKEN}")

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_model_detail(model_id):
    """Fetch detailed model info including param count."""
    url = f"{BASE_URL}/models/{model_id}"
    req = urllib.request.Request(url)
    if HF_TOKEN:
        req.add_header("Authorization", f"Bearer {HF_TOKEN}")

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"    Error fetching {model_id}: {e.code}")
        return None


def extract_license(tags):
    """Extract license from tags array."""
    for tag in (tags or []):
        if tag.startswith("license:"):
            return tag.replace("license:", "")
    return None


def extract_languages(tags):
    """Extract language codes from tags (2-letter codes)."""
    langs = []
    for tag in (tags or []):
        if len(tag) == 2 and tag.isalpha() and not tag.startswith("license"):
            langs.append(tag)
    return langs


def normalize_to_schema(model, detail=None):
    """Convert HuggingFace model to our unified schema."""
    model_id = model.get("id", model.get("modelId", ""))
    tags = model.get("tags", [])
    pipeline_tag = model.get("pipeline_tag", "")

    # Map pipeline to category
    category_map = {
        "automatic-speech-recognition": "stt",
        "text-to-speech": "tts",
        "text-to-image": "image_generation",
        "text-to-video": "video_generation",
    }

    # Extract param count from detail if available
    params = None
    if detail:
        safetensors = detail.get("safetensors", {})
        if safetensors:
            params = safetensors.get("total")

    license_id = extract_license(tags)
    languages = extract_languages(tags)

    return {
        "model_id": f"huggingface/{model_id}",
        "display_name": model_id.split("/")[-1] if "/" in model_id else model_id,
        "provider": model_id.split("/")[0] if "/" in model_id else "community",
        "provider_slug": "huggingface",
        "category": category_map.get(pipeline_tag, pipeline_tag),
        "hf_model_id": model_id,
        "connection_types": {
            "rest_sync": "endpoints_compatible" in tags,
            "rest_batch": False,
            "rest_streaming": False,
            "websocket_streaming": False,
            "grpc": False,
            "sse": False,
        },
        "capabilities": {
            "real_time": False,
            "streaming": False,
            "multilingual": len(languages) > 1,
            "languages": languages,
            "language_count": len(languages) if languages else None,
            "self_hostable": True,
            "inference_api": "endpoints_compatible" in tags,
        },
        "pricing": {
            "model": "open_source",
            "amount": 0,
            "currency": "USD",
            "unit": "free",
            "normalized": {},
            "free_tier": True,
            "notes": "Open source - self-host or use via inference providers",
        },
        "technical": {
            "parameters": params,
            "architecture": model.get("library_name", "unknown"),
            "license": license_id or "unknown",
            "open_source": True,
            "self_hostable": True,
            "openai_compatible": False,
        },
        "popularity": {
            "hf_downloads": model.get("downloads", 0),
            "hf_likes": model.get("likes", 0),
        },
        "provider_info": {
            "signup_url": "https://huggingface.co/join",
            "model_url": f"https://huggingface.co/{model_id}",
            "api_base_url": "https://huggingface.co/api",
        },
        "data_source": "huggingface_api",
    }


def main():
    print("=" * 60)
    print("Fetching top models from HuggingFace Hub")
    print("=" * 60)

    if HF_TOKEN:
        print("HF_TOKEN found — using authenticated requests (1000 req/5min)")
    else:
        print("No HF_TOKEN — using anonymous rate limits (500 req/5min)")

    os.makedirs("data", exist_ok=True)
    all_normalized = []
    all_raw = {}

    for pipeline_tag, config in PIPELINE_CONFIGS.items():
        category = config["category"]
        top_n = config["top_n"]
        print(f"\nPipeline: {pipeline_tag} (category: {category}, top {top_n})")

        # Fetch list
        models = fetch_models_list(pipeline_tag, limit=top_n)
        print(f"  Fetched {len(models)} models")
        all_raw[pipeline_tag] = models

        # Fetch details for top 20 to get param counts
        detailed_models = []
        detail_count = min(20, len(models))
        print(f"  Fetching details for top {detail_count}...")

        for i, model in enumerate(models[:detail_count]):
            model_id = model.get("id", model.get("modelId", ""))
            detail = fetch_model_detail(model_id)
            normalized = normalize_to_schema(model, detail)
            detailed_models.append(normalized)

            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{detail_count} done")
            time.sleep(0.3)  # Rate limiting

        # Normalize remaining without detail fetch
        for model in models[detail_count:]:
            normalized = normalize_to_schema(model)
            detailed_models.append(normalized)

        all_normalized.extend(detailed_models)
        print(f"  Processed {len(detailed_models)} models for {category}")

    # Save raw data
    output_raw = "data/huggingface_models_raw.json"
    with open(output_raw, "w") as f:
        json.dump(all_raw, f, indent=2)
    print(f"\nSaved raw data: {output_raw}")

    # Save normalized data
    output_normalized = "data/huggingface_models.json"
    with open(output_normalized, "w") as f:
        json.dump(all_normalized, f, indent=2)
    print(f"Saved normalized data: {output_normalized} ({len(all_normalized)} models)")

    # Summary
    from collections import Counter
    categories = Counter(m["category"] for m in all_normalized)
    print("\nCategory breakdown:")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")

    # Top models by downloads per category
    print("\nTop 5 by downloads per category:")
    for cat in ["stt", "tts", "image_generation", "video_generation"]:
        cat_models = [m for m in all_normalized if m["category"] == cat]
        cat_models.sort(key=lambda x: x["popularity"].get("hf_downloads", 0), reverse=True)
        print(f"\n  {cat}:")
        for m in cat_models[:5]:
            dl = m["popularity"].get("hf_downloads", 0)
            params = m["technical"].get("parameters")
            params_str = f" ({params/1e9:.1f}B)" if params else ""
            print(f"    {m['hf_model_id']}: {dl:,} downloads{params_str}")


if __name__ == "__main__":
    main()
