from sec_edgar_api.EdgarClient import EdgarClient
from ticker_utils import get_cik_for_ticker
import requests
import os
from bs4 import BeautifulSoup
import re
from openai import OpenAI
from dotenv import load_dotenv
import collections
import json

load_dotenv()

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("10Q_MODEL_NAME", "gpt-4.1-nano")
llm_client = OpenAI(api_key=OPENAI_API_KEY)
edgar = EdgarClient(user_agent="Company Screener Tool contact@companyscreenertool.com")

def is_section_header(line):
    """Identify section headers in 10-Q documents"""
    norm = line.strip()
    if len(norm) < 5 or len(norm) > 100:
        return False
    # Starts with number and period or parenthesis (e.g., '6. ', '(6) ')
    if re.match(r'^\(?\d+(\.\d+)*\)?[\s\-–\.]*[A-Za-z]', norm):
        return True
    # Title case with more than 2 words (e.g., 'Liquidity and Capital Resources')
    if norm.istitle() and len(norm.split()) > 2:
        return True
    # All uppercase
    if norm.isupper():
        return True
    # Facility-specific headers (e.g., "Revolving Credit Facility", "Senior Notes")
    facility_keywords = ["revolving", "credit", "facility", "senior", "notes", "debt", "loan", "agreement"]
    if any(keyword in norm.lower() for keyword in facility_keywords) and len(norm.split()) >= 2:
        return True
    # Headers with common patterns like "==== Header ===="
    if re.match(r'^=+\s*[A-Za-z]', norm):
        return True
    return False

# Keywords for debt-related content extraction (GENERIC - works for any company)
EXPANDED_KEYWORDS = [
    "debt", "credit agreement", "credit facilities", "notes payable", "indebtedness", "long-term debt",
    "term loan", "term facility", "revolving credit facility", "note", "exhibit", "schedule", "obligations",
    "borrowings", "secured", "unsecured", "guarantee", "indenture", "senior notes", "convertible", "loan agreement",
    "amendment", "table", "summary", "schedule of long-term debt", "liquidity", "capital resources", "financial condition",
    "cash flows", "supplemental", "supplemental information", "commitment", "outstanding", "principal", "interest",
    "sofr", "libor", "basis points", "bps", "million", "billion", "facility size", "commitment amount",
    "term loan facility", "revolving credit facility", "revolver", "senior notes due", "notes due",
    "administrative agent", "trustee", "maturity date", "interest rate", "aggregate principal"
]
NOTE_REGEX = re.compile(r'(note|exhibit|schedule)\s*\d+[A-Za-z]*', re.IGNORECASE)

