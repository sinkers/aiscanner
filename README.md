# OpenRouter Infrastructure Provider Map

**Complete mapping of all infrastructure providers hosting AI models on OpenRouter** - discover who hosts what, where they are, how much they charge, and their real-time performance metrics.

## 🎯 What This Does

Ever wondered:
- "Which provider has the cheapest Llama 3.1?"
- "Who hosts Claude models besides Anthropic?"
- "Are there providers in Europe?"
- "Which infrastructure provider is fastest/most reliable?"

This project answers all of those questions with **live data from OpenRouter's API**.

### The Big Picture

OpenRouter aggregates 368 AI models from 67 infrastructure providers worldwide. Each model can be hosted by multiple providers with different:
- **Pricing** (varies 2-50x for the same model!)
- **Performance** (latency: 199ms to 10,000ms)
- **Reliability** (uptime: 95% to 100%)
- **Location** (US, China, Singapore, Europe, etc.)

This project maps it all and presents it in an interactive web interface.

## 🚀 Quick Start

### View the Data (No Setup Required)

```bash
# Just open the standalone HTML file
open index_standalone.html  # Mac
start index_standalone.html  # Windows

# Or start a web server
python3 serve.py
# Then open: http://localhost:8000/index.html
```

The web interface shows:
- ✅ All 67 infrastructure providers
- ✅ 368 models with pricing and performance
- ✅ Geographic distribution by country
- ✅ Performance leaderboards
- ✅ Free and cheapest model comparisons

### Refresh the Data

```bash
# Update with latest data from OpenRouter (~2 minutes)
python3 map_infrastructure_providers.py

# Then regenerate the standalone HTML
python3 << 'EOF'
import json
with open('infrastructure_provider_map.json') as f:
    data = json.load(f)
with open('index.html') as f:
    html = f.read()
import re
html = re.sub(
    r'const response = await fetch.*?infraData = await response\.json\(\);',
    f'infraData = {json.dumps(data)};',
    html, flags=re.DOTALL
)
with open('index_standalone.html', 'w') as f:
    f.write(html)
print("✅ Generated index_standalone.html")
EOF
```

## 📊 What You'll Discover

### Top Providers
1. **Novita** (US) - 73 models, $0.00-$0.02 per 1M tokens
2. **DeepInfra** (US) - 64 models, competitive pricing, 6 quantization options
3. **Google** (US) - 62 models including Gemini family
4. **OpenAI** (US) - 59 models, premium pricing
5. **Alibaba** (Singapore) - 43 models

### Geographic Distribution
- 🇺🇸 **United States**: 37 providers (55%)
- 🇸🇬 **Singapore**: 6 providers (9%)  
- 🇨🇳 **China**: 4 providers (6%)
- 🇫🇷 **France**: 1 provider (Mistral)
- 🇳🇱 **Netherlands**: 1 provider (Nebius)
- 🇮🇱 **Israel**: 2 providers
- 🌍 **Other**: Indonesia, Sweden, Canada, Australia, South Korea

### Performance Leaders
- **🚀 Fastest**: Cerebras (199ms average latency)
- **⚡ Most Reliable**: 14 providers at 100% uptime
- **💰 Cheapest**: DeepInfra, Novita, Venice (many free options)

### Price Competition
Same model, different prices:
- **Llama 3.1 70B**: $0.40/1M (DeepInfra) vs $3.00/1M (others)
- **Free tiers**: Baidu, Nvidia, Venice, Poolside offer free models
- **Premium services**: OpenAI, Azure charge 10-100x more

## 🏗️ How It Works

### The Critical Distinction

OpenRouter has **TWO types of "providers"**:

1. **Model Creator** - Company that trained the model
   - Found in model ID: `anthropic/claude-3.5-sonnet` → creator is `anthropic`
   
2. **Infrastructure Provider** - Company that hosts/serves the model
   - Examples: AWS Bedrock, Azure, DeepInfra, Together
   - One model can be on multiple infrastructure providers

**This project maps infrastructure providers** (who actually hosts and serves the models).

### The Data Pipeline

```
┌─────────────────────────────────────────────────────────┐
│  1. FETCH MODELS & PROVIDERS                            │
│  python3 fetch_openrouter.py                            │
│  ├─ GET /api/v1/models (368 models)                     │
│  └─ GET /api/v1/providers (67 providers)                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  2. MAP INFRASTRUCTURE                                  │
│  python3 map_infrastructure_providers.py (~2 min)       │
│  ├─ For EACH of 368 models:                            │
│  │  └─ GET /api/v1/models/{id}/endpoints                │
│  │     └─ Returns which providers host this model       │
│  ├─ Aggregates pricing, performance, location           │
│  └─ Output: infrastructure_provider_map.json (1.1MB)    │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  3. ENRICH WITH RESEARCH (Optional)                     │
│  python3 integrate_research.py                          │
│  ├─ Adds homepage, contact email, support URL           │
│  ├─ Adds headquarters city, company description         │
│  └─ Updates infrastructure_provider_map.json            │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  4. WEB INTERFACE                                       │
│  index.html + infrastructure_provider_map.json          │
│  └─ Interactive dashboard with filtering & sorting      │
└─────────────────────────────────────────────────────────┘
```

