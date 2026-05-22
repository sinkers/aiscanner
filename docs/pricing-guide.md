# Pricing Display Guide

## ✅ Fixed: All Prices Now Show Per 1M Tokens (Standard Format)

### What Changed

The JSON data from OpenRouter stores prices as **dollars per token**.  
The UI now converts and displays as **dollars per 1M tokens** (industry standard).

### Examples

**Raw JSON value**: `0.0000004`  
**Displayed as**: `$0.4000 per 1M tokens`

**Raw JSON value**: `0.000003`  
**Displayed as**: `$3.00 per 1M tokens`

**Raw JSON value**: `0.00003`  
**Displayed as**: `$30.00 per 1M tokens`

### Where Prices Are Shown

1. **Main Table** - "Price Range (per 1M)" column
   - Shows: `$0.2700 - $1.0800`
   - This is the TOTAL price range (prompt + completion)

2. **Provider Details Modal**
   - "Prompt Price Range (per 1M tokens)": `$0.2000 - $0.5000`
   - "Completion Price Range (per 1M tokens)": `$0.8000 - $2.0000`
   - Individual model prices: `$0.2700 / $1.0800 per 1M`

3. **Pricing Comparison Tab**
   - Cheapest Paid Models table
   - Columns: "Prompt (per 1M)", "Completion (per 1M)", "Total (per 1M)"
   - Shows: `$0.2700`, `$1.0800`, `$1.3500`

### Smart Formatting

The UI automatically adjusts decimal places based on price:
- **Under $1**: Shows 4 decimals (e.g., `$0.2700`)
- **$1-$100**: Shows 2 decimals (e.g., `$3.50`)
- **Over $100**: Shows whole numbers (e.g., `$150`)

### Common Pricing Ranges

**Free Models**: `FREE` (no cost)
- Examples: Baidu models, Nvidia models, Venice models

**Very Cheap** ($0.10 - $1.00 per 1M):
- Qwen models: ~$0.27 - $1.00
- Gemma models: ~$0.10 - $0.50
- DeepSeek: ~$0.14 - $0.60

**Budget** ($1 - $10 per 1M):
- Llama 3.1 8B: ~$0.10 - $1.00
- Llama 3.1 70B: ~$0.40 - $2.00
- Mistral 7B: ~$0.20 - $0.60

**Standard** ($10 - $50 per 1M):
- GPT-4: ~$30 - $60
- Claude Sonnet: ~$3 - $15

**Premium** ($50+ per 1M):
- GPT-4 Turbo: ~$60 - $150
- Claude Opus: ~$15 - $75

### Calculating Your Costs

**Example**: Using DeepSeek v4 Flash
- Prompt: $0.14 per 1M tokens
- Completion: $0.60 per 1M tokens

**Your usage**: 10M prompt tokens, 2M completion tokens

**Cost**:
- Prompt: 10 × $0.14 = $1.40
- Completion: 2 × $0.60 = $1.20
- **Total**: $2.60

### Comparing Providers

When comparing prices for the same model:

**Example: Llama 3.1 70B Instruct**
- DeepInfra: $0.40 per 1M (prompt + completion)
- Amazon Bedrock: $1.44 per 1M
- WandB: $1.60 per 1M

**Savings**: DeepInfra is 72% cheaper than Amazon Bedrock!

### Price Range Meaning

"Price Range" shows MIN to MAX across all models that provider hosts:

**Novita**: `$0.0001 - $4.0000 per 1M`
- Cheapest model: $0.0001 per 1M (essentially free)
- Most expensive: $4.00 per 1M
- Range of 73 different models

This helps you understand:
- What's the cheapest option from this provider?
- What's their most expensive offering?
- How much price variation do they have?

### Tips

1. **Free Models First**: Start with free models for testing
2. **Compare Total Cost**: Add prompt + completion for true comparison
3. **Consider Latency**: Cheapest isn't always best (check speed too)
4. **Volume Matters**: Some providers offer bulk discounts (not shown in UI)
5. **Context Length**: Longer context = more tokens = higher cost

### Still Confused?

All prices in the UI are **per 1 million tokens**.

If you use 500,000 tokens (0.5M), divide the displayed price by 2.  
If you use 5,000,000 tokens (5M), multiply the displayed price by 5.

**Quick Reference**:
- 1K tokens ≈ 750 words
- 1M tokens ≈ 750,000 words
- Average API call: 1K-10K tokens

Most use cases: **under 100K tokens/month** = **less than $10/month** with budget providers
