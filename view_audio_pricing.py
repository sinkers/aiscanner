#!/usr/bin/env python3
"""
Quick audio model pricing viewer

Usage:
  python3 view_audio_pricing.py                # Show all audio models
  python3 view_audio_pricing.py stt            # STT only
  python3 view_audio_pricing.py tts            # TTS only
  python3 view_audio_pricing.py conversation   # Full conversation (STT+TTS)
  python3 view_audio_pricing.py providers      # Group by provider
"""

import json
import sys

def load_data():
    with open('infrastructure_provider_map.json') as f:
        return json.load(f)

def is_audio_model(model_id):
    """Check if model supports audio based on known patterns"""
    audio_patterns = [
        'gpt-audio', 'lyria', 'voxtral', 'mimo', 'nemotron-3-nano-omni',
        'gemini-2.0-flash', 'gemini-2.5-flash', 'gemini-2.5-pro',
        'gemini-3.1-flash', 'gemini-3.1-pro', 'gemini-3-flash',
        'gemini-pro-latest', 'gemini-flash-latest'
    ]
    return any(p in model_id for p in audio_patterns)

def categorize_model(model_id):
    """Categorize audio model type"""
    if 'gpt-audio' in model_id or 'gpt-4o-audio' in model_id:
        return 'conversation'  # STT + TTS
    elif 'lyria' in model_id:
        return 'tts'
    else:
        return 'stt'

def show_all_audio(data):
    print("\n" + "="*100)
    print("ALL AUDIO MODELS - DETAILED PRICING")
    print("="*100)

    models = []
    for provider_name, provider_data in data['providers'].items():
        for model in provider_data['models']:
            if is_audio_model(model['model_id']):
                pricing = model['pricing']
                total = (pricing['prompt'] + pricing['completion']) * 1_000_000
                category = categorize_model(model['model_id'])
                models.append({
                    'model_id': model['model_id'],
                    'provider': provider_name,
                    'category': category,
                    'prompt': pricing['prompt'] * 1_000_000,
                    'completion': pricing['completion'] * 1_000_000,
                    'total': total,
                    'uptime': model['performance'].get('uptime_24h', 0),
                    'context': model['context_length']
                })

    # Sort by category then price
    models.sort(key=lambda x: (x['category'], x['total']))

    current_category = None
    for model in models:
        if model['category'] != current_category:
            current_category = model['category']
            cat_name = {
                'conversation': '\n🎙️  FULL CONVERSATION (STT + TTS)',
                'tts': '\n🔊 TEXT-TO-SPEECH (TTS)',
                'stt': '\n🎤 SPEECH-TO-TEXT (STT)'
            }[current_category]
            print(cat_name)
            print("-" * 100)
            print(f"{'Model':<50} {'Provider':<20} {'Price/1M':<15} {'Uptime':<10} {'Context'}")
            print("-" * 100)

        price_str = f"${model['total']:.2f}" if model['total'] > 0 else "FREE"
        uptime_str = f"{model['uptime']:.1f}%" if model['uptime'] else "N/A"
        context_str = f"{model['context']:,}" if model['context'] else "N/A"

        print(f"{model['model_id']:<50} {model['provider']:<20} {price_str:<15} {uptime_str:<10} {context_str}")

