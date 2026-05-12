# LLM Benchmark Rankings — Research & Options

This document covers the landscape of publicly available LLM benchmarks and leaderboards that could be used for model comparison in this project, along with the rationale for the current choice and what alternatives exist.

---

## Current Implementation: Open LLM Leaderboard v2

**Source**: [huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard](https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard)  
**Data API**: HuggingFace Datasets Server (no auth required)  
**Update cadence**: Continuously updated as new submissions arrive  
**Models ranked**: ~4,576 (as of May 2026)  
**Access cost**: Free, no API key  

### Why it was chosen
- Fully open, no API key or account required
- Machine-readable via the HuggingFace datasets-server API (`datasets-server.huggingface.co/rows`)
- Covers a very wide range of open-source models
- Uses hard, well-regarded academic benchmarks rather than vibes-based human ratings
- Community-trusted source (run by HuggingFace)

### Benchmark tasks included
| Task | Full name | What it tests | Paper |
|---|---|---|---|
| **IFEval** | Instruction Following Evaluation | Ability to follow explicit formatting/structural instructions precisely | [arxiv 2311.07911](https://arxiv.org/abs/2311.07911) |
| **BBH** | BIG-Bench Hard | 23 challenging multi-step reasoning, logic, and language tasks | [arxiv 2210.09261](https://arxiv.org/abs/2210.09261) |
| **MATH Lvl 5** | MATH Level 5 | Hardest competition-level mathematics (AMC/AIME/olympiad) | [arxiv 2103.03874](https://arxiv.org/abs/2103.03874) |
| **GPQA** | Graduate-level Professional QA | PhD-level questions in biology, chemistry, physics — even domain experts score ~65% | [arxiv 2311.12022](https://arxiv.org/abs/2311.12022) |
| **MUSR** | Multi-step Soft Reasoning | Long-context narrative reasoning requiring chained inference steps | [arxiv 2310.16049](https://arxiv.org/abs/2310.16049) |
| **MMLU-Pro** | MMLU Professional | Expert-level questions across 14 academic disciplines — harder variant of MMLU | [arxiv 2406.01574](https://arxiv.org/abs/2406.01574) |

### Limitations
- Scores are relatively low (top models ~50%) because v2 uses deliberately hard benchmarks
- Heavy representation of fine-tuned/merged models that may not be production-ready
- Does not include closed-source models (GPT, Claude, Gemini) — those are on a separate leaderboard
- Model IDs are HuggingFace `owner/repo` format which needs normalisation to match OpenRouter IDs

---

## Alternative Leaderboards Considered

### 1. Open LLM Leaderboard v1 (legacy)
**URL**: `huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard` (archived)  
**Status**: Deprecated in favour of v2  
**Tasks**: HellaSwag, ARC, WinoGrande, TruthfulQA, GSM8K, MMLU  
**Verdict**: Not worth using — superseded, easier tasks, leaderboard gaming was rampant.

---

### 2. LMSYS Chatbot Arena
**URL**: [lmarena.ai](https://lmarena.ai)  
**Method**: Elo rating from blind human pairwise comparisons (~2M+ votes)  
**Includes closed models**: Yes (GPT-4o, Claude 3.5, Gemini 1.5 etc.)  
**API access**: No public machine-readable API — leaderboard is web-only  
**Update cadence**: Continuously  

**Pros**:
- Highly respected; closest to real-world preference
- Covers both open and closed models
- Arena Hard and Arena-Hard-Auto sub-benchmarks are reproducible

**Cons**:
- No public REST API; would require scraping HTML or using unofficial endpoints
- Elo scores not directly comparable to capability scores
- Open-source models tend to underperform vs. their benchmark scores here

**Verdict**: Would be valuable to add for closed models (GPT, Claude, Gemini), but requires scraping. Worth adding in a future iteration.

---

### 3. Artificial Analysis Quality Index
**URL**: [artificialanalysis.ai](https://artificialanalysis.ai)  
**Method**: Aggregate of multiple benchmarks + human preference + speed/cost metrics  
**Includes closed models**: Yes  
**API access**: No public API  

**Pros**:
- Combines quality + latency + cost into one view
- Very clean presentation
- Covers all major commercial APIs

**Cons**:
- Proprietary methodology, not reproducible
- No API — data would need scraping

**Verdict**: Good reference but not suitable for automated ingestion.

---

### 4. Scale SEAL Leaderboards
**URL**: [scale.com/leaderboard](https://scale.com/leaderboard)  
**Method**: Expert human evaluation across domains (coding, instruction, safety, etc.)  
**Includes closed models**: Yes  
**API access**: No public API  

**Pros**:
- High-quality expert evaluations
- Domain-specific breakdowns (Enterprise, Coding, Reasoning, etc.)

**Cons**:
- Infrequent updates
- No API; limited public access to raw scores

**Verdict**: Useful for spot-checks but not suitable for automated daily ingestion.

---

### 5. EvalPlus / HumanEval+
**URL**: [evalplus.github.io/leaderboard.html](https://evalplus.github.io/leaderboard.html)  
**Method**: Code generation — HumanEval and MBPP with enhanced test suites  
**Includes closed models**: Partial  
**API access**: GitHub-hosted static JSON  

**Pros**:
- Machine-readable static JSON files on GitHub
- Specifically measures coding ability
- Well-maintained

**Cons**:
- Coding-only — not a general capability measure
- Fewer models than Open LLM Leaderboard

**Verdict**: Worth adding as a supplementary coding-specific score. Could pull `pass@1` from the GitHub JSON.  
**Implementation**: `https://raw.githubusercontent.com/evalplus/evalplus.github.io/main/leaderboard.json`

---

### 6. LiveCodeBench
**URL**: [livecodebench.github.io](https://livecodebench.github.io)  
**Method**: Live coding problems scraped from LeetCode, Codeforces, AtCoder — contamination-resistant  
**Includes closed models**: Yes  
**API access**: GitHub-hosted JSON  

**Pros**:
- Contamination-resistant (new problems added continuously)
- Covers both open and closed models
- GitHub-hosted data files

**Cons**:
- Coding-only

**Verdict**: Good companion to EvalPlus for coding-focused comparisons.

---

### 7. MMLU (standard)
**URL**: Various hosting; commonly used in papers  
**Method**: 57-subject multiple-choice knowledge test  
**Status**: Largely superseded by MMLU-Pro (already in Open LLM Leaderboard v2)  
**Verdict**: Skip — use MMLU-Pro instead.

---

### 8. BigCodeBench
**URL**: [bigcode-bench.github.io](https://bigcode-bench.github.io)  
**Method**: Function-level code completion across diverse libraries  
**Includes closed models**: Yes  
**API access**: HuggingFace dataset  

**Pros**:
- Broader than HumanEval (covers numpy, pandas, web APIs etc.)
- Machine-readable via HuggingFace datasets-server (same pattern as current implementation)

**Cons**:
- Coding-only

**Verdict**: Could reuse existing `fetch_benchmarks.py` pattern to ingest this.

---

### 9. MT-Bench / Alpaca Eval
**Method**: GPT-4 as judge on multi-turn conversations / instruction following  
**Status**: Largely superseded by Chatbot Arena and better evals  
**Verdict**: Dated — skip.

---

### 10. OpenCompass
**URL**: [opencompass.org.cn/leaderboard-llm](https://opencompass.org.cn/leaderboard-llm)  
**Method**: Aggregate of 80+ benchmarks, strong coverage of Chinese models  
**Includes closed models**: Yes  
**API access**: No public API  

**Pros**:
- Best coverage of Chinese-origin models (Qwen, DeepSeek, Kimi etc.)
- Wide benchmark variety

**Cons**:
- No machine-readable API
- Chinese-language first

**Verdict**: Useful for cross-referencing Chinese model quality.

---

## Recommended Future Additions

Priority order for extending benchmark coverage:

| Priority | Source | Value | Effort |
|---|---|---|---|
| 1 | **Chatbot Arena** (scrape) | Real human preference, covers all closed models | Medium — requires HTML scraping |
| 2 | **EvalPlus** | Coding capability, GitHub JSON | Low — direct JSON fetch |
| 3 | **LiveCodeBench** | Contamination-resistant coding | Low — GitHub JSON |
| 4 | **BigCodeBench** | Broad coding, HuggingFace dataset | Low — same pattern as current |
| 5 | **Artificial Analysis** | Quality + speed + cost composite | Hard — scraping required |

---

## Data Pipeline Notes

### Current fetch pattern (easily reusable)
```python
# HuggingFace datasets-server — works for any public dataset
HF_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset={dataset_id}"
    "&config=default&split=train&length=100&offset={offset}"
)
# Paginate until offset >= num_rows_total
```

### Key normalisation issue
OpenRouter model IDs are lowercase (`meta-llama/llama-3.1-70b-instruct`).  
HuggingFace model IDs use original casing (`meta-llama/Llama-3.1-70B-Instruct`).  
Match using `.lower()` comparison. Secondary fallback: match on the repo name portion after `/`.

### Storage location
`rollups/benchmarks.json` — fetched daily by Lambda, structure:
```json
{
  "fetched_at": "ISO 8601",
  "total": 4576,
  "models": [
    {
      "id": "owner/repo",
      "rank": 1,
      "avg": 52.1,
      "ifeval": 84.3,
      "bbh": 71.2,
      "math": 48.6,
      "gpqa": 42.1,
      "musr": 38.4,
      "mmlu_pro": 58.9
    }
  ]
}
```
