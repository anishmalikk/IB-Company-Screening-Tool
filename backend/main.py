# backend/main.py

from fastapi import FastAPI
from exec_scraper import get_execs_via_serp
from get_industry import get_industry_and_blurb, openai_client
from get_10q import get_latest_10q_link_for_ticker, get_laymanized_debt_liquidity
from email_scraper import scrape_emails
import asyncio

app = FastAPI()

def parse_execs(exec_str):
    lines = exec_str.splitlines()
    cfo = treasurer = ceo = None
    for line in lines:
        if line.lower().startswith("cfo:"):
            cfo = line.split(":", 1)[1].strip()
        elif line.lower().startswith("treasurer"):
            treasurer = line.split(":", 1)[1].strip()
        elif line.lower().startswith("ceo:"):
            ceo = line.split(":", 1)[1].strip()
    return cfo, treasurer, ceo

@app.get("/company_info/{company_name}/{ticker}")
async def company_info(company_name: str, ticker: str):
    execs_str = await get_execs_via_serp(company_name)
    cfo, treasurer, ceo = parse_execs(execs_str)
    tenq_link = get_latest_10q_link_for_ticker(ticker)
    debt_liquidity_summary = get_laymanized_debt_liquidity(tenq_link) if tenq_link else ""
    email_info = scrape_emails(company_name, cfo, treasurer)
    return {
        "executives": {
            "cfo": cfo,
            "treasurer": treasurer,
            "ceo": ceo
        },
        "emails": email_info,
        "latest_10q_link": tenq_link,
        "debt_liquidity_summary": debt_liquidity_summary
    }