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
MODEL_NAME = os.getenv("10Q_MODEL_NAME", "gpt-4.1-nano")
SECONDPASS_MODEL = os.getenv("SECONDPASS_MODEL", "gpt-4.1-nano")
llm_client = OpenAI(api_key=OPENAI_API_KEY)

def extract_debt_note_sections(soup, text_content):
    """
    Extract specific debt note sections and credit facility sections which contain the most accurate debt information.
    """
    debt_sections = []
    
    # Look for debt-related note sections AND credit facility sections
    note_patterns = [
        r'note\s*\d+[:\-\s]*debt',
        r'note\s*\d+[:\-\s]*long[–\-\s]?term\s*debt',
        r'note\s*\d+[:\-\s]*credit',
        r'note\s*\d+[:\-\s]*borrowings',
        r'\d+\.\s*debt',
        r'\d+\.\s*long[–\-\s]?term\s*debt',
        r'\d+\.\s*credit\s*facilities',
        r'credit\s*facilities',
        r'revolving\s*credit\s*facility',
        r'amended\s*and\s*restated\s*credit\s*agreement',
        r'term\s*loan\s*agreement'
    ]
    
    lines = text_content.split('\n')
    
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        
        # Check if this line is a debt note header
        for pattern in note_patterns:
            if re.search(pattern, line_lower):
                # Found a debt note section, extract content
                section_content = []
                section_content.append(line.strip())
                
                # Extract the next 200 lines or until we hit another note section
                j = i + 1
                while j < len(lines) and j < i + 200:
                    next_line = lines[j].strip()
                    
                    # Stop if we hit another major note section
                    if re.search(r'^(note\s*\d+|item\s*\d+|\d+\.\s*[A-Z])', next_line.lower()):
                        if j > i + 10:  # Only stop if we've captured substantial content
                            break
                    
                    section_content.append(next_line)
                    j += 1
                
                debt_sections.append({
                    'header': line.strip(),
                    'content': '\n'.join(section_content),
                    'start_line': i
                })
                break
    
    return debt_sections

