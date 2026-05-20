#!/usr/bin/env python3
"""
Daily LLM Provider Report Generator

Generates comprehensive daily reports tracking:
- Overall model and provider statistics
- Advanced features (TTS, STT, audio, image generation, video)
- Pricing trends and comparisons
- Provider rankings
- Feature availability by provider

Output formats:
- Markdown report (daily_report.md)
- JSON data (daily_report.json)
- HTML dashboard (optional)
"""

import json
import sys
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Set, Tuple

def load_data():
    """Load all necessary data files"""
    try:
        with open('openrouter_models.json') as f:
            models_data = json.load(f)
        with open('infrastructure_provider_map.json') as f:
            infra_data = json.load(f)
        return models_data, infra_data
    except FileNotFoundError as e:
        print(f"Error: Required data file not found: {e}")
        print("Run fetch_openrouter.py and map_infrastructure_providers.py first")
        sys.exit(1)

def categorize_models_by_features(models: List[dict]) -> Dict[str, dict]:
    """Categorize all models by their advanced features"""

    features = {
        'stt': [],           # Speech to Text (audio input)
        'tts': [],           # Text to Speech (audio output)
        'stt_tts': [],       # Both STT and TTS
        'video_input': [],   # Video input
        'image_gen': [],     # Image generation
        'multimodal': [],    # Multiple input types
    }

    for model in models:
        model_id = model['id']
        arch = model.get('architecture', {})
        input_mods = arch.get('input_modalities', [])
        output_mods = arch.get('output_modalities', [])

        has_audio_in = 'audio' in input_mods
        has_audio_out = 'audio' in output_mods
        has_video_in = 'video' in input_mods
        has_image_out = 'image' in output_mods

        model_info = {
            'id': model_id,
            'name': model['name'],
            'modality': arch.get('modality', 'unknown'),
            'input_modalities': input_mods,
            'output_modalities': output_mods,
            'pricing': model.get('pricing', {}),
            'context_length': model.get('context_length', 0),
            'supported_voices': model.get('supported_voices'),
        }

        # Categorize by feature
        if has_audio_in and has_audio_out:
            features['stt_tts'].append(model_info)
        elif has_audio_in:
            features['stt'].append(model_info)
        elif has_audio_out:
            features['tts'].append(model_info)

        if has_video_in:
            features['video_input'].append(model_info)

        if has_image_out:
            features['image_gen'].append(model_info)

        # Multimodal = 2+ input types
        if len(input_mods) >= 2:
            features['multimodal'].append(model_info)

    return features

def analyze_providers_by_features(infra_data: dict, feature_models: Dict[str, list]) -> Dict[str, dict]:
    """Analyze which infrastructure providers support which features"""

    # Create sets of model IDs for each feature
    feature_model_ids = {
        feature: set(m['id'] for m in models)
        for feature, models in feature_models.items()
    }

    provider_features = {}

    for provider_name, provider_data in infra_data['providers'].items():
        provider_info = provider_data.get('provider_info', {})

        feature_counts = {
            'stt': 0,
            'tts': 0,
            'stt_tts': 0,
            'video_input': 0,
            'image_gen': 0,
            'multimodal': 0,
        }

        feature_model_lists = {
            'stt': [],
            'tts': [],
            'stt_tts': [],
            'video_input': [],
            'image_gen': [],
            'multimodal': [],
        }

        # Check each model this provider hosts
        for model in provider_data.get('models', []):
            model_id = model.get('model_id', '')

            for feature, model_ids in feature_model_ids.items():
                if model_id in model_ids:
                    feature_counts[feature] += 1
                    feature_model_lists[feature].append({
                        'id': model_id,
                        'name': model.get('model_name', ''),
                        'pricing': model.get('pricing', {}),
                        'performance': model.get('performance', {}),
                    })

        provider_features[provider_name] = {
            'info': {
                'location': provider_info.get('headquarters', 'Unknown'),
                'city': provider_info.get('headquarters_city', ''),
                'homepage': provider_info.get('homepage', ''),
                'support_url': provider_info.get('support_url', ''),
            },
            'total_models': provider_data.get('total_models', 0),
            'feature_counts': feature_counts,
            'feature_models': feature_model_lists,
            'total_advanced': sum(feature_counts.values()),
        }

    return provider_features

