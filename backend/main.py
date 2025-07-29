# backend/main.py

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from exec_scraper import get_execs_via_serp
from get_industry import get_industry_and_blurb, openai_client
from get_10q import get_latest_10q_link_for_ticker
from email_scraper import scrape_emails
from laymans10qparser import run_debt_extraction_pipeline
import asyncio
import os

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

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
async def company_info(
    company_name: str, 
    ticker: str,
    include_executives: bool = Query(True, description="Include executive information"),
    include_emails: bool = Query(True, description="Include email information"),
    include_industry: bool = Query(True, description="Include industry information"),
    include_industry_blurb: bool = Query(True, description="Include industry blurb"),
    include_10q_link: bool = Query(True, description="Include latest 10-Q link"),
    include_debt_liquidity: bool = Query(True, description="Include debt and liquidity summary")
):
    result = {}
    
    # Get executives if requested
    if include_executives:
        try:
            execs_str = await get_execs_via_serp(company_name)
            cfo, treasurer, ceo = parse_execs(execs_str)
            result["executives"] = {
                "cfo": cfo,
                "treasurer": treasurer,
                "ceo": ceo
            }
        except Exception as e:
            result["executives"] = {"error": f"Failed to get executives: {str(e)}"}
    
    # Get emails if requested
    if include_emails:
        try:
            # Get executives first if not already included
            if not include_executives:
                execs_str = await get_execs_via_serp(company_name)
                cfo, treasurer, ceo = parse_execs(execs_str)
            else:
                cfo = result.get("executives", {}).get("cfo")
                treasurer = result.get("executives", {}).get("treasurer")
                ceo = result.get("executives", {}).get("ceo")
            
            email_info = scrape_emails(company_name, cfo, treasurer, ceo)
            result["emails"] = email_info
        except Exception as e:
            result["emails"] = {"error": f"Failed to get emails: {str(e)}"}
    
    # Get industry and blurb if requested
    if include_industry or include_industry_blurb:
        try:
            industry_blurb_full = get_industry_and_blurb(company_name)
            if industry_blurb_full:
                industry_lines = industry_blurb_full.strip().splitlines()
                if industry_lines:
                    first_line = industry_lines[0].strip()
                    if '.' in first_line:
                        period_idx = first_line.find('.')
                        industry = first_line[:period_idx+1].strip()
                        blurb = first_line[period_idx+1:].strip()
                        if len(industry_lines) > 1:
                            blurb += "\n" + "\n".join(industry_lines[1:]).strip()
                    else:
                        industry = first_line
                        blurb = "\n".join(industry_lines[1:]).strip() if len(industry_lines) > 1 else ""
                else:
                    industry = ""
                    blurb = ""
            else:
                industry = ""
                blurb = ""
            
            if include_industry:
                result["industry"] = industry
            if include_industry_blurb:
                result["industry_blurb"] = blurb
        except Exception as e:
            if include_industry:
                result["industry"] = f"Error: {str(e)}"
            if include_industry_blurb:
                result["industry_blurb"] = f"Error: {str(e)}"
    
    # Get 10-Q link if requested
    if include_10q_link:
        try:
            tenq_link = get_latest_10q_link_for_ticker(ticker)
            result["latest_10q_link"] = tenq_link
        except Exception as e:
            result["latest_10q_link"] = f"Error: {str(e)}"
    
    # Get debt and liquidity summary if requested
    if include_debt_liquidity:
        try:
            debt_liquidity_summary = run_debt_extraction_pipeline(ticker, debug=False)
            result["debt_liquidity_summary"] = debt_liquidity_summary
        except Exception as e:
            result["debt_liquidity_summary"] = [f"Error: {str(e)}"]
    
    return result