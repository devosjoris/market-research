"""
Market Research Agent
=====================
Identifies relevant companies in a market segment and builds a company sheet
for each company using web search and AI-powered information extraction.

Usage:
    python agent.py [options]

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
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def read_lines(filepath: str) -> list[str]:
    """Read non-empty, non-comment lines from a text file."""
    path = Path(filepath)
    if not path.exists():
        logger.warning("File not found: %s", filepath)
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def load_manual_companies(filepath: str) -> list[dict[str, Any]]:
    """Load manually entered companies from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        logger.info("No manual companies file found at %s", filepath)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("companies_manual.json must contain a JSON array; skipping.")
            return []
        return data
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse %s: %s", filepath, exc)
        return []


# ---------------------------------------------------------------------------
# Web search (DuckDuckGo HTML — no API key required)
# ---------------------------------------------------------------------------

_DDGS_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Perform a DuckDuckGo HTML search and return a list of {title, url, snippet}."""
    results = []
    try:
        response = requests.post(
            _DDGS_URL,
            data={"q": query, "b": ""},
            headers=_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for result in soup.select("div.result")[:max_results]:
            title_tag = result.select_one("a.result__a")
            snippet_tag = result.select_one("a.result__snippet")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            url = title_tag.get("href", "")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            if url:
                results.append({"title": title, "url": url, "snippet": snippet})
    except requests.RequestException as exc:
        logger.warning("Search request failed for query '%s': %s", query, exc)
    return results


def discover_companies(
    segments: list[str],
    subsegments: list[str],
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """
    Search for companies for every (segment, subsegment) combination.
    Returns a deduplicated list of company stubs.
    """
    seen_domains: set[str] = set()
    companies: list[dict[str, Any]] = []

    for segment in segments:
        for subsegment in subsegments:
            query = f"{segment} {subsegment} company"
            logger.info("Searching: %s", query)
            results = _ddg_search(query, max_results=max_results)
            time.sleep(1)  # polite delay
            for r in results:
                domain = _extract_domain(r["url"])
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)
                companies.append(
                    {
                        "company_name": r["title"],
                        "website": r["url"],
                        "linkedin_url": "",
                        "_segment": segment,
                        "_subsegment": subsegment,
                        "_source": "search",
                    }
                )
    return companies


def _extract_domain(url: str) -> str:
    """Return the netloc of a URL, or empty string on failure."""
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Web page content fetcher
# ---------------------------------------------------------------------------

def fetch_page_text(url: str, max_chars: int = 4000) -> str:
    """Fetch a web page and return its visible text content (truncated)."""
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove script / style noise
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except requests.RequestException as exc:
        logger.debug("Could not fetch %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# AI-powered company sheet extraction
# ---------------------------------------------------------------------------

def _build_client(model: str) -> tuple[OpenAI, str]:
    """Build an OpenAI-compatible client for GitHub Models."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN environment variable is not set. "
            "Please set it to a GitHub personal access token with access to GitHub Models."
        )
    client = OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=token,
    )
    return client, model