def show_by_category(data, category):
    models = []
    for provider_name, provider_data in data['providers'].items():
        for model in provider_data['models']:
            if is_audio_model(model['model_id']) and categorize_model(model['model_id']) == category:
                pricing = model['pricing']
                total = (pricing['prompt'] + pricing['completion']) * 1_000_000
                models.append({
                    'model_id': model['model_id'],
                    'provider': provider_name,
                    'prompt': pricing['prompt'] * 1_000_000,
                    'completion': pricing['completion'] * 1_000_000,
                    'total': total,
                    'uptime': model['performance'].get('uptime_24h', 0),
                    'context': model['context_length']
                })

    models.sort(key=lambda x: x['total'])

    cat_names = {
        'conversation': 'FULL CONVERSATION (STT + TTS)',
        'tts': 'TEXT-TO-SPEECH (TTS)',
        'stt': 'SPEECH-TO-TEXT (STT)'
    }

    print("\n" + "="*100)
    print(f"{cat_names[category]} - {len(models)} MODELS")
    print("="*100)
    print(f"\n{'Model':<50} {'Provider':<20} {'Price/1M':<15} {'Uptime':<10} {'Context'}")
    print("-" * 100)

    for model in models:
        price_str = f"${model['total']:.2f}" if model['total'] > 0 else "FREE"
        uptime_str = f"{model['uptime']:.1f}%" if model['uptime'] else "N/A"
        context_str = f"{model['context']:,}" if model['context'] else "N/A"

        print(f"{model['model_id']:<50} {model['provider']:<20} {price_str:<15} {uptime_str:<10} {context_str}")

    # Show pricing summary
    free_count = sum(1 for m in models if m['total'] == 0)
    paid_models = [m for m in models if m['total'] > 0]

    print("\n" + "="*100)
    print("PRICING SUMMARY")
    print("="*100)
    print(f"Total models: {len(models)}")
    print(f"Free models: {free_count}")
    if paid_models:
        print(f"Paid models: {len(paid_models)}")
        print(f"Price range: ${min(m['total'] for m in paid_models):.2f} - ${max(m['total'] for m in paid_models):.2f} per 1M tokens")
        print(f"Average price: ${sum(m['total'] for m in paid_models) / len(paid_models):.2f} per 1M tokens")

def show_by_provider(data):
    print("\n" + "="*100)
    print("AUDIO MODELS GROUPED BY PROVIDER")
    print("="*100)

    providers = {}
    for provider_name, provider_data in data['providers'].items():
        audio_models = []
        for model in provider_data['models']:
            if is_audio_model(model['model_id']):
                pricing = model['pricing']
                total = (pricing['prompt'] + pricing['completion']) * 1_000_000
                audio_models.append({
                    'model_id': model['model_id'],
                    'category': categorize_model(model['model_id']),
                    'total': total
                })

        if audio_models:
            providers[provider_name] = {
                'models': audio_models,
                'info': provider_data['provider_info']
            }

    # Sort providers by number of models
    sorted_providers = sorted(providers.items(), key=lambda x: len(x[1]['models']), reverse=True)

    for provider_name, data in sorted_providers:
        info = data['info']
        models = data['models']

        stt_count = sum(1 for m in models if m['category'] == 'stt')
        tts_count = sum(1 for m in models if m['category'] == 'tts')
        conv_count = sum(1 for m in models if m['category'] == 'conversation')

        location = f"{info.get('headquarters_city', '')}, {info.get('headquarters', 'Unknown')}" if info.get('headquarters_city') else info.get('headquarters', 'Unknown')

        print(f"\n🏢 {provider_name} ({location})")
        print(f"   Total audio models: {len(models)}")
        if conv_count:
            print(f"   • Full Conversation (STT+TTS): {conv_count}")
        if stt_count:
            print(f"   • STT only: {stt_count}")
        if tts_count:
            print(f"   • TTS only: {tts_count}")

        # Show models
        for model in sorted(models, key=lambda x: x['total'])[:5]:
            price_str = f"${model['total']:.2f}/1M" if model['total'] > 0 else "FREE"
            cat_icon = {'conversation': '🎙️ ', 'stt': '🎤', 'tts': '🔊'}[model['category']]
            print(f"     {cat_icon} {model['model_id']} - {price_str}")

        if len(models) > 5:
            print(f"     ... and {len(models) - 5} more")

def main():
    data = load_data()

    if len(sys.argv) < 2:
        show_all_audio(data)
    else:
        cmd = sys.argv[1].lower()

        if cmd == 'stt':
            show_by_category(data, 'stt')
        elif cmd == 'tts':
            show_by_category(data, 'tts')
        elif cmd in ['conversation', 'full', 'stt-tts']:
            show_by_category(data, 'conversation')
        elif cmd == 'providers':
            show_by_provider(data)
        else:
            print(f"Unknown command: {cmd}")
            print("\nUsage:")
            print("  python3 view_audio_pricing.py                # Show all")
            print("  python3 view_audio_pricing.py stt            # STT only")
            print("  python3 view_audio_pricing.py tts            # TTS only")
            print("  python3 view_audio_pricing.py conversation   # Full conversation")
            print("  python3 view_audio_pricing.py providers      # By provider")
            sys.exit(1)

if __name__ == "__main__":
    main()
