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

def deduplicate_facilities(facility_list: str) -> str:
    """
    Remove duplicates from facility list and clean up formatting.
    """
    if not facility_list or facility_list.startswith("Error:"):
        return facility_list
    
    # Split into lines and clean up
    lines = facility_list.strip().split('\n')
    unique_facilities = []
    seen = set()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Remove numbering if present (e.g., "1. ", "2. ", etc.)
        if line and line[0].isdigit() and '. ' in line:
            line = line.split('. ', 1)[1]
        
        # Normalize the line for comparison
        normalized = line.lower().strip()
        
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_facilities.append(line)
    
    return '\n'.join(unique_facilities)

def extract_facility_names_from_10q(soup, text_content, debug=False):
    """
    First pass: Extract all currently active debt facility names from the 10-Q document.
    Returns a list of facility names/types/currencies/maturities.
    """
    prompt = f"""
You are reviewing the latest 10-Q for a company. Your task is to scan the full document (text and tables) and list every UNIQUE currently active debt facility or note mentioned.

For each UNIQUE facility or note, extract the following:
- Name or label (e.g., 2024 Term Loan, Revolving Credit Facility, Senior Notes)
- Currency
- Facility type (e.g., Term Loan, Revolver, Note, etc.)

CRITICAL INSTRUCTIONS:
- List each UNIQUE facility only ONCE, even if it appears multiple times in the document
- Do not duplicate the same facility with different numbering
- Focus on the actual facility name/type, not individual mentions
- For notes, group by maturity year and currency (e.g., "2025 Senior Unsecured Notes (USD)" not individual note numbers)
- For revolving facilities, list once per facility type
- For term loans, list once per facility

Format each facility as: [Facility Name] ([Currency], [Facility Type])

List one UNIQUE facility per line. Do not number them.

DOCUMENT TEXT:
{text_content}
"""

    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a financial document analyzer. Extract UNIQUE currently active debt facilities and notes from 10-Q filings. List each facility only once, avoiding duplicates."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent extraction
        )
        
        facility_list = response.choices[0].message.content.strip()
        
        # Apply deduplication
        facility_list = deduplicate_facilities(facility_list)
        
        return facility_list
        
    except Exception as e:
        return f"Error extracting facilities: {str(e)}"

def generate_manual_gpt_prompt(facility_list_10q: str, facility_list_10k: str, html_content: str):
    """
    Second function: Generate a prompt for manual GPT analysis with the full HTML document.
    Returns plaintext prompt that can be used with GPT online.
    """
    prompt = f"""
Your task is to extract the full debt capital stack for this company using the HTML provided. You must:

- Include every facility listed above if active. Ignore if outdated or not a debt instrument.
- Add any additional **active** facilities not listed above.
- Do **not omit** any active:
  - Term loans
  - Revolving credit facilities
  - Senior unsecured notes (USD or foreign currency) — **each one must be listed separately**
  - Working capital loans
  - Receivables purchase agreements
  - Factoring or discounting agreements

- ❗️**NEVER put drawn or usage amount in the main line.**  
  Use the full committed facility amount in the main bullet.  
  If the full amount is not disclosed, leave it out of the main bullet and list usage in the bullets.

- Follow this strict output format for every debt instrument:

  $[Full Facility Amount] [Facility Type] @ [Interest Rate] mat. MM/YYYY (Lead Bank)  
    - Bullet 1  
    - Bullet 2

- If the full amount, interest rate, or lead bank is not disclosed:
  - Leave them out of the main bullet line.
  - Include a supporting bullet stating that the info is missing.

- CRITICAL: **List all instruments from earliest to latest maturity.**

- For receivables or factoring agreements, include even if not traditional debt, but label them clearly.

- If instruments are hedged, swapped, partially prepaid, or restructured, explain in bullets.

- Do not group or summarize. **List each active instrument individually with full details.**

Begin now using the full HTML filings.
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
    #facility_list = extract_facility_names_from_10q(soup, text_content, debug=debug)
    facility_list = ""
    
    # Step 3: Generate manual GPT prompt
    manual_prompt = generate_manual_gpt_prompt(facility_list, "", html_content) # Pass empty string for 10k_facility_list
    
    return facility_list, manual_prompt

def get_latest_10k_link_for_ticker(ticker: str) -> str:
    """
    Get the latest 10-K filing URL for a given ticker.
    """
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return ""
    
    try:
        submissions = edgar.get_submissions(cik=cik)
        recent_filings = submissions["filings"]["recent"]
        
        for i, form in enumerate(recent_filings["form"]):
            if form == "10-K":
                accession = recent_filings["accessionNumber"][i]
                primary_doc = recent_filings["primaryDocument"][i]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik):010d}/{accession.replace('-', '')}/{primary_doc}"
                return filing_url
        
        return ""
        
    except Exception as e:
        return ""

def download_and_parse_10k(ticker: str):
    """
    Download and parse the latest 10-K document for a given ticker.
    """
    link = get_latest_10k_link_for_ticker(ticker)
    
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

def extract_facility_names_from_10k(soup, text_content, debug=False):
    """
    First pass: Extract all currently active debt facility names from the 10-K document.
    Returns a list of facility names/types/currencies/maturities.
    """
    prompt = f"""
You are reviewing the latest 10-K for a company. Your task is to scan the full document (text and tables) and list every UNIQUE currently active debt facility or note mentioned.

For each UNIQUE facility or note, extract the following:
- Name or label (e.g., 2024 Term Loan, Revolving Credit Facility, Senior Notes)
- Currency
- Facility type (e.g., Term Loan, Revolver, Note, etc.)

CRITICAL INSTRUCTIONS:
- List each UNIQUE facility only ONCE, even if it appears multiple times in the document
- Do not duplicate the same facility with different numbering
- Focus on the actual facility name/type, not individual mentions
- For notes, group by maturity year and currency (e.g., "2025 Senior Unsecured Notes (USD)" not individual note numbers)
- For revolving facilities, list once per facility type
- For term loans, list once per facility

Format each facility as: [Facility Name] ([Currency], [Facility Type])

List one UNIQUE facility per line. Do not number them.

DOCUMENT TEXT:
{text_content}
"""

    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a financial document analyzer. Extract UNIQUE currently active debt facilities and notes from 10-K filings. List each facility only once, avoiding duplicates."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent extraction
        )
        
        facility_list = response.choices[0].message.content.strip()
        
        # Apply deduplication
        facility_list = deduplicate_facilities(facility_list)
        
        return facility_list
        
    except Exception as e:
        return f"Error extracting facilities: {str(e)}"

def run_10k_prompt_generation_pipeline(ticker: str, debug=False):
    """
    Run the complete pipeline to generate facility list and manual GPT prompt for 10-K.
    Returns the facility list and the manual GPT prompt.
    """
    # Step 1: Download and parse
    soup, text_content, html_content = download_and_parse_10k(ticker)
    
    if soup is None:
        return None, None
    
    # Step 2: Extract facility names
    #facility_list = extract_facility_names_from_10k(soup, text_content, debug=debug)
    facility_list = ""
    
    # Step 3: Generate manual GPT prompt
    manual_prompt = generate_manual_gpt_prompt("", facility_list, html_content) # Pass empty string for 10q_facility_list
    
    return facility_list, manual_prompt

if __name__ == "__main__":
    ticker = "CE"
    debug = False
    facility_list, manual_prompt = run_prompt_generation_pipeline(ticker, debug=debug)

    if manual_prompt:
        print(manual_prompt)
    else:
        print(f"❌ Failed to generate prompt for {ticker}")
