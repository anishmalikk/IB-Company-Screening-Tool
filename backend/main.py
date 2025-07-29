# backend/main.py

from fastapi import FastAPI
from exec_scraper import get_execs_via_serp
from get_industry import get_industry_and_blurb, openai_client
from get_10q import get_latest_10q_link_for_ticker
from email_scraper import scrape_emails
from laymans10qparser import run_debt_extraction_pipeline
import asyncio
import os

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
    
    # Run the debt extraction pipeline
    debt_liquidity_summary = run_debt_extraction_pipeline(ticker, debug=False)
    
    email_info = scrape_emails(company_name, cfo, treasurer, ceo)
    industry_blurb_full = get_industry_and_blurb(company_name)
    # Split industry_blurb into industry (first 5 words, capitalized) and the rest as industry_blurb
    if industry_blurb_full:
        industry_lines = industry_blurb_full.strip().splitlines()
        if industry_lines:
            # If the first line contains a period, split by the first period
            first_line = industry_lines[0].strip()
            if '.' in first_line:
                period_idx = first_line.find('.')
                industry = first_line[:period_idx+1].strip()
                blurb = first_line[period_idx+1:].strip()
                # If there are more lines, add them to the blurb
                if len(industry_lines) > 1:
                    blurb += "\n" + "\n".join(industry_lines[1:]).strip()
            else:
                industry = first_line
                blurb = "\n".join(industry_lines[1:]).strip() if len(industry_lines) > 1 else ""
    else:
        industry = ""
        blurb = ""
    
    return {
        "executives": {
            "cfo": cfo,
            "treasurer": treasurer,
            "ceo": ceo
        },
        "emails": email_info,
        "industry": industry,
        "industry_blurb": blurb,
        "latest_10q_link": tenq_link,
        "debt_liquidity_summary": debt_liquidity_summary
    }