## 🖥️ Web Interface Features

### 4 Interactive Views

1. **All Providers** - Sortable table of all 67 providers
   - Click columns to sort (name, location, models, uptime, latency, price)
   - Search by provider name or model ID
   - Filter by location, minimum models, minimum uptime
   
2. **By Geography** - Providers grouped by country
   - See all US providers (37)
   - Asian providers (Singapore: 6, China: 4)
   - European providers (France, Netherlands, Sweden)
   
3. **Performance Leaders** - Top 15 leaderboards
   - Best Uptime (100% club)
   - Lowest Latency (sub-500ms)
   
4. **Pricing Comparison** - Best deals
   - Top 20 free models
   - Top 20 cheapest paid models

### Provider Details Modal

Click any provider name to see:
- 📝 Company description
- 📍 Location (country + city)
- 🏠 Homepage link
- 📧 Contact email
- 💬 Support URL
- 📊 Status page
- 💰 Pricing ranges
- ⚡ Performance metrics
- 📋 Full model list (up to 50 shown)

## 🔧 Command Line Tools

### Query Infrastructure Data

```bash
# View all providers
python3 view_infrastructure_map.py list

# Get details on a specific provider
python3 view_infrastructure_map.py provider "DeepInfra"

# Compare providers for a specific model
python3 view_infrastructure_map.py model "meta-llama/llama-3.1-70b-instruct"
# Shows: DeepInfra (156ms, $0.40/1M) vs Bedrock (472ms, $0.72/1M) vs WandB (195ms, $0.80/1M)

# Find providers in a country
python3 view_infrastructure_map.py location US
python3 view_infrastructure_map.py location SG
python3 view_infrastructure_map.py location CN

# Find cheapest models
python3 view_infrastructure_map.py cheapest 20
```

## 📁 Key Files

### Data Files
- **infrastructure_provider_map.json** - Main data (1.1MB, 67 providers)
- **openrouter_models.json** - All 368 models (raw from API)
- **openrouter_providers.json** - Provider metadata (raw from API)
- **provider_research.json** - Enriched company info (homepage, contact, description)

### Scripts
- **map_infrastructure_providers.py** - Core mapper (fetches all endpoint data)
- **fetch_openrouter.py** - Initial data fetcher
- **integrate_research.py** - Merges research data
- **view_infrastructure_map.py** - CLI query tool
- **research_providers.py** - Research helper

### Web Interface
- **index.html** - Main UI (requires web server)
- **index_standalone.html** - Embedded data version (no server needed)
- **serve.py** - Simple HTTP server

## 💡 Example Use Cases

### Find the Best Provider for Your Use Case

**Scenario 1: Need cheapest Llama 3.1 70B**
```bash
python3 view_infrastructure_map.py model "meta-llama/llama-3.1-70b-instruct"
```
Result: DeepInfra at $0.40/1M tokens (vs $3.00/1M elsewhere)

**Scenario 2: Need fastest Claude Opus**
```bash
python3 view_infrastructure_map.py model "anthropic/claude-opus-4.7"
```
Compare latency across 6 providers

**Scenario 3: Need GDPR-compliant European provider**
```bash
python3 view_infrastructure_map.py location FR  # Mistral (France)
python3 view_infrastructure_map.py location NL  # Nebius (Netherlands)
```

**Scenario 4: Need most reliable provider**
Open web UI → Performance Leaders → Best Uptime
14 providers at 100% uptime

**Scenario 5: Want to try models for free**
Open web UI → Pricing Comparison → Free Models
20+ free options from Baidu, Nvidia, Venice

## 📊 Data Quality & Reliability

### ✅ Highly Reliable (Direct from OpenRouter API)
- **Pricing**: Real-time from OpenRouter
- **Performance**: Live metrics (uptime, latency, throughput)
- **Model availability**: Accurate, updated
- **Country codes**: Official provider data

### ⚠️ Best Effort
- **Headquarters location**: 79% coverage (53 of 67 providers)
- **Datacenter locations**: 27% coverage (18 of 67 providers)
- **Company info**: 88% coverage (59 of 67 providers have homepage/description)

### ❌ Not Included (Would Be Unreliable)
- No guessed locations
- No scraped/inferred data
- No third-party sources

**Philosophy**: Better to show "Unknown" than incorrect data.

