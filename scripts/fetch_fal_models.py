#!/usr/bin/env python3
"""
Fetch all models from fal.ai API with pricing.

Model listing requires no auth.
Pricing requires FAL_API_KEY environment variable.

Categories: text-to-image, image-to-video, text-to-speech, speech-to-text, text-to-video, etc.
"""

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

BASE_URL = "https://api.fal.ai/v1"
FAL_API_KEY = os.environ.get("FAL_API_KEY", "")

# Categories relevant to our tracker
CATEGORIES = [
    "text-to-image",
    "image-to-image",
    "image-to-video",
    "text-to-video",
    "text-to-speech",
    "speech-to-text",
    "text-to-music",
    "text-to-audio",
]


def fetch_models_page(category=None, cursor=None, limit=100, retries=3):
    """Fetch a single page of models from fal.ai with retry on rate limit."""
    params = {"limit": str(limit), "status": "active"}
    if category:
        params["category"] = category
    if cursor:
        params["cursor"] = cursor

    url = f"{BASE_URL}/models?{urllib.parse.urlencode(params)}"

    for attempt in range(retries):
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = (attempt + 1) * 10
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def fetch_all_models(category=None):
    """Paginate through all models for a given category."""
    all_models = []
    cursor = None
    page = 0

    while True:
        page += 1
        data = fetch_models_page(category=category, cursor=cursor)
        models = data.get("models", [])
        all_models.extend(models)

        print(f"  Page {page}: {len(models)} models (total: {len(all_models)})")

        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data["next_cursor"]
        time.sleep(1.0)  # Respect rate limits

    return all_models


def fetch_pricing(endpoint_ids):
    """Fetch pricing for a batch of endpoint IDs (max 50 per request). Requires auth."""
    if not FAL_API_KEY:
        return {}

    # Batch into groups of 50
    pricing = {}
    for i in range(0, len(endpoint_ids), 50):
        batch = endpoint_ids[i : i + 50]
        params = "&".join(f"endpoint_id={urllib.parse.quote(eid)}" for eid in batch)
        url = f"{BASE_URL}/models/pricing?{params}"

        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Key {FAL_API_KEY}")

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                for price in data.get("prices", []):
                    pricing[price["endpoint_id"]] = {
                        "unit_price": price.get("unit_price"),
                        "unit": price.get("unit"),
                        "currency": price.get("currency", "USD"),
                    }
        except urllib.error.HTTPError as e:
            print(f"  Pricing error for batch starting {batch[0]}: {e.code} {e.reason}")

        time.sleep(0.3)

    return pricing


def normalize_to_schema(model, pricing_data):
    """Convert fal.ai model to our unified schema."""
    endpoint_id = model.get("endpoint_id", "")
    metadata = model.get("metadata", {})
    category = metadata.get("category", "")
    price_info = pricing_data.get(endpoint_id, {})

    # Map fal categories to our categories
    category_map = {
        "text-to-image": "image_generation",
        "image-to-image": "image_generation",
        "image-to-video": "video_generation",
        "text-to-video": "video_generation",
        "text-to-speech": "tts",
        "speech-to-text": "stt",
        "text-to-music": "music_generation",
        "text-to-audio": "music_generation",
    }

    # Normalize pricing
    pricing = {}
    if price_info:
        unit = price_info.get("unit", "")
        amount = price_info.get("unit_price", 0)
        pricing = {
            "model": f"per_{unit}" if unit else "unknown",
            "amount": amount,
            "currency": price_info.get("currency", "USD"),
            "unit": unit,
        }

        # Normalize to standard units
        if category_map.get(category) == "stt" and unit == "second":
            pricing["normalized"] = {"per_hour_usd": amount * 3600}
        elif category_map.get(category) == "tts" and unit == "character":
            pricing["normalized"] = {"per_million_chars_usd": amount * 1_000_000}
        elif unit == "image":
            pricing["normalized"] = {"per_image_usd": amount}
        elif unit == "second" and "video" in category:
            pricing["normalized"] = {"per_second_usd": amount}

    return {
        "model_id": f"fal/{endpoint_id}",
        "display_name": metadata.get("display_name", endpoint_id),
        "provider": "fal.ai",
        "provider_slug": "fal",
        "category": category_map.get(category, category),
        "fal_category": category,
        "fal_endpoint_id": endpoint_id,
        "connection_types": {
            "rest_sync": True,
            "rest_batch": False,
            "rest_streaming": False,
            "websocket_streaming": False,
            "grpc": False,
            "sse": False,
        },
        "capabilities": {
            "real_time": False,
            "streaming": False,
            "description": metadata.get("description", ""),
            "tags": metadata.get("tags", []),
            "license_type": metadata.get("license_type", ""),
        },
        "pricing": pricing,
        "technical": {
            "license": metadata.get("license_type", "unknown"),
            "open_source": metadata.get("license_type") not in ("commercial",),
        },
        "provider_info": {
            "signup_url": "https://fal.ai/dashboard",
            "api_base_url": "https://api.fal.ai",
            "model_url": metadata.get("model_url", ""),
            "thumbnail_url": metadata.get("thumbnail_url", ""),
        },
        "data_source": "fal_api",
    }


def main():
    print("=" * 60)
    print("Fetching models from fal.ai")
    print("=" * 60)

    all_models = []

    for category in CATEGORIES:
        print(f"\nCategory: {category}")
        models = fetch_all_models(category=category)
        print(f"  Found {len(models)} models")
        all_models.extend(models)

    print(f"\nTotal models across all categories: {len(all_models)}")

    # Fetch pricing if we have an API key
    if FAL_API_KEY:
        print("\nFetching pricing (FAL_API_KEY found)...")
        endpoint_ids = [m.get("endpoint_id") for m in all_models if m.get("endpoint_id")]
        pricing_data = fetch_pricing(endpoint_ids)
        print(f"  Got pricing for {len(pricing_data)} models")
    else:
        print("\nNo FAL_API_KEY set — skipping pricing. Set FAL_API_KEY env var to fetch pricing.")
        pricing_data = {}

    # Normalize to unified schema
    normalized = [normalize_to_schema(m, pricing_data) for m in all_models]

    # Save raw data
    output_raw = "data/fal_models_raw.json"
    os.makedirs("data", exist_ok=True)
    with open(output_raw, "w") as f:
        json.dump(all_models, f, indent=2)
    print(f"\nSaved raw data: {output_raw} ({len(all_models)} models)")

    # Save normalized data
    output_normalized = "data/fal_models.json"
    with open(output_normalized, "w") as f:
        json.dump(normalized, f, indent=2)
    print(f"Saved normalized data: {output_normalized} ({len(normalized)} models)")

    # Print summary
    from collections import Counter
    categories = Counter(m["category"] for m in normalized)
    print("\nCategory breakdown:")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
