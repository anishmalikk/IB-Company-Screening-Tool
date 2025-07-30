# backend/main.py

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from exec_scraper import get_execs_via_serp
from get_industry import get_industry_and_blurb, openai_client
from get_10q import get_latest_10q_link_for_ticker
from email_scraper import scrape_emails
from promptand10q import run_prompt_generation_pipeline
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
            print(f"🔍 Getting 10-Q link for ticker: {ticker}")
            tenq_link = get_latest_10q_link_for_ticker(ticker)
            print(f"✅ 10-Q link: {tenq_link}")
            result["latest_10q_link"] = tenq_link
        except Exception as e:
            print(f"❌ Error getting 10-Q link: {str(e)}")
            result["latest_10q_link"] = f"Error: {str(e)}"
    
    # Get debt and liquidity summary if requested
    if include_debt_liquidity:
        try:
            # Get 10-Q link for debt analysis (even if 10-Q link checkbox is not checked)
            print(f"🔍 Getting 10-Q link for debt analysis ticker: {ticker}")
            tenq_link = get_latest_10q_link_for_ticker(ticker)
            print(f"✅ 10-Q link for debt analysis: {tenq_link}")
            
            # Store the 10-Q link in the result so the frontend can use it
            result["latest_10q_link"] = tenq_link
            
            # Generate the debt analysis prompt
            print(f"🔍 Generating debt analysis prompt for ticker: {ticker}")
            facility_list, manual_prompt = run_prompt_generation_pipeline(ticker, debug=False)
            
            if manual_prompt:
                result["debt_liquidity_summary"] = ["PDF file available for download"]
                result["debt_analysis_prompt"] = manual_prompt
                result["facility_list"] = facility_list
            else:
                result["debt_liquidity_summary"] = ["PDF file available for download"]
                result["debt_analysis_prompt"] = f"Error: Failed to generate prompt for {ticker}"
                result["facility_list"] = f"Error: Failed to extract facilities for {ticker}"
                
        except Exception as e:
            print(f"❌ Error in debt analysis: {str(e)}")
            result["debt_liquidity_summary"] = [f"Error: {str(e)}"]
            result["latest_10q_link"] = f"Error: {str(e)}"
            result["debt_analysis_prompt"] = f"Error: {str(e)}"
            result["facility_list"] = f"Error: {str(e)}"
    
    return result

@app.get("/download_10q/{ticker}")
async def download_10q(ticker: str, company_name: str = ""):
    """
    Download 10-Q file for a given ticker.
    """
    try:
        # Get the 10-Q link
        tenq_link = get_latest_10q_link_for_ticker(ticker)
        if not tenq_link or tenq_link.startswith("Error:"):
            return {"error": "No 10-Q filing found"}
        
        # Fetch the file content
        import requests
        headers = {
            "User-Agent": "Company Screener Tool contact@companyscreenertool.com"
        }
        response = requests.get(tenq_link, headers=headers)
        response.raise_for_status()
        
        # Create a better filename with company name
        if company_name:
            # Clean company name for filename (remove special chars, replace spaces with underscores)
            clean_company_name = company_name.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and")
            filename = f"{clean_company_name}_latest_10Q.html"
        else:
            # Fallback to ticker-based filename
            filename = f"{ticker}_latest_10Q.html"
        
        print(f"🔍 Download filename: {filename}")
        print(f"🔍 Company name: {company_name}")
        print(f"🔍 Ticker: {ticker}")
        
        # Return the file content
        from fastapi.responses import Response
        return Response(
            content=response.content,
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Type": "text/html"
            }
        )
        
    except Exception as e:
        return {"error": f"Failed to download 10-Q: {str(e)}"}