### Performance Metrics Caveats
- **Uptime**: Last 24 hours only (not historical)
- **Latency**: Last 30 minutes (p50 median)
- **Throughput**: Last 30 minutes (tokens/second)

Metrics fluctuate. Run `python3 map_infrastructure_providers.py` weekly for fresh data.

## 🔍 Important Technical Details

### API Endpoints

```bash
# Get all models
curl https://openrouter.ai/api/v1/models

# Get all providers
curl https://openrouter.ai/api/v1/providers

# Get endpoints for a specific model (requires auth)
curl "https://openrouter.ai/api/v1/models/meta-llama/llama-3.1-70b-instruct/endpoints" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Critical**: Model IDs in URLs should NOT be URL-encoded. Use raw paths:
- ✅ `/api/v1/models/openai/gpt-4/endpoints`
- ❌ `/api/v1/models/openai%2Fgpt-4/endpoints` (causes 404)

### Pricing Format

**In JSON**: Dollars per token
```json
{"prompt": "0.0000004", "completion": "0.0000006"}
```

**In UI**: Dollars per 1M tokens
```
Prompt: $0.4000 per 1M tokens
Completion: $0.6000 per 1M tokens
```

Always multiply by 1,000,000 for display (industry standard).

### Progress Tracking

`map_infrastructure_providers.py` takes ~2 minutes to fetch 368 model endpoints. It saves progress every 10 models in `mapping_progress.json`. If interrupted, just re-run - it continues where it left off.

## 🌟 Key Insights

### Market Dynamics
- **US dominance**: 55% of providers are US-based
- **Asian growth**: Singapore emerging as hub (6 providers)
- **Price wars**: 2-50x variation for same model
- **Free tier competition**: Major providers offering free models

### Performance Patterns
- **Latency spread**: 50x difference (199ms to 10,000ms)
- **Smaller can be better**: Niche providers often have better uptime than giants
- **Quantization matters**: DeepInfra offers 6 variants (fp8, bf16, etc.)

### Multi-Cloud Reality
Popular models available through 4-17 different providers:
- Choose based on: price, latency, reliability, location, features
- No single "best" provider - depends on use case

## 📚 Documentation

- **[DATA_SOURCES.md](DATA_SOURCES.md)** - Where data comes from, reliability analysis
- **[WEB_UI_GUIDE.md](WEB_UI_GUIDE.md)** - Complete web interface guide
- **[INFRASTRUCTURE_MAP_SUMMARY.md](INFRASTRUCTURE_MAP_SUMMARY.md)** - Key findings and statistics
- **[PRICING_GUIDE.md](PRICING_GUIDE.md)** - Understanding pricing data
- **[CLAUDE.md](CLAUDE.md)** - Technical guide for Claude Code

## 🤝 Contributing

The data updates automatically when you run the mapper script. To add new features:

1. **Web UI**: Edit `index.html` (JavaScript, CSS, HTML all in one file)
2. **Data processing**: Edit `map_infrastructure_providers.py`
3. **CLI tools**: Edit `view_infrastructure_map.py`
4. **Research enrichment**: Update `integrate_research.py`

After making changes to `index.html`, regenerate standalone version:
```bash
python3 << 'EOF'
import json, re
with open('infrastructure_provider_map.json') as f:
    data = json.load(f)
with open('index.html') as f:
    html = f.read()
html = re.sub(r'const response = await fetch.*?infraData = await response\.json\(\);',
    f'infraData = {json.dumps(data)};', html, flags=re.DOTALL)
with open('index_standalone.html', 'w') as f:
    f.write(html)
EOF
```

## 🐛 Troubleshooting

### "Error loading data" in browser
- Make sure `infrastructure_provider_map.json` exists
- Check browser console (F12) for errors
- Try `index_standalone.html` instead (doesn't need server)

### API 401 Unauthorized
- OpenRouter token may be expired
- Update `API_TOKEN` in `map_infrastructure_providers.py`

### Stale data in browser
- Browser caching issue
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
- Or open in incognito/private window

### Script takes too long
- Normal: ~2 minutes for 368 models
- Uses progress tracking, can resume if interrupted
- Check `mapping_progress.json` for status

## 📈 Future Enhancements

Possible additions:
- [ ] Historical price tracking
- [ ] Real-time monitoring dashboard
- [ ] Email alerts for price drops
- [ ] Export to CSV/Excel
- [ ] Cost calculator (estimate monthly spend)
- [ ] Provider comparison charts
- [ ] Regional latency heatmaps
- [ ] Model quality/performance benchmarks

## 📄 License

This project analyzes public data from OpenRouter's API. Check OpenRouter's terms of service for API usage guidelines.

---

**Last Updated**: May 7, 2026  
**Data Source**: OpenRouter API (https://openrouter.ai)  
**Total Providers**: 67  
**Total Models**: 368  
**Data Freshness**: Run mapper script weekly for latest data
