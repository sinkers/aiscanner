#!/usr/bin/env python3
"""
Seed S3 with the existing infrastructure_provider_map.json data.

Run once after first deploy:
    python3 scripts/bootstrap_s3.py <bucket-name> [--upload-ui]

--upload-ui also uploads the HTML UI files.

IMPORTANT: This script NEVER overwrites existing rollup history files.
If a rollup already exists in S3 it is left untouched. To upload only
UI files without touching any data, use --upload-ui alone:
    python3 scripts/bootstrap_s3.py <bucket-name> --upload-ui --ui-only
"""

import json
import os
import re
import sys
import boto3
from datetime import datetime, timezone


def safe_key(name):
    return re.sub(r"[/\s]", "_", name)


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def put(s3, bucket, key, data, cache_seconds=3600, content_type="application/json"):
    if content_type == "application/json":
        body = json.dumps(data, separators=(",", ":"), default=str).encode()
    else:
        body = data
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
        CacheControl=f"max-age={cache_seconds}",
    )
    print(f"  uploaded: {key}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    bucket_name = sys.argv[1]
    upload_ui = "--upload-ui" in sys.argv
    ui_only    = "--ui-only"   in sys.argv

    s3 = boto3.client("s3")

    def s3_key_exists(key):
        try:
            s3.head_object(Bucket=bucket_name, Key=key)
            return True
        except Exception:
            return False
    today = datetime.now(timezone.utc).date().isoformat()

    base_dir = os.path.join(os.path.dirname(__file__), "..")

    if not ui_only:
        data_file = os.path.join(base_dir, "infrastructure_provider_map.json")

        with open(data_file) as f:
            snapshot = json.load(f)

        snapshot["generated_at"] = datetime.now(timezone.utc).isoformat()

        # ------------------------------------------------------------------
        # Raw snapshot — write-once per day
        # ------------------------------------------------------------------
        snapshot_key = f"snapshots/{today}.json"
        if not s3_key_exists(snapshot_key):
            print("Uploading snapshot and latest...")
            put(s3, bucket_name, snapshot_key, snapshot, cache_seconds=86400)
        else:
            print(f"  skipping snapshot (already exists): {snapshot_key}")
        put(s3, bucket_name, "rollups/latest.json", snapshot)

        infra_map = snapshot.get("providers", {})

        # ------------------------------------------------------------------
        # Provider rollups — NEVER overwrite existing history
        # ------------------------------------------------------------------
        print(f"\nGenerating provider rollups ({len(infra_map)} providers)...")
        model_day = {}

        for provider_name, provider_data in infra_map.items():
            rollup_key = f"rollups/providers/{safe_key(provider_name)}.json"
            if s3_key_exists(rollup_key):
                print(f"  skipping (already seeded): {rollup_key}")
                # Still collect model data for model rollups below
                models = provider_data.get("models", [])
                for model in models:
                    mid = model["model_id"]
                    if mid not in model_day:
                        model_day[mid] = []
                    model_day[mid].append({
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
                continue

            models = provider_data.get("models", [])
            latency_vals = [
                m["performance"]["latency_30m"]["p50"]
                for m in models
                if m["performance"].get("latency_30m") and m["performance"]["latency_30m"].get("p50")
            ]
            point = {
                "date": today,
                "avg_prompt_price": mean(m["pricing"]["prompt"] for m in models),
                "avg_completion_price": mean(m["pricing"]["completion"] for m in models),
                "model_count": len(models),
                "avg_uptime_24h": mean(m["performance"].get("uptime_24h") for m in models),
                "avg_latency_p50": mean(latency_vals),
            }
            put(
                s3, bucket_name,
                rollup_key,
                {"provider_name": provider_name, "history": [point]},
            )

            for model in models:
                mid = model["model_id"]
                if mid not in model_day:
                    model_day[mid] = []
                model_day[mid].append({
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
        # Model rollups — NEVER overwrite existing history
        # ------------------------------------------------------------------
        print(f"\nGenerating model rollups ({len(model_day)} models)...")
        for model_id, providers_today in model_day.items():
            safe_model_id = model_id.replace(":", "_")
            rollup_key = f"rollups/models/{safe_model_id}.json"
            if s3_key_exists(rollup_key):
                continue  # preserve existing history
            put(
                s3, bucket_name,
                rollup_key,
                {"model_id": model_id, "history": [{"date": today, "providers": providers_today}]},
            )

    # ------------------------------------------------------------------
    # UI files
    # ------------------------------------------------------------------
    if upload_ui:
        print("\nUploading UI files...")
        # Upload HTML files
        for filename in ["index.html", "llm.html", "gpu.html", "voice.html"]:
            filepath = os.path.join(base_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    put(s3, bucket_name, filename, f.read(),
                        cache_seconds=300, content_type="text/html; charset=utf-8")

        # Upload models data (required for model type filter)
        models_file = os.path.join(base_dir, "openrouter_models.json")
        if os.path.exists(models_file):
            with open(models_file, "r") as f:
                models_data = json.load(f)
                put(s3, bucket_name, "openrouter_models.json", models_data,
                    cache_seconds=3600, content_type="application/json")

        # Upload voice/video data file if present (generated locally by scripts/)
        voice_data_file = os.path.join(base_dir, "data", "voice_video_models.json")
        if os.path.exists(voice_data_file):
            with open(voice_data_file, "r") as f:
                voice_data = json.load(f)
            put(s3, bucket_name, "data/voice_video_models.json", voice_data,
                cache_seconds=3600, content_type="application/json")

    print(f"\nBootstrap complete.")
    print(f"Bucket: s3://{bucket_name}")


if __name__ == "__main__":
    main()
