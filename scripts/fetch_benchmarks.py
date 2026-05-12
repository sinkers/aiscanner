#!/usr/bin/env python3
"""
Fetch Open LLM Leaderboard v2 scores and upload to S3.

Usage:
    python3 scripts/fetch_benchmarks.py <bucket-name>
    python3 scripts/fetch_benchmarks.py --dry-run   # print summary, no upload
"""

import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=open-llm-leaderboard%2Fcontents"
    "&config=default&split=train&length=100&offset={offset}"
)

_COL_AVG = "Average \u2b06\ufe0f"   # "Average ⬆️"


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dame-benchmark-fetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  error fetching {url}: {e}")
        return None


def fetch():
    models = []
    offset = 0
    total = None

    while True:
        data = http_get(HF_ROWS_URL.format(offset=offset))
        if not data:
            break

        if total is None:
            total = data.get("num_rows_total", 0)
            print(f"Total rows: {total}")

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
                "ifeval":   round(float(r.get("IFEval")     or 0), 2),
                "bbh":      round(float(r.get("BBH")        or 0), 2),
                "math":     round(float(r.get("MATH Lvl 5") or 0), 2),
                "gpqa":     round(float(r.get("GPQA")       or 0), 2),
                "musr":     round(float(r.get("MUSR")       or 0), 2),
                "mmlu_pro": round(float(r.get("MMLU-PRO")   or 0), 2),
            })

        offset += len(rows)
        print(f"  fetched {offset}/{total}...", end="\r")
        if offset >= (total or 0):
            break

    print()

    models.sort(key=lambda m: m["avg"], reverse=True)
    for i, m in enumerate(models):
        m["rank"] = i + 1

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": len(models),
        "models": models,
    }


def main():
    dry_run = "--dry-run" in sys.argv
    bucket = next((a for a in sys.argv[1:] if not a.startswith("-")), None)

    if not dry_run and not bucket:
        print(__doc__)
        sys.exit(1)

    print("Fetching Open LLM Leaderboard benchmarks...")
    data = fetch()

    print(f"\nFetched {data['total']} models")
    print(f"Top 5:")
    for m in data["models"][:5]:
        print(f"  #{m['rank']:4d}  avg={m['avg']:5.1f}  {m['id']}")

    if dry_run:
        print("\n--dry-run: skipping S3 upload")
        return

    if data["total"] == 0:
        print("\nFetch returned no models — skipping S3 upload to avoid overwriting good data")
        sys.exit(1)

    import boto3
    s3 = boto3.client("s3")
    body = json.dumps(data, separators=(",", ":")).encode()
    s3.put_object(
        Bucket=bucket,
        Key="rollups/benchmarks.json",
        Body=body,
        ContentType="application/json",
        CacheControl="max-age=86400",
    )
    print(f"\nUploaded rollups/benchmarks.json to s3://{bucket} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
