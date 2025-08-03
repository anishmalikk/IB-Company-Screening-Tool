# ceo_cfo_extractor.py

import os
from llm_client import get_llm_client
from serpapi.google_search import GoogleSearch
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import asyncio
from playwright.async_api import async_playwright
import re
from datetime import datetime
from typing import Optional, Dict

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4.1-nano")

LEADERSHIP_KEYWORDS = [
    "leadership", "executive", "management", "officers", "team", "board", "directors"
]

def fetch_serp_results(company_name: str, query: str, num_results: int = 20) -> str:
    """Fetch search results for CEO/CFO extraction"""
    search = GoogleSearch({
        "q": f"{company_name} {query}",
        "api_key": SERPAPI_API_KEY,
        "num": num_results
    })
    results = search.get_dict()
    text_blobs = []
    
    for result in results.get("organic_results", []):
        snippet = result.get("snippet")
        if snippet:
            text_blobs.append(snippet)

    return "\n".join(text_blobs)

def fetch_leadership_page_url(company_name: str) -> str:
    """Get leadership page URL for CEO/CFO extraction"""
    search = GoogleSearch({
        "q": f"{company_name} CEO CFO executives",
        "api_key": SERPAPI_API_KEY,
        "num": 10
    })
    results = search.get_dict()
    company_domain = None

    # Try to extract the company's domain from the first result
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            parsed = urlparse(link)
            if not company_domain and parsed.netloc:
                company_domain = parsed.netloc

    # Prefer links with leadership-related keywords and from the company domain
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            parsed = urlparse(link)
            if any(keyword in link.lower() for keyword in LEADERSHIP_KEYWORDS):
                if company_domain and parsed.netloc == company_domain:
                    return link  # Best match: keyword + company domain
    # Fallback: any link with a keyword
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link and any(keyword in link.lower() for keyword in LEADERSHIP_KEYWORDS):
            return link
    # Fallback: just return the first result
    for result in results.get("organic_results", []):
        link = result.get("link")
        if link:
            return link
    return ""

async def get_leadership_page_text(url: str) -> str:
    """Scrape and extract plain text from leadership page using Playwright, fallback to requests."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)  # Wait for JS
            html_content = await page.content()
            await browser.close()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            return text
    except Exception as e:
        print(f"Playwright scraping error: {e}")
        # Fallback to requests
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            return text
        except Exception as e2:
            print(f"Requests fallback error: {e2}")
            return ""

def format_ceo_cfo_info(ceo_cfo_text: str, leadership_text: str, company_name: str) -> str:
    """
    Extract CEO and CFO information using LLM.
    This function focuses only on CEO and CFO extraction.
    """
    
    # Combine all sources for CEO/CFO extraction
    all_sources = ""
    if ceo_cfo_text:
        all_sources += f"General search results:\n{ceo_cfo_text}\n\n"
    if leadership_text:
        all_sources += f"Leadership page content:\n{leadership_text}\n"
    
    # Use LLM for CEO/CFO extraction (which works well)
    prompt = f"""
I need to do a public screen on {company_name}. Tell me their current CEO and CFO.

IMPORTANT: 
- Only extract names that are clearly mentioned in the provided snippets. Do not make up or guess names.
- For CEO, look for the MOST RECENT/current CEO mentioned. If there are multiple CEOs mentioned, choose the one with the most recent date or current role.
- For CFO, look for the MOST RECENT/current CFO mentioned. If there are multiple CFOs mentioned, choose the one with the most recent date or current role.
- Ignore former, past, or interim CEOs/CFOs unless they are clearly the current ones.
- Focus ONLY on CEO and CFO. Do not extract treasurer information.

Format (no extra words):
CEO: [CEO name]
CFO: [CFO name]

Source snippets:
---
{all_sources}
---
"""
    
    client = get_llm_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

def parse_ceo_cfo_execs(exec_str: str) -> Dict[str, Optional[str]]:
    """Parse CEO and CFO from the formatted string"""
    lines = exec_str.splitlines()
    cfo = ceo = None
    
    for line in lines:
        line_lower = line.lower().strip()
        if line_lower.startswith("cfo:"):
            cfo = line.split(":", 1)[1].strip()
        elif line_lower.startswith("ceo:"):
            ceo = line.split(":", 1)[1].strip()
    
    return {"ceo": ceo, "cfo": cfo}

async def get_ceo_cfo_executives(company_name: str) -> Dict[str, Optional[str]]:
    """
    Main function to extract CEO and CFO information.
    Returns a dictionary with 'ceo' and 'cfo' keys.
    """
    try:
        # Get CEO/CFO snippets (this works well already)
        ceo_cfo_text = fetch_serp_results(company_name, "CEO CFO")
        
        # Get leadership page
        leadership_url = fetch_leadership_page_url(company_name)
        leadership_text = await get_leadership_page_text(leadership_url) if leadership_url else ""
        
        # Format CEO/CFO information
        exec_str = format_ceo_cfo_info(ceo_cfo_text, leadership_text, company_name)
        
        # Parse the results
        return parse_ceo_cfo_execs(exec_str)
        
    except Exception as e:
        print(f"Error extracting CEO/CFO for {company_name}: {e}")
        return {"ceo": None, "cfo": None}

# Legacy function for backward compatibility
def get_execs_via_serp_sync(company_name: str) -> str:
    """Sync wrapper for backward compatibility"""
    return asyncio.run(get_execs_via_serp(company_name))

async def get_execs_via_serp(company_name: str) -> str:
    """
    Legacy function that returns formatted string for backward compatibility.
    This maintains the old interface while using the new extraction logic.
    """
    result = await get_ceo_cfo_executives(company_name)
    
    # Format as legacy string
    lines = []
    if result.get("ceo"):
        lines.append(f"CEO: {result['ceo']}")
    if result.get("cfo"):
        lines.append(f"CFO: {result['cfo']}")
    
    return "\n".join(lines) 