def calculate_pricing_stats(models: List[dict]) -> dict:
    """Calculate pricing statistics for a set of models"""
    if not models:
        return {'min': 0, 'max': 0, 'avg': 0, 'free_count': 0, 'paid_count': 0}

    prices = []
    free_count = 0

    for model in models:
        pricing = model.get('pricing', {})
        prompt = float(pricing.get('prompt', 0))
        completion = float(pricing.get('completion', 0))
        total = prompt + completion

        # Skip negative prices (e.g., auto router placeholder)
        if total < 0:
            continue

        if total == 0:
            free_count += 1
        else:
            prices.append(total)

    if not prices:
        return {'min': 0, 'max': 0, 'avg': 0, 'free_count': free_count, 'paid_count': 0}

    return {
        'min': min(prices) * 1_000_000,  # Per 1M tokens
        'max': max(prices) * 1_000_000,
        'avg': (sum(prices) / len(prices)) * 1_000_000,
        'free_count': free_count,
        'paid_count': len(prices),
    }

def generate_markdown_report(data: dict) -> str:
    """Generate markdown formatted report"""

    timestamp = data['timestamp']
    overall = data['overall_stats']
    features = data['feature_stats']
    providers = data['provider_rankings']

    md = f"""# OpenRouter Daily LLM Provider Report
**Generated:** {timestamp}

---

## 📊 Overall Statistics

- **Total Models:** {overall['total_models']}
- **Total Infrastructure Providers:** {overall['total_providers']}
- **Models with Advanced Features:** {overall['advanced_feature_models']}
- **Providers with Advanced Features:** {overall['providers_with_features']}

---

## 🎙️ Audio Features (TTS & STT)

### Full Voice Conversation (STT + TTS)
**Models with both audio input and output:** {len(features['stt_tts']['models'])}

"""

    if features['stt_tts']['models']:
        md += "| Model ID | Provider | Pricing (per 1M tokens) | Context |\n"
        md += "|----------|----------|------------------------|----------|\n"

        # Sort by price
        sorted_models = sorted(features['stt_tts']['models'],
                              key=lambda m: float(m['pricing'].get('prompt', 0)) + float(m['pricing'].get('completion', 0)))

        for model in sorted_models:
            pricing = model['pricing']
            prompt_price = float(pricing.get('prompt', 0)) * 1_000_000
            comp_price = float(pricing.get('completion', 0)) * 1_000_000
            total_price = prompt_price + comp_price

            price_str = "FREE" if total_price == 0 else f"${prompt_price:.2f} / ${comp_price:.2f}"
            context = f"{model['context_length']:,}" if model['context_length'] else "N/A"
            provider = model['id'].split('/')[0]

            md += f"| `{model['id']}` | {provider} | {price_str} | {context} |\n"

    pricing_stats = features['stt_tts']['pricing']
    if pricing_stats['free_count'] > 0:
        md += f"\n**Free models available:** {pricing_stats['free_count']}\n"
    if pricing_stats['min'] > 0:
        md += f"**Price range:** ${pricing_stats['min']:.2f} - ${pricing_stats['max']:.2f} per 1M tokens (avg: ${pricing_stats['avg']:.2f})\n"

    md += f"\n### Speech-to-Text Only (STT)\n"
    md += f"**Models with audio input:** {len(features['stt']['models'])}\n\n"

    if features['stt']['models']:
        # Show top 10 cheapest
        sorted_models = sorted(features['stt']['models'],
                              key=lambda m: float(m['pricing'].get('prompt', 0)) + float(m['pricing'].get('completion', 0)))[:10]

        md += "**Top 10 Most Affordable:**\n\n"
        md += "| Model ID | Pricing (per 1M) | Additional Features |\n"
        md += "|----------|-----------------|---------------------|\n"

        for model in sorted_models:
            pricing = model['pricing']
            prompt_price = float(pricing.get('prompt', 0)) * 1_000_000
            comp_price = float(pricing.get('completion', 0)) * 1_000_000
            total_price = prompt_price + comp_price

            price_str = "FREE" if total_price == 0 else f"${total_price:.2f}"

            # List additional input modalities
            additional = [m for m in model['input_modalities'] if m not in ['text', 'audio']]
            additional_str = ', '.join(additional) if additional else 'audio only'

            md += f"| `{model['id']}` | {price_str} | {additional_str} |\n"

    pricing_stats = features['stt']['pricing']
    md += f"\n**Free models:** {pricing_stats['free_count']}\n"
    if pricing_stats['min'] > 0:
        md += f"**Price range:** ${pricing_stats['min']:.2f} - ${pricing_stats['max']:.2f} per 1M tokens\n"

    md += f"\n### Text-to-Speech Only (TTS)\n"
    md += f"**Models with audio output:** {len(features['tts']['models'])}\n\n"

    if features['tts']['models']:
        md += "| Model ID | Provider | Pricing | Voices |\n"
        md += "|----------|----------|---------|--------|\n"

        for model in features['tts']['models']:
            pricing = model['pricing']
            prompt_price = float(pricing.get('prompt', 0)) * 1_000_000
            comp_price = float(pricing.get('completion', 0)) * 1_000_000
            total_price = prompt_price + comp_price

            price_str = "FREE" if total_price == 0 else f"${total_price:.2f}"
            provider = model['id'].split('/')[0]
            voices = model.get('supported_voices', 'N/A')

            md += f"| `{model['id']}` | {provider} | {price_str} | {voices} |\n"

    md += f"\n---\n\n## 🎬 Video Input Support\n\n"
    md += f"**Models with video input:** {len(features['video_input']['models'])}\n\n"

    pricing_stats = features['video_input']['pricing']
    md += f"- **Free models:** {pricing_stats['free_count']}\n"
    if pricing_stats['min'] > 0:
        md += f"- **Price range:** ${pricing_stats['min']:.2f} - ${pricing_stats['max']:.2f} per 1M tokens (avg: ${pricing_stats['avg']:.2f})\n"

    # Count by provider
    video_by_provider = defaultdict(int)
    for model in features['video_input']['models']:
        provider = model['id'].split('/')[0]
        video_by_provider[provider] += 1

    md += f"\n**Top providers by video model count:**\n\n"
    for provider, count in sorted(video_by_provider.items(), key=lambda x: x[1], reverse=True)[:10]:
        md += f"- **{provider}:** {count} models\n"

    md += f"\n---\n\n## 🎨 Image Generation Support\n\n"
    md += f"**Models with image generation:** {len(features['image_gen']['models'])}\n\n"

    if features['image_gen']['models']:
        md += "| Model ID | Provider | Pricing (per 1M) |\n"
        md += "|----------|----------|------------------|\n"

        for model in features['image_gen']['models']:
            pricing = model['pricing']
            prompt_price = float(pricing.get('prompt', 0)) * 1_000_000
            comp_price = float(pricing.get('completion', 0)) * 1_000_000
            total_price = prompt_price + comp_price

            price_str = "FREE" if total_price == 0 else f"${total_price:.2f}"
            provider = model['id'].split('/')[0]

            md += f"| `{model['id']}` | {provider} | {price_str} |\n"

    md += f"\n---\n\n## 🏢 Infrastructure Provider Rankings\n\n"
    md += f"### Top 20 Providers by Advanced Feature Support\n\n"
    md += "| Rank | Provider | Location | Audio | Video | Image | Total |\n"
    md += "|------|----------|----------|-------|-------|-------|-------|\n"

    for i, (name, data) in enumerate(providers['by_advanced_features'][:20], 1):
        location = f"{data['info']['city']}, {data['info']['location']}" if data['info']['city'] else data['info']['location']
        counts = data['feature_counts']
        audio = counts['stt'] + counts['tts'] + counts['stt_tts']
        video = counts['video_input']
        image = counts['image_gen']
        total = data['total_advanced']

        md += f"| {i} | **{name}** | {location} | {audio} | {video} | {image} | **{total}** |\n"

    md += f"\n### Providers by Specific Features\n\n"

    md += f"#### Audio (TTS/STT) Support\n"
    audio_providers = [(name, data) for name, data in providers['by_advanced_features']
                      if data['feature_counts']['stt'] + data['feature_counts']['tts'] + data['feature_counts']['stt_tts'] > 0]

    md += f"\n**{len(audio_providers)} providers** support audio features:\n\n"
    for name, data in audio_providers[:10]:
        counts = data['feature_counts']
        audio_total = counts['stt'] + counts['tts'] + counts['stt_tts']
        location = f"{data['info']['city']}, {data['info']['location']}" if data['info']['city'] else data['info']['location']

        md += f"- **{name}** ({location}): {audio_total} models"
        if counts['stt_tts'] > 0:
            md += f" - {counts['stt_tts']} full conversation"
        if data['info']['homepage']:
            md += f" - [{data['info']['homepage']}]({data['info']['homepage']})"
        md += "\n"

    md += f"\n#### Video Input Support\n"
    video_providers = [(name, data) for name, data in providers['by_advanced_features']
                      if data['feature_counts']['video_input'] > 0]

    md += f"\n**{len(video_providers)} providers** support video input\n\n"

    md += f"\n#### Image Generation Support\n"
    image_providers = [(name, data) for name, data in providers['by_advanced_features']
                      if data['feature_counts']['image_gen'] > 0]

    md += f"\n**{len(image_providers)} providers** support image generation:\n\n"
    for name, data in image_providers:
        counts = data['feature_counts']
        location = f"{data['info']['city']}, {data['info']['location']}" if data['info']['city'] else data['info']['location']
        md += f"- **{name}** ({location}): {counts['image_gen']} models\n"

    md += f"\n---\n\n## 💡 Key Insights\n\n"

    # Calculate some insights
    total_models = overall['total_models']
    audio_pct = (len(features['stt']['models']) + len(features['tts']['models']) + len(features['stt_tts']['models'])) / total_models * 100
    video_pct = len(features['video_input']['models']) / total_models * 100
    image_pct = len(features['image_gen']['models']) / total_models * 100

    md += f"- **{audio_pct:.1f}%** of models support audio features (STT or TTS)\n"
    md += f"- **{video_pct:.1f}%** of models support video input\n"
    md += f"- **{image_pct:.1f}%** of models support image generation\n"

    # Find cheapest options
    all_audio = features['stt']['models'] + features['tts']['models'] + features['stt_tts']['models']
    free_audio = [m for m in all_audio if float(m['pricing'].get('prompt', 0)) + float(m['pricing'].get('completion', 0)) == 0]

    if free_audio:
        md += f"- **{len(free_audio)} free audio models** available\n"

    # Provider concentration
    total_providers = overall['total_providers']
    providers_with_features = overall['providers_with_features']
    feature_pct = providers_with_features / total_providers * 100

    md += f"- **{feature_pct:.1f}%** of infrastructure providers support advanced features\n"

    md += f"\n---\n\n## 📈 Pricing Summary\n\n"

    md += "### Audio Models (STT + TTS)\n"
    if features['stt_tts']['pricing']['free_count'] > 0:
        md += f"- **Free options:** {features['stt_tts']['pricing']['free_count']} models\n"
    if features['stt_tts']['pricing']['min'] > 0:
        md += f"- **Paid range:** ${features['stt_tts']['pricing']['min']:.2f} - ${features['stt_tts']['pricing']['max']:.2f} per 1M tokens\n"
        md += f"- **Average:** ${features['stt_tts']['pricing']['avg']:.2f} per 1M tokens\n"

    md += "\n### STT Only Models\n"
    if features['stt']['pricing']['free_count'] > 0:
        md += f"- **Free options:** {features['stt']['pricing']['free_count']} models\n"
    if features['stt']['pricing']['min'] > 0:
        md += f"- **Paid range:** ${features['stt']['pricing']['min']:.2f} - ${features['stt']['pricing']['max']:.2f} per 1M tokens\n"
        md += f"- **Average:** ${features['stt']['pricing']['avg']:.2f} per 1M tokens\n"

    md += "\n### Video Input Models\n"
    if features['video_input']['pricing']['free_count'] > 0:
        md += f"- **Free options:** {features['video_input']['pricing']['free_count']} models\n"
    if features['video_input']['pricing']['min'] > 0:
        md += f"- **Paid range:** ${features['video_input']['pricing']['min']:.2f} - ${features['video_input']['pricing']['max']:.2f} per 1M tokens\n"
        md += f"- **Average:** ${features['video_input']['pricing']['avg']:.2f} per 1M tokens\n"

    md += "\n### Image Generation Models\n"
    if features['image_gen']['pricing']['free_count'] > 0:
        md += f"- **Free options:** {features['image_gen']['pricing']['free_count']} models\n"
    if features['image_gen']['pricing']['min'] > 0:
        md += f"- **Paid range:** ${features['image_gen']['pricing']['min']:.2f} - ${features['image_gen']['pricing']['max']:.2f} per 1M tokens\n"
        md += f"- **Average:** ${features['image_gen']['pricing']['avg']:.2f} per 1M tokens\n"

    md += f"\n---\n\n*Report generated by DAME LLM Providers Infrastructure Mapper*\n"
    md += f"*Data source: OpenRouter API*\n"

    return md

