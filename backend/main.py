# backend/main.py

from fastapi import FastAPI
from exec_scraper import get_execs_via_serp
from get_industry import get_industry_and_blurb, openai_client
from get_10q import get_latest_10q_link_for_ticker, get_laymanized_debt_liquidity

app = FastAPI()

@app.get("/company_info/{company_name}/{ticker}")
async def company_info(company_name: str, ticker: str):
    #execs = await get_execs_via_serp(company_name)
    #industry_blurb = get_industry_and_blurb(company_name)
    tenq_link = get_latest_10q_link_for_ticker(ticker)
    debt_liquidity_summary = get_laymanized_debt_liquidity(tenq_link) if tenq_link else ""
    return {
        #"executives": execs,
        #"industry_blurb": industry_blurb,
        "latest_10q_link": tenq_link,
        "debt_liquidity_summary": debt_liquidity_summary
    }