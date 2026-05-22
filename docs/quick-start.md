# Quick Start Guide

## What You Have

A complete infrastructure provider map for OpenRouter showing:
- **67 infrastructure providers** hosting **368 models**
- Where they're located (US, Singapore, China, Europe, etc.)
- How much they charge (pricing per 1M tokens)
- Performance metrics (uptime, latency, throughput)
- Which providers serve which models

## Files

### Data Files
- `infrastructure_provider_map.json` - Complete dataset (generated)
- `openrouter_models.json` - All models (fetched)
- `openrouter_providers.json` - All providers (fetched)

### Scripts
- `map_infrastructure_providers.py` - Regenerate the complete map
- `view_infrastructure_map.py` - Query and explore the data
- `fetch_openrouter.py` - Initial data fetch
- `filter_by_provider.py` - Demo filtering options
- `analyze_providers.py` - Analysis examples

### Documentation
- `INFRASTRUCTURE_MAP_SUMMARY.md` - Complete documentation
- `README.md` - Project overview
- `QUICK_START.md` - This file

## Quick Commands

### View All Providers
```bash
python3 view_infrastructure_map.py list
```
Shows all 67 providers sorted by model count.

### Provider Details
```bash
# See everything about a provider
python3 view_infrastructure_map.py provider "DeepInfra"
python3 view_infrastructure_map.py provider "Amazon Bedrock"
python3 view_infrastructure_map.py provider "Anthropic"
```

### Compare Providers for a Model
```bash
# Which provider is best for this model?
python3 view_infrastructure_map.py model "anthropic/claude-opus-4.7"
python3 view_infrastructure_map.py model "meta-llama/llama-3.1-70b-instruct"
python3 view_infrastructure_map.py model "deepseek/deepseek-v4-pro"
```

### Filter by Location
```bash
# US providers
python3 view_infrastructure_map.py location US

# Singapore providers
python3 view_infrastructure_map.py location SG

# China providers
python3 view_infrastructure_map.py location CN

# France providers
python3 view_infrastructure_map.py location FR
```

### Find Cheapest Models
```bash
# Top 20 cheapest
python3 view_infrastructure_map.py cheapest 20

# Top 100 cheapest
python3 view_infrastructure_map.py cheapest 100
```

## Key Findings

### Best Performance
- **Fastest**: Cerebras (199ms), Liquid (268ms), Cohere (295ms)
- **Most Reliable**: 14 providers at 100% uptime
- **Best Balance**: Mistral (342ms latency, 99.6% uptime)

### Best Value
- **Free Models**: Baidu, Nvidia, Poolside, Venice
- **Cheapest Paid**: DeepInfra, Novita ($0.00000002-0.000001/1M)
- **Premium**: OpenAI, Azure (10-100x more expensive)

### Most Models
1. Novita (73 models)
2. DeepInfra (64 models)
3. Google (62 models)
4. OpenAI (59 models)
5. Alibaba (43 models)

### By Region
- **US Dominated**: 37 of 67 providers (55%)
- **Asia Growing**: Singapore (6), China (4)
- **Europe Limited**: France (1), Netherlands (1), Sweden (1)

## Example Queries

### "I want the cheapest Claude model"
```bash
python3 view_infrastructure_map.py model "anthropic/claude-3-haiku"
```
Shows: Amazon Bedrock and Google both host it with pricing comparison.

### "Show me all Chinese providers"
```bash
python3 view_infrastructure_map.py location CN
```
Shows: Baidu (5 models), Xiaomi (5), DeepSeek (2), StreamLake (2)

### "What does DeepInfra offer?"
```bash
python3 view_infrastructure_map.py provider "DeepInfra"
```
Shows: 64 models, multiple quantization options, detailed pricing and performance.

### "Find free models"
```bash
python3 view_infrastructure_map.py cheapest 50 | grep ":free"
```
Shows: Models with :free suffix from various providers.

## Update the Data

To refresh with latest data from OpenRouter:
```bash
# This takes ~2 minutes and queries all 368 models
python3 map_infrastructure_providers.py
```

The script:
1. Loads existing model/provider data
2. Fetches endpoints for each model
3. Collects pricing and performance metrics
4. Saves to `infrastructure_provider_map.json`
5. Auto-resumes if interrupted

## Data Structure

### Provider Entry
```json
{
  "provider_name": {
    "provider_info": {
      "name": "DeepInfra",
      "headquarters": "US",
      "datacenters": ["US", "EU"],
      "privacy_policy": "...",
      "terms_of_service": "..."
    },
    "models": [...],
    "total_models": 64,
    "pricing_range": {
      "min_prompt": 0.00000002,
      "max_prompt": 0.00000120
    },
    "performance_stats": {
      "avg_uptime": 98.04,
      "avg_latency_p50": 1026,
      "avg_throughput_p50": 35.9
    }
  }
}
```

### Model Entry (within provider)
```json
{
  "model_id": "meta-llama/llama-3.1-70b-instruct",
  "model_name": "Meta: Llama 3.1 70B Instruct",
  "pricing": {
    "prompt": 0.0000004,
    "completion": 0.0000004
  },
  "performance": {
    "uptime_24h": 99.2,
    "latency_30m": {
      "p50": 156,
      "p90": 586,
      "p99": 3946
    }
  },
  "context_length": 131072,
  "supported_parameters": ["temperature", "top_p", "tools", ...]
}
```

## Next Steps

### For Analysis
- Open `infrastructure_provider_map.json` in your preferred tool
- Import into Excel, pandas, or your analytics platform
- Use the viewer script for quick queries

### For Integration
- Parse the JSON for your application
- Filter by criteria (price, location, performance)
- Build cost optimization logic
- Monitor price changes over time

### For Monitoring
- Set up cron job to run `map_infrastructure_providers.py` daily
- Track pricing trends
- Monitor provider uptime
- Alert on new model availability

## Pro Tips

1. **Compare Providers**: Same model often available at different prices
   - Claude Opus 4.7 varies by provider
   - Llama 3.1 70B: DeepInfra (cheapest) vs Amazon Bedrock vs WandB

2. **Check Latency**: Geographic location ≠ latency
   - Cerebras (US): 199ms
   - Mistral (France): 342ms
   - Perplexity (US): 8405ms (!!)

3. **Free Models**: Great for testing/development
   - Venice: Free Llama, Qwen, Mistral models
   - Nvidia: Free Nemotron models
   - Baidu: Free Chinese models

4. **Quantization**: DeepInfra offers 6 levels
   - fp4, fp8, bf16, fp16, base, turbo
   - Trade-off: speed vs accuracy vs cost

5. **Multi-Region**: Some providers have global datacenters
   - Xiaomi: SG and NL
   - Check datacenter list in provider details

## Questions?

Run any command without arguments to see usage:
```bash
python3 view_infrastructure_map.py
```

Or check the full documentation:
- `INFRASTRUCTURE_MAP_SUMMARY.md` - Complete guide
- `README.md` - Project overview