def extract_tables_with_captions(soup):
    """Extract tables and their captions from 10-Q"""
    tables = []
    for table in soup.find_all('table'):
        caption = None
        prev = table.find_previous(['b', 'strong', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if prev:
            caption = prev.get_text(strip=True)
        else:
            prev_text = table.find_previous(string=True)
            if prev_text:
                caption = prev_text.strip()
        tables.append((caption, str(table)))
    return tables

def find_note_references(text):
    """Find cross-references like 'see Note 7'"""
    return set(re.findall(r'Note\s*\d+[A-Za-z]*', text, re.IGNORECASE))

def extract_all_relevant_sections(soup, min_len=200, max_len=50000, debug=False, debug_log=None):
    """
    Extract all relevant sections from 10-Q for debt facility analysis
    """
    text = soup.get_text(separator="\n", strip=True)
    lines = text.splitlines()
    section_headers = []
    for i, line in enumerate(lines):
        if i < len(lines) * 0.1:
            continue
        if is_section_header(line):
            section_headers.append((i, line.strip()))
    extracted = collections.OrderedDict()
    always_include = ["liquidity", "capital resources", "management's discussion", "debt", "credit", "facility", "note"]
    for i, (idx, header) in enumerate(section_headers):
        next_idx = section_headers[i+1][0] if i+1 < len(section_headers) else len(lines)
        section_text = "\n".join(lines[idx+1:next_idx])
        # Always include full sections with debt/credit/facility keywords in header
        if any(x in header.lower() for x in always_include):
            extracted[header] = section_text[:max_len]
            continue
        # If any keyword is in the section body, include the whole section
        if any(kw in section_text.lower() for kw in EXPANDED_KEYWORDS):
            extracted[header] = section_text[:max_len]
    # Also scan all paragraphs for facility keywords
    for para in text.split("\n\n"):
        if any(kw in para.lower() for kw in EXPANDED_KEYWORDS):
            key = f"PARAGRAPH_MATCH_{hash(para) % 1000000}"
            if key not in extracted:
                extracted[key] = para[:max_len]
    
    # Scan for detailed debt sections that might be missed (GENERIC)
    debt_section_keywords = [
        "Senior Secured Credit Facility", "Term Loan Facility", "Revolving Credit Facility",
        "Senior Notes due", "issued $", "million aggregate principal", "pursuant to",
        "administrative agent", "maturity date", "interest rate", "basis points", "SOFR", "LIBOR", 
        "indenture", "guarantors", "trustee", "Term Loan", "Revolver", "Revolving", 
        "Senior Notes", "Notes due", "Credit Agreement", "credit facility", "loan agreement"
    ]
    
    for para in text.split("\n\n"):
        if any(kw in para for kw in debt_section_keywords):
            key = f"DEBT_DETAIL_{hash(para) % 1000000}"
            if key not in extracted:
                extracted[key] = para[:max_len]
    
    # Table and cross-ref extraction
    tables = extract_tables_with_captions(soup)
    for caption, table_html in tables:
        if caption:
            for kw in EXPANDED_KEYWORDS:
                if kw in caption.lower() or NOTE_REGEX.search(caption):
                    key = f"TABLE: {caption}"
                    extracted[key] = table_html
                    break
    referenced_notes = set()
    for content in extracted.values():
        referenced_notes.update(find_note_references(content))
    for note in referenced_notes:
        for idx, heading in section_headers:
            if note.lower() in heading.lower():
                next_idx = None
                for j, (idx2, heading2) in enumerate(section_headers):
                    if idx2 > idx:
                        next_idx = idx2
                        break
                if next_idx is None:
                    next_idx = len(lines)
                content = "\n".join(lines[idx+1:next_idx])
                if len(content) >= min_len:
                    key = f"{heading} (cross-ref)"
                    extracted[key] = content[:max_len]
    if debug and debug_log is not None:
        debug_log.append(f"Extracted {len(extracted)} relevant sections/tables/notes.")
    return extracted

def get_latest_10q_link_for_ticker(ticker: str) -> str:
    """Get the latest 10-Q filing URL for a given ticker"""
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return ""
    submissions = edgar.get_submissions(cik=cik)
    recent_filings = submissions["filings"]["recent"]
    for i, form in enumerate(recent_filings["form"]):
        if form == "10-Q":
            accession = recent_filings["accessionNumber"][i]
            primary_doc = recent_filings["primaryDocument"][i]
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik):010d}/{accession.replace('-', '')}/{primary_doc}"
            return filing_url
    return ""

