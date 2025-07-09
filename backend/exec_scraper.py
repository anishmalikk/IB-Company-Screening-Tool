# exec_scraper.py

import os
from llm_client import get_llm_client
from serpapi.google_search import GoogleSearch

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")


def fetch_serp_results(company_name: str, query: str, num_results: int = 20) -> str:
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


def fetch_leadership_page_snippets(company_name: str) -> str:
    return fetch_serp_results(company_name, "leadership site")


def fetch_treasurer_search_snippets(company_name: str) -> str:
    return fetch_serp_results(company_name, '"treasurer"')


def format_exec_info(snippets_ceo_cfo: str, leadership_snippets: str, treasurer_snippets: str, company_name: str) -> str:
    prompt = f"""
I need to do a public screen on {company_name}. Tell me their current CEO, CFO, and Treasurer. If they don't have a treasurer on their site or in the results, just put "same" under treasurer. I want just the information I’m asking for in this format, no extra words or info. Make sure you are looking at the latest news (for example if a new person was appointed recently), and double check any leadership changes from the company leadership site. You can also use LinkedIn links or other credible sources to find the Treasurer if it's not on the main site. Here's how I want the format:

CFO: ...
Treasurer (or closest): ...
CEO: ...

Use the snippets below:
---
[CEO and CFO snippets]
{snippets_ceo_cfo}
---
[Leadership Page Snippets]
{leadership_snippets}
---
[Treasurer Search Snippets]
{treasurer_snippets}
"""

    client = get_llm_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def get_execs_via_serp(company_name: str) -> str:
    ceo_cfo_text = fetch_serp_results(company_name, "CEO CFO")
    leadership_text = fetch_leadership_page_snippets(company_name)
    treasurer_text = fetch_treasurer_search_snippets(company_name)
    return format_exec_info(ceo_cfo_text, leadership_text, treasurer_text, company_name)
