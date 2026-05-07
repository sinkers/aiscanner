# Data Sources & Reliability

## Overview

All data in this infrastructure provider map comes from **OpenRouter's official APIs**. Nothing is guessed, inferred, or scraped from third-party sources.

---

## Data Sources

### 1. Provider Location Data

**Source**: `GET https://openrouter.ai/api/v1/providers`

**Fields Used**:
- `headquarters` - Two-letter country code (e.g., "US", "CN", "SG")
- `datacenters` - Array of datacenter locations
- `privacy_policy_url` - Link to privacy policy
- `terms_of_service_url` - Link to terms of service
- `status_page_url` - Link to status page

**Example Response**:
```json
{
  "name": "DeepInfra",
  "slug": "deepinfra",
  "headquarters": "US",
  "datacenters": null,
  "privacy_policy_url": "https://deepinfra.com/privacy",
  "terms_of_service_url": "https://deepinfra.com/terms",
  "status_page_url": "https://status.deepinfra.com/"
}
```

### 2. Model Endpoints Data

**Source**: `GET https://openrouter.ai/api/v1/models/{model_id}/endpoints`

**Fields Used**:
- `provider_name` - Display name (e.g., "DeepInfra")
- `tag` - Internal identifier (e.g., "deepinfra/turbo")
- `pricing.prompt` - Cost per 1M prompt tokens
- `pricing.completion` - Cost per 1M completion tokens
- `uptime_last_1d` - Uptime percentage (last 24 hours)
- `latency_last_30m` - Latency percentiles (p50, p75, p90, p99)
- `throughput_last_30m` - Throughput percentiles
- `context_length` - Maximum context window
- `max_completion_tokens` - Maximum output tokens
- `supported_parameters` - Available parameters (temperature, tools, etc.)

**Example Response**:
```json
{
  "name": "DeepInfra | meta-llama/llama-3.1-70b-instruct",
  "provider_name": "DeepInfra",
  "tag": "deepinfra/turbo",
  "pricing": {
    "prompt": "0.0000004",
    "completion": "0.0000004"
  },
  "uptime_last_1d": 99.2,
  "latency_last_30m": {
    "p50": 156,
    "p90": 586,
    "p99": 3946
  },
  "context_length": 131072
}
```

### 3. Models List

**Source**: `GET https://openrouter.ai/api/v1/models`

**Fields Used**:
- `id` - Model identifier (e.g., "meta-llama/llama-3.1-70b-instruct")
- `name` - Human-readable name
- `description` - Model description
- `context_length` - Context window size
- `links.details` - Path to endpoints API

---

## Matching Process

### How We Determine Provider Location

1. **Fetch Models**: Get all 368 models from `/api/v1/models`

2. **Fetch Endpoints**: For each model, fetch `/api/v1/models/{model_id}/endpoints`
   - Returns list of infrastructure providers hosting that model
   - Each endpoint has `provider_name` and `tag`

3. **Extract Slug**: From the `tag` field, extract the provider slug
   - Example: `"deepinfra/turbo"` → slug is `"deepinfra"`

4. **Match to Providers API**: Look up the slug in `/api/v1/providers`
   - Find matching provider by slug
   - Copy `headquarters` and `datacenters` fields

5. **Handle Missing Data**: If `headquarters` is `null` or provider not found
   - Show as "N/A" or "Unknown"
   - Do NOT guess or infer location

### Example Matching

```
Endpoint Data:
  provider_name: "DeepInfra"
  tag: "deepinfra/turbo"

Extract Slug:
  tag "deepinfra/turbo" → slug "deepinfra"

Look Up Provider:
  slug "deepinfra" → find in providers API

Copy Location:
  headquarters: "US"
  datacenters: null
```

---

## Data Completeness

### Location Data (Headquarters)
- **With data**: 53 of 67 providers (79.1%)
- **Without data**: 14 of 67 providers (20.9%)

Providers without headquarters data:
- NextBit (16 models)
- AkashML (6 models)
- Mancer 2 (5 models)
- Poolside (2 models)
- Reka (2 models)
- Liquid (2 models)
- And 8 others with 1-2 models each

### Datacenter Data
- **With data**: 18 of 67 providers (26.9%)
- **Without data**: 49 of 67 providers (73.1%)

Most providers don't disclose specific datacenter locations.