def extract_debt_tables_focused(soup):
    """
    Extract debt tables with better preservation of structure using more detailed parsing.
    """
    debt_tables = []
    
    for table in soup.find_all("table"):
        # Get table as HTML first to preserve structure better
        table_html = str(table)
        
        # Also get text version with better separators
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                cell_text = td.get_text(strip=True)
                cells.append(cell_text)
            if cells:
                rows.append(' || '.join(cells))
        
        table_text = '\n'.join(rows)
        
        # Check if table contains debt-related keywords
        if re.search(r'\b(debt|note|credit|loan|maturity|interest|facility|principal|outstanding|borrowing|matur|due)\b', table_text, re.IGNORECASE):
            # Look for table caption/header more thoroughly
            caption = ""
            
            # Check previous elements for caption
            for elem in table.find_all_previous(['b', 'strong', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p']):
                elem_text = elem.get_text(strip=True)
                if len(elem_text) > 5 and len(elem_text) < 100:
                    if re.search(r'\b(debt|note|credit|loan|maturity|facility)\b', elem_text, re.IGNORECASE):
                        caption = elem_text
                        break
                # Don't look too far back
                if len(debt_tables) > 0 and elem_text:
                    break
            
            debt_tables.append({
                'caption': caption,
                'content': table_text,
                'html': table_html,
                'row_count': len(rows)
            })
    
    return debt_tables

def extract_debt_related_text_focused(text_content: str, debt_tables: list, middle_section: str, debug=False):
    """
    Use OpenAI to extract all debt-related text from the 10-Q document.
    """
    # Format debt tables for the prompt
    tables_text = ""
    if debt_tables:
        tables_text = "\n\nDEBT TABLES (SUPPORTING DATA):\n" + "="*50 + "\n"
        for i, table in enumerate(debt_tables, 1):
            tables_text += f"\nTable {i}: {table['caption']} ({table['row_count']} rows)\n"
            tables_text += f"{table['content']}\n"
            tables_text += "-" * 40 + "\n"

    # Format middle section for the prompt
    middle_section_text = f"\n\nMIDDLE 80% OF 10-Q DOCUMENT:\n" + "="*60 + "\n"
    middle_section_text += middle_section

    prompt = f"""
You are a financial document expert. Extract ONLY the actual debt facilities from this 10-Q filing.

CRITICAL INSTRUCTIONS:
1. Focus PRIMARILY on the MIDDLE 80% OF THE 10-Q DOCUMENT - this contains the most comprehensive debt information
2. Pay special attention to the "CREDIT FACILITIES SECTION" - this contains revolving credit facility and term loan agreement details
3. Use tables as supporting evidence to validate amounts, rates, and maturities
4. DO NOT make up or infer facilities that are not explicitly mentioned
5. If information is missing (like lead bank or interest rate), mark as "MISSING"
6. Be extremely precise with amounts and maturities - only use what's explicitly stated

FACILITIES TO LOOK FOR:
- **Revolving Credit Facilities** (look for revolving credit commitments, backup liquidity facilities)
- **Term Loans** (look for term loan agreements, quarterly payments, balloon payments)
- **Senior Notes** (look for notes payable, debt securities with fixed rates and maturity dates)
- **Credit Lines** (look for lines of credit, working capital facilities)
- **Credit Agreements** (look for amended and restated credit agreements)
- Any other debt instrument that is mentioned in the 10-Q

- **Senior Notes** are debt securities (usually have explicit fixed rates)

CRITICAL RULES:
- Look for revolving credit facility total amounts available
- Look for lead arrangers, lenders, or banking partners mentioned
- Look for interest rate terms (SOFR, LIBOR, fixed rates, basis points spreads)
- Look for maturity dates and payment terms
- Use EXACT amounts and rates from tables and narrative text
- CRITICAL: Distinguish between revolving credit facilities, term loans, and senior notes - they are different instrument types
- CRITICAL: Extract facilities in their original currency (CHF, EUR, USD, etc.)
- Use EXACT amounts from the source (do not round or estimate)
- Include currency exactly as stated in the source document
- Distinguish between different tranches and facilities clearly

OUTPUT FORMAT:
For each facility found, provide:
- Facility Type (Revolver, Term Loan, Senior Notes, etc.)
- Amount (with currency) - EXACT amount from source
- Interest Rate (or MISSING if not stated)
- Maturity Date (MM/YYYYor MISSING if not stated)
- Lead Bank/Lender (or MISSING if not stated)
- Source section where found (supporting text about the facility, put as much info as possible about the facility here)

SPECIAL FOCUS AREAS:
- Look for revolving credit facility commitments and available amounts, and specifcally max agreement amounts
- Look for term loan agreements and payment terms
- Look for lead banks, arrangers, or lender references
- Look for interest rate terms (SOFR, LIBOR, fixed rates, spreads)
- Look for maturity dates and payment schedules. Make sure you get these maturities correct, dont use any other dates like ones from other types of debt or the filing date.
- CRITICAL: Extract both term loans AND senior notes as separate facility types
- CRITICAL: Preserve original currency amounts (CHF, EUR, etc.) not just USD equivalents
- The more information you can get about the facility, the better.

{tables_text}

{middle_section_text}

Extract ONLY the facilities that are clearly documented in the above sections. Pay special attention to the Credit Facilities sections for the main USD revolving and term loan facilities.
"""

    try:
        if debug:
            print(f"🤖 Calling OpenAI API with model: {MODEL_NAME}")
            print(f"📄 Input text length: {len(text_content):,} characters")
        
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Extract ALL debt-related information from 10-Q filings. Be comprehensive and include complete sections, not just individual sentences."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent extraction
        )
        
        extracted_text = response.choices[0].message.content.strip()
        
        if debug:
            print(f"✅ OpenAI API call successful")
        
        return extracted_text
        
    except Exception as e:
        if debug:
            print(f"❌ OpenAI API call failed: {e}")
        return f"Error extracting debt-related text: {str(e)}"


def enhance_debt_extraction_with_context(initial_extraction: str, additional_context: str, debug=False):
    """
    Enhance the initial debt extraction with additional context from the middle 70% of the 10-Q.
    This function asks the LLM to add more supporting info for facilities found and identify any missed facilities.
    """
    prompt = f"""
You are a financial document expert. I have an initial debt extraction from a 10-Q filing, and I want you to enhance it with additional context from the middle section of the document.

INITIAL DEBT EXTRACTION:
{initial_extraction}

ADDITIONAL CONTEXT (Middle 70% of 10-Q):
{additional_context}

YOUR TASK:
1. **Review the initial extraction** - identify all debt facilities that were found
2. **Add supporting information** - for each facility found, add any additional details from the additional context (interest rates, maturity dates, lead banks, covenants, etc.)
3. **Find missed facilities** - identify any debt facilities that were missed in the initial extraction but are mentioned in the additional context
4. **Enhance existing facilities** - add any missing details like interest rates, maturity dates, or lead banks that are mentioned in the additional context

CRITICAL INSTRUCTIONS:
- DO NOT remove any facilities from the initial extraction
- DO NOT change facility amounts unless you find explicit evidence they are wrong
- ONLY add information that is explicitly stated in the additional context
- If you find new facilities, add them with the same format as the existing ones
- If you find additional details for existing facilities, add them as supporting information
- Be extremely precise - only use information that is explicitly stated

OUTPUT FORMAT:
- Keep the same structure as the initial extraction
- Add supporting details under each facility
- Add any new facilities you find
- Use the same format for new facilities as existing ones

Return the enhanced debt extraction with all additional information found:
"""

    try:
        if debug:
            print(f"🤖 Calling OpenAI API to enhance debt extraction with additional context")
            print(f"📄 Initial extraction length: {len(initial_extraction):,} characters")
            print(f"📄 Additional context length: {len(additional_context):,} characters")
        
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Enhance debt extractions with additional context while preserving all existing information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent enhancement
        )
        
        enhanced_text = response.choices[0].message.content.strip()
        
        if debug:
            print(f"✅ Debt extraction enhancement successful")
        
        return enhanced_text
        
    except Exception as e:
        if debug:
            print(f"❌ Debt extraction enhancement failed: {e}")
        return f"Error enhancing debt extraction: {str(e)}"


