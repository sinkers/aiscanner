#!/usr/bin/env python3
"""
Fetch model/voice listings from STT and TTS provider APIs.

Providers with public model listing endpoints (no auth or optional auth):
- Deepgram: GET /v1/models (no auth)
- ElevenLabs: GET /v1/models (no auth)
- OpenAI: GET /v1/models (auth required)
- Groq: GET /models (auth required)
- Fireworks: GET /models (auth required)

Set env vars for providers that require auth:
- OPENAI_API_KEY
- GROQ_API_KEY
- FIREWORKS_API_KEY
"""

import json
import os
import time
import urllib.request
import urllib.error

# API keys from environment
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY", "")


def fetch_json(url, headers=None):
    """Generic JSON fetch helper."""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.reason} for {url}")
        return None


# =============================================================================
# DEEPGRAM
# =============================================================================

# Pricing by model family (per minute, USD)
DEEPGRAM_STT_PRICING = {
    "nova-3":             {"streaming": 0.0059, "batch": 0.0077, "unit": "per_minute"},
    "nova-3-multilingual": {"streaming": 0.0058, "batch": 0.0092, "unit": "per_minute"},
    "nova-2":             {"streaming": 0.0043, "batch": 0.0059, "unit": "per_minute"},
    "nova-2-medical":     {"streaming": 0.0077, "batch": 0.0077, "unit": "per_minute"},
    "nova-1":             {"streaming": 0.0025, "batch": 0.0036, "unit": "per_minute"},
    "flux":               {"streaming": 0.0065, "batch": 0.0077, "unit": "per_minute"},
    "whisper":            {"batch":     0.0048, "unit": "per_minute"},
}

DEEPGRAM_TTS_PRICING = {
    "aura-2": {"amount": 0.030, "unit": "per_1k_chars"},
    "aura-1": {"amount": 0.015, "unit": "per_1k_chars"},
}

# Map API model names → canonical family for rollup.
# Models not listed here are skipped (test/internal/niche).
# Format: api_name -> (family_key, use_case_tag)
DEEPGRAM_STT_FAMILY_MAP = {
    # Nova-2 use-case variants → nova-2 family
    "2-general":         ("nova-2", "general"),
    "2-automotive":      ("nova-2", "automotive"),
    "2-atc":             ("nova-2", "atc"),
    "2-conversationalai": ("nova-2", "conversational AI"),
    "2-drivethru":       ("nova-2", "drive-thru"),
    "2-finance":         ("nova-2", "finance"),
    "2-meeting":         ("nova-2", "meeting"),
    "2-phonecall":       ("nova-2", "phone call"),
    "2-video":           ("nova-2", "video"),
    "2-voicemail":       ("nova-2", "voicemail"),
    # Nova-2 Medical (distinct pricing)
    "2-medical":         ("nova-2-medical", "medical"),
    # Nova-1 use-case variants → nova-1 family
    "general":           ("nova-1", "general"),
    "automotive":        ("nova-1", "automotive"),
    "conversationalai":  ("nova-1", "conversational AI"),
    "drivethru":         ("nova-1", "drive-thru"),
    "finance":           ("nova-1", "finance"),
    "meeting":           ("nova-1", "meeting"),
    "phonecall":         ("nova-1", "phone call"),
    "video":             ("nova-1", "video"),
    "voicemail":         ("nova-1", "voicemail"),
    "medical":           ("nova-1", "medical"),
    # Whisper sizes → whisper family
    "base":              ("whisper", "general"),
    "small":             ("whisper", "general"),
    "medium":            ("whisper", "general"),
    "large":             ("whisper", "general"),
    "tiny":              ("whisper", "general"),
    # Nova-3 (if present in API response)
    "3-general":         ("nova-3", "general"),
    "nova-3":            ("nova-3", "general"),
    "nova-3-multilingual": ("nova-3-multilingual", "multilingual"),
}

# Display config per family
DEEPGRAM_FAMILY_CONFIG = {
    "nova-3":             {"display": "Deepgram Nova-3", "streaming": True, "notes": None},
    "nova-3-multilingual": {"display": "Deepgram Nova-3 Multilingual", "streaming": True, "notes": None},
    "nova-2":             {"display": "Deepgram Nova-2", "streaming": True, "notes": None},
    "nova-2-medical":     {"display": "Deepgram Nova-2 Medical", "streaming": True, "notes": "Medical-grade accuracy, English only"},
    "nova-1":             {"display": "Deepgram Nova-1 (Enhanced)", "streaming": True, "notes": "Legacy tier — Nova-2 recommended for new projects"},
    "whisper":            {"display": "Deepgram Whisper", "streaming": False, "notes": "Batch only. Available in sizes: tiny, base, small, medium, large"},
}


def _free_tier_limit(price_per_min, credit=200.0):
    """Compute how many hours $200 credit buys at a given $/min rate."""
    if not price_per_min:
        return None
    hrs = credit / price_per_min / 60
    return f"~{hrs:,.0f} hrs on ${credit:.0f} credit"