def extract_facilities_direct(extracted_sections, llm_client, model_name, debug=False):
    """
    Direct extraction of debt facilities using comprehensive LLM prompt
    """
    # Use raw 10-Q text for comprehensive extraction
    raw_text = extracted_sections.get("RAW_10Q_TEXT", "")
    if not raw_text:
        full_text = "\n\n".join([f"=== {header} ===\n{content}" for header, content in extracted_sections.items()])
    else:
        full_text = raw_text
    prompt = f"""
You are a financial document expert. Extract ONLY CURRENT and ACTIVE debt facilities from this 10-Q filing.

CRITICAL: Focus ONLY on CURRENT debt facilities that are still active and in force. IGNORE:
- Outdated/amended facilities that have been replaced
- Royalties, milestone payments, or non-debt obligations
- Litigation settlements or royalty agreements
- Historical debt that has been refinanced

SCAN FOR CURRENT DEBT FACILITIES ONLY:
1. Active Term Loans: Current term loan facilities still in force
2. Active Revolving Credit: Current revolving credit facilities still in force
3. Current Debt Securities: Senior notes, bonds that are still outstanding

CRITICAL RULES FOR CURRENT FACILITIES:
- ONLY extract facilities that are CURRENTLY ACTIVE and in force
- IGNORE facilities that have been "amended and restated" or replaced
- IGNORE historical debt that has been refinanced
- IGNORE royalties, milestone payments, or non-debt obligations
- IGNORE litigation settlements or royalty agreements
- IGNORE facilities that are "replaced" or "superseded" by newer agreements
- IGNORE facilities with phrases like "original agreement from 2021, now replaced"
- IGNORE facilities that are "amended and restated" unless this IS the current version
- ONLY include the MOST RECENT version of any facility

CRITICAL RULES FOR AMOUNTS:
- NEVER use debt table amounts (e.g., "Long-term debt consisted of $X")
- NEVER use outstanding/borrowed amounts (e.g., "outstanding $X", "borrowed $X")
- ONLY use MAXIMUM facility sizes: "facility of $X", "up to $X", "commitment of $X", "aggregate principal amount of $X"
- If you only see debt table or outstanding amounts, use "MISSING" for max_amount

CRITICAL RULES FOR DETAILS:
- Extract SPECIFIC interest rates: "SOFR + 500 bps", "SOFR + 5.0%", "5.00%"
- Extract SPECIFIC maturity dates: "May 2030", "December 2026"
- Extract SPECIFIC bank names from the same paragraph as the facility
- Look for interest rate ranges like "SOFR + 112.5 to 162.5 bps"
- Look for specific banks like "Bank of America", "BofA", "JPMorgan"
- If bank/rate/maturity not mentioned for that specific facility, use "MISSING"
- CRITICAL: For source_text, include COMPLETE paragraphs/sections containing ALL information used

LOOK FOR THESE PATTERNS FOR CURRENT FACILITIES:
- "entered into a $X credit facility" (if current)
- "providing the Company with a $X term loan" (if current)
- "credit agreement providing $X term loan" (if current)
- "revolving credit facility of $X" (if current)
- "issued $X aggregate principal amount" (for current notes)
- "SOFR + X to Y bps" (interest rate ranges)
- "Bank of America" or "BofA" (specific banks)
- "JPMorgan" or "Morgan Stanley" (specific banks)
- "matures on [date]" or "due [date]" (maturity dates)

AVOID THESE (outdated or non-debt):
- "amended and restated" facilities (unless this is the current version)
- "previously entered into" facilities
- "original agreement from 2021, now replaced"
- "replaced by" or "superseded by" facilities
- Royalty payments or milestone payments
- Litigation settlements
- Historical debt that has been refinanced
- ANY facility that mentions being "replaced" or "superseded"

EXAMPLES:
✅ GOOD: "entered into a $250M term loan facility" (if current) → Amount: 250000000
✅ GOOD: "issued $500M aggregate principal amount of 4.375% Senior Notes" (if current) → Amount: 500000000
✅ GOOD: "SOFR + 500 bps" → Interest Rate: SOFR + 500 bps
❌ BAD: "previously entered into" → Don't include (historical)
❌ BAD: "amended and restated" → Don't include (unless this is current version)
❌ BAD: "original agreement from 2021, now replaced" → Don't include (outdated)
❌ BAD: "replaced by" or "superseded by" → Don't include (outdated)
❌ BAD: "royalty payments" → Don't include (not debt)
❌ BAD: "milestone payments" → Don't include (not debt)

SOURCE TEXT REQUIREMENTS:
- Include COMPLETE paragraphs or sections that contain ALL the information you extracted
- Source text should be comprehensive enough to verify every piece of information (amount, rate, maturity, bank)
- Include surrounding context that provides additional details about the facility/note
- If information comes from multiple paragraphs, combine them in the source_text
- Make source text detailed enough that someone could verify your extraction from it alone

Return ONLY valid JSON:
{{
  "facilities": [
    {{
      "name": "exact facility name",
      "max_amount": "maximum facility size or MISSING",
      "currency": "USD",
      "interest_rate": "specific rate or MISSING",
      "maturity": "specific maturity or MISSING",
      "lead_bank": "specific bank or MISSING",
      "source_text": "COMPLETE source text containing ALL information used for this facility (amount, rate, maturity, bank, etc.) - include full paragraphs/sections"
    }}
  ],
  "notes": [
    {{
      "name": "exact note name",
      "max_amount": "note amount or MISSING",
      "currency": "USD",
      "interest_rate": "specific rate or MISSING",
      "maturity": "specific maturity or MISSING",
      "lead_bank": "trustee/agent or MISSING",
      "source_text": "COMPLETE source text containing ALL information used for this note (amount, rate, maturity, trustee, etc.) - include full paragraphs/sections"
    }}
  ]
}}

Document text:
{full_text}
"""
    
    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Extract ALL debt facilities and securities accurately. Focus on maximum facility sizes, not current usage."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', raw_response)
        if json_match:
            result = json.loads(json_match.group(0))
            
            # Clean up and validate results
            if result.get("facilities"):
                result["facilities"] = clean_facilities(result["facilities"], debug)
            if result.get("notes"):
                result["notes"] = clean_notes(result["notes"], debug)
            
            return result
        else:
            return {"facilities": [], "notes": [], "error": "No JSON found in response"}
        
    except Exception as e:
        return {"facilities": [], "notes": [], "error": str(e)}

