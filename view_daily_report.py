#!/usr/bin/env python3
"""
Daily Report Viewer

Interactive CLI tool to query and explore the daily report data:
- Show overall stats
- Filter by feature (TTS, STT, video, image gen)
- Compare pricing
- List top providers
- Export specific data
"""

import json
import sys
from datetime import datetime

def load_report():
    """Load the daily report JSON"""
    try:
        with open('daily_report.json') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: daily_report.json not found")
        print("Run generate_daily_report.py first")
        sys.exit(1)

def show_summary(report):
    """Show high-level summary"""
    print("\n" + "="*80)
    print("DAILY REPORT SUMMARY")
    print("="*80)
    print(f"\nGenerated: {report['timestamp']}")

    stats = report['overall_stats']
    print(f"\n📊 Overall Statistics:")
    print(f"  Total Models: {stats['total_models']}")
    print(f"  Total Providers: {stats['total_providers']}")
    print(f"  Models with Advanced Features: {stats['advanced_feature_models']}")
    print(f"  Providers with Advanced Features: {stats['providers_with_features']}")

    print(f"\n🎙️ Audio Features:")
    features = report['feature_stats']
    print(f"  STT + TTS (full conversation): {features['stt_tts']['count']} models")
    print(f"  STT only: {features['stt']['count']} models")
    print(f"  TTS only: {features['tts']['count']} models")

    print(f"\n🎬 Video & Image:")
    print(f"  Video input: {features['video_input']['count']} models")
    print(f"  Image generation: {features['image_gen']['count']} models")

def show_feature_details(report, feature):
    """Show detailed info for a specific feature"""
    feature_map = {
        'stt': 'Speech-to-Text (STT)',
        'tts': 'Text-to-Speech (TTS)',
        'stt_tts': 'Full Voice Conversation (STT + TTS)',
        'video': 'Video Input',
        'video_input': 'Video Input',
        'image': 'Image Generation',
        'image_gen': 'Image Generation',
    }

    # Normalize feature name
    feature_key = feature.lower().replace('-', '_')
    if feature_key not in report['feature_stats']:
        # Try aliases
        if feature_key == 'video':
            feature_key = 'video_input'
        elif feature_key == 'image':
            feature_key = 'image_gen'

    if feature_key not in report['feature_stats']:
        print(f"Unknown feature: {feature}")
        print(f"Available features: {', '.join(report['feature_stats'].keys())}")
        return

    feature_data = report['feature_stats'][feature_key]
    feature_name = feature_map.get(feature_key, feature_key.upper())

    print("\n" + "="*80)
    print(f"{feature_name}")
    print("="*80)

    print(f"\n📊 Statistics:")
    print(f"  Total Models: {feature_data['count']}")

    pricing = feature_data['pricing']
    if pricing['free_count'] > 0:
        print(f"  Free Models: {pricing['free_count']}")

    if pricing['min'] > 0:
        print(f"\n💰 Pricing (per 1M tokens):")
        print(f"  Cheapest: ${pricing['min']:.2f}")
        print(f"  Most Expensive: ${pricing['max']:.2f}")
        print(f"  Average: ${pricing['avg']:.2f}")

    print(f"\n📦 Models:")
    for i, model_id in enumerate(feature_data['model_ids'], 1):
        print(f"  {i:3}. {model_id}")

def show_pricing_comparison(report):
    """Compare pricing across all features"""
    print("\n" + "="*80)
    print("PRICING COMPARISON (per 1M tokens)")
    print("="*80)

    features = report['feature_stats']

    print(f"\n{'Feature':<30} {'Count':<8} {'Free':<8} {'Min $':<12} {'Max $':<12} {'Avg $':<12}")
    print("-" * 80)

    for feature_key, feature_data in features.items():
        if feature_key == 'multimodal':
            continue  # Skip multimodal for clarity

        feature_names = {
            'stt_tts': 'STT + TTS',
            'stt': 'STT only',
            'tts': 'TTS only',
            'video_input': 'Video input',
            'image_gen': 'Image generation',
        }

        name = feature_names.get(feature_key, feature_key)
        count = feature_data['count']
        pricing = feature_data['pricing']

        min_price = f"${pricing['min']:.2f}" if pricing['min'] > 0 else "N/A"
        max_price = f"${pricing['max']:.2f}" if pricing['max'] > 0 else "N/A"
        avg_price = f"${pricing['avg']:.2f}" if pricing['avg'] > 0 else "N/A"

        print(f"{name:<30} {count:<8} {pricing['free_count']:<8} {min_price:<12} {max_price:<12} {avg_price:<12}")