def fetch_deepgram():
    """Fetch Deepgram models (no auth required for public endpoint).

    Rolls up all use-case variants into 4-5 family entries (Nova-3, Nova-2,
    Nova-2 Medical, Nova-1, Whisper) and 2 TTS entries (Aura-2, Aura-1).
    """
    print("\n--- Deepgram ---")
    data = fetch_json("https://api.deepgram.com/v1/models")
    if not data:
        print("  Failed to fetch Deepgram models")
        return []

    models = []

    # Process STT models — roll up into families
    stt_raw = data.get("stt", data.get("models", []))
    families = {}  # family_key -> {"languages": set(), "use_cases": set()}
    if isinstance(stt_raw, list):
        for m in stt_raw:
            model_name = m.get("name", m.get("canonical_name", "unknown"))
            languages = m.get("languages", [])
            lang_codes = [l.get("code", l) if isinstance(l, dict) else l for l in languages]

            family_info = DEEPGRAM_STT_FAMILY_MAP.get(model_name)
            if family_info is None:
                continue  # skip test/internal/niche models

            family_key, use_case = family_info
            if family_key not in families:
                families[family_key] = {"languages": set(), "use_cases": set()}
            families[family_key]["languages"].update(lang_codes)
            if use_case:
                families[family_key]["use_cases"].add(use_case)

    print(f"  STT: {len(stt_raw)} raw entries -> {len(families)} families")

    _base_provider = {
        "signup_url": "https://console.deepgram.com/signup",
        "api_base_url": "https://api.deepgram.com",
        "docs_url": "https://developers.deepgram.com",
        "auth_method": "header",
        "auth_header": "Authorization",
        "auth_format": "Token {key}",
        "python_sdk": "deepgram-sdk",
    }
    _base_tech = {
        "architecture": "proprietary",
        "license": "commercial",
        "open_source": False,
        "self_hostable": False,
        "openai_compatible": False,
    }

    for family_key, fdata in families.items():
        price_info = DEEPGRAM_STT_PRICING.get(family_key, {})
        streaming_price = price_info.get("streaming")
        batch_price = price_info.get("batch")
        effective_price = streaming_price or batch_price or 0
        cfg = DEEPGRAM_FAMILY_CONFIG.get(family_key, {})
        has_streaming = cfg.get("streaming", False) and bool(streaming_price)
        all_langs = sorted(fdata["languages"])
        use_cases = sorted(fdata["use_cases"])

        ft_limit = _free_tier_limit(effective_price)

        models.append({
            "model_id": f"deepgram/{family_key}",
            "display_name": cfg.get("display", f"Deepgram {family_key}"),
            "provider": "Deepgram",
            "provider_slug": "deepgram",
            "category": "stt",
            "connection_types": {
                "rest_sync": True,
                "rest_batch": True,
                "rest_streaming": False,
                "websocket_streaming": has_streaming,
                "grpc": False,
                "sse": False,
            },
            "capabilities": {
                "real_time": has_streaming,
                "streaming": has_streaming,
                "multilingual": len(all_langs) > 1,
                "languages": all_langs,
                "language_count": len(all_langs),
                "diarization": True,
                "timestamps": True,
                "custom_vocabulary": True,
                "use_cases": use_cases,
            },
            "pricing": {
                "model": "per_minute",
                "amount": effective_price,
                "currency": "USD",
                "unit": "minute",
                "streaming_rate": streaming_price,
                "batch_rate": batch_price,
                "normalized": {
                    "per_hour_usd": round(effective_price * 60, 4)
                },
                "free_tier": True,
                "free_tier_type": "trial_credit",
                "free_tier_amount": "$200 one-time credit",
                "free_tier_limit": ft_limit,
                "billing_increment": "per_second",
                **({"notes": cfg["notes"]} if cfg.get("notes") else {}),
            },
            "technical": _base_tech,
            "provider_info": _base_provider,
            "data_source": "deepgram_api",
        })

    # Process TTS — roll up voices into Aura-2 / Aura-1 entries
    tts_raw = data.get("tts", [])
    tts_voices = {"aura-2": [], "aura-1": []}
    if isinstance(tts_raw, list):
        for m in tts_raw:
            voice_name = m.get("name", m.get("canonical_name", "unknown"))
            model_version = m.get("model", m.get("version", ""))
            if "aura-1" in str(model_version).lower():
                tts_voices["aura-1"].append(voice_name)
            else:
                tts_voices["aura-2"].append(voice_name)

    print(f"  TTS: {len(tts_raw)} voices -> 2 model entries (Aura-2, Aura-1)")

    for model_key in ["aura-2", "aura-1"]:
        voices = tts_voices[model_key]
        price_info = DEEPGRAM_TTS_PRICING[model_key]
        amt = price_info["amount"]
        ft_limit = f"~{200 / amt / 1000:,.1f}M chars on $200 credit"
        display_name = "Deepgram Aura 2" if model_key == "aura-2" else "Deepgram Aura 1"

        models.append({
            "model_id": f"deepgram-tts/{model_key}",
            "display_name": display_name,
            "provider": "Deepgram",
            "provider_slug": "deepgram",
            "category": "tts",
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
                "voice_cloning": False,
                "multilingual": False,
                "languages": ["en"],
                "language_count": 1,
                "voices_count": len(voices) or None,
                "voices": voices[:20] if voices else None,
                "max_input_chars": 2000,
            },
            "pricing": {
                "model": "per_1k_chars",
                "amount": amt,
                "currency": "USD",
                "unit": "1k_characters",
                "normalized": {
                    "per_million_chars_usd": amt * 1000
                },
                "free_tier": True,
                "free_tier_type": "trial_credit",
                "free_tier_amount": "$200 one-time credit (shared with STT)",
                "free_tier_limit": ft_limit,
            },
            "technical": _base_tech,
            "provider_info": _base_provider,
            "data_source": "deepgram_api",
        })

    print(f"  Total: {len(models)} entries (rolled up)")
    return models


