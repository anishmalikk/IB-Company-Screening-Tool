import os
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
}

def scrape_exec_names(url: str) -> Dict[str, str]:
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text().lower()

        execs = {"CEO": "Not Found", "CFO": "Not Found", "Treasurer": "Not Found"}

        for role in execs:
            for tag in soup.find_all(["h1", "h2", "h3", "p", "div"]):
                content = tag.get_text().strip()
                if role.lower() in content.lower():
                    words = content.split()
                    name = " ".join([w for w in words if w.istitle() and len(w) > 2])
                    if len(name.split()) >= 2:
                        execs[role] = name
                        break

        return execs

    except Exception as e:
        print(f"Scraping error: {e}")
        return {
            "CEO": "Not Found",
            "CFO": "Not Found",
            "Treasurer": "Not Found"
        }

def get_exec_info(ticker: str) -> Dict[str, str]:
    query = f"{ticker} executive leadership site:{ticker.lower()}.com"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 3
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        for result in results.get("organic_results", []):
            link = result.get("link", "")
            if ticker.lower() in link and any(k in link.lower() for k in ["leadership", "executives", "management", "team"]):
                return scrape_exec_names(link)
    except Exception as e:
        print(f"Exec name search error: {e}")

    return {
        "CEO": "Not Found",
        "CFO": "Not Found",
        "Treasurer": "Not Found"
    }

def search_linkedin(name: str, company: str) -> Dict[str, str]:
    query = f"{name} {company} site:linkedin.com/in"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 5
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()

        for result in results.get("organic_results", []):
            link = result.get("link", "")
            if "linkedin.com/in/" in link:
                return {
                    "linkedin": link,
                    "email": f"{name.lower().replace(' ', '.')}@{company.lower()}corp.com"
                }

        return {"linkedin": "", "email": ""}
    except Exception as e:
        print(f"SerpAPI error: {e}")
        return {"linkedin": "", "email": ""}
