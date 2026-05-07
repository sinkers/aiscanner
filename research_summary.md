# Provider Research Summary - Providers 21-67

## Research Completed
Successfully researched 47 infrastructure providers (providers 21-67) and added their information to `provider_research.json`.

## Key Findings

### Geographic Distribution
- **United States (US)**: 26 providers
  - Major hubs: San Francisco (5), Mountain View (2), Sunnyvale (2), Palo Alto (2)
  - Notable companies: Groq, Fireworks, SambaNova, Cerebras, Nvidia, BaseTen, Arcee AI, Liquid AI, Inflection, Clarifai

- **China (CN)**: 5 providers
  - Cities: Beijing (2), Hangzhou (2)
  - Notable: Baidu, Xiaomi, DeepSeek, StreamLake, StepFun

- **Singapore (SG)**: 2 providers
  - Minimax, Z.AI

- **Canada (CA)**: 1 provider
  - Cohere (Toronto)

- **France (FR)**: 1 provider
  - Mancer 2 (Paris)

- **Australia (AU)**: 1 provider
  - Moonshot AI (Sydney)

- **South Korea (KR)**: 1 provider
  - Upstage (Seoul)

- **Israel (IL)**: 2 providers
  - AI21 (Tel Aviv), AionLabs

- **Sweden (SE)**: 1 provider
  - Inceptron (limited info)

- **Indonesia (ID)**: 1 provider
  - DekaLLM (limited info)

- **Unknown/Limited Info**: 6 providers
  - Poolside, Reka (actually found: Sunnyvale), ModelRun, Stealth, Inception, Mara

### Data Completeness by Provider Size

#### Large Providers (8+ models):
- **Chutes (13)**: Homepage ✓, Email ✓, HQ city missing
- **Phala (13)**: Homepage ✓, HQ Newark, CA ✓
- **Z.AI (13)**: Homepage ✓, Singapore HQ confirmed
- **Minimax (10)**: Full data ✓, Singapore HQ
- **SambaNova (9)**: Full data ✓, Palo Alto HQ
- **Fireworks (8)**: Full data ✓, San Mateo HQ
- **Groq (8)**: Full data ✓, Mountain View HQ

#### Medium Providers (4-7 models):
- **Friendli (7)**: Complete data, San Francisco HQ
- **AkashML (6)**: Homepage ✓, decentralized
- **DekaLLM (6)**: Limited info, Indonesia
- **Baidu (5)**: Complete data, Beijing HQ
- **Nvidia (5)**: Complete data, Santa Clara HQ
- **Cerebras (4)**: Complete data, Sunnyvale HQ
- **Cohere (4)**: Complete data, Toronto HQ

#### Small Providers (1-3 models):
Most have basic information but some missing contact details

### Notable Companies

#### Major Tech Giants:
- **Nvidia**: Santa Clara, CA - AI computing leadership
- **Baidu**: Beijing, CN - ERNIE LLM series
- **Xiaomi**: Beijing, CN - MiMo LLM models, $8.7B AI investment

#### Well-Funded Startups:
- **Groq**: Mountain View, CA - LPU architecture
- **Cerebras**: Sunnyvale, CA - Wafer-Scale Engine
- **Cohere**: Toronto, CA - Enterprise AI (founded 2019)
- **Inflection AI**: Palo Alto, CA - Pi assistant
- **SambaNova**: Palo Alto, CA - Custom AI hardware

#### Emerging Players:
- **DeepSeek**: Hangzhou, CN - Founded 2023, research-focused
- **Minimax**: Singapore - Founded 2021, 200+ countries
- **Liquid AI**: Cambridge, MA - Ultra-efficient models
- **Arcee AI**: San Francisco - Open-weight models

#### Specialized/Niche:
- **Phala**: Newark, CA - Confidential computing with TEEs
- **AkashML**: Decentralized GPU network
- **Featherless**: 30,000+ open-source models
- **Ambient**: Redwood City, CA - Computer vision for security
- **Upstage**: Seoul, KR - Document processing

### Missing Information Summary

#### Complete Data (Homepage, Email, Support, HQ): 19 providers
- Minimax, Friendli, Baidu, Cerebras, Cohere, DeepSeek, Moonshot AI, Arcee AI, Liquid, Relace, Inflection, Ambient, Ionstream, Upstage, Clarifai, AI21, Featherless, Seed, Phala

#### Partial Data (Missing some fields): 21 providers
- Chutes, Z.AI, SambaNova, Fireworks, Groq, AkashML, Nvidia, Morph, GMICloud, Xiaomi, Perplexity, Mancer 2, BaseTen, AionLabs, Io Net, Poolside, StreamLake, Reka, Infermatic

#### Limited Data (Minimal info): 7 providers
- DekaLLM, Inceptron, OpenInference, ModelRun, Stealth, Inception, Mara, Switchpoint

### Research Challenges

1. **Stealth Mode Companies**: Several providers appear to be operating in stealth or early development
2. **Decentralized Providers**: Some (AkashML, Chutes, Phala) are decentralized with no single HQ
3. **Website Issues**: Some websites were inaccessible, timed out, or had minimal public info
4. **Chinese Companies**: Some Chinese providers had Chinese-only websites with limited English info
5. **Regional Variations**: Some companies redirect based on geography (e.g., Moonshot AI to Australia)

### Data Quality Notes

- **Contact Emails**: Found for ~35% of providers
- **Support URLs**: Found for ~60% of providers
- **Headquarters Cities**: Found for ~70% of providers
- **Headquarters Countries**: Confirmed for ~90% of providers
- **Company Descriptions**: Created for 100% of providers (even if based on limited info)

## Methodology

1. Direct URL access to company websites (tried common patterns like company.ai, company.com)
2. LinkedIn company pages for headquarters information
3. Wikipedia for well-known companies
4. API documentation pages
5. GitHub repositories (when available)
6. Inference from available information for stealth/limited-info companies

## Files Updated

- `/Users/andrewsinclair/workspace/DAME/llm-providers/provider_research.json` - Added 47 providers (21-67)
- Total providers in file: 67 (20 from previous research + 47 new)

## Recommendations

1. **Follow-up Research Needed**:
   - DekaLLM (Indonesia) - website appears down
   - Inceptron (Sweden) - very limited public info
   - Stealth, Inception, Mara - appear to be in stealth mode
   - Switchpoint, ModelRun - minimal web presence

2. **Contact Verification**:
   - Many email addresses need verification via website contact forms
   - Some support URLs may need manual verification

3. **HQ Location Updates**:
   - ~30% of providers missing specific city information
   - Some decentralized providers may not have traditional HQ

4. **Ongoing Monitoring**:
   - Several providers appear to be early-stage or emerging
   - Information may become available as they mature