# =============================================================================
# ELEVENLABS
# =============================================================================

ELEVENLABS_KNOWN_MODELS = {
    "eleven_multilingual_v2": {
        "name": "Eleven Multilingual v2",
        "cost_factor": 1.0,
        "languages": 29,
        "latency_ms": 300,
        "can_clone": True,
        "can_style": True,
    },
    "eleven_turbo_v2_5": {
        "name": "Eleven Turbo v2.5",
        "cost_factor": 0.5,
        "languages": 32,
        "latency_ms": 150,
        "can_clone": True,
        "can_style": True,
    },
    "eleven_flash_v2_5": {
        "name": "Eleven Flash v2.5",
        "cost_factor": 0.25,
        "languages": 32,
        "latency_ms": 75,
        "can_clone": True,
        "can_style": False,
    },
    "eleven_english_sts_v2": {
        "name": "Eleven English v2 (STS)",
        "cost_factor": 1.0,
        "languages": 1,
        "latency_ms": 300,
        "can_clone": True,
        "can_style": True,
    },
    "eleven_multilingual_sts_v2": {
        "name": "Eleven Multilingual v2 (STS)",
        "cost_factor": 1.0,
        "languages": 29,
        "latency_ms": 300,
        "can_clone": True,
        "can_style": True,
    },
}


def fetch_elevenlabs():
    """Fetch ElevenLabs models (using known model list + voices endpoint)."""
    print("\n--- ElevenLabs ---")

    # Try to get voice count from public voices endpoint
    voices_data = fetch_json("https://api.elevenlabs.io/v1/voices")
    voice_count = len(voices_data.get("voices", [])) if voices_data else 21
    print(f"  Public voices available: {voice_count}")

    models = []
    base_rate_per_1k = 0.30  # Approximate at Scale tier

    for model_id, info in ELEVENLABS_KNOWN_MODELS.items():
        cost_factor = info["cost_factor"]
        effective_rate = base_rate_per_1k * cost_factor

        models.append({
            "model_id": f"elevenlabs/{model_id}",
            "display_name": info["name"],
            "provider": "ElevenLabs",
            "provider_slug": "elevenlabs",
            "category": "tts",
            "connection_types": {
                "rest_sync": True,
                "rest_batch": False,
                "rest_streaming": True,
                "websocket_streaming": True,
                "grpc": False,
                "sse": False,
            },
            "capabilities": {
                "real_time": True,
                "streaming": True,
                "voice_cloning": info["can_clone"],
                "voice_conversion": "sts" in model_id,
                "style_control": info["can_style"],
                "multilingual": info["languages"] > 1,
                "language_count": info["languages"],
                "latency_ms": info["latency_ms"],
                "voices_available": voice_count,
            },
            "pricing": {
                "model": "per_character",
                "cost_factor": cost_factor,
                "estimated_per_1k_chars": effective_rate,
                "currency": "USD",
                "unit": "character",
                "normalized": {
                    "per_million_chars_usd": effective_rate * 1000
                },
                "free_tier": True,
                "free_tier_amount": "10,000 chars/month",
                "notes": f"Cost factor {cost_factor}x base rate. Actual rate depends on subscription tier.",
            },
            "technical": {
                "architecture": "proprietary",
                "license": "commercial",
                "open_source": False,
                "self_hostable": False,
                "openai_compatible": False,
            },
            "provider_info": {
                "signup_url": "https://elevenlabs.io/sign-up",
                "api_base_url": "https://api.elevenlabs.io",
                "docs_url": "https://elevenlabs.io/docs",
                "auth_method": "header",
                "auth_header": "xi-api-key",
                "auth_format": "{key}",
                "python_sdk": "elevenlabs",
            },
            "data_source": "elevenlabs_known",
        })

    print(f"  {len(models)} TTS models")
    return models


# =============================================================================
# OPENAI
# =============================================================================

OPENAI_AUDIO_MODELS = {
    "whisper-1": {
        "category": "stt",
        "rate": 0.006,
        "unit": "per_minute",
        "languages": 57,
        "streaming": False,
    },
    "tts-1": {
        "category": "tts",
        "rate": 15.0,
        "unit": "per_million_chars",
        "languages": 57,
        "streaming": True,
    },
    "tts-1-hd": {
        "category": "tts",
        "rate": 30.0,
        "unit": "per_million_chars",
        "languages": 57,
        "streaming": True,
    },
    "gpt-4o-mini-tts": {
        "category": "tts",
        "rate": 12.0,
        "unit": "per_million_chars",
        "languages": 57,
        "streaming": True,
    },
    "gpt-4o-transcribe": {
        "category": "stt",
        "rate": 0.006,
        "unit": "per_minute",
        "languages": 57,
        "streaming": False,
    },
    "gpt-4o-mini-transcribe": {
        "category": "stt",
        "rate": 0.003,
        "unit": "per_minute",
        "languages": 57,
        "streaming": False,
    },
}


