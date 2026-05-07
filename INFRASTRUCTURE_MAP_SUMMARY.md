# OpenRouter Infrastructure Provider Map

**Complete mapping of who hosts what, where they are, how much they charge, and performance metrics.**

Generated: 2026-05-07  
Total Models: 368  
Infrastructure Providers: 67

---

## 📊 Key Statistics

### Top Providers by Model Count
1. **Novita** (US) - 73 models | 96.8% uptime | 1583ms latency
2. **DeepInfra** (US) - 64 models | 98.0% uptime | 1026ms latency
3. **Google** (US) - 62 models | 98.0% uptime | 2078ms latency
4. **OpenAI** (US) - 59 models | 99.4% uptime | 4903ms latency
5. **Alibaba** (SG) - 43 models | 99.5% uptime | 1086ms latency

### Performance Leaders
- **🚀 Lowest Latency**: Cerebras (199ms average)
- **⚡ Best Uptime**: Multiple providers at 100% (Reka, Mancer 2, BaseTen, Seed, AionLabs, etc.)
- **💰 Cheapest**: Many free options from Baidu, Nvidia, Poolside, Venice

### Geographic Distribution
- **US**: 37 providers (55%)
- **Singapore**: 6 providers (9%)
- **China**: 4 providers (6%)
- **Unknown**: 14 providers (21%)
- **Other**: 6 providers (9%) - France, Israel, Netherlands, Indonesia, Sweden

---

## 🌍 Providers by Region

### United States (37 providers)
Leading infrastructure providers based in the US include:
- Amazon Bedrock (35 models)
- Azure (39 models)
- OpenAI (59 models)
- DeepInfra (64 models)
- Anthropic (15 models)
- AtlasCloud (43 models)
- Parasail (31 models)
- Together (28 models)
- Venice (28 models)

### Asia-Pacific
**Singapore (6 providers)**
- Alibaba - 43 models
- SiliconFlow - 31 models
- Minimax - 10 models
- Z.AI - 13 models
- Moonshot AI - 2 models
- Seed - 4 models

**China (4 providers)**
- Baidu - 5 models (offers free models)
- Xiaomi - 5 models
- DeepSeek - 2 models
- StreamLake - 2 models

**Indonesia**
- DekaLLM - 6 models

### Europe
**France**
- Mistral - 21 models | 99.6% uptime | 342ms latency (excellent performance!)

**Netherlands**
- Nebius - 14 models

**Sweden**
- Inceptron - 5 models

### Middle East
**Israel (2 providers)**
- AionLabs - 4 models
- AI21 - 1 model

---

## 💰 Pricing Analysis

### Price Ranges by Top Providers

| Provider | Prompt (per 1M tokens) | Completion (per 1M tokens) |
|----------|------------------------|----------------------------|
| Novita | $0.000000 - $0.000002 | $0.000000 - $0.000004 |
| DeepInfra | $0.000000 - $0.000001 | $0.000000 - $0.000003 |
| Google | $0.000000 - $0.000015 | $0.000000 - $0.000075 |
| OpenAI | $0.000000 - $0.000150 | $0.000000 - $0.000600 |
| Alibaba | $0.000000 - $0.000001 | $0.000000 - $0.000006 |
| Azure | $0.000000 - $0.000030 | $0.000000 - $0.000180 |
| Amazon Bedrock | $0.000000 - $0.000015 | $0.000000 - $0.000075 |

### Free Models (Top 15)
1. baidu/cobuddy:free
2. baidu/qianfan-ocr-fast:free
3. nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
4. nvidia/nemotron-3-super-120b-a12b:free
5. nvidia/nemotron-3-nano-30b-a3b:free
6. poolside/laguna-xs.2:free
7. poolside/laguna-m.1:free
8. qwen/qwen3-next-80b-a3b-instruct:free (Venice)
9. meta-llama/llama-3.3-70b-instruct:free (Venice)
10. meta-llama/llama-3.2-3b-instruct:free (Venice)

---

## ⚡ Performance Metrics

### Latency (p50 average, lower is better)
- **Cerebras**: 199ms ⭐
- **Liquid**: 268ms
- **Cohere**: 295ms
- **Mistral**: 342ms
- **BaseTen**: 344ms
- **Cloudflare**: 413ms
- **Friendli**: 434ms

### Uptime (24h average)
- **100% Uptime**: Reka, Mancer 2, BaseTen, Seed, AionLabs, Liquid, Relace, Inflection, Stealth, Inception, Upstage, Clarifai, AI21, Switchpoint
- **99.9%+**: Groq, Perplexity, Poolside, StepFun, Ionstream

### Throughput (tokens/second, higher is better)
Top performers for token generation speed:
- DeepInfra: 35.9 tok/s average
- High variability depending on model and quantization

---

## 🔍 Example Use Cases

### Case 1: You want the cheapest Claude model
```bash
python3 view_infrastructure_map.py model "anthropic/claude-opus-4.7"
```
Shows 6 providers hosting it with price and performance comparison.

### Case 2: You want all models available in Europe
```bash
python3 view_infrastructure_map.py location FR
python3 view_infrastructure_map.py location NL
```

### Case 3: You want the fastest Llama 3.1 70B
```bash
python3 view_infrastructure_map.py model "meta-llama/llama-3.1-70b-instruct"
```
Result: DeepInfra (156ms) vs Amazon Bedrock (472ms) vs WandB (195ms)

