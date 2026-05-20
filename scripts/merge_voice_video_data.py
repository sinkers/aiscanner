#!/usr/bin/env python3
"""
Merge all voice/video data sources into a single unified dataset.

Reads from:
- data/voice_providers.json (Deepgram, ElevenLabs, OpenAI, Groq, Fireworks, manual providers)
- data/fal_models.json (fal.ai image/video/audio models)
- data/huggingface_models.json (open source models)

Outputs:
- data/voice_video_models.json (unified dataset)
"""

import json
import os
from collections import Counter
from datetime import date


def load_json(path):
    """Load JSON file, return empty list if not found."""
    if not os.path.exists(path):
        print(f"  Warning: {path} not found, skipping")
        return []
    with open(path) as f:
        return json.load(f)


def deduplicate(models):
    """Remove duplicate models (same model on same provider)."""
    seen = set()
    unique = []
    for m in models:
        key = m.get("model_id", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(m)
        elif not key:
            unique.append(m)
    return unique


def enrich_metadata(models):
    """Add computed fields to each model."""
    for m in models:
        # Add last_updated
        m["last_updated"] = str(date.today())

        # Compute streaming_support boolean
        ct = m.get("connection_types", {})
        m["has_streaming"] = (
            ct.get("websocket_streaming", False)
            or ct.get("rest_streaming", False)
            or ct.get("sse", False)
        )

        # Compute real_time boolean
        m["has_real_time"] = m.get("capabilities", {}).get("real_time", False)

    return models


def generate_summary(models):
    """Generate summary statistics."""
    categories = Counter(m.get("category") for m in models)
    providers = Counter(m.get("provider") for m in models)
    data_sources = Counter(m.get("data_source") for m in models)

    # Streaming stats
    streaming = [m for m in models if m.get("has_streaming")]
    realtime = [m for m in models if m.get("has_real_time")]

    # Pricing stats per category
    pricing_stats = {}
    for cat in ["stt", "tts", "image_generation", "video_generation"]:
        cat_models = [m for m in models if m.get("category") == cat]
        priced = [m for m in cat_models if m.get("pricing", {}).get("normalized")]

        if cat == "stt":
            rates = [m["pricing"]["normalized"]["per_hour_usd"]
                     for m in priced if m["pricing"]["normalized"].get("per_hour_usd")]
        elif cat == "tts":
            rates = [m["pricing"]["normalized"]["per_million_chars_usd"]
                     for m in priced if m["pricing"]["normalized"].get("per_million_chars_usd")]
        elif cat == "image_generation":
            rates = [m["pricing"]["normalized"]["per_image_usd"]
                     for m in priced if m["pricing"]["normalized"].get("per_image_usd")]
        elif cat == "video_generation":
            rates = [m["pricing"]["normalized"]["per_second_usd"]
                     for m in priced if m["pricing"]["normalized"].get("per_second_usd")]
        else:
            rates = []

        if rates:
            pricing_stats[cat] = {
                "count": len(cat_models),
                "priced_count": len(rates),
                "min": min(rates),
                "max": max(rates),
                "median": sorted(rates)[len(rates) // 2],
            }
        else:
            pricing_stats[cat] = {"count": len(cat_models), "priced_count": 0}

    return {
        "total_models": len(models),
        "categories": dict(categories.most_common()),
        "providers": dict(providers.most_common()),
        "data_sources": dict(data_sources.most_common()),
        "streaming_support": len(streaming),
        "real_time_support": len(realtime),
        "pricing_stats": pricing_stats,
        "generated_date": str(date.today()),
    }


def main():
    print("=" * 60)
    print("Merging voice/video data sources")
    print("=" * 60)

    os.makedirs("data", exist_ok=True)
    all_models = []

    # Load each data source
    print("\nLoading data sources:")

    voice = load_json("data/voice_providers.json")
    print(f"  voice_providers.json: {len(voice)} models")
    all_models.extend(voice)

    fal = load_json("data/fal_models.json")
    print(f"  fal_models.json: {len(fal)} models")
    all_models.extend(fal)

    hf = load_json("data/huggingface_models.json")
    print(f"  huggingface_models.json: {len(hf)} models")
    all_models.extend(hf)

    print(f"\nTotal before dedup: {len(all_models)}")

    # Deduplicate
    all_models = deduplicate(all_models)
    print(f"Total after dedup: {len(all_models)}")

    # Enrich
    all_models = enrich_metadata(all_models)

    # Generate summary
    summary = generate_summary(all_models)

    # Save unified dataset
    output = {
        "metadata": summary,
        "models": all_models,
    }

    output_path = "data/voice_video_models.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {output_path}")

    # Print summary
    print(f"\n{'=' * 40}")
    print(f"SUMMARY")
    print(f"{'=' * 40}")
    print(f"Total models: {summary['total_models']}")
    print(f"\nBy category:")
    for cat, count in summary["categories"].items():
        print(f"  {cat}: {count}")
    print(f"\nBy provider (top 15):")
    for prov, count in list(summary["providers"].items())[:15]:
        print(f"  {prov}: {count}")
    print(f"\nStreaming support: {summary['streaming_support']} models")
    print(f"Real-time support: {summary['real_time_support']} models")
    print(f"\nPricing stats:")
    for cat, stats in summary["pricing_stats"].items():
        if stats.get("min"):
            unit = "hr" if cat == "stt" else "1M chars" if cat == "tts" else "image" if cat == "image_generation" else "sec"
            print(f"  {cat}: ${stats['min']:.4f} - ${stats['max']:.2f} per {unit} ({stats['priced_count']} priced)")
        else:
            print(f"  {cat}: {stats['count']} models (pricing TBD)")


if __name__ == "__main__":
    main()