def clean_facilities(facilities, debug=False):
    """Clean and validate facility data - focus on core debt facilities only"""
    cleaned = []
    seen_names = set()
    
    # Filter out non-core financial instruments
    exclude_keywords = [
        "swap", "derivative", "hedge", "mortgage", "guarantee", 
        "letter of credit", "foreign", "subsidiary", "schaublin", "swiss tool"
    ]
    
    for facility in facilities:
        name = facility.get("name", "").strip()
        if not name:
            continue
            
        # Skip non-core financial instruments
        if any(keyword in name.lower() for keyword in exclude_keywords):
            continue
            
        # Skip duplicates
        if name.lower() in seen_names:
            continue
            
        seen_names.add(name.lower())
        
        # Validate amount is not from debt table
        source_text = facility.get("source_text", "").lower()
        amount = facility.get("max_amount", "")
        
        # Improved amount validation - but allow facility descriptions
        if amount != "MISSING" and any(indicator in source_text for indicator in [
            "long-term debt consisted", "debt as of", "(in thousands)", "balance sheet",
            "outstanding under", "borrowed under"
        ]):
            # Exception: Allow if it's describing facility establishment
            if not any(good_indicator in source_text for good_indicator in [
                "entered into", "providing", "credit agreement", "facility of", "amended to"
            ]):
                facility["max_amount"] = "MISSING"
        
        cleaned.append(facility)
    
    return cleaned

def clean_notes(notes, debug=False):
    """Clean and validate notes data - remove duplicates and invalid entries"""
    cleaned = []
    seen_notes = set()
    
    for note in notes:
        name = note.get("name", "").strip()
        amount = note.get("max_amount", "")
        maturity = note.get("maturity", "")
        
        if not name:
            continue
        
        # Create unique identifier for note (name + amount + maturity)
        note_id = f"{name.lower()}_{amount}_{maturity}".replace(" ", "_")
        
        # Skip duplicates based on unique identifier
        if note_id in seen_notes:
            continue
            
        seen_notes.add(note_id)
        cleaned.append(note)
    
    return cleaned

