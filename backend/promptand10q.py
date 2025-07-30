from sec_edgar_api.EdgarClient import EdgarClient
from ticker_utils import get_cik_for_ticker
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from openai import OpenAI
import re

load_dotenv()

# Initialize the Edgar client
edgar = EdgarClient(user_agent="Company Screener Tool contact@companyscreenertool.com")

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("10Q_MODEL_NAME", "gpt-4o-mini")
llm_client = OpenAI(api_key=OPENAI_API_KEY)

def extract_facility_names_from_10q(soup, text_content, debug=False):
    """
    First pass: Extract all currently active debt facility names from the 10-Q document.
    Returns a list of facility names/types/currencies/maturities.
    """
    prompt = f"""
You are reviewing the latest 10-Q for a company. Your task is to scan the full document (text and tables) and list every currently active debt facility or note mentioned.

For each facility or note, extract the following:
- Name or label (e.g., 2024 Term Loan, Revolving Credit Facility, CHF Senior Notes)
- Currency
- Maturity date (if known)
- Facility type (e.g., Term Loan, Revolver, Note, etc.)

You do NOT need to format it precisely. Just list every unique facility that is currently active, regardless of how much detail is available.

Do not summarize. Do not skip any facility mentioned in a table or section like "Note 5 – Credit Facilities".

List one facility per line.

DOCUMENT TEXT:
{text_content}
"""

    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a financial document analyzer. Extract all currently active debt facilities and notes from 10-Q filings. Be comprehensive and list every facility mentioned."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent extraction
        )
        
        facility_list = response.choices[0].message.content.strip()
        
        return facility_list
        
    except Exception as e:
        return f"Error extracting facilities: {str(e)}"

def generate_manual_gpt_prompt(facility_list: str, html_content: str):
    """
    Second function: Generate a prompt for manual GPT analysis with the full HTML document.
    Returns plaintext prompt that can be used with GPT online.
    """
    prompt = f"""I performed an initial manual pass through the company's 10-Q and identified the following currently active debt facilities and notes:

{facility_list}

Your task is to extract the full debt capital stack for this company using the HTML provided. You must:

- Include every facility listed above if they are active, ignore them if they aren't actual debt facilities or they are outdated
- Add any facilities you find that were not in the list
- Do not omit any active term loans, revolvers, or notes
- Follow this strict format:
  $[Amount] [Facility Type] @ [Interest Rate] mat. MM/YYYY (Lead Bank)
    - Bullet 1
    - Bullet 2

If any detail is missing, write:
"MISSING"

CRITICAL: LIST THE FACILITIES FROM EARLIEST TO LATEST MATURITY. Do not summarize. Do not omit any bullet points.

Begin now using the full HTML document.
"""

    return prompt

def get_latest_10q_link_for_ticker(ticker: str) -> str:
    """
    Get the latest 10-Q filing URL for a given ticker.
    """
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return ""
    
    try:
        submissions = edgar.get_submissions(cik=cik)
        recent_filings = submissions["filings"]["recent"]
        
        for i, form in enumerate(recent_filings["form"]):
            if form == "10-Q":
                accession = recent_filings["accessionNumber"][i]
                primary_doc = recent_filings["primaryDocument"][i]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik):010d}/{accession.replace('-', '')}/{primary_doc}"
                return filing_url
        
        return ""
        
    except Exception as e:
        return ""

def download_and_parse_10q(ticker: str):
    """
    Download and parse the latest 10-Q document for a given ticker.
    """
    link = get_latest_10q_link_for_ticker(ticker)
    
    if not link:
        return None, None, None
    
    try:
        response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        text_content = soup.get_text(separator="\n", strip=True)
        html_content = response.text
        
        return soup, text_content, html_content
        
    except Exception as e:
        return None, None, None

def run_prompt_generation_pipeline(ticker: str, debug=False):
    """
    Run the complete pipeline to generate facility list and manual GPT prompt.
    Returns the facility list and the manual GPT prompt.
    """
    # Step 1: Download and parse
    soup, text_content, html_content = download_and_parse_10q(ticker)
    
    if soup is None:
        return None, None
    
    # Step 2: Extract facility names
    facility_list = extract_facility_names_from_10q(soup, text_content, debug=debug)
    
    # Step 3: Generate manual GPT prompt
    manual_prompt = generate_manual_gpt_prompt(facility_list, html_content)
    
    return facility_list, manual_prompt

if __name__ == "__main__":
    ticker = "CE"
    debug = False
    facility_list, manual_prompt = run_prompt_generation_pipeline(ticker, debug=debug)

    if manual_prompt:
        print(manual_prompt)
    else:
        print(f"❌ Failed to generate prompt for {ticker}")
