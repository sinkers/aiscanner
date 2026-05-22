"""Interactive CLI to query and explore the daily provider report."""

import json
import sys
from datetime import datetime

from llm_providers import config


def load_report() -> dict:
    if not config.DAILY_REPORT_JSON.exists():
        print(f"Error: {config.DAILY_REPORT_JSON} not found")
        print("Run 'make generate-report' first")
        sys.exit(1)
    return json.loads(config.DAILY_REPORT_JSON.read_text())


def show_summary(report: dict) -> None:
    print(f"\n{'='*80}\nDAILY REPORT SUMMARY\n{'='*80}")
    print(f"\nGenerated: {report['timestamp']}")
    s = report["overall_stats"]
    print(f"\nOverall:")
    print(f"  Total Models:                    {s['total_models']}")
    print(f"  Total Providers:                 {s['total_providers']}")
    print(f"  Models with Advanced Features:   {s['advanced_feature_models']}")
    print(f"  Providers with Advanced Features:{s['providers_with_features']}")
    features = report["feature_stats"]
    print(f"\nAudio:")
    print(f"  STT + TTS (full conversation): {features['stt_tts']['count']} models")
    print(f"  STT only:                      {features['stt']['count']} models")
    print(f"  TTS only:                      {features['tts']['count']} models")
    print(f"\nVideo & Image:")
    print(f"  Video input:      {features['video_input']['count']} models")
    print(f"  Image generation: {features['image_gen']['count']} models")


def show_feature_details(report: dict, feature: str) -> None:
    aliases = {"video": "video_input", "image": "image_gen", "stt-tts": "stt_tts"}
    key = aliases.get(feature.lower().replace("-", "_"), feature.lower().replace("-", "_"))

    if key not in report["feature_stats"]:
        print(f"Unknown feature: {feature}")
        print(f"Available: {', '.join(report['feature_stats'])}")
        return

    feature_data = report["feature_stats"][key]
    labels = {
        "stt": "Speech-to-Text (STT)",
        "tts": "Text-to-Speech (TTS)",
        "stt_tts": "Full Voice Conversation (STT + TTS)",
        "video_input": "Video Input",
        "image_gen": "Image Generation",
    }
    print(f"\n{'='*80}\n{labels.get(key, key.upper())}\n{'='*80}")
    print(f"\n  Total Models: {feature_data['count']}")

    p = feature_data["pricing"]
    if p["free_count"]:
        print(f"  Free Models: {p['free_count']}")
    if p["min"] > 0:
        print(f"\n  Pricing (per 1M tokens):")
        print(f"    Cheapest:       ${p['min']:.2f}")
        print(f"    Most Expensive: ${p['max']:.2f}")
        print(f"    Average:        ${p['avg']:.2f}")

    print(f"\n  Models:")
    for i, mid in enumerate(feature_data["model_ids"], 1):
        print(f"    {i:3}. {mid}")


def show_pricing_comparison(report: dict) -> None:
    print(f"\n{'='*80}\nPRICING COMPARISON (per 1M tokens)\n{'='*80}")
    labels = {
        "stt_tts": "STT + TTS",
        "stt": "STT only",
        "tts": "TTS only",
        "video_input": "Video input",
        "image_gen": "Image generation",
    }
    print(f"\n{'Feature':<30} {'Count':<8} {'Free':<8} {'Min $':<12} {'Max $':<12} {'Avg $':<12}")
    print("-" * 82)
    for key, label in labels.items():
        fd = report["feature_stats"].get(key, {})
        p = fd.get("pricing", {})
        min_p = f"${p['min']:.2f}" if p.get("min", 0) > 0 else "N/A"
        max_p = f"${p['max']:.2f}" if p.get("max", 0) > 0 else "N/A"
        avg_p = f"${p['avg']:.2f}" if p.get("avg", 0) > 0 else "N/A"
        print(f"{label:<30} {fd.get('count', 0):<8} {p.get('free_count', 0):<8} {min_p:<12} {max_p:<12} {avg_p:<12}")


