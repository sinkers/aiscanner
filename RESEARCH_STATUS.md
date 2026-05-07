# Provider Research Status

## 🔬 What's Happening

An AI agent is currently performing web research on the top 20 infrastructure providers to find:

### Information Being Collected

1. **Homepage** - Main company website
2. **Contact Email** - Support or contact email address
3. **Support URL** - Help/support page
4. **Headquarters City** - Specific city location
5. **Headquarters Country** - Verify or fill in country
6. **Company Description** - Brief 1-2 sentence description

### Providers Being Researched (Top 20 by Model Count)

1. ✓ Novita (73 models) - US
2. ✓ DeepInfra (64 models) - US
3. ✓ Google (62 models) - US
4. ✓ OpenAI (59 models) - US
5. ✓ Alibaba (43 models) - SG
6. ✓ AtlasCloud (43 models) - US
7. ✓ Azure (39 models) - US
8. ✓ Amazon Bedrock (35 models) - US
9. ✓ Parasail (31 models) - US
10. ✓ SiliconFlow (31 models) - SG
11. ✓ Venice (28 models) - US
12. ✓ Together (28 models) - US
13. ✓ Mistral (21 models) - FR
14. ✓ Google AI Studio (18 models) - US
15. ✓ NextBit (16 models) - UNKNOWN ⚠️
16. ✓ xAI (15 models) - US
17. ✓ Anthropic (15 models) - US
18. ✓ Cloudflare (14 models) - US
19. ✓ Nebius (14 models) - NL
20. ✓ WandB (13 models) - US

## 📊 Current Data Status

**Before Research**:
- Providers with headquarters: 53/67 (79%)
- Providers with privacy policy: 60/67 (90%)
- Providers with terms: 59/67 (88%)
- Providers with status page: 23/67 (34%)
- **Providers with homepage: 0/67 (0%)** ⚠️
- **Providers with contact email: 0/67 (0%)** ⚠️
- **Providers with support URL: 0/67 (0%)** ⚠️
- **Providers with city: 0/67 (0%)** ⚠️

**After Research (Expected)**:
- Providers with headquarters: 67/67 (100%) ✅
- Providers with homepage: 20/67 (30%) ✅
- Providers with contact email: 15-20/67 (22-30%) ✅
- Providers with support URL: 15-20/67 (22-30%) ✅
- Providers with city: 20/67 (30%) ✅

## 🔄 Process

### Step 1: Web Research (IN PROGRESS)
AI agent is searching for each provider:
- Google: "{provider name} official website"
- Google: "{provider name} headquarters location"
- Google: "{provider name} contact support"
- Visiting websites to extract info

**Status**: Agent running in background...

### Step 2: Integration (PENDING)
Once research completes:
```bash
python3 integrate_research.py
```

This will:
- Load `provider_research.json` (agent output)
- Merge into `infrastructure_provider_map.json`
- Preserve existing data
- Add new fields

### Step 3: Regenerate UI (PENDING)
```bash
# Recreate standalone HTML with new data
python3 << 'EOF'
import json
with open('infrastructure_provider_map.json') as f:
    data = json.load(f)
with open('index.html') as f:
    html = f.read()
embedded_html = html.replace(
    "async function loadData() {",
    "async function loadData() {\n        infraData = " + json.dumps(data) + ";\n        initializeUI();\n        return;\n        /*"
).replace(
    "// Load data on page load\n        loadData();",
    "*/\n    }\n\n        loadData();"
)
with open('index_standalone.html', 'w') as f:
    f.write(embedded_html)
print("✅ Updated index_standalone.html")
EOF
```

### Step 4: Open Updated UI
```bash
open index_standalone.html
```

## 📝 Output Files

### `provider_research.json`
Raw research data from agent:
```json
{
  "Novita": {
    "homepage": "https://novita.ai",
    "contact_email": "support@novita.ai",
    "support_url": "https://novita.ai/support",
    "headquarters_city": "San Francisco",
    "headquarters_country": "US",
    "company_description": "AI inference platform..."
  },
  ...
}
```

### `infrastructure_provider_map.json` (Updated)
Original data enriched with research:
```json
{
  "providers": {
    "Novita": {
      "provider_info": {
        "name": "Novita",
        "headquarters": "US",
        "headquarters_city": "San Francisco",  // NEW
        "homepage": "https://novita.ai",       // NEW
        "contact_email": "support@novita.ai",  // NEW
        "support_url": "https://novita.ai/support", // NEW
        "company_description": "...",           // NEW
        ...
      }
    }
  }
}
```

## 🎨 UI Updates

The web interface now shows new fields in provider modals:

**Before**:
- Location badge
- Datacenters
- Links: Privacy, Terms, Status

**After**:
- Location badge + city (e.g., "US, San Francisco")
- Company description (at top of modal)
- Links & Contact:
  - 🏠 Homepage (prominent)
  - 📧 Email address (clickable mailto:)
  - 💬 Support (support page)
  - 📊 Status (status page)
  - Privacy & Terms (smaller, less prominent)

## ⏱️ Timeline

- **Started**: Now (agent launched)
- **Research Duration**: 5-10 minutes (searching 20 providers)
- **Integration**: 10 seconds
- **UI Regeneration**: 5 seconds
- **Total**: ~10-15 minutes

## 🔍 Research Methods

The agent uses:
1. **Web Search** - Google searches for official info
2. **Web Scraping** - Visits websites to extract contact details
3. **Verification** - Cross-checks multiple sources
4. **Manual Fallback** - If automated search fails, tries alternative queries

## 🚨 Known Challenges

Some providers may be hard to research:
- **NextBit** - Unknown, might be new/stealth
- **Smaller providers** - Limited web presence
- **Corporate divisions** - Azure (Microsoft), Bedrock (Amazon)
- **Chinese providers** - May need .cn domains

For these, agent will:
- Leave fields blank if can't verify
- Note in research output
- Can be manually filled later

## 📈 Future Enhancements

After initial 20:
1. Research remaining 47 providers
2. Add more fields:
   - Founded year
   - Employee count
   - Funding/valuation
   - CEO/leadership
   - Social media links
3. Automated refresh (monthly)
4. Community contributions

## ✅ Next Steps

Once agent completes:
1. Check `provider_research.json`
2. Run `python3 integrate_research.py`
3. Regenerate standalone HTML
4. Review results in web UI
5. Document any missing/incorrect data
6. Optionally research remaining 47 providers

---

**Status**: 🟡 Research in progress...  
**Check progress**: The agent will notify when complete