def fetch_openai():
    """Fetch OpenAI audio models."""
    print("\n--- OpenAI ---")
    if not OPENAI_API_KEY:
        print("  No OPENAI_API_KEY — using known model list")
        api_models = []
    else:
        data = fetch_json(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        )
        api_models = data.get("data", []) if data else []
        print(f"  Fetched {len(api_models)} total models from API")

    # Filter to audio models or use known list
    models = []
    for model_id, info in OPENAI_AUDIO_MODELS.items():
        # Check if it exists in API response (if we have one)
        if api_models:
            found = any(m.get("id") == model_id for m in api_models)
            if not found:
                print(f"  Note: {model_id} not found in API (may be limited access)")

        is_tts = info["category"] == "tts"
        is_stt = info["category"] == "stt"

        if is_tts:
            pricing_normalized = {"per_million_chars_usd": info["rate"]}
        else:
            pricing_normalized = {"per_hour_usd": info["rate"] * 60}

        models.append({
            "model_id": f"openai/{model_id}",
            "display_name": f"OpenAI {model_id}",
            "provider": "OpenAI",
            "provider_slug": "openai",
            "category": info["category"],
            "connection_types": {
                "rest_sync": True,
                "rest_batch": False,
                "rest_streaming": info.get("streaming", False),
                "websocket_streaming": False,
                "grpc": False,
                "sse": False,
            },
            "capabilities": {
                "real_time": info.get("streaming", False),
                "streaming": info.get("streaming", False),
                "voice_cloning": False,
                "multilingual": True,
                "language_count": info["languages"],
                "voices": ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"] if is_tts else None,
            },
            "pricing": {
                "model": info["unit"],
                "amount": info["rate"],
                "currency": "USD",
                "unit": "minute" if is_stt else "million_characters",
                "normalized": pricing_normalized,
                "free_tier": False,
                "free_tier_amount": "$5 credit for new accounts (shared)",
            },
            "technical": {
                "architecture": "proprietary",
                "license": "commercial",
                "open_source": False,
                "self_hostable": False,
                "openai_compatible": True,
            },
            "provider_info": {
                "signup_url": "https://platform.openai.com/signup",
                "api_base_url": "https://api.openai.com/v1",
                "docs_url": "https://platform.openai.com/docs",
                "auth_method": "header",
                "auth_header": "Authorization",
                "auth_format": "Bearer {key}",
                "python_sdk": "openai",
            },
            "data_source": "openai_known",
        })

    print(f"  {len(models)} audio models (STT + TTS)")
    return models


# =============================================================================
# GROQ
# =============================================================================

GROQ_AUDIO_MODELS = {
    "whisper-large-v3": {
        "category": "stt",
        "rate_per_hour": 0.111,
        "speed": "217x realtime",
        "streaming": False,
    },
    "whisper-large-v3-turbo": {
        "category": "stt",
        "rate_per_hour": 0.04,
        "speed": "228x realtime",
        "streaming": False,
    },
    "canopylabs/orpheus-v1-english": {
        "category": "tts",
        "rate_per_million_chars": 22.0,
        "streaming": True,
    },
    "canopylabs/orpheus-arabic-saudi": {
        "category": "tts",
        "rate_per_million_chars": 40.0,
        "streaming": True,
    },
}


