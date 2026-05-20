#!/usr/bin/env python3
"""
Rebuild provider and model rollup history from existing daily snapshots.

The bootstrap_s3.py script used to overwrite rollup files on every deploy,
causing history to be reset to a single entry. This script reconstructs the
full history by replaying all snapshots in S3 in date order.

Usage:
    python3 scripts/rebuild_history.py <bucket-name> [--dry-run]

Reads:   snapshots/YYYY-MM-DD.json  (all available dates)
Writes:  rollups/providers/{name}.json
         rollups/models/{model_id}.json
"""

import json
import re
import sys
from collections import defaultdict

import boto3

BUCKET = sys.argv[1] if len(sys.argv) > 1 else None
DRY_RUN = "--dry-run" in sys.argv

if not BUCKET:
    print(__doc__)
    sys.exit(1)

s3 = boto3.client("s3")


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def safe_key(name):
    return re.sub(r"[/\s]", "_", name)


def list_snapshots():
    """Return sorted list of (date_str, s3_key) for all LLM snapshots."""
    paginator = s3.get_paginator("list_objects_v2")
    dates = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix="snapshots/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Match snapshots/YYYY-MM-DD.json (not snapshots/gpu/...)
            m = re.match(r"snapshots/(\d{4}-\d{2}-\d{2})\.json$", key)
            if m:
                dates.append((m.group(1), key))
    return sorted(dates)


def load_json(key):
    try:
        resp = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(resp["Body"].read())
    except Exception as e:
        print(f"  ERROR loading {key}: {e}")
        return None


def extract_point(date, provider_data):
    """Build a provider history point from a snapshot's provider data."""
    models = provider_data.get("models", [])
    latency_vals = [
        m["performance"]["latency_30m"]["p50"]
        for m in models
        if m["performance"].get("latency_30m") and m["performance"]["latency_30m"].get("p50")
    ]
    return {
        "date": date,
        "avg_prompt_price": mean(m["pricing"]["prompt"] for m in models),
        "avg_completion_price": mean(m["pricing"]["completion"] for m in models),
        "model_count": len(models),
        "avg_uptime_24h": mean(m["performance"].get("uptime_24h") for m in models),
        "avg_latency_p50": mean(latency_vals),
    }


def main():
    snapshots = list_snapshots()
    if not snapshots:
        print("No snapshots found.")
        sys.exit(1)

    print(f"Found {len(snapshots)} snapshots: {[d for d, _ in snapshots]}")
    print(f"Dry run: {DRY_RUN}\n")

    # provider_history[provider_name] = {date: point}
    provider_history = defaultdict(dict)
    # model_history[model_id] = {date: [provider_entries]}
    model_history = defaultdict(dict)

    for date, key in snapshots:
        print(f"Processing {key}...")
        snapshot = load_json(key)
        if not snapshot:
            continue

        infra_map = snapshot.get("providers", {})
        for provider_name, provider_data in infra_map.items():
            point = extract_point(date, provider_data)
            provider_history[provider_name][date] = point

            models = provider_data.get("models", [])
            for model in models:
                mid = model["model_id"]
                if date not in model_history[mid]:
                    model_history[mid][date] = []
                model_history[mid][date].append({
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

    # ------------------------------------------------------------------
    # Write rebuilt provider rollups
    # ------------------------------------------------------------------
    print(f"\nWriting {len(provider_history)} provider rollups...")
    for provider_name, day_points in provider_history.items():
        history = sorted(day_points.values(), key=lambda p: p["date"])
        rollup = {"provider_name": provider_name, "history": history}
        s3_key = f"rollups/providers/{safe_key(provider_name)}.json"
        if DRY_RUN:
            print(f"  [dry-run] would write {s3_key} ({len(history)} entries: {[p['date'] for p in history]})")
        else:
            body = json.dumps(rollup, separators=(",", ":"), default=str).encode()
            s3.put_object(
                Bucket=BUCKET, Key=s3_key, Body=body,
                ContentType="application/json", CacheControl="max-age=3600",
            )
            print(f"  wrote {s3_key} ({len(history)} entries)")

    # ------------------------------------------------------------------
    # Write rebuilt model rollups
    # ------------------------------------------------------------------
    print(f"\nWriting {len(model_history)} model rollups...")
    written = 0
    for model_id, day_entries in model_history.items():
        history = sorted(
            [{"date": d, "providers": p} for d, p in day_entries.items()],
            key=lambda x: x["date"],
        )
        safe_model_id = model_id.replace(":", "_")
        s3_key = f"rollups/models/{safe_model_id}.json"
        rollup = {"model_id": model_id, "history": history}
        if DRY_RUN:
            if written < 3:
                print(f"  [dry-run] would write {s3_key} ({len(history)} entries)")
        else:
            body = json.dumps(rollup, separators=(",", ":"), default=str).encode()
            s3.put_object(
                Bucket=BUCKET, Key=s3_key, Body=body,
                ContentType="application/json", CacheControl="max-age=3600",
            )
        written += 1

    if not DRY_RUN:
        print(f"  wrote {written} model rollup files")

    print("\nDone.")
    if DRY_RUN:
        print("Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