### Performance Data
- **Uptime**: Available for most providers
- **Latency**: Available for most providers (last 30 minutes)
- **Throughput**: Available for most providers (last 30 minutes)

Some newer/smaller providers may have `null` performance data.

---

## Data Reliability

### ✅ Highly Reliable
- **Pricing**: Directly from OpenRouter, updated in real-time
- **Performance**: Real metrics from OpenRouter's monitoring
- **Model Availability**: Accurate list of which providers host which models
- **Country Codes**: Official from OpenRouter (when provided)

### ⚠️ Moderately Reliable
- **Headquarters Location**: Accurate when provided (79% coverage)
  - Based on provider-supplied information to OpenRouter
  - May not reflect actual infrastructure location
  - Some providers don't disclose this information

- **Datacenters**: Limited coverage (27%)
  - Most providers don't share specific datacenter locations
  - When provided, it's official from the provider

### ❌ Not Included (Would Be Unreliable)
We specifically DO NOT include:
- ❌ Guessed locations based on provider name
- ❌ Inferred locations from domain registration
- ❌ Scraped data from provider websites
- ❌ IP geolocation of API endpoints
- ❌ Third-party data sources

**Reason**: We prioritize accuracy over completeness. It's better to show "Unknown" than to show incorrect data.

---

## Important Caveats

### 1. Headquarters ≠ Data Location
- A provider's headquarters (legal entity) may differ from where they host models
- Example: Company HQ in US but servers in Singapore
- Datacenter field (when available) is more accurate for data residency

### 2. Multi-Region Providers
- Some providers have multiple datacenters (e.g., Xiaomi: SG, NL)
- OpenRouter doesn't specify which region serves which request
- Actual server location may vary per request

### 3. Performance Metrics Are Recent
- Uptime: Last 24 hours only
- Latency: Last 30 minutes only
- Throughput: Last 30 minutes only
- Historical data is not available

### 4. Dynamic Data
- Pricing can change
- Providers can add/remove models
- Performance metrics fluctuate
- Run `python3 map_infrastructure_providers.py` to refresh

### 5. Missing Data
- 14 providers (21%) have no location data in OpenRouter's API
- 49 providers (73%) have no datacenter data
- This is a limitation of OpenRouter's data, not our script

---

## Verification

You can verify any data point yourself:

### Check Provider Location
```bash
curl https://openrouter.ai/api/v1/providers | jq '.data[] | select(.slug == "deepinfra")'
```

### Check Model Endpoints
```bash
curl https://openrouter.ai/api/v1/models/meta-llama/llama-3.1-70b-instruct/endpoints \
  -H "Authorization: Bearer <your-token>"
```

### Check All Models
```bash
curl https://openrouter.ai/api/v1/models | jq '.data | length'
```

---

## Data Freshness

### Static Data (Rarely Changes)
- Provider headquarters
- Provider datacenters
- Model context lengths

### Dynamic Data (Changes Frequently)
- Pricing (can change weekly)
- Performance metrics (real-time, last 30 min)
- Model availability (new models added regularly)

**Recommendation**: Refresh data weekly or before important decisions:
```bash
python3 map_infrastructure_providers.py
```

This takes ~2 minutes to fetch all endpoints and generate the map.

---

## Enhancing Location Data

If you need better location coverage for the 14 providers without data:

### Option 1: Manual Research
Look up company websites:
- NextBit: likely US or Europe (serves many models)
- Poolside: appears to be a coding-focused provider
- Reka: privacy-focused, location intentionally undisclosed?

### Option 2: Request from OpenRouter
Contact OpenRouter to add missing provider data to their API.

### Option 3: Community Sourcing
Create a `manual_locations.json` file:
```json
{
  "nextbit": "US",
  "akashml": "US",
  "poolside": "US"
}
```

Then merge this with the official data (with clear labeling of "community-sourced" vs "official").

### Option 4: IP Geolocation
Query provider API endpoints and geolocate their IPs:
```bash
dig api.provider.com
whois <ip_address>
```

**Note**: This gives server location, not legal headquarters.

---

## Conclusion

- **100% of data comes from OpenRouter's official APIs**
- **79% of providers have official headquarters data**
- **27% of providers have datacenter data**
- **No guessing or inference is used**
- **"Unknown" means data not provided by OpenRouter**
- **Pricing and performance data is highly reliable and current**

This approach prioritizes **accuracy over completeness**.
