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
You are a financial analyst assistant. Your task is to extract the **complete and accurate debt capital stack** for this company using the **entire HTML filing(s)** provided. You must:

---

🎯 **INCLUSION RULES:**
- Include **every active** debt instrument, whether listed explicitly or mentioned in footnotes or tables.
- Do **NOT omit** any:
  - Term loans
  - Revolving credit facilities
  - Senior unsecured notes (USD or foreign currency) — **each one must be listed separately**
  - Working capital loans
  - Receivables purchase agreements
  - Factoring or discounting agreements

---

📏 **FORMATTING REQUIREMENTS:**
- For each instrument, use this strict format:

  $[Full Facility Amount] [Facility Type] @ [Interest Rate] mat. MM/YYYY (Lead Bank)  
    - Bullet 1  
    - Bullet 2

- If full facility amount, rate, or lead bank is not disclosed:
  - Omit it from the main bullet.
  - Include a bullet explaining which details are missing.

- ❗️NEVER put **drawn, outstanding, or usage amounts** in the main bullet — only the full committed amount.

---
🚫 CRITICAL RULE:
You MUST use the full committed facility amount in the main bullet.
Never substitute drawn, outstanding, or usage amounts.
If only usage is disclosed and the full commitment is not, omit the dollar amount and explain in a bullet.

---

📚 **SEARCH AND VERIFICATION REQUIREMENTS:**
- You MUST:
  1. Search for all term loans and revolving credit facilities
  2. Search for ALL senior unsecured notes — even if found in separate sections, footnotes, or tables
  3. Search for all working capital or AR facilities, receivables/factoring agreements, even if not labeled as traditional debt
  4. Capture hedging, swaps, restructurings, or covenant notes related to any facility

---

📅 **ORDERING:**
- List all instruments strictly from **earliest to latest maturity**.
- Do **not group or summarize** instruments. List each one individually.

---

🚨 **FAILSAFE CLAUSE:**
If you are **not 100% confident** that all relevant debt instruments — including **senior notes in buried sections** — have been found, **do not respond** yet. Search further.

---

Your response must be complete, structured, and ready for downstream formatting.
"""



    return prompt

def generate_debt_summary_prompt():
    """
    Generate a prompt for converting structured debt stack to concise one-line summaries.
    """
    prompt = """
Using the full HTML filings and the debt stack you generated, you will now generate a concise summary of the debt stack.

---

Your task is to convert the above debt stack into concise, one-line summary notes that highlight key deal terms. Follow these rules exactly:

---

🎯 **INCLUSION RULES:**
For each facility, include:
- Full amount (e.g., "$750M")
- Facility type (e.g., "Senior Notes", "Term Loan", "Revolver")
- Interest rate (e.g., "@ 6.375%" or "@ SOFR + 150 bps") if disclosed
- Maturity in "mat. M/YYYY" or "mat. YYYY" format
- Lead bank in parentheses (e.g., "(JPM)") if disclosed

---

📅 **MATURITY-BASED GROUPING RULE (for Senior Notes):**
- **Senior notes maturing in 2027 or earlier** → write them as individual lines  
- **Senior notes maturing in 2028 or later** → group them into a single line using this format:  
  > $[total] Senior Notes @ [rate range]% mat. [first year]–[last year]

  Example:  
  > $3.75B Senior Notes @ 6.35–6.95% mat. 2028–2033

  - You may approximate the **total amount** by summing the face values
  - Use the **lowest and highest interest rates** in the group as the range
  - Do **not** include banks, bullets, or partial commentary for the grouped notes

---

🔍 **OTHER RULES:**
- Do NOT include bullets, guarantee notes, hedging info, or accounting treatment
- Preserve original currencies (e.g., CHF, EUR) if applicable
- Do NOT mention missing data — omit silently
- One line per facility unless aggregation is explicitly allowed above

---

📌 **EXAMPLES:**

From:
$499M Senior Unsecured Notes @ 3.200% mat. 10/2026  
  - Guaranteed

To:
$499M Senior Notes @ 3.200% mat. 10/2026

From:
$999M, $1.0B, $750M Senior Notes @ 6.35–6.95% mat. 2028–2033  
  - Guaranteed  
  - Some hedged

To:
$2.75B Senior Notes @ 6.35–6.95% mat. 2028–2033

---

🎯 Output only the final summary lines — no bullets, no commentary."""

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
