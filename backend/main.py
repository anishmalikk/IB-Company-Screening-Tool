# backend/main.py

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from ceo_cfo_extractor import get_ceo_cfo_executives, get_execs_via_serp
from improved_treasurer_extractor import get_improved_treasurer_info
from get_industry import get_industry_and_blurb, openai_client
from promptand10q import get_latest_10q_link_for_ticker, get_latest_10k_link_for_ticker
from email_scraper import scrape_emails
from promptand10q import run_prompt_generation_pipeline, run_10k_prompt_generation_pipeline
from getcreditrating import get_company_credit_rating
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
    """Legacy parsing function for backward compatibility"""
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

async def get_intelligent_executives(company_name: str):
    """Get executives using the split CEO/CFO and treasurer extraction systems"""
    try:
        # Get CEO/CFO using the dedicated extractor
        ceo_cfo_result = await get_ceo_cfo_executives(company_name)
        ceo = ceo_cfo_result.get("ceo")
        cfo = ceo_cfo_result.get("cfo")
        
        # Get treasurer using the improved extractor
        treasurer_result = await get_improved_treasurer_info(company_name)
        treasurer = treasurer_result.get("treasurer", "same")
        
        # Extract candidate data from the improved system
        candidate_data = []
        if treasurer_result.get("candidates"):
            for candidate in treasurer_result["candidates"]:
                candidate_data.append({
                    'name': candidate['name'],
                    'linkedin_url': candidate['url'] if candidate['url'] != 'NO_URL_FOUND' else None,
                    'score': candidate.get('score', 0)
                })
        
        # Add candidates to metadata
        treasurer_metadata = {
            'candidates': candidate_data
        }
        
        return {
            "cfo": cfo,
            "treasurer": treasurer,
            "ceo": ceo,
            "treasurer_metadata": treasurer_metadata
        }
    except Exception as e:
        # Fallback to legacy system
        print(f"Split system failed, using legacy: {e}")
        legacy_exec_str = await get_execs_via_serp(company_name)
        cfo, treasurer, ceo = parse_execs(legacy_exec_str)
        return {
            "cfo": cfo,
            "treasurer": treasurer,
            "ceo": ceo,
            "treasurer_metadata": {
                "confidence": "legacy",
                "status": "fallback",
                "email_strategy": "use_cfo_only",
                "recommendation": "Used legacy system due to error",
                "candidates": []
            }
        }



