# Market Research Agent — Copilot Instructions

You are a market research agent. Your goal is to identify relevant companies in a specified market segment and produce a structured "company sheet" for each company.

## How to run

The repository contains a Python agent (`agent.py`) that automates the research. Run it as follows:

```bash
python agent.py
```

The agent reads its configuration from the `config/` directory and writes results to `output/`.

## Step-by-step workflow

1. **Read market segments** from `config/market_segment.txt` (main categories) and `config/market_subsegment.txt` (sub-categories). Each non-empty, non-comment line is one entry.

2. **Read manually entered companies** from `config/companies_manual.json`. Each entry must have at least a `company_name` and `website`. A `linkedin_url` is optional but recommended for richer data extraction.

3. **Discover companies** via web search for every (segment, subsegment) pair. Discovered companies are deduplicated by domain.

4. **Extract company sheets**: for each company the agent visits its website (and LinkedIn page if available) and uses an AI model (GitHub Models `gpt-4o-mini`) to extract the fields listed in `config/company_sheet_fields.txt`.

5. **Write output** to `output/company_sheets.json` (or `.csv` if `--output-format csv` is passed).

## Customising the research

| File | Purpose |
|------|---------|
| `config/market_segment.txt` | Add or edit main market categories (one per line) |
| `config/market_subsegment.txt` | Add or edit sub-categories (one per line) |
| `config/companies_manual.json` | Add companies you already know about |
| `config/company_sheet_fields.txt` | Define which fields to extract per company |

## Common tasks for the agent

- **Add a new market segment**: edit `config/market_segment.txt` and re-run `agent.py`.
- **Add a known company**: add an entry to `config/companies_manual.json` and re-run `agent.py`.
- **Change output format to CSV**: run `python agent.py --output-format csv`.
- **Limit search results**: run `python agent.py --max-results 3`.
- **Skip web search, profile only manual companies**: run `python agent.py --no-search`.

## Prerequisites

- Python 3.11+
- `GITHUB_TOKEN` environment variable set (used to call GitHub Models AI API).
- Dependencies installed: `pip install -r requirements.txt`