### Case 4: You want to know everything about DeepInfra
```bash
python3 view_infrastructure_map.py provider "DeepInfra"
```
Shows all 64 models they host, pricing, performance, location, etc.

---

## 📁 Data Files

### `infrastructure_provider_map.json`
Main data file containing:
- Complete provider information (headquarters, datacenters, policies)
- All models served by each provider
- Pricing for each model/provider combination
- Performance metrics (uptime, latency, throughput)
- Supported parameters and features

### `view_infrastructure_map.py`
Interactive query tool with commands:
- `list` - Show all providers
- `provider <name>` - Provider details
- `model <model_id>` - Compare providers for a model
- `location <country>` - Filter by location
- `cheapest [limit]` - Find cheapest models

---

## 🎯 Key Insights

### 1. Geographic Concentration
- **US dominance**: 55% of providers are based in the US
- **Asia-Pacific growth**: Singapore emerging as a hub (6 providers)
- **China**: 4 major providers, many with free tiers
- **Europe underrepresented**: Only France, Netherlands, Sweden have providers

### 2. Pricing Competition
- **Free tier competition**: Baidu, Nvidia, Venice, Poolside offering free models
- **Race to the bottom**: DeepInfra and Novita very competitive on pricing
- **Premium pricing**: OpenAI, Azure charge 10-100x more for same models
- **Geographic pricing**: No clear correlation between location and price

### 3. Performance Patterns
- **Latency varies 50x**: From 199ms (Cerebras) to 10,090ms (Stealth)
- **Uptime leaders**: Smaller providers often have better uptime than giants
- **Regional latency**: Not always correlated with physical distance
- **Quantization options**: DeepInfra offers 6 different quantization levels

### 4. Model Availability
- **Multi-cloud is real**: Popular models available through 4-17 providers
- **Llama dominance**: Most widely available model family
- **Proprietary barriers**: Some models only on native platforms (e.g., some Claude, GPT)
- **Long tail**: Many niche providers specialize in specific model families

---

## 🚀 Future Features (Coming Soon)

Based on your "more features to come" requirement, here are suggested additions:

### Data Tracking
- [ ] Historical pricing trends
- [ ] Uptime monitoring over time
- [ ] Model availability changelog
- [ ] Provider reliability scoring

### Advanced Filtering
- [ ] Filter by supported parameters (tools, streaming, etc.)
- [ ] Filter by quantization options
- [ ] Filter by context length
- [ ] Multi-criteria optimization (price + latency + uptime)

### Cost Analysis
- [ ] Total cost calculator (prompt + completion)
- [ ] Cost comparison charts
- [ ] Volume discount tracking
- [ ] Price alerts

### Performance Benchmarking
- [ ] Response quality comparison
- [ ] Throughput vs latency tradeoffs
- [ ] Provider reliability scoring
- [ ] Regional latency maps

### Integration Features
- [ ] Export to CSV/Excel
- [ ] API endpoint for programmatic access
- [ ] Webhook notifications for price changes
- [ ] Dashboard web interface

---

## 📝 Usage Examples

### Find the Best Provider for a Specific Model
```bash
# Compare all providers hosting Claude Opus 4.7
python3 view_infrastructure_map.py model "anthropic/claude-opus-4.7"

# Result: 6 providers with different prices and performance
# Anthropic direct, Amazon Bedrock, Google, Azure, Novita, AtlasCloud
```

### Find All Models in a Region
```bash
# US providers
python3 view_infrastructure_map.py location US

# Singapore providers  
python3 view_infrastructure_map.py location SG

# China providers
python3 view_infrastructure_map.py location CN
```

### Deep Dive on a Provider
```bash
# See everything DeepInfra offers
python3 view_infrastructure_map.py provider "DeepInfra"

# Shows:
# - 64 models across multiple families
# - Pricing: $0.00000002 - $0.00000120/1M tokens
# - Performance: 98% uptime, 1026ms latency
# - Quantization options: base, turbo, fp8, bf16, fp16, fp4
```

### Find Best Deals
```bash
# Top 50 cheapest models
python3 view_infrastructure_map.py cheapest 50

# Many free options from:
# - Baidu (Chinese models)
# - Nvidia (Nemotron family)
# - Poolside (code models)
# - Venice (Llama, Qwen, Mistral)
```

---

## 📞 Contact & Contributions

This is an evolving dataset. OpenRouter adds new providers and models frequently.

To update the data:
```bash
# Refresh the entire dataset (takes ~2 minutes)
python3 map_infrastructure_providers.py

# The script:
# - Fetches all 368 models
# - Queries endpoints for each model
# - Collects pricing, performance, and location data
# - Generates infrastructure_provider_map.json
```

---

## 🔗 References

- [OpenRouter Models API](https://openrouter.ai/api/v1/models)
- [OpenRouter Providers API](https://openrouter.ai/api/v1/providers)
- [OpenRouter Endpoints API](https://openrouter.ai/api/v1/models/{model_id}/endpoints)

---

**Last Updated**: 2026-05-07  
**Data Freshness**: Real-time (queries live APIs)  
**Total Data Points**: 368 models × 67 providers = 24,656 potential combinations  
**Actual Endpoints**: 368 models with endpoint data (some models on multiple providers)
