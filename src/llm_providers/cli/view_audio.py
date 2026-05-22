"""Quick audio model pricing viewer."""

import json
import sys

from llm_providers import config


_AUDIO_PATTERNS = [
    "gpt-audio", "lyria", "voxtral", "mimo", "nemotron-3-nano-omni",
    "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro",
    "gemini-3.1-flash", "gemini-3.1-pro", "gemini-3-flash",
    "gemini-pro-latest", "gemini-flash-latest",
]


def load_data() -> dict:
    if not config.INFRA_MAP_FILE.exists():
        print(f"Error: {config.INFRA_MAP_FILE} not found")
        print("Run 'make map-infra' first")
        sys.exit(1)
    return json.loads(config.INFRA_MAP_FILE.read_text())


def is_audio_model(model_id: str) -> bool:
    return any(p in model_id for p in _AUDIO_PATTERNS)


def categorize(model_id: str) -> str:
    if "gpt-audio" in model_id or "gpt-4o-audio" in model_id:
        return "conversation"
    if "lyria" in model_id:
        return "tts"
    return "stt"


def _collect_models(data: dict, category: str | None = None) -> list[dict]:
    rows = []
    for provider_name, pd in data["providers"].items():
        for m in pd["models"]:
            mid = m["model_id"]
            if not is_audio_model(mid):
                continue
            cat = categorize(mid)
            if category and cat != category:
                continue
            pricing = m["pricing"]
            total = (pricing["prompt"] + pricing["completion"]) * 1_000_000
            rows.append({
                "model_id": mid,
                "provider": provider_name,
                "category": cat,
                "prompt": pricing["prompt"] * 1_000_000,
                "completion": pricing["completion"] * 1_000_000,
                "total": total,
                "uptime": m["performance"].get("uptime_24h", 0),
                "context": m["context_length"],
            })
    return sorted(rows, key=lambda x: (x["category"], x["total"]))


def _row(m: dict) -> str:
    price = f"${m['total']:.2f}" if m["total"] > 0 else "FREE"
    uptime = f"{m['uptime']:.1f}%" if m["uptime"] else "N/A"
    ctx = f"{m['context']:,}" if m["context"] else "N/A"
    return f"{m['model_id']:<50} {m['provider']:<20} {price:<15} {uptime:<10} {ctx}"


def show_all(data: dict) -> None:
    models = _collect_models(data)
    print(f"\n{'='*100}\nALL AUDIO MODELS\n{'='*100}")
    current_cat = None
    cat_labels = {
        "conversation": "FULL CONVERSATION (STT + TTS)",
        "tts": "TEXT-TO-SPEECH (TTS)",
        "stt": "SPEECH-TO-TEXT (STT)",
    }
    header = f"{'Model':<50} {'Provider':<20} {'Price/1M':<15} {'Uptime':<10} {'Context'}"
    for m in models:
        if m["category"] != current_cat:
            current_cat = m["category"]
            print(f"\n{cat_labels[current_cat]}\n{'-'*100}\n{header}\n{'-'*100}")
        print(_row(m))


def show_by_category(data: dict, category: str) -> None:
    models = _collect_models(data, category)
    labels = {
        "conversation": "FULL CONVERSATION (STT + TTS)",
        "tts": "TEXT-TO-SPEECH (TTS)",
        "stt": "SPEECH-TO-TEXT (STT)",
    }
    print(f"\n{'='*100}\n{labels[category]} — {len(models)} MODELS\n{'='*100}")
    header = f"{'Model':<50} {'Provider':<20} {'Price/1M':<15} {'Uptime':<10} {'Context'}"
    print(f"\n{header}\n{'-'*100}")
    for m in models:
        print(_row(m))

    free_count = sum(1 for m in models if m["total"] == 0)
    paid = [m["total"] for m in models if m["total"] > 0]
    print(f"\n{'='*100}\nSUMMARY\n{'='*100}")
    print(f"Total: {len(models)} | Free: {free_count}")
    if paid:
        print(f"Paid range: ${min(paid):.2f} – ${max(paid):.2f} per 1M tokens")
        print(f"Average: ${sum(paid) / len(paid):.2f} per 1M tokens")


def show_by_provider(data: dict) -> None:
    print(f"\n{'='*100}\nAUDIO MODELS BY PROVIDER\n{'='*100}")
    by_provider: dict[str, dict] = {}
    for provider_name, pd in data["providers"].items():
        models = [
            {"model_id": m["model_id"], "category": categorize(m["model_id"]),
             "total": (m["pricing"]["prompt"] + m["pricing"]["completion"]) * 1_000_000}
            for m in pd["models"] if is_audio_model(m["model_id"])
        ]
        if models:
            by_provider[provider_name] = {"models": models, "info": pd["provider_info"]}

    for name, pdata in sorted(by_provider.items(), key=lambda x: len(x[1]["models"]), reverse=True):
        info = pdata["info"]
        models = pdata["models"]
        city = info.get("headquarters_city", "")
        hq = info.get("headquarters", "Unknown")
        loc = f"{city}, {hq}" if city else hq
        stt = sum(1 for m in models if m["category"] == "stt")
        tts = sum(1 for m in models if m["category"] == "tts")
        conv = sum(1 for m in models if m["category"] == "conversation")
        print(f"\n{name} ({loc})  —  {len(models)} audio models")
        if conv:
            print(f"  Full conversation: {conv}")
        if stt:
            print(f"  STT only: {stt}")
        if tts:
            print(f"  TTS only: {tts}")
        for m in sorted(models, key=lambda x: x["total"])[:5]:
            icon = {"conversation": "[STT+TTS]", "stt": "[STT]", "tts": "[TTS]"}[m["category"]]
            price = f"${m['total']:.2f}/1M" if m["total"] > 0 else "FREE"
            print(f"    {icon} {m['model_id']} — {price}")
        if len(models) > 5:
            print(f"    ... and {len(models) - 5} more")


def main() -> None:
    data = load_data()
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    if not cmd:
        show_all(data)
    elif cmd == "stt":
        show_by_category(data, "stt")
    elif cmd == "tts":
        show_by_category(data, "tts")
    elif cmd in ("conversation", "full", "stt-tts"):
        show_by_category(data, "conversation")
    elif cmd == "providers":
        show_by_provider(data)
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 -m llm_providers.cli.view_audio [stt|tts|conversation|providers]")
        sys.exit(1)


if __name__ == "__main__":
    main()
