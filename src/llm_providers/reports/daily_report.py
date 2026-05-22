"""Daily LLM Provider Report Generator.

Generates comprehensive daily reports tracking:
- Overall model and provider statistics
- Advanced features (TTS, STT, audio, image generation, video)
- Pricing trends and comparisons
- Provider rankings

Outputs:
- daily_report.md  — human-readable markdown
- daily_report.json — machine-readable JSON
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

from llm_providers import config


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> tuple[dict, dict]:
    for path in (config.MODELS_FILE, config.INFRA_MAP_FILE):
        if not path.exists():
            print(f"Error: required file not found: {path}")
            print("Run 'make fetch-openrouter map-infra' first")
            sys.exit(1)
    return (
        json.loads(config.MODELS_FILE.read_text()),
        json.loads(config.INFRA_MAP_FILE.read_text()),
    )


# ---------------------------------------------------------------------------
# Feature categorisation
# ---------------------------------------------------------------------------

def categorize_models_by_features(models: list[dict]) -> dict[str, list[dict]]:
    """Return a dict mapping feature key → list of model info dicts."""
    features: dict[str, list] = {
        "stt": [], "tts": [], "stt_tts": [],
        "video_input": [], "image_gen": [], "multimodal": [],
    }

    for model in models:
        arch = model.get("architecture", {})
        inputs = arch.get("input_modalities", [])
        outputs = arch.get("output_modalities", [])

        info = {
            "id": model["id"],
            "name": model["name"],
            "modality": arch.get("modality", "unknown"),
            "input_modalities": inputs,
            "output_modalities": outputs,
            "pricing": model.get("pricing", {}),
            "context_length": model.get("context_length", 0),
            "supported_voices": model.get("supported_voices"),
        }

        has_audio_in = "audio" in inputs
        has_audio_out = "audio" in outputs

        if has_audio_in and has_audio_out:
            features["stt_tts"].append(info)
        elif has_audio_in:
            features["stt"].append(info)
        elif has_audio_out:
            features["tts"].append(info)

        if "video" in inputs:
            features["video_input"].append(info)
        if "image" in outputs:
            features["image_gen"].append(info)
        if len(inputs) >= 2:
            features["multimodal"].append(info)

    return features


def analyze_providers_by_features(
    infra_data: dict, feature_models: dict[str, list]
) -> dict[str, dict]:
    feature_ids = {k: {m["id"] for m in v} for k, v in feature_models.items()}
    result = {}

    for name, provider_data in infra_data["providers"].items():
        info = provider_data.get("provider_info", {})
        counts: dict[str, int] = {k: 0 for k in feature_ids}
        model_lists: dict[str, list] = {k: [] for k in feature_ids}

        for model in provider_data.get("models", []):
            mid = model.get("model_id", "")
            for feature, ids in feature_ids.items():
                if mid in ids:
                    counts[feature] += 1
                    model_lists[feature].append({
                        "id": mid,
                        "name": model.get("model_name", ""),
                        "pricing": model.get("pricing", {}),
                        "performance": model.get("performance", {}),
                    })

        result[name] = {
            "info": {
                "location": info.get("headquarters", "Unknown"),
                "city": info.get("headquarters_city", ""),
                "homepage": info.get("homepage", ""),
                "support_url": info.get("support_url", ""),
            },
            "total_models": provider_data.get("total_models", 0),
            "feature_counts": counts,
            "feature_models": model_lists,
            "total_advanced": sum(counts.values()),
        }

    return result


# ---------------------------------------------------------------------------
# Pricing statistics
# ---------------------------------------------------------------------------

def pricing_stats(models: list[dict]) -> dict[str, Any]:
    prices = []
    free_count = 0
    for model in models:
        pricing = model.get("pricing", {})
        total = float(pricing.get("prompt", 0)) + float(pricing.get("completion", 0))
        if total < 0:
            continue
        if total == 0:
            free_count += 1
        else:
            prices.append(total)

    if not prices:
        return {"min": 0, "max": 0, "avg": 0, "free_count": free_count, "paid_count": 0}

    per_m = [p * 1_000_000 for p in prices]
    return {
        "min": min(per_m),
        "max": max(per_m),
        "avg": sum(per_m) / len(per_m),
        "free_count": free_count,
        "paid_count": len(prices),
    }


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _price_range_line(stats: dict[str, Any]) -> str:
    lines = []
    if stats["free_count"]:
        lines.append(f"**Free models available:** {stats['free_count']}")
    if stats["min"] > 0:
        lines.append(
            f"**Price range:** ${stats['min']:.2f} – ${stats['max']:.2f} per 1M tokens"
            f" (avg: ${stats['avg']:.2f})"
        )
    return "\n".join(lines)


def generate_markdown(data: dict) -> str:
    ts = data["timestamp"]
    overall = data["overall_stats"]
    features = data["feature_stats"]
    providers = data["provider_rankings"]

    lines = [
        f"# OpenRouter Daily LLM Provider Report",
        f"**Generated:** {ts}",
        "",
        "---",
        "",
        "## Overall Statistics",
        "",
        f"- **Total Models:** {overall['total_models']}",
        f"- **Total Infrastructure Providers:** {overall['total_providers']}",
        f"- **Models with Advanced Features:** {overall['advanced_feature_models']}",
        f"- **Providers with Advanced Features:** {overall['providers_with_features']}",
        "",
        "---",
        "",
        "## Audio Features (TTS & STT)",
        "",
        "### Full Voice Conversation (STT + TTS)",
        f"**Models:** {len(features['stt_tts']['models'])}",
        "",
    ]

    if features["stt_tts"]["models"]:
        lines += [
            "| Model ID | Provider | Pricing (per 1M tokens) | Context |",
            "|----------|----------|------------------------|---------|",
        ]
        for model in sorted(
            features["stt_tts"]["models"],
            key=lambda m: float(m["pricing"].get("prompt", 0)) + float(m["pricing"].get("completion", 0)),
        ):
            p = model["pricing"]
            prompt_p = float(p.get("prompt", 0)) * 1_000_000
            comp_p = float(p.get("completion", 0)) * 1_000_000
            total_p = prompt_p + comp_p
            price_str = "FREE" if total_p == 0 else f"${prompt_p:.2f} / ${comp_p:.2f}"
            ctx = f"{model['context_length']:,}" if model["context_length"] else "N/A"
            lines.append(f"| `{model['id']}` | {model['id'].split('/')[0]} | {price_str} | {ctx} |")

    lines += ["", _price_range_line(features["stt_tts"]["pricing"]), ""]

    lines += [
        "### Speech-to-Text Only (STT)",
        f"**Models:** {len(features['stt']['models'])}",
        "",
    ]
    if features["stt"]["models"]:
        sorted_stt = sorted(
            features["stt"]["models"],
            key=lambda m: float(m["pricing"].get("prompt", 0)) + float(m["pricing"].get("completion", 0)),
        )[:10]
        lines += [
            "**Top 10 Most Affordable:**",
            "",
            "| Model ID | Pricing (per 1M) | Additional Features |",
            "|----------|-----------------|---------------------|",
        ]
        for m in sorted_stt:
            p = m["pricing"]
            total = (float(p.get("prompt", 0)) + float(p.get("completion", 0))) * 1_000_000
            price_str = "FREE" if total == 0 else f"${total:.2f}"
            extra = [x for x in m["input_modalities"] if x not in ("text", "audio")]
            lines.append(f"| `{m['id']}` | {price_str} | {', '.join(extra) or 'audio only'} |")

    lines += ["", _price_range_line(features["stt"]["pricing"]), ""]

    lines += [
        "### Text-to-Speech Only (TTS)",
        f"**Models:** {len(features['tts']['models'])}",
        "",
    ]
    if features["tts"]["models"]:
        lines += [
            "| Model ID | Provider | Pricing | Voices |",
            "|----------|----------|---------|--------|",
        ]
        for m in features["tts"]["models"]:
            p = m["pricing"]
            total = (float(p.get("prompt", 0)) + float(p.get("completion", 0))) * 1_000_000
            lines.append(
                f"| `{m['id']}` | {m['id'].split('/')[0]} "
                f"| {'FREE' if total == 0 else f'${total:.2f}'} "
                f"| {m.get('supported_voices') or 'N/A'} |"
            )

    lines += [
        "",
        "---",
        "",
        "## Video Input Support",
        "",
        f"**Models with video input:** {len(features['video_input']['models'])}",
        "",
        _price_range_line(features["video_input"]["pricing"]),
        "",
    ]

    video_by_creator: dict[str, int] = defaultdict(int)
    for m in features["video_input"]["models"]:
        video_by_creator[m["id"].split("/")[0]] += 1

    lines += ["**Top creators by video model count:**", ""]
    for creator, cnt in sorted(video_by_creator.items(), key=lambda x: x[1], reverse=True)[:10]:
        lines.append(f"- **{creator}:** {cnt} models")

    lines += [
        "",
        "---",
        "",
        "## Image Generation Support",
        "",
        f"**Models with image generation:** {len(features['image_gen']['models'])}",
        "",
    ]
    if features["image_gen"]["models"]:
        lines += [
            "| Model ID | Provider | Pricing (per 1M) |",
            "|----------|----------|------------------|",
        ]
        for m in features["image_gen"]["models"]:
            p = m["pricing"]
            total = (float(p.get("prompt", 0)) + float(p.get("completion", 0))) * 1_000_000
            lines.append(f"| `{m['id']}` | {m['id'].split('/')[0]} | {'FREE' if total == 0 else f'${total:.2f}'} |")

    lines += [
        "",
        "---",
        "",
        "## Infrastructure Provider Rankings",
        "",
        "### Top 20 Providers by Advanced Feature Support",
        "",
        "| Rank | Provider | Location | Audio | Video | Image | Total |",
        "|------|----------|----------|-------|-------|-------|-------|",
    ]
    for i, (name, pd) in enumerate(providers["by_advanced_features"][:20], 1):
        loc = f"{pd['info']['city']}, {pd['info']['location']}" if pd["info"]["city"] else pd["info"]["location"]
        c = pd["feature_counts"]
        audio = c["stt"] + c["tts"] + c["stt_tts"]
        lines.append(f"| {i} | **{name}** | {loc} | {audio} | {c['video_input']} | {c['image_gen']} | **{pd['total_advanced']}** |")

    total = overall["total_models"]
    audio_m = len(features["stt"]["models"]) + len(features["tts"]["models"]) + len(features["stt_tts"]["models"])

    lines += [
        "",
        "---",
        "",
        "## Key Insights",
        "",
        f"- **{audio_m / total * 100:.1f}%** of models support audio features (STT or TTS)",
        f"- **{len(features['video_input']['models']) / total * 100:.1f}%** of models support video input",
        f"- **{len(features['image_gen']['models']) / total * 100:.1f}%** of models support image generation",
        "",
        "---",
        "",
        "*Report generated by DAME LLM Providers Infrastructure Mapper*",
        "*Data source: OpenRouter API*",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_report() -> None:
    print("Loading data...")
    models_data, infra_data = load_data()
    models = models_data["data"]
    print(f"Analysing {len(models)} models and {len(infra_data['providers'])} providers...")

    feature_models = categorize_models_by_features(models)
    provider_features = analyze_providers_by_features(infra_data, feature_models)

    feature_stats = {
        name: {
            "count": len(model_list),
            "models": model_list,
            "pricing": pricing_stats(model_list),
        }
        for name, model_list in feature_models.items()
    }

    providers_with_features = {k: v for k, v in provider_features.items() if v["total_advanced"] > 0}
    ranked = sorted(providers_with_features.items(), key=lambda x: x[1]["total_advanced"], reverse=True)

    report_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "overall_stats": {
            "total_models": len(models),
            "total_providers": len(infra_data["providers"]),
            "advanced_feature_models": len({m["id"] for fl in feature_models.values() for m in fl}),
            "providers_with_features": len(providers_with_features),
        },
        "feature_stats": feature_stats,
        "provider_rankings": {"by_advanced_features": ranked},
        "provider_details": provider_features,
    }

    config.DAILY_REPORT_MD.write_text(generate_markdown(report_data))
    print(f"✓ Saved markdown report → {config.DAILY_REPORT_MD}")

    json_report = {
        "timestamp": report_data["timestamp"],
        "overall_stats": report_data["overall_stats"],
        "feature_stats": {
            feat: {
                "count": stats["count"],
                "pricing": stats["pricing"],
                "model_ids": [m["id"] for m in stats["models"]],
            }
            for feat, stats in feature_stats.items()
        },
        "provider_rankings": {
            "by_advanced_features": [
                {
                    "name": name,
                    "location": d["info"]["location"],
                    "city": d["info"]["city"],
                    "feature_counts": d["feature_counts"],
                    "total_advanced": d["total_advanced"],
                }
                for name, d in ranked
            ]
        },
    }
    config.DAILY_REPORT_JSON.write_text(json.dumps(json_report, indent=2))
    print(f"✓ Saved JSON report → {config.DAILY_REPORT_JSON}")

    s = report_data["overall_stats"]
    print(f"\n{'='*60}\nDAILY REPORT SUMMARY\n{'='*60}")
    print(f"Total Models: {s['total_models']}")
    print(f"Total Providers: {s['total_providers']}")
    print(f"\nAdvanced Features:")
    for key in ("stt_tts", "stt", "tts", "video_input", "image_gen"):
        print(f"  {key}: {feature_stats[key]['count']} models")
    print(f"\nProviders with advanced features: {s['providers_with_features']}")


def main() -> None:
    generate_report()


if __name__ == "__main__":
    main()