def extract_company_sheet(
    company: dict[str, Any],
    fields: list[str],
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    """
    Use AI to extract company sheet fields from the company's web page.
    Returns a dict mapping field names to extracted values.
    """
    website_text = fetch_page_text(company.get("website", ""))
    linkedin_text = fetch_page_text(company.get("linkedin_url", ""))
    combined_text = "\n\n".join(filter(None, [website_text, linkedin_text]))

    fields_list = "\n".join(f"- {f}" for f in fields)
    prompt = (
        f"You are a market research analyst. "
        f"Based on the web content below, extract the following information about the company.\n\n"
        f"Fields to extract:\n{fields_list}\n\n"
        f"Company name (hint): {company.get('company_name', 'Unknown')}\n"
        f"Website: {company.get('website', '')}\n"
        f"LinkedIn: {company.get('linkedin_url', '')}\n\n"
        f"Web content:\n{combined_text}\n\n"
        f"Return a JSON object where each key is one of the field names above "
        f"and the value is the extracted information (string). "
        f"Use null for fields where information is not available. "
        f"Do not include any markdown formatting — output raw JSON only."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        # Strip potential markdown code fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        sheet = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Could not parse AI response as JSON for %s: %s", company.get("company_name"), exc)
        sheet = {}
    except Exception as exc:
        logger.error("AI extraction failed for %s: %s", company.get("company_name"), exc)
        sheet = {}

    # Ensure all requested fields are present
    for field in fields:
        if field not in sheet:
            sheet[field] = None

    # Carry over known metadata
    for key in ("website", "linkedin_url", "_segment", "_subsegment", "_source"):
        if key in company and key not in sheet:
            sheet[key] = company[key]

    return sheet


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json(sheets: list[dict[str, Any]], filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_text(json.dumps(sheets, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %d company sheets to %s", len(sheets), filepath)


def write_csv(sheets: list[dict[str, Any]], filepath: str) -> None:
    if not sheets:
        logger.warning("No data to write to CSV.")
        return
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    # Collect all keys preserving insertion order
    all_keys: list[str] = []
    seen_keys: set[str] = set()
    for sheet in sheets:
        for key in sheet:
            if key not in seen_keys:
                all_keys.append(key)
                seen_keys.add(key)

    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sheets)
    logger.info("Wrote %d company sheets to %s", len(sheets), filepath)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Market Research Agent — discovers and profiles companies in a market segment."
    )
    parser.add_argument(
        "--segment",
        default="config/market_segment.txt",
        help="Path to market segment file (default: config/market_segment.txt)",
    )
    parser.add_argument(
        "--subsegment",
        default="config/market_subsegment.txt",
        help="Path to market sub-segment file (default: config/market_subsegment.txt)",
    )
    parser.add_argument(
        "--fields",
        default="config/company_sheet_fields.txt",
        help="Path to company sheet fields file (default: config/company_sheet_fields.txt)",
    )
    parser.add_argument(
        "--manual",
        default="config/companies_manual.json",
        help="Path to manually entered companies JSON (default: config/companies_manual.json)",
    )
    parser.add_argument(
        "--output",
        default="output/company_sheets.json",
        help="Output file path (default: output/company_sheets.json)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "csv"],
        default="json",
        help="Output format: json or csv (default: json)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max search results per segment/subsegment pair (default: 5)",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="GitHub Models model name (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="Skip web search, use only manually entered companies",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Load configuration
    segments = read_lines(args.segment)
    subsegments = read_lines(args.subsegment)
    fields = read_lines(args.fields)
    manual_companies = load_manual_companies(args.manual)

    if not fields:
        logger.error("No company sheet fields defined in %s. Aborting.", args.fields)
        return 1

    logger.info(
        "Config: %d segment(s), %d subsegment(s), %d field(s), %d manual company/ies",
        len(segments),
        len(subsegments),
        len(fields),
        len(manual_companies),
    )

    # Discover companies via web search
    discovered: list[dict[str, Any]] = []
    if not args.no_search:
        if segments and subsegments:
            discovered = discover_companies(segments, subsegments, max_results=args.max_results)
            logger.info("Discovered %d unique companies via search.", len(discovered))
        else:
            logger.warning("No segments/subsegments defined; skipping web search.")

    # Merge: manual companies take priority (deduplicate by domain)
    seen_domains: set[str] = set()
    all_companies: list[dict[str, Any]] = []

    for company in manual_companies:
        domain = _extract_domain(company.get("website", ""))
        if domain:
            seen_domains.add(domain)
        company.setdefault("_source", "manual")
        all_companies.append(company)

    for company in discovered:
        domain = _extract_domain(company.get("website", ""))
        if domain and domain in seen_domains:
            continue
        if domain:
            seen_domains.add(domain)
        all_companies.append(company)

    if not all_companies:
        logger.warning("No companies found. Check your segment/subsegment configuration.")
        return 0

    logger.info("Total companies to profile: %d", len(all_companies))

    # Build AI client
    try:
        client, model = _build_client(args.model)
    except EnvironmentError as exc:
        logger.error("%s", exc)
        return 1

    # Extract company sheets
    sheets: list[dict[str, Any]] = []
    for i, company in enumerate(all_companies, start=1):
        name = company.get("company_name", company.get("website", f"Company {i}"))
        logger.info("[%d/%d] Profiling: %s", i, len(all_companies), name)
        sheet = extract_company_sheet(company, fields, client, model)
        sheets.append(sheet)
        time.sleep(0.5)  # polite delay between AI calls

    # Write output
    output_path = args.output
    if args.output_format == "csv":
        if not output_path.endswith(".csv"):
            output_path = Path(output_path).with_suffix(".csv").as_posix()
        write_csv(sheets, output_path)
    else:
        if not output_path.endswith(".json"):
            output_path = Path(output_path).with_suffix(".json").as_posix()
        write_json(sheets, output_path)

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