def fetch_groq():
    """Fetch Groq audio models."""
    print("\n--- Groq ---")

    if GROQ_API_KEY:
        data = fetch_json(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
        if data:
            api_models = data.get("data", [])
            audio_ids = [m["id"] for m in api_models if any(k in m["id"] for k in ["whisper", "orpheus"])]
            print(f"  Found audio models in API: {audio_ids}")
    else:
        print("  No GROQ_API_KEY — using known model list")

    models = []
    for model_id, info in GROQ_AUDIO_MODELS.items():
        is_tts = info["category"] == "tts"

        if is_tts:
            pricing = {
                "model": "per_million_chars",
                "amount": info["rate_per_million_chars"],
                "currency": "USD",
                "unit": "million_characters",
                "normalized": {"per_million_chars_usd": info["rate_per_million_chars"]},
            }
        else:
            pricing = {
                "model": "per_hour",
                "amount": info["rate_per_hour"],
                "currency": "USD",
                "unit": "hour",
                "normalized": {"per_hour_usd": info["rate_per_hour"]},
                "billing_increment": "10_second_minimum",
            }

        models.append({
            "model_id": f"groq/{model_id}",
            "display_name": f"Groq {model_id.split('/')[-1]}",
            "provider": "Groq",
            "provider_slug": "groq",
            "category": info["category"],
            "connection_types": {
                "rest_sync": True,
                "rest_batch": False,
                "rest_streaming": info.get("streaming", False),
                "websocket_streaming": False,
                "grpc": False,
                "sse": False,
            },
            "capabilities": {
                "real_time": False,
                "streaming": info.get("streaming", False),
                "voice_cloning": False,
                "multilingual": True if info["category"] == "stt" else False,
                "language_count": 57 if info["category"] == "stt" else 1,
                "speed": info.get("speed"),
                "voices": ["troy", "hannah", "austin"] if is_tts else None,
                "emotion_tags": is_tts,
            },
            "pricing": {
                **pricing,
                "free_tier": True,
                "free_tier_amount": "Daily free token allocation",
            },
            "technical": {
                "architecture": "LPU inference",
                "license": "commercial",
                "open_source": False,
                "self_hostable": False,
                "openai_compatible": True,
            },
            "provider_info": {
                "signup_url": "https://console.groq.com/signup",
                "api_base_url": "https://api.groq.com/openai/v1",
                "docs_url": "https://console.groq.com/docs",
                "auth_method": "header",
                "auth_header": "Authorization",
                "auth_format": "Bearer {key}",
                "python_sdk": "groq",
            },
            "data_source": "groq_known",
        })

    print(f"  {len(models)} audio models")
    return models


# =============================================================================
# FIREWORKS
# =============================================================================

FIREWORKS_AUDIO_MODELS = {
    "accounts/fireworks/models/whisper-v3": {
        "category": "stt",
        "rate_per_minute": 0.0015,
        "streaming": False,
    },
    "accounts/fireworks/models/whisper-v3-turbo": {
        "category": "stt",
        "rate_per_minute": 0.0009,
        "streaming": False,
    },
}


def fetch_fireworks():
    """Fetch Fireworks audio models."""
    print("\n--- Fireworks AI ---")

    if FIREWORKS_API_KEY:
        data = fetch_json(
            "https://api.fireworks.ai/inference/v1/models",
            headers={"Authorization": f"Bearer {FIREWORKS_API_KEY}"},
        )
        if data:
            api_models = data.get("data", [])
            audio_ids = [m["id"] for m in api_models if "whisper" in m.get("id", "")]
            print(f"  Found audio models in API: {audio_ids}")
    else:
        print("  No FIREWORKS_API_KEY — using known model list")

    models = []
    for model_id, info in FIREWORKS_AUDIO_MODELS.items():
        short_name = model_id.split("/")[-1]
        rate = info["rate_per_minute"]

        models.append({
            "model_id": f"fireworks/{short_name}",
            "display_name": f"Fireworks {short_name}",
            "provider": "Fireworks AI",
            "provider_slug": "fireworks",
            "category": info["category"],
            "fireworks_model_id": model_id,
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
                "multilingual": True,
                "language_count": 57,
            },
            "pricing": {
                "model": "per_minute",
                "amount": rate,
                "currency": "USD",
                "unit": "minute",
                "normalized": {"per_hour_usd": rate * 60},
                "free_tier": True,
                "free_tier_amount": "$1 credit",
                "billing_increment": "per_second",
            },
            "technical": {
                "architecture": "whisper",
                "license": "commercial",
                "open_source": False,
                "self_hostable": False,
                "openai_compatible": True,
            },
            "provider_info": {
                "signup_url": "https://fireworks.ai/login",
                "api_base_url": "https://api.fireworks.ai/inference/v1",
                "docs_url": "https://docs.fireworks.ai",
                "auth_method": "header",
                "auth_header": "Authorization",
                "auth_format": "Bearer {key}",
                "python_sdk": "fireworks-ai",
            },
            "data_source": "fireworks_known",
        })

    print(f"  {len(models)} audio models")
    return models


# =============================================================================
# MANUAL PROVIDERS (no API listing, data from pricing pages)
# =============================================================================