def simple_validation(result, debug=False):
    """Simple validation with proper categorization of facilities vs notes"""
    facilities = result.get("facilities", [])
    notes = result.get("notes", [])
    
    # Properly categorize facilities vs notes
    corrected_facilities = []
    corrected_notes = []
    
    # Process facilities - move notes to notes section
    for facility in facilities:
        name = facility.get("name", "").lower()
        if any(note_keyword in name for note_keyword in ["notes", "bond", "debenture"]):
            corrected_notes.append(facility)
        else:
            corrected_facilities.append(facility)
    
    # Add existing notes
    corrected_notes.extend(notes)
    
    # Clean and validate
    corrected_facilities = clean_facilities(corrected_facilities, debug)
    corrected_notes = clean_notes(corrected_notes, debug)
    
    return {
        "facilities": corrected_facilities,
        "notes": corrected_notes
    }

def extract_final_facilities(ticker, output_json_file="final_facilities_json.json"):
    """
    PRODUCTION FUNCTION: Extract debt facilities from 10-Q filings
    """
    link = get_latest_10q_link_for_ticker(ticker)
    if not link:
        return {"error": "No 10-Q found"}
    
    response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    
    # Get the raw 10-Q text first
    raw_text = soup.get_text(separator="\n", strip=True)
    
    # Also extract sections for enhanced context
    extracted = extract_all_relevant_sections(soup, debug=False)
    extracted["RAW_10Q_TEXT"] = raw_text
    
    # Use direct extraction with comprehensive prompts
    result = extract_facilities_direct(extracted, llm_client, MODEL_NAME, debug=False)
    
    if result and not result.get("error"):
        # Simple validation and categorization
        result = simple_validation(result, debug=False)
    
        # Save final result
        with open(output_json_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        
        # Save raw text for summary function
        with open("raw_10q_text.txt", "w", encoding="utf-8") as f:
            f.write(raw_text)
        
        return result, raw_text
    else:
        error_msg = result.get("error", "Unknown error") if result else "No result returned"
        return {"error": error_msg}, ""

def create_debt_stack_summary(json_file_path="final_facilities_json.json", raw_text="", debug=False):
    """
    Use LLM to create a proper debt stack summary from the JSON output
    This handles deduplication, max amounts, and converts to layman's terms
    """
    import json
    
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return f"❌ File {json_file_path} not found. Run extraction first."
    except json.JSONDecodeError:
        return f"❌ Invalid JSON in {json_file_path}"
    
    facilities = data.get('facilities', [])
    notes = data.get('notes', [])
    
    if not facilities and not notes:
        return "❌ No facilities or notes found in the JSON file."
    
    # Prepare the data for LLM processing
    json_data = json.dumps(data, indent=2)
    
    prompt = f"""
You are a financial analyst creating a debt capital stack summary. I have extracted debt facilities and notes from a 10-Q filing, but the data may have duplicates, missing information, or inaccuracies.

EXTRACTED DATA:
{json_data}

RAW 10-Q TEXT (for additional context and verification):
{raw_text[:5000] if raw_text else "Raw 10-Q text not available"}

TASK: Create a comprehensive debt capital stack summary with the following requirements:

IMPORTANT: You MUST filter out outdated facilities. If you see a facility that mentions being "prior to" another agreement, "before" another agreement, or has been "amended and restated" by a newer agreement, DO NOT include it in your summary. Only include CURRENT and ACTIVE facilities.

1. **CURRENT FACILITIES ONLY**: Focus ONLY on CURRENT and ACTIVE debt facilities
2. **DEDUPLICATION**: Remove duplicate facilities/notes and combine similar ones
3. **MAX AMOUNTS**: Use the maximum facility size, not current usage
4. **LAYMAN'S TERMS**: Convert complex financial language to clear, simple terms
5. **ORGANIZATION**: Order by maturity date (earliest to latest)
6. **FORMAT**: Use this exact format for each facility/note:
   [Amount] [Type] @ [Interest Rate] mat. [MM/YYYY] ([Lead Bank])
   - [Supporting details in bullets]

7. **CRITICAL RULES FOR CURRENT FACILITIES**:
   - ONLY include facilities that are CURRENTLY ACTIVE and in force
   - IGNORE facilities that have been "amended and restated" or replaced
   - IGNORE historical debt that has been refinanced
   - IGNORE royalties, milestone payments, or non-debt obligations
   - IGNORE litigation settlements or royalty agreements
   - IGNORE facilities that are "replaced" or "superseded" by newer agreements
   - IGNORE facilities with phrases like "original agreement from 2021, now replaced"
   - IGNORE facilities with phrases like "prior to A&R agreement" or "before A&R"
   - IGNORE facilities that mention being "amended and restated" by newer agreements
   - If you see multiple versions of the same facility, use ONLY the CURRENT version
   - If a facility mentions being "replaced" or "superseded", DO NOT include it
   - If a facility name contains "prior to" or "before", DO NOT include it
   - ONLY include the MOST RECENT version of any facility

8. **INTELLIGENCE**: 
   - If you see multiple entries for the same facility, use ONLY the CURRENT one
   - IGNORE any facility that mentions being "prior to" or "before" another agreement
   - IGNORE any facility that has been "amended and restated" by a newer agreement
   - If amounts are missing, use "MISSING" but try to infer from context
   - If interest rates are missing, use "MISSING" but try to infer from similar facilities
   - If lead banks are missing, use "MISSING" but try to infer from context
   - Add bullet points for important details like amortization, covenants, etc.

9. **EXAMPLES OF GOOD FORMAT**:
   - $300M Term Loan @ SOFR + 112.5 to 162.5 bps mat. 12/2026
   - 165.3M CHF Term Loan mat. 2027
   - 297M CHF Senior Notes @ 1.01% mat. 12/2029
   - $900M Revolver @ SOFR + 100–150 bps mat. 1/2029 (BofA)
   - 300M CHF Senior Notes @ 0.88% mat. 12/2031
   - 50M CHF Senior Notes @ 2.56% mat. 4/2034
   - 146M CHF + 50M CHF Senior Notes @ 2.60%, 2.62% mat. 4/2036

10. **CRITICAL RULES**:
    - NEVER make up information that's not in the source data
    - If information is truly missing, use "MISSING"
    - Use ONLY the CURRENT facility if there are multiple versions
    - IGNORE any facility that mentions being "prior to" or "before" another agreement
    - IGNORE any facility that has been "amended and restated" by a newer agreement
    - Use the highest amount if there are conflicting amounts
    - Prioritize specific bank names over generic terms like "group of banks"
    - Convert all amounts to millions (e.g., 125,000,000 → $125M)
    - Clean up interest rate formatting (e.g., "SOFR + 5.0%" not "SOFR + 5.0% per annum")
    - Convert percentages to basis points where appropriate (e.g., "5.0%" → "500 bps")
    - For CHF amounts, use format like "165.3M CHF" (no $ symbol)
    - For EUR amounts, use format like "150M EUR" (no $ symbol)
    - For USD amounts, use format like "$900M" (with $ symbol)
    - Keep formatting concise and clean

Return ONLY the formatted debt stack summary, no additional text or explanations.
"""
    
    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a financial analyst creating debt capital stack summaries. Be precise, accurate, and use the exact format specified."},
                {"role": "user", "content": prompt}
            ]
        )
        
        summary = response.choices[0].message.content.strip()
        
        return summary
        
    except Exception as e:
        return f"❌ Failed to create summary: {str(e)}"

def get_facilities_for_ticker(ticker):
    return extract_final_facilities(ticker)

# Production entry point
if __name__ == "__main__":
    # You can change the ticker here for testing
    test_ticker = "BRKR"
    
    # Production extraction
    result, raw_text = extract_final_facilities(test_ticker)
    
    # Create LLM-powered debt stack summary
    summary = create_debt_stack_summary(raw_text=raw_text, debug=False)
    print(summary)