def generate_report():
    """Main report generation function"""

    print("Loading data...")
    models_data, infra_data = load_data()
    models = models_data['data']

    print(f"Analyzing {len(models)} models and {len(infra_data['providers'])} providers...")

    # Categorize models by features
    print("Categorizing models by features...")
    feature_models = categorize_models_by_features(models)

    # Analyze providers
    print("Analyzing provider capabilities...")
    provider_features = analyze_providers_by_features(infra_data, feature_models)

    # Calculate pricing stats
    print("Calculating pricing statistics...")
    feature_stats = {}
    for feature_name, feature_model_list in feature_models.items():
        feature_stats[feature_name] = {
            'count': len(feature_model_list),
            'models': feature_model_list,
            'pricing': calculate_pricing_stats(feature_model_list),
        }

    # Rank providers
    print("Ranking providers...")
    providers_with_features = {k: v for k, v in provider_features.items() if v['total_advanced'] > 0}
    ranked_providers = sorted(providers_with_features.items(),
                             key=lambda x: x[1]['total_advanced'],
                             reverse=True)

    # Compile report data
    report_data = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'overall_stats': {
            'total_models': len(models),
            'total_providers': len(infra_data['providers']),
            'advanced_feature_models': len(set(
                m['id'] for feature in feature_models.values() for m in feature
            )),
            'providers_with_features': len(providers_with_features),
        },
        'feature_stats': feature_stats,
        'provider_rankings': {
            'by_advanced_features': ranked_providers,
        },
        'provider_details': provider_features,
    }

    # Generate outputs
    print("Generating markdown report...")
    markdown_report = generate_markdown_report(report_data)

    with open('daily_report.md', 'w') as f:
        f.write(markdown_report)
    print("✓ Saved markdown report to: daily_report.md")

    # Save JSON (for programmatic access)
    print("Generating JSON report...")
    # Simplify for JSON (remove full model lists to reduce size)
    json_report = {
        'timestamp': report_data['timestamp'],
        'overall_stats': report_data['overall_stats'],
        'feature_stats': {
            feature: {
                'count': stats['count'],
                'pricing': stats['pricing'],
                'model_ids': [m['id'] for m in stats['models']],
            }
            for feature, stats in report_data['feature_stats'].items()
        },
        'provider_rankings': {
            'by_advanced_features': [
                {
                    'name': name,
                    'location': data['info']['location'],
                    'city': data['info']['city'],
                    'feature_counts': data['feature_counts'],
                    'total_advanced': data['total_advanced'],
                }
                for name, data in ranked_providers
            ]
        }
    }

    with open('daily_report.json', 'w') as f:
        json.dump(json_report, f, indent=2)
    print("✓ Saved JSON report to: daily_report.json")

    print(f"\n{'='*60}")
    print("DAILY REPORT SUMMARY")
    print(f"{'='*60}")
    print(f"Total Models: {report_data['overall_stats']['total_models']}")
    print(f"Total Providers: {report_data['overall_stats']['total_providers']}")
    print(f"\nAdvanced Features:")
    print(f"  STT+TTS: {feature_stats['stt_tts']['count']} models")
    print(f"  STT only: {feature_stats['stt']['count']} models")
    print(f"  TTS only: {feature_stats['tts']['count']} models")
    print(f"  Video input: {feature_stats['video_input']['count']} models")
    print(f"  Image generation: {feature_stats['image_gen']['count']} models")
    print(f"\nProviders with advanced features: {len(providers_with_features)}")
    print(f"{'='*60}")
    print("\nReports generated successfully!")

if __name__ == "__main__":
    generate_report()
