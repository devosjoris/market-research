# Market Research Agent

An AI-powered agent that identifies relevant companies in a market segment and builds a structured **company sheet** for each one. Designed to run in the [GitHub Copilot cloud agent](https://docs.github.com/en/copilot/using-github-copilot/using-claude-sonnet-in-github-copilot) environment — no special software required.

---

## How it works

1. The agent reads the market **segment** and **sub-segment** definitions from plain text files.
2. It performs web searches (DuckDuckGo) to discover companies for every segment/sub-segment combination.
3. Manual companies you already know about can be added in `config/companies_manual.json`.
4. For each company the agent visits its website (and LinkedIn page if provided) and uses **GitHub Models** (`gpt-4o-mini`) to extract the fields defined in `config/company_sheet_fields.txt`.
5. Results are written to `output/company_sheets.json` (or CSV).

---

## Quick start

### Prerequisites

- Python 3.11+
- A GitHub personal access token with access to [GitHub Models](https://docs.github.com/en/github-models) exported as `GITHUB_TOKEN`

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure your research

| File | Purpose |
|------|---------|
| `config/market_segment.txt` | Main market categories (one per line) |
| `config/market_subsegment.txt` | Sub-categories (one per line) |
| `config/company_sheet_fields.txt` | Fields to extract per company |
| `config/companies_manual.json` | Companies you want to include manually |

### Run

```bash
# Default: JSON output
python agent.py

# CSV output
python agent.py --output-format csv

# Only profile manually entered companies (skip web search)
python agent.py --no-search

# Limit search results per query
python agent.py --max-results 3
```

Results are written to `output/company_sheets.json` (or `.csv`).

---

## Configuration files

### `config/market_segment.txt`

```
laser diode
```

### `config/market_subsegment.txt`

```
test service
fab service
packaging
epitaxy
```

### `config/company_sheet_fields.txt`

```
company_name
website
linkedin_url
headquarters_location
founded_year
employee_count
annual_revenue
business_description
key_products_services
target_markets
key_customers
technology_focus
certifications
contact_email
contact_phone
```

### `config/companies_manual.json`

```json
[
  {
    "company_name": "Example Laser Inc.",
    "website": "https://www.example-laser.com",
    "linkedin_url": "https://www.linkedin.com/company/example-laser"
  }
]
```

---

## CLI reference

```
usage: agent.py [-h] [--segment FILE] [--subsegment FILE] [--fields FILE]
                [--manual FILE] [--output FILE] [--output-format {json,csv}]
                [--max-results N] [--model MODEL] [--no-search]

Options:
  --segment FILE        Path to market segment file (default: config/market_segment.txt)
  --subsegment FILE     Path to market sub-segment file (default: config/market_subsegment.txt)
  --fields FILE         Path to company sheet fields file (default: config/company_sheet_fields.txt)
  --manual FILE         Path to manually entered companies JSON (default: config/companies_manual.json)
  --output FILE         Output file path (default: output/company_sheets.json)
  --output-format FMT   Output format: json or csv (default: json)
  --max-results N       Max search results per segment/subsegment pair (default: 5)
  --model MODEL         GitHub Models model name (default: gpt-4o-mini)
  --no-search           Skip web search, use only manual companies
```

---

## Running in the Copilot cloud agent

The `.github/copilot-setup-steps.yml` file pre-installs all Python dependencies automatically so the agent runs without any manual setup steps in the Copilot cloud environment.