@app.get("/company_info/{company_name}/{ticker}")
async def company_info(
    company_name: str, 
    ticker: str,
    include_executives: bool = Query(True, description="Include executive information"),
    include_emails: bool = Query(True, description="Include email information"),
    include_industry: bool = Query(True, description="Include industry information"),
    include_industry_blurb: bool = Query(True, description="Include industry blurb"),
    include_10q_link: bool = Query(True, description="Include latest 10-Q link"),
    include_10k_link: bool = Query(False, description="Include latest 10-K link"),
    include_debt_liquidity: bool = Query(True, description="Include debt and liquidity summary"),
    include_credit_rating: bool = Query(True, description="Include credit rating")
):
    result = {}
    
    # Get executives if requested
    if include_executives:
        try:
            exec_data = await get_intelligent_executives(company_name)
            result["executives"] = exec_data
        except Exception as e:
            result["executives"] = {"error": f"Failed to get executives: {str(e)}"}
    
    # Get emails if requested
    if include_emails:
        try:
            # Get executives first if not already included
            if not include_executives:
                exec_data = await get_intelligent_executives(company_name)
                cfo = exec_data.get("cfo")
                ceo = exec_data.get("ceo")
                treasurer = exec_data.get("treasurer", "same")
            else:
                cfo = result.get("executives", {}).get("cfo")
                ceo = result.get("executives", {}).get("ceo")
                treasurer = result.get("executives", {}).get("treasurer", "same")
            
            # Use simple legacy email scraper
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
    
    # Get 10-K link if requested
    if include_10k_link:
        try:
            print(f"🔍 Getting 10-K link for ticker: {ticker}")
            tenk_link = get_latest_10k_link_for_ticker(ticker)
            print(f"✅ 10-K link: {tenk_link}")
            result["latest_10k_link"] = tenk_link
        except Exception as e:
            print(f"❌ Error getting 10-K link: {str(e)}")
            result["latest_10k_link"] = f"Error: {str(e)}"
    
    # Get debt and liquidity summary if requested
    if include_debt_liquidity:
        try:
            # Get 10-Q link for debt analysis (even if 10-Q link checkbox is not checked)
            print(f"🔍 Getting 10-Q link for debt analysis ticker: {ticker}")
            tenq_link = get_latest_10q_link_for_ticker(ticker)
            print(f"✅ 10-Q link for debt analysis: {tenq_link}")
            
            # Get 10-K link for debt analysis (even if 10-K link checkbox is not checked)
            print(f"🔍 Getting 10-K link for debt analysis ticker: {ticker}")
            tenk_link = get_latest_10k_link_for_ticker(ticker)
            print(f"✅ 10-K link for debt analysis: {tenk_link}")
            
            # Store both links in the result so the frontend can use them
            result["latest_10q_link"] = tenq_link
            result["latest_10k_link"] = tenk_link
            
            # Generate the debt analysis prompt
            print(f"🔍 Generating debt analysis prompt for ticker: {ticker}")
            
            # Download and parse 10-Q and 10-K documents
            from promptand10q import generate_manual_gpt_prompt, download_and_parse_10q, download_and_parse_10k
            
            # Get 10-Q document
            tenq_soup, tenq_text, tenq_html = download_and_parse_10q(ticker)
            
            # Get 10-K document
            tenk_soup, tenk_text, tenk_html = download_and_parse_10k(ticker)
            
            # Set facility lists to empty since we're not using them
            tenq_facilities = ""
            tenk_facilities = ""
            
            # Generate manual prompt with both facility lists
            manual_prompt = generate_manual_gpt_prompt(tenq_facilities, tenk_facilities, tenq_html if tenq_html else "")
            
            # Generate debt summary prompt
            from promptand10q import generate_debt_summary_prompt
            debt_summary_prompt = generate_debt_summary_prompt()
            
            if manual_prompt:
                result["debt_liquidity_summary"] = ["PDF file available for download"]
                result["debt_analysis_prompt"] = manual_prompt
                result["debt_summary_prompt"] = debt_summary_prompt
                result["facility_list_10q"] = tenq_facilities
                result["facility_list_10k"] = tenk_facilities
            else:
                result["debt_liquidity_summary"] = ["PDF file available for download"]
                result["debt_analysis_prompt"] = f"Error: Failed to generate prompt for {ticker}"
                result["debt_summary_prompt"] = f"Error: Failed to generate summary prompt for {ticker}"
                result["facility_list_10q"] = f"Error: Failed to extract facilities for {ticker}"
                result["facility_list_10k"] = f"Error: Failed to extract facilities for {ticker}"
                
        except Exception as e:
            print(f"❌ Error in debt analysis: {str(e)}")
            result["debt_liquidity_summary"] = [f"Error: {str(e)}"]
            result["latest_10q_link"] = f"Error: {str(e)}"
            result["latest_10k_link"] = f"Error: {str(e)}"
            result["debt_analysis_prompt"] = f"Error: {str(e)}"
            result["debt_summary_prompt"] = f"Error: {str(e)}"
            result["facility_list_10q"] = f"Error: {str(e)}"
            result["facility_list_10k"] = f"Error: {str(e)}"
    
    # Get credit rating if requested
    if include_credit_rating:
        try:
            print(f"🔍 Getting credit rating for company: {company_name}")
            credit_rating = get_company_credit_rating(company_name)
            print(f"✅ Credit rating: {credit_rating}")
            result["credit_rating"] = credit_rating
        except Exception as e:
            print(f"❌ Error getting credit rating: {str(e)}")
            result["credit_rating"] = f"Error: {str(e)}"
    
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

@app.get("/download_10k/{ticker}")
async def download_10k(ticker: str, company_name: str = ""):
    """
    Download 10-K file for a given ticker.
    """
    try:
        # Get the 10-K link
        tenk_link = get_latest_10k_link_for_ticker(ticker)
        if not tenk_link or tenk_link.startswith("Error:"):
            return {"error": "No 10-K filing found"}
        
        # Fetch the file content
        import requests
        headers = {
            "User-Agent": "Company Screener Tool contact@companyscreenertool.com"
        }
        response = requests.get(tenk_link, headers=headers)
        response.raise_for_status()
        
        # Create a better filename with company name
        if company_name:
            # Clean company name for filename (remove special chars, replace spaces with underscores)
            clean_company_name = company_name.replace(" ", "_").replace(",", "").replace(".", "").replace("&", "and")
            filename = f"{clean_company_name}_latest_10K.html"
        else:
            # Fallback to ticker-based filename
            filename = f"{ticker}_latest_10K.html"
        
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
        return {"error": f"Failed to download 10-K: {str(e)}"}