def extract_credit_facilities_from_liquidity(text_content: str):
    """
    Extract the specific Credit Facilities section from the Liquidity section,
    which contains details about the revolving credit facility and credit agreements.
    """
    # Look for the Credit Facilities section within the liquidity section
    credit_facilities_section = ""
    
    # Find the Credit Facilities header
    credit_patterns = [
        "Credit Facilities",
        "Revolving Credit Facility",
        "Credit Agreement", 
        "Amended and Restated Credit Agreement"
    ]
    
    for pattern in credit_patterns:
        start_pos = text_content.find(pattern)
        if start_pos != -1:
            # Take the next 5000 characters to capture full facility details
            end_pos = min(start_pos + 5000, len(text_content))
            credit_facilities_section = text_content[start_pos:end_pos].strip()
            break
    
    return credit_facilities_section

def extract_liquidity_section(text_content: str):
    """
    Extract the Liquidity and Capital Resources section by finding the header and taking the next 20,000 characters.
    """
    # Look for liquidity section headers
    liquidity_headers = [
        "LIQUIDITY AND CAPITAL RESOURCES",
        "Liquidity and Capital Resources", 
        "Liquidity and Capital",
        "Capital Resources",
        "Financial Condition",
        "Cash Flows"
    ]
    
    liquidity_section = ""
    
    # Find the header and extract 20,000 characters after it
    for header in liquidity_headers:
        pos = text_content.find(header)
        if pos != -1:
            # Take 20,000 characters starting from the header
            start_pos = pos
            end_pos = min(start_pos + 20000, len(text_content))
            liquidity_section = text_content[start_pos:end_pos].strip()
            break
    
    return liquidity_section

def convert_debt_to_laymans_terms(complete_debt_info: str, debug=False):
    """
    Convert the complete debt information (including liquidity section) to layman's terms with specific formatting.
    Organizes facilities by maturity date and uses the specified format.
    """
    prompt = f"""
I'm going to give you their "Debt" and "Liquidity and Capital Resources" section from their latest 10-Q, along with other important information. I want you to convert these sections to layman's terms, and specifically focus on their debt capital stack. I want them organized from maturing the earliest to maturing the latest, and the format for the credit facilities should be:
facility @ (interest rate) mat. mm/yyyy (Lead Bank)
and then any supporting bullet points and specifics in bullets underneath it. make sure the full facility is at the top, and then supporting bullets like what they drew. here's an example: 
650M Term Loan @ SOFR + 137-187 bps mat. 3/2030 (BofA) 

Make sure you get the maturity dates correct, and if they are not stated, you can add a supporting bullet point under it like the usage and "Check credit agreement for missing information".

This is the most important part of the process, so make sure you do it correctly:
Critical: ONLY USE FULL FACILITY AMOUNTS FOR THE MAIN NOTES. if any information if missing, you can add a supporting bullet point under it like the usage and "Check credit agreement for missing information".
Critical: Dont give any fluff or extra information or extra words (such as "heres the debt information"), just the debt information and supporting notes.
Critical: Make sure you include ALL facilities, and dont miss any.

Heres an example of some good output:
$300M Term Loan @ MISSING - CHECK CREDIT AGREEMENT mat. 12/2026 (MISSING - CHECK CREDIT AGREEMENT)
$900M Revolver @ MISSING - CHECK CREDIT AGREEMENT mat. MISSING - CHECK CREDIT AGREEMENT (MISSING - CHECK CREDIT AGREEMENT)  
297M CHF Sr. Notes @ 1.01% mat. 12/2029 
300M CHF Sr. Notes @ 0.88% mat. 12/2031 
150M EUR Sr. Notes @ 1.03% mat. 12/2031
50M CHF Sr. Notes @ 2.56% mat. 4/2034
$100M Term Loan @ 4.5% mat. 12/2026 (BofA)

Its really important that this information is correct, otherwise its useless- make sure you think through it, take your time, and make sure you get it right. Triple check all the information before you return it.
Make sure each facility is unique and is an actual facility, not stuff like total long term debt or short term debt.
---------------------------------------------------------------------------

COMPLETE DEBT AND LIQUIDITY INFORMATION:
{complete_debt_info}
"""

    try:
        if debug:
            print(f"Calling OpenAI API to convert debt info to layman's terms")
        
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a financial analyst who converts complex debt information into clear, layman's terms. Organize facilities by maturity date and use the exact format specified."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1  # Low temperature for consistent formatting
        )
        
        laymans_text = response.choices[0].message.content.strip()
        
        if debug:
            print(f"✅ Layman's terms conversion successful")
        
        return laymans_text
        
    except Exception as e:
        if debug:
            print(f"❌ Layman's terms conversion failed: {e}")
        return f"Error converting to layman's terms: {str(e)}"

def verify_and_correct_debt_info(laymans_debt_info: str, complete_debt_info: str, debug=False):
    """
    Conservative verification pass to organize by maturity and flag usage amounts.
    Uses SECONDPASS_MODEL to perform minimal corrections while preserving all facilities.
    """
    prompt = f"""
You are a conservative financial verification expert. Your job is to make MINIMAL corrections to the debt analysis while preserving ALL facilities.

CONSERVATIVE VERIFICATION TASKS (ONLY DO THESE):
1. Organize ALL facilities by maturity date (earliest to latest)
2. If a facility amount appears to be USAGE rather than full facility size, add a bullet point: "THIS IS USAGE, CHECK CREDIT AGREEMENT FOR FULL FACILITY AMOUNT". Then for the main bullet point, replace the usage amount with the full facility amount if its in the source data, otherwise with "max amt not stated".
3. Remove interest rates that are not explicitly stated in the source data

CRITICAL RULES:
- PRESERVE ALL FACILITIES - do not drop any facility that appears in the input
- KEEP ALL AMOUNTS - only add warning bullets if amounts appear to be usage
- ONLY remove interest rates if they are clearly not in the source data
- Do NOT change facility names, lead banks, or other details
- Do NOT add new facilities or change existing facility information
- ONLY organize by maturity and add usage warnings

USAGE vs FACILITY DETECTION:
- If source says "borrowed $X" or "outstanding $X" for that amount, add usage warning
- If source says "facility of $X" or "up to $X", keep the amount as-is
- When in doubt, keep the amount and do NOT add usage warning

INTEREST RATE VERIFICATION:
- Only remove interest rates if they are clearly NOT mentioned in source data
- If source mentions the rate in any form, keep it
- When in doubt, keep the interest rate

ORGANIZATION:
- Sort by maturity date from earliest to latest
- Keep exact same format and structure
- Preserve all bullet points and details

LAYMAN'S TERMS DEBT ANALYSIS TO VERIFY:
{laymans_debt_info}

SOURCE DATA FOR VERIFICATION:
{complete_debt_info}

INSTRUCTIONS:
1. Keep ALL facilities from the input analysis
2. Only organize by maturity date
3. Only add usage warnings where clearly warranted
4. Only remove interest rates if clearly not in source
5. Preserve everything else exactly as-is
6. Return only the debt information, no other filler text such as "heres the debt information" or "heres the debt information in layman's terms" or anything like that.

Return the conservatively verified debt analysis organized by maturity:
"""

    try:
        if debug:
            print(f"🔍 Calling conservative verification pass with {SECONDPASS_MODEL}")
        
        response = llm_client.chat.completions.create(
            model=SECONDPASS_MODEL,
            messages=[
                {"role": "system", "content": "You are a conservative financial verification expert. Make MINIMAL changes - only organize by maturity and flag clear usage amounts. Preserve ALL facilities and information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3  # Low temperature for accuracy
        )
        
        verified_text = response.choices[0].message.content.strip()
        
        if debug:
            print(f"✅ Conservative verification pass completed")
        
        return verified_text
        
    except Exception as e:
        if debug:
            print(f"❌ Verification pass failed: {e}")
        return f"Error in verification pass: {str(e)}"

def get_latest_10q_link_for_ticker(ticker: str) -> str:
    """
    Get the latest 10-Q filing URL for a given ticker.
    This is the same function from get_10q.py
    """
    cik = get_cik_for_ticker(ticker)
    if not cik:
        print(f"No CIK found for ticker {ticker}")
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
        
        print(f"No 10-Q filing found for ticker {ticker}")
        return ""
        
    except Exception as e:
        print(f"Error getting 10-Q link for {ticker}: {e}")
        return ""

def download_and_parse_10q(ticker: str):
    """
    Download and parse the latest 10-Q document for a given ticker.
    This combines steps 1 and 2 from the original flow.
    """
    print(f"🔍 Step 1: Getting 10-Q link for ticker {ticker}")
    link = get_latest_10q_link_for_ticker(ticker)
    
    if not link:
        print(f"❌ No 10-Q link found for ticker {ticker}")
        return None, None
    
    print(f"✅ Found 10-Q link: {link}")
    
    print(f"🔍 Step 2: Downloading and parsing 10-Q document")
    try:
        response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        print(f"✅ Successfully downloaded and parsed 10-Q document")
        print(f"📄 Document size: {len(response.content)} bytes")
        
        return soup, link
        
    except Exception as e:
        print(f"❌ Error downloading/parsing 10-Q for {ticker}: {e}")
        return None, None


def run_debt_extraction_pipeline(ticker: str, debug=False):
    """
    Run the complete debt extraction pipeline for a given ticker.
    Returns the final layman's terms debt analysis as a list of strings.
    """
    print(f"🔍 Starting debt extraction pipeline for {ticker}")
    
    # Step 1 & 2: Download and parse
    soup, link = download_and_parse_10q(ticker)
    
    if soup is None:
        print(f"❌ Failed to download and parse 10-Q document for {ticker}")
        return []
    
    # Step 3: Extract debt-related text using focused approach
    print(f"🔍 Step 3: Extracting debt information with tables and middle 80% of 10-Q")
    
    # Get text content
    text_content = soup.get_text(separator="\n", strip=True)
    
    # Extract debt tables as supporting data
    debt_tables = extract_debt_tables_focused(soup)
    print(f"📊 Found {len(debt_tables)} debt-related tables")
    
    # Get the middle 80% of the document for comprehensive debt information (FIRST PASS)
    total_lines = len(text_content.split('\n'))
    start_line_80 = int(total_lines * 0.10)  # Start at 10%
    end_line_80 = int(total_lines * 0.90)    # End at 90%
    
    lines = text_content.split('\n')
    middle_section_80 = '\n'.join(lines[start_line_80:end_line_80])
    
    print(f"📄 Using middle 80% of document for first pass (lines {start_line_80} to {end_line_80} of {total_lines})")
    
    # Extract debt information using tables + middle 80% of 10-Q (FIRST PASS)
    extracted_debt_text = extract_debt_related_text_focused(text_content, debt_tables, middle_section_80, debug=debug)
    
    # Step 4: Enhance the initial extraction with middle 60% of 10-Q (SECOND PASS)
    print(f"\n🔍 Step 4: Enhancing debt extraction with middle 60% of 10-Q")
    
    # Get the middle 60% of the document for second pass
    start_line_60 = int(total_lines * 0.20)  # Start at 20%
    end_line_60 = int(total_lines * 0.80)    # End at 80%
    
    middle_section_60 = '\n'.join(lines[start_line_60:end_line_60])
    print(f"📄 Using middle 60% of document for second pass (lines {start_line_60} to {end_line_60} of {total_lines})")
    
    # Enhance the initial extraction with middle 60% context
    enhanced_debt_info = enhance_debt_extraction_with_context(extracted_debt_text, middle_section_60, debug=debug)
    
    # Convert enhanced debt info to layman's terms
    laymans_debt_text = convert_debt_to_laymans_terms(enhanced_debt_info, debug=debug)
    
    # Step 5: Conservative verification pass - only organize by maturity and flag usage amounts
    print(f"\n🔍 Step 5: Running conservative verification pass")
    verified_debt_text = verify_and_correct_debt_info(laymans_debt_text, enhanced_debt_info, debug=debug)
    
    # Convert the verified text to a list of lines, filtering out empty lines
    debt_lines = [line.strip() for line in verified_debt_text.split('\n') if line.strip()]
    
    print(f"✅ Debt extraction pipeline completed for {ticker}")
    return debt_lines


if __name__ == "__main__":
    ticker = "CE"
    debug = False
    debt_lines = run_debt_extraction_pipeline(ticker, debug=debug)

    print(f"\n📋 Final debt analysis for {ticker}:")
    for line in debt_lines:
        print(f"   {line}")