def get_manual_providers():
    """Providers without model listing APIs — data from docs/pricing pages."""
    print("\n--- Manual providers (from pricing pages) ---")

    manual = [
        # AssemblyAI
        {
            "model_id": "assemblyai/universal-3-pro",
            "display_name": "AssemblyAI Universal-3 Pro",
            "provider": "AssemblyAI",
            "provider_slug": "assemblyai",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": False, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": False, "streaming": False, "multilingual": True,
                "language_count": 99, "diarization": True, "timestamps": True,
            },
            "pricing": {
                "model": "per_hour", "amount": 0.21, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 0.21},
                "free_tier": True, "free_tier_amount": "185 hours",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://www.assemblyai.com/dashboard/signup",
                "api_base_url": "https://api.assemblyai.com",
                "docs_url": "https://www.assemblyai.com/docs",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "{key}",
                "python_sdk": "assemblyai",
            },
            "data_source": "manual_pricing_page",
        },
        {
            "model_id": "assemblyai/universal-2",
            "display_name": "AssemblyAI Universal-2",
            "provider": "AssemblyAI",
            "provider_slug": "assemblyai",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 16, "diarization": True, "timestamps": True,
            },
            "pricing": {
                "model": "per_hour", "amount": 0.15, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 0.15},
                "free_tier": True, "free_tier_amount": "333 hours streaming",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://www.assemblyai.com/dashboard/signup",
                "api_base_url": "https://api.assemblyai.com",
                "docs_url": "https://www.assemblyai.com/docs",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "{key}",
                "python_sdk": "assemblyai",
            },
            "data_source": "manual_pricing_page",
        },
        # Rev.ai
        {
            "model_id": "revai/reverb",
            "display_name": "Rev.ai Reverb",
            "provider": "Rev.ai",
            "provider_slug": "revai",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": False,
                "language_count": 1, "languages": ["en"],
            },
            "pricing": {
                "model": "per_hour", "amount": 0.20, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 0.20},
                "free_tier": True, "free_tier_amount": "5 hours",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://www.rev.ai/access_token",
                "api_base_url": "https://api.rev.ai/speechtotext/v1",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "rev_ai",
            },
            "data_source": "manual_pricing_page",
        },
        # Gladia
        {
            "model_id": "gladia/default",
            "display_name": "Gladia",
            "provider": "Gladia",
            "provider_slug": "gladia",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 100, "auto_language_switch": True,
            },
            "pricing": {
                "model": "per_hour", "amount": 0.61, "currency": "USD", "unit": "hour",
                "streaming_rate_per_hour": 0.75,
                "normalized": {"per_hour_usd": 0.61},
                "free_tier": True, "free_tier_amount": "10 hours/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://app.gladia.io/auth/signup",
                "api_base_url": "https://api.gladia.io",
                "auth_method": "header", "auth_header": "x-gladia-key", "auth_format": "{key}",
                "python_sdk": "gladia",
            },
            "data_source": "manual_pricing_page",
        },
        # Speechmatics
        {
            "model_id": "speechmatics/default",
            "display_name": "Speechmatics",
            "provider": "Speechmatics",
            "provider_slug": "speechmatics",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 50, "diarization": True, "on_premise": True,
            },
            "pricing": {
                "model": "per_hour", "amount": 0.24, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 0.24},
                "free_tier": True, "free_tier_amount": "8 hours/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://portal.speechmatics.com/signup",
                "api_base_url": "https://asr.api.speechmatics.com/v2",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "speechmatics-python",
            },
            "data_source": "manual_pricing_page",
        },
        # Cartesia STT
        {
            "model_id": "cartesia/ink-whisper",
            "display_name": "Cartesia Ink-Whisper",
            "provider": "Cartesia",
            "provider_slug": "cartesia",
            "category": "stt",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 57,
            },
            "pricing": {
                "model": "per_hour", "amount": 0.13, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 0.13},
                "free_tier": True, "free_tier_amount": "20K credits/month",
            },
            "technical": {"architecture": "whisper-variant", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://play.cartesia.ai/keys",
                "api_base_url": "https://api.cartesia.ai",
                "auth_method": "header", "auth_header": "X-API-Key", "auth_format": "{key}",
                "python_sdk": "cartesia",
                "extra_headers": {"Cartesia-Version": "2026-03-01"},
            },
            "data_source": "manual_pricing_page",
        },
        # Cartesia TTS
        {
            "model_id": "cartesia/sonic-3.5",
            "display_name": "Cartesia Sonic 3.5",
            "provider": "Cartesia",
            "provider_slug": "cartesia",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": True,
                "websocket_streaming": True, "grpc": False, "sse": True,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 30,
                "emotion_control": True, "speed_control": True,
                "latency_ms": 75,
            },
            "pricing": {
                "model": "per_second_audio",
                "amount": 0.03,
                "currency": "USD",
                "unit": "second_of_audio",
                "notes": "15 credits/sec at Scale plan pricing",
                "normalized": {"per_million_chars_usd": None},
                "free_tier": True, "free_tier_amount": "20K credits/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://play.cartesia.ai/keys",
                "api_base_url": "https://api.cartesia.ai",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "cartesia",
                "extra_headers": {"Cartesia-Version": "2026-03-01"},
            },
            "data_source": "manual_pricing_page",
        },
        # LMNT
        {
            "model_id": "lmnt/default",
            "display_name": "LMNT",
            "provider": "LMNT",
            "provider_slug": "lmnt",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 10,
                "latency_ms": 50,
            },
            "pricing": {
                "model": "per_1k_chars", "amount": 0.035, "currency": "USD", "unit": "1k_characters",
                "normalized": {"per_million_chars_usd": 35.0},
                "free_tier": True, "free_tier_amount": "15K chars/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://app.lmnt.com",
                "api_base_url": "https://api.lmnt.com",
                "auth_method": "header", "auth_header": "X-API-Key", "auth_format": "{key}",
                "python_sdk": "lmnt",
                "extra_headers": {"lmnt-version": "1.0"},
            },
            "data_source": "manual_pricing_page",
        },
        # Resemble.ai
        {
            "model_id": "resemble/default",
            "display_name": "Resemble.ai",
            "provider": "Resemble.ai",
            "provider_slug": "resemble",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": True,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 24,
                "on_premise": True, "deepfake_detection": True,
            },
            "pricing": {
                "model": "per_second_audio", "amount": 0.0005, "currency": "USD", "unit": "second_of_audio",
                "normalized": {"per_million_chars_usd": None},
                "free_tier": False,
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://app.resemble.ai/signup",
                "api_base_url": "https://app.resemble.ai/api/v2",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Token token={key}",
                "python_sdk": "resemble",
            },
            "data_source": "manual_pricing_page",
        },
        # Play.ht
        {
            "model_id": "playht/3.0-mini",
            "display_name": "Play.ht 3.0 Mini",
            "provider": "Play.ht",
            "provider_slug": "playht",
            "category": "tts",
            "connection_types": {
                "rest_sync": False, "rest_batch": False, "rest_streaming": True,
                "websocket_streaming": False, "grpc": True, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 140,
            },
            "pricing": {
                "model": "subscription", "amount": None, "currency": "USD",
                "notes": "Creator ~$31/mo, Pro ~$79/mo",
                "free_tier": True, "free_tier_amount": "Limited trial",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://play.ht/studio/api-access",
                "api_base_url": "https://api.play.ht/api/v2",
                "auth_method": "dual_header",
                "auth_headers": {"X-USER-ID": "{user_id}", "AUTHORIZATION": "{key}"},
                "python_sdk": "pyht",
            },
            "data_source": "manual_pricing_page",
        },
        # Speechify
        {
            "model_id": "speechify/simba",
            "display_name": "Speechify Simba",
            "provider": "Speechify",
            "provider_slug": "speechify",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": True,
                "websocket_streaming": False, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 60,
                "voices_count": 1000, "latency_ms": 250,
            },
            "pricing": {
                "model": "per_million_chars", "amount": 10.0, "currency": "USD", "unit": "million_characters",
                "normalized": {"per_million_chars_usd": 10.0},
                "free_tier": True, "free_tier_amount": "50K chars/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://speechify.com/api",
                "api_base_url": "https://api.sws.speechify.com",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "speechify",
            },
            "data_source": "manual_pricing_page",
        },
        # Unreal Speech
        {
            "model_id": "unrealspeech/default",
            "display_name": "Unreal Speech",
            "provider": "Unreal Speech",
            "provider_slug": "unrealspeech",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": True, "rest_streaming": True,
                "websocket_streaming": False, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": False,
                "multilingual": False, "language_count": 1, "languages": ["en"],
                "voices_count": 6,
            },
            "pricing": {
                "model": "per_1k_chars", "amount": 0.008, "currency": "USD", "unit": "1k_characters",
                "normalized": {"per_million_chars_usd": 8.0},
                "free_tier": True, "free_tier_amount": "250K chars/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://unrealspeech.com",
                "api_base_url": "https://api.v7.unrealspeech.com",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "unrealspeech",
            },
            "data_source": "manual_pricing_page",
        },
        # Fish Audio
        {
            "model_id": "fishaudio/default",
            "display_name": "Fish Audio",
            "provider": "Fish Audio",
            "provider_slug": "fishaudio",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 10,
                "community_voices": True,
            },
            "pricing": {
                "model": "per_1k_chars", "amount": 0.01, "currency": "USD", "unit": "1k_characters",
                "normalized": {"per_million_chars_usd": 10.0},
                "free_tier": True, "free_tier_amount": "Limited credits",
            },
            "technical": {"architecture": "sovits", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://fish.audio",
                "api_base_url": "https://api.fish.audio",
                "auth_method": "header", "auth_header": "Authorization", "auth_format": "Bearer {key}",
                "python_sdk": "fish-audio-sdk",
            },
            "data_source": "manual_pricing_page",
        },
        # AWS Polly
        {
            "model_id": "aws/polly-neural",
            "display_name": "AWS Polly Neural",
            "provider": "AWS",
            "provider_slug": "aws",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": False, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": False, "streaming": False, "voice_cloning": False,
                "multilingual": True, "language_count": 30,
                "ssml": True, "speech_marks": True,
            },
            "pricing": {
                "model": "per_million_chars", "amount": 16.0, "currency": "USD", "unit": "million_characters",
                "normalized": {"per_million_chars_usd": 16.0},
                "free_tier": True, "free_tier_amount": "1M chars/month (12 months)",
            },
            "technical": {"architecture": "neural", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://aws.amazon.com/polly/",
                "api_base_url": "https://polly.{region}.amazonaws.com",
                "auth_method": "aws_sig_v4",
                "python_sdk": "boto3",
            },
            "data_source": "manual_pricing_page",
        },
        # Google Cloud TTS
        {
            "model_id": "google/cloud-tts-neural2",
            "display_name": "Google Cloud TTS Neural2",
            "provider": "Google Cloud",
            "provider_slug": "google-cloud",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": False, "rest_streaming": True,
                "websocket_streaming": False, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": False, "streaming": True, "voice_cloning": False,
                "multilingual": True, "language_count": 50,
                "voices_count": 400, "ssml": True,
            },
            "pricing": {
                "model": "per_million_chars", "amount": 16.0, "currency": "USD", "unit": "million_characters",
                "normalized": {"per_million_chars_usd": 16.0},
                "free_tier": True, "free_tier_amount": "1M chars/month (always free)",
            },
            "technical": {"architecture": "neural", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://console.cloud.google.com",
                "api_base_url": "https://texttospeech.googleapis.com",
                "auth_method": "oauth2_or_api_key",
                "python_sdk": "google-cloud-texttospeech",
            },
            "data_source": "manual_pricing_page",
        },
        # Azure Speech TTS
        {
            "model_id": "azure/speech-tts-neural",
            "display_name": "Azure Speech Neural TTS",
            "provider": "Azure",
            "provider_slug": "azure",
            "category": "tts",
            "connection_types": {
                "rest_sync": True, "rest_batch": True, "rest_streaming": True,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "voice_cloning": True,
                "multilingual": True, "language_count": 140,
                "voices_count": 400, "ssml": True,
                "speaking_styles": True, "emotion_control": True,
            },
            "pricing": {
                "model": "per_million_chars", "amount": 16.0, "currency": "USD", "unit": "million_characters",
                "normalized": {"per_million_chars_usd": 16.0},
                "free_tier": True, "free_tier_amount": "500K chars/month",
            },
            "technical": {"architecture": "neural", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://portal.azure.com",
                "api_base_url": "https://{region}.tts.speech.microsoft.com",
                "auth_method": "header", "auth_header": "Ocp-Apim-Subscription-Key", "auth_format": "{key}",
                "python_sdk": "azure-cognitiveservices-speech",
            },
            "data_source": "manual_pricing_page",
        },
        # Google Cloud STT
        {
            "model_id": "google/cloud-stt-chirp",
            "display_name": "Google Cloud Speech (Chirp)",
            "provider": "Google Cloud",
            "provider_slug": "google-cloud",
            "category": "stt",
            "connection_types": {
                "rest_sync": True, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": False, "grpc": True, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 100, "diarization": True,
            },
            "pricing": {
                "model": "per_minute", "amount": 0.024, "currency": "USD", "unit": "minute",
                "normalized": {"per_hour_usd": 1.44},
                "free_tier": True, "free_tier_amount": "60 min/month",
                "billing_increment": "15_seconds",
            },
            "technical": {"architecture": "chirp", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://console.cloud.google.com",
                "api_base_url": "https://speech.googleapis.com",
                "auth_method": "oauth2_or_api_key",
                "python_sdk": "google-cloud-speech",
            },
            "data_source": "manual_pricing_page",
        },
        # AWS Transcribe
        {
            "model_id": "aws/transcribe",
            "display_name": "AWS Transcribe",
            "provider": "AWS",
            "provider_slug": "aws",
            "category": "stt",
            "connection_types": {
                "rest_sync": False, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 100, "diarization": True,
                "custom_vocabulary": True, "content_redaction": True,
            },
            "pricing": {
                "model": "per_minute", "amount": 0.024, "currency": "USD", "unit": "minute",
                "normalized": {"per_hour_usd": 1.44},
                "free_tier": True, "free_tier_amount": "60 min/month (12 months)",
                "billing_increment": "per_second",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://aws.amazon.com/transcribe/",
                "api_base_url": "https://transcribe.{region}.amazonaws.com",
                "auth_method": "aws_sig_v4",
                "python_sdk": "boto3",
            },
            "data_source": "manual_pricing_page",
        },
        # Azure STT
        {
            "model_id": "azure/speech-stt",
            "display_name": "Azure Speech STT",
            "provider": "Azure",
            "provider_slug": "azure",
            "category": "stt",
            "connection_types": {
                "rest_sync": True, "rest_batch": True, "rest_streaming": False,
                "websocket_streaming": True, "grpc": False, "sse": False,
            },
            "capabilities": {
                "real_time": True, "streaming": True, "multilingual": True,
                "language_count": 100, "diarization": True,
                "custom_models": True,
            },
            "pricing": {
                "model": "per_hour", "amount": 1.00, "currency": "USD", "unit": "hour",
                "normalized": {"per_hour_usd": 1.00},
                "free_tier": True, "free_tier_amount": "5 hours/month",
            },
            "technical": {"architecture": "proprietary", "license": "commercial", "open_source": False, "openai_compatible": False},
            "provider_info": {
                "signup_url": "https://portal.azure.com",
                "api_base_url": "https://{region}.stt.speech.microsoft.com",
                "auth_method": "header", "auth_header": "Ocp-Apim-Subscription-Key", "auth_format": "{key}",
                "python_sdk": "azure-cognitiveservices-speech",
            },
            "data_source": "manual_pricing_page",
        },
    ]

    print(f"  {len(manual)} manually-defined models")
    return manual


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Fetching voice provider models (STT + TTS)")
    print("=" * 60)

    os.makedirs("data", exist_ok=True)
    all_models = []

    # Fetch from APIs
    all_models.extend(fetch_deepgram())
    time.sleep(0.5)
    all_models.extend(fetch_elevenlabs())
    time.sleep(0.5)
    all_models.extend(fetch_openai())
    time.sleep(0.5)
    all_models.extend(fetch_groq())
    time.sleep(0.5)
    all_models.extend(fetch_fireworks())

    # Add manual providers
    all_models.extend(get_manual_providers())

    # Remove raw_data before saving (too verbose)
    for m in all_models:
        m.pop("raw_data", None)

    # Save
    output = "data/voice_providers.json"
    with open(output, "w") as f:
        json.dump(all_models, f, indent=2)
    print(f"\nSaved: {output} ({len(all_models)} models)")

    # Summary
    from collections import Counter
    categories = Counter(m["category"] for m in all_models)
    providers = Counter(m["provider"] for m in all_models)

    print("\nCategory breakdown:")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")

    print("\nProvider breakdown:")
    for prov, count in providers.most_common():
        print(f"  {prov}: {count}")

    # Streaming support summary
    streaming_stt = [m for m in all_models if m["category"] == "stt" and m["connection_types"].get("websocket_streaming")]
    streaming_tts = [m for m in all_models if m["category"] == "tts" and m["connection_types"].get("websocket_streaming")]
    print(f"\nStreaming support:")
    print(f"  STT with WebSocket: {len(streaming_stt)} ({', '.join(m['provider'] for m in streaming_stt)})")
    print(f"  TTS with WebSocket: {len(streaming_tts)} ({', '.join(m['provider'] for m in streaming_tts)})")

    # Cheapest per category
    print("\nCheapest STT (per hour):")
    stt = [m for m in all_models if m["category"] == "stt" and m["pricing"].get("normalized", {}).get("per_hour_usd")]
    stt.sort(key=lambda x: x["pricing"]["normalized"]["per_hour_usd"])
    for m in stt[:5]:
        print(f"  ${m['pricing']['normalized']['per_hour_usd']:.3f}/hr - {m['display_name']}")

    print("\nCheapest TTS (per million chars):")
    tts = [m for m in all_models if m["category"] == "tts" and m["pricing"].get("normalized", {}).get("per_million_chars_usd")]
    tts.sort(key=lambda x: x["pricing"]["normalized"]["per_million_chars_usd"])
    for m in tts[:5]:
        print(f"  ${m['pricing']['normalized']['per_million_chars_usd']:.1f}/1M chars - {m['display_name']}")


if __name__ == "__main__":
    main()