def show_top_providers(report: dict, limit: int = 20) -> None:
    print(f"\n{'='*80}\nTOP {limit} PROVIDERS BY ADVANCED FEATURES\n{'='*80}")
    providers = report["provider_rankings"]["by_advanced_features"]
    print(f"\n{'#':<4} {'Provider':<30} {'Location':<20} {'Audio':<8} {'Video':<8} {'Image':<8} {'Total'}")
    print("-" * 100)
    for i, p in enumerate(providers[:limit], 1):
        loc = f"{p['city']}, {p['location']}" if p.get("city") else p["location"]
        c = p["feature_counts"]
        audio = c["stt"] + c["tts"] + c["stt_tts"]
        print(f"{i:<4} {p['name']:<30} {loc:<20} {audio:<8} {c['video_input']:<8} {c['image_gen']:<8} {p['total_advanced']}")


def show_audio_providers(report: dict) -> None:
    print(f"\n{'='*80}\nPROVIDERS WITH AUDIO SUPPORT\n{'='*80}")
    audio_providers = [
        p for p in report["provider_rankings"]["by_advanced_features"]
        if p["feature_counts"]["stt"] + p["feature_counts"]["tts"] + p["feature_counts"]["stt_tts"] > 0
    ]
    print(f"\nFound {len(audio_providers)} providers with audio support:\n")
    for i, p in enumerate(audio_providers, 1):
        loc = f"{p['city']}, {p['location']}" if p.get("city") else p["location"]
        c = p["feature_counts"]
        print(f"{i}. {p['name']} ({loc})")
        print(f"   Total audio models: {c['stt'] + c['tts'] + c['stt_tts']}")
        if c["stt_tts"]:
            print(f"   - Full conversation (STT+TTS): {c['stt_tts']}")
        if c["stt"]:
            print(f"   - STT only: {c['stt']}")
        if c["tts"]:
            print(f"   - TTS only: {c['tts']}")
        print()


def export_models_by_feature(report: dict, feature: str, output_file: str) -> None:
    aliases = {"video": "video_input", "image": "image_gen", "stt-tts": "stt_tts"}
    key = aliases.get(feature.lower().replace("-", "_"), feature.lower().replace("-", "_"))

    if key not in report["feature_stats"]:
        print(f"Unknown feature: {feature}")
        return

    fd = report["feature_stats"][key]
    export = {
        "feature": key,
        "count": fd["count"],
        "pricing": fd["pricing"],
        "models": fd["model_ids"],
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(output_file, "w") as f:
        json.dump(export, f, indent=2)
    print(f"✓ Exported {fd['count']} models → {output_file}")


def main() -> None:
    usage = (
        "Usage:\n"
        "  python3 -m llm_providers.cli.view_report summary\n"
        "  python3 -m llm_providers.cli.view_report feature <name>\n"
        "  python3 -m llm_providers.cli.view_report pricing\n"
        "  python3 -m llm_providers.cli.view_report providers [limit]\n"
        "  python3 -m llm_providers.cli.view_report audio-providers\n"
        "  python3 -m llm_providers.cli.view_report export <feature> <file>\n"
        "\nFeature names: stt, tts, stt-tts, video, image\n"
    )
    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)

    report = load_report()
    cmd = sys.argv[1].lower()

    if cmd == "summary":
        show_summary(report)
    elif cmd == "feature" and len(sys.argv) > 2:
        show_feature_details(report, sys.argv[2])
    elif cmd == "pricing":
        show_pricing_comparison(report)
    elif cmd == "providers":
        show_top_providers(report, int(sys.argv[2]) if len(sys.argv) > 2 else 20)
    elif cmd == "audio-providers":
        show_audio_providers(report)
    elif cmd == "export" and len(sys.argv) > 3:
        export_models_by_feature(report, sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {cmd}\n{usage}")
        sys.exit(1)


if __name__ == "__main__":
    main()
