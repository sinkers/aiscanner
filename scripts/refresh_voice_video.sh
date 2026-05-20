#!/bin/bash
# Refresh all voice/video model data
#
# Optional env vars for richer data:
#   FAL_API_KEY - fal.ai pricing data
#   HF_TOKEN - HuggingFace higher rate limits
#   OPENAI_API_KEY - OpenAI model verification
#   GROQ_API_KEY - Groq model verification
#   FIREWORKS_API_KEY - Fireworks model verification

set -e
cd "$(dirname "$0")/.."

echo "=== Voice & Video Data Refresh ==="
echo ""

# Step 1: Voice providers (Deepgram, ElevenLabs, OpenAI, Groq, Fireworks, manual)
echo "Step 1/4: Fetching voice providers..."
python3 scripts/fetch_voice_providers.py
echo ""

# Step 2: fal.ai (image, video, audio models)
echo "Step 2/4: Fetching fal.ai models..."
python3 scripts/fetch_fal_models.py
echo ""

# Step 3: HuggingFace (open source models)
echo "Step 3/4: Fetching HuggingFace models..."
python3 scripts/fetch_huggingface_models.py
echo ""

# Step 4: Merge all sources
echo "Step 4/4: Merging all data..."
python3 scripts/merge_voice_video_data.py
echo ""

echo "=== Done! ==="
echo "Output: data/voice_video_models.json"
echo ""
echo "To view summary:"
echo "  python3 -c \"import json; d=json.load(open('data/voice_video_models.json')); print(json.dumps(d['metadata'], indent=2))\""