def show_top_providers(report, limit=20):
    """Show top providers by advanced feature support"""
    print("\n" + "="*80)
    print(f"TOP {limit} PROVIDERS BY ADVANCED FEATURES")
    print("="*80)

    providers = report['provider_rankings']['by_advanced_features']

    print(f"\n{'#':<4} {'Provider':<30} {'Location':<20} {'Audio':<8} {'Video':<8} {'Image':<8} {'Total'}")
    print("-" * 100)

    for i, provider in enumerate(providers[:limit], 1):
        name = provider['name']
        location = f"{provider['city']}, {provider['location']}" if provider['city'] else provider['location']
        counts = provider['feature_counts']

        audio = counts['stt'] + counts['tts'] + counts['stt_tts']
        video = counts['video_input']
        image = counts['image_gen']
        total = provider['total_advanced']

        print(f"{i:<4} {name:<30} {location:<20} {audio:<8} {video:<8} {image:<8} {total}")

def show_audio_providers(report):
    """Show only providers supporting audio features"""
    print("\n" + "="*80)
    print("PROVIDERS WITH AUDIO SUPPORT (TTS/STT)")
    print("="*80)

    providers = report['provider_rankings']['by_advanced_features']
    audio_providers = [
        p for p in providers
        if p['feature_counts']['stt'] + p['feature_counts']['tts'] + p['feature_counts']['stt_tts'] > 0
    ]

    print(f"\nFound {len(audio_providers)} providers with audio support:\n")

    for i, provider in enumerate(audio_providers, 1):
        name = provider['name']
        location = f"{provider['city']}, {provider['location']}" if provider['city'] else provider['location']
        counts = provider['feature_counts']

        stt_tts = counts['stt_tts']
        stt = counts['stt']
        tts = counts['tts']
        total_audio = stt + tts + stt_tts

        print(f"{i}. {name} ({location})")
        print(f"   Total audio models: {total_audio}")
        if stt_tts > 0:
            print(f"   - Full conversation (STT+TTS): {stt_tts}")
        if stt > 0:
            print(f"   - STT only: {stt}")
        if tts > 0:
            print(f"   - TTS only: {tts}")
        print()

def export_models_by_feature(report, feature, output_file):
    """Export model list for a specific feature to JSON"""
    feature_key = feature.lower().replace('-', '_')
    if feature_key == 'video':
        feature_key = 'video_input'
    elif feature_key == 'image':
        feature_key = 'image_gen'

    if feature_key not in report['feature_stats']:
        print(f"Unknown feature: {feature}")
        return

    feature_data = report['feature_stats'][feature_key]
    export_data = {
        'feature': feature_key,
        'count': feature_data['count'],
        'pricing': feature_data['pricing'],
        'models': feature_data['model_ids'],
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"✓ Exported {feature_data['count']} models to: {output_file}")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 view_daily_report.py summary              # Show overall summary")
        print("  python3 view_daily_report.py feature <name>       # Show feature details")
        print("  python3 view_daily_report.py pricing              # Compare pricing")
        print("  python3 view_daily_report.py providers [limit]    # Top providers")
        print("  python3 view_daily_report.py audio-providers      # Providers with audio")
        print("  python3 view_daily_report.py export <feature> <file>  # Export to JSON")
        print("\nFeature names: stt, tts, stt-tts, video, image")
        print("\nExamples:")
        print("  python3 view_daily_report.py summary")
        print("  python3 view_daily_report.py feature stt-tts")
        print("  python3 view_daily_report.py providers 10")
        print("  python3 view_daily_report.py export video video_models.json")
        sys.exit(1)

    report = load_report()
    command = sys.argv[1].lower()

    if command == 'summary':
        show_summary(report)
    elif command == 'feature' and len(sys.argv) > 2:
        show_feature_details(report, sys.argv[2])
    elif command == 'pricing':
        show_pricing_comparison(report)
    elif command == 'providers':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_top_providers(report, limit)
    elif command == 'audio-providers':
        show_audio_providers(report)
    elif command == 'export' and len(sys.argv) > 3:
        export_models_by_feature(report, sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
