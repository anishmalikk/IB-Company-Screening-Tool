from sec_edgar_api.EdgarClient import EdgarClient
from ticker_utils import get_cik_for_ticker
import requests
import os
from bs4 import BeautifulSoup
import re
import requests
from bs4 import BeautifulSoup
import re
import os
from openai import OpenAI
from ticker_utils import get_cik_for_ticker
from sec_edgar_api.EdgarClient import EdgarClient
from dotenv import load_dotenv
import collections

load_dotenv()

def is_section_header(line):
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

# Improved extraction: finds all relevant sections, tables, and referenced notes/exhibits
EXPANDED_KEYWORDS = [
    "debt", "credit agreement", "credit facilities", "notes payable", "indebtedness", "long-term debt",
    "term loan", "term facility", "revolving credit facility", "note", "exhibit", "schedule", "obligations",
    "borrowings", "secured", "unsecured", "guarantee", "indenture", "senior notes", "convertible", "loan agreement",
    "amendment", "table", "summary", "schedule of long-term debt", "liquidity", "capital resources", "financial condition",
    "cash flows", "supplemental", "supplemental information", "commitment", "outstanding", "principal", "interest"
]
NOTE_REGEX = re.compile(r'(note|exhibit|schedule)\s*\d+[A-Za-z]*', re.IGNORECASE)

# Helper: extract tables and their captions/headings

def extract_tables_with_captions(soup):
    tables = []
    for table in soup.find_all('table'):
        # Try to find a preceding heading, bold, or all-caps line
        caption = None
        prev = table.find_previous(['b', 'strong', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if prev:
            caption = prev.get_text(strip=True)
        else:
            # Fallback: look for previous text node
            prev_text = table.find_previous(string=True)
            if prev_text:
                caption = prev_text.strip()
        tables.append((caption, str(table)))
    return tables

# Helper: find cross-references like 'see Note 7'
def find_note_references(text):
    return set(re.findall(r'Note\s*\d+[A-Za-z]*', text, re.IGNORECASE))

# Improved extraction: always include full Liquidity/Capital Resources/MD&A sections, include any section whose body contains a facility keyword, and scan all paragraphs for facility keywords.
def extract_all_relevant_sections(soup, min_len=200, max_len=50000, debug=False, debug_log=None):
    """
    Improved extraction:
    - Always include the full text of sections with headers containing 'liquidity', 'capital resources', or 'management's discussion'.
    - For all other sections, include the section if any EXPANDED_KEYWORDS appear in the section body (not just the header).
    - Additionally, scan all paragraphs in the document and include any paragraph containing a facility keyword (as a PARAGRAPH_MATCH entry).
    - Retain table and cross-reference extraction as before.
    - INCREASED max_len to 50000 to capture more comprehensive content.
    Returns a dict {header: content, ...}
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
    # Table and cross-ref extraction as before
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

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("10Q_MODEL_NAME", "MODEL_NAME")
SECONDPASS_MODEL = os.getenv("SECONDPASS_MODEL", MODEL_NAME)
llm_client = OpenAI(api_key=OPENAI_API_KEY)
edgar = EdgarClient(user_agent="Company Screener Tool contact@companyscreenertool.com")

def get_latest_10q_link_for_ticker(ticker: str) -> str:
    print(f"🔍 Getting CIK for ticker: {ticker}")
    cik = get_cik_for_ticker(ticker)
    print(f"✅ CIK: {cik}")
    
    if not cik:
        print(f"❌ No CIK found for ticker: {ticker}")
        return ""
    
    try:
        print(f"🔍 Getting submissions for CIK: {cik}")
        submissions = edgar.get_submissions(cik=cik)
        recent_filings = submissions["filings"]["recent"]
        print(f"✅ Found {len(recent_filings['form'])} recent filings")
        
        for i, form in enumerate(recent_filings["form"]):
            if form == "10-Q":
                accession = recent_filings["accessionNumber"][i]
                primary_doc = recent_filings["primaryDocument"][i]
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik):010d}/{accession.replace('-', '')}/{primary_doc}"
                print(f"✅ Found 10-Q filing: {filing_url}")
                return filing_url
        
        print(f"❌ No 10-Q filing found for ticker: {ticker}")
        return ""
        
    except Exception as e:
        print(f"❌ Error getting submissions: {str(e)}")
        return ""


def identify_debt_facilities_first_pass(text_content, llm_client, model_name, debug=False):
    """
    FIRST PASS: Identify only the names of actual debt facilities and notes.
    This pass focuses solely on identifying what debt facilities exist, not their details.
    """
    import json
    import re
    
    prompt = f"""
You are a financial document expert. Your ONLY job is to identify the NAMES of actual debt facilities and notes from this 10-Q filing.

CONTEXT: This is the first pass of a two-pass system. You are ONLY identifying facility names, not extracting details.

CRITICAL RULES FOR FIRST PASS:
- ONLY identify actual debt facilities (credit agreements, loans, notes, bonds)
- EXCLUDE: bank guarantees, working capital lines, letters of credit, trade payables, accounts payable
- EXCLUDE: any non-debt financial instruments
- EXCLUDE: operating leases, capital leases, or other non-debt obligations
- ONLY include facilities that represent actual borrowing/debt
- For notes, identify each individual note separately
- Use the EXACT facility/note names as mentioned in the document
- Focus on active/current facilities, not expired or terminated ones
- CRITICAL: DO NOT include duplicate entries - each facility/note should appear only once

WHAT TO LOOK FOR IN FACILITIES (Credit Agreements):
- Credit agreements that provide borrowing facilities (e.g., "2024 Amended and Restated Credit Agreement")
- Loan agreements that provide actual borrowing capacity
- Facility agreements that provide revolving or term loan capacity
- CRITICAL: These should be agreements that provide BORROWING capacity, not just note purchase agreements

WHAT TO LOOK FOR IN NOTES (Individual Debt Securities):
- Individual notes with specific names (e.g., "4.500% Notes due 2029")
- Senior notes with specific terms
- Convertible notes with specific terms
- Bonds with specific names
- CRITICAL: These should be individual debt securities, not agreements

WHAT TO EXCLUDE:
- Bank guarantees
- Working capital lines (unless they represent actual borrowing)
- Letters of credit
- Trade payables
- Accounts payable
- Operating leases
- Capital leases
- Any non-debt financial instruments
- Note purchase agreements (these are not borrowing facilities)
- Generic terms like "Term Loan" or "Revolver" without the full agreement name

EXAMPLES OF WHAT TO INCLUDE IN FACILITIES:
- "2024 Amended and Restated Credit Agreement" (provides borrowing capacity)
- "2019 Amended and Restated Credit Agreement" (provides borrowing capacity)
- "2024 Term Loan Agreement" (if it provides actual borrowing capacity)

EXAMPLES OF WHAT TO INCLUDE IN NOTES:
- "4.500% Notes due 2029"
- "Senior Notes due 2029"
- "Convertible Notes due 2028"
- "2021 Notes due December 8, 2031 - CHF"
- "2019 Notes due December 11, 2029 - CHF"
- "2024 Notes due April 15, 2034 - CHF"

EXAMPLES OF WHAT TO EXCLUDE:
- "Bank guarantees and working capital line"
- "Letters of credit"
- "Trade payables"
- "Accounts payable"
- "2012 Note Purchase Agreement" (this is not a borrowing facility)
- "2019 Note Purchase Agreement" (this is not a borrowing facility)
- Just "Term Loan" (should be part of credit agreement)
- Just "Revolver" (should be part of credit agreement)

CRITICAL: If you see a credit agreement that provides for both a term loan and revolving facility, identify the CREDIT AGREEMENT name, not the individual facility types.

CRITICAL: Each facility and note should appear only ONCE in the results. No duplicates.

CRITICAL: Note purchase agreements are NOT borrowing facilities - they are agreements to purchase existing notes.

Return ONLY valid JSON with facility and note names:
{{
  "facilities": [
    "exact credit agreement name 1",
    "exact credit agreement name 2"
  ],
  "notes": [
    "exact note name 1",
    "exact note name 2"
  ]
}}

Document text:
{text_content}
"""
    
    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Identify ONLY actual debt facility and note names. Exclude non-debt instruments like guarantees and working capital lines. Credit agreements provide borrowing capacity and go in facilities. Individual notes are debt securities and go in notes. DO NOT include duplicate entries."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        if debug:
            print(f"First pass raw response: {raw_response[:500]}")
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', raw_response)
        if json_match:
            result = json.loads(json_match.group(0))
            # Ensure we have the expected structure
            if "facilities" not in result:
                result["facilities"] = []
            if "notes" not in result:
                result["notes"] = []
            
            # Remove duplicates from facilities and notes
            if "facilities" in result:
                result["facilities"] = list(dict.fromkeys(result["facilities"]))  # Remove duplicates while preserving order
            if "notes" in result:
                result["notes"] = list(dict.fromkeys(result["notes"]))  # Remove duplicates while preserving order
            
            # Post-process to ensure proper classification
            # Move any notes that were incorrectly classified as facilities
            note_keywords = ["notes", "bonds", "debentures"]
            credit_agreement_keywords = ["credit agreement", "loan agreement", "facility agreement"]
            
            facilities_to_move = []
            for facility in result["facilities"]:
                if any(keyword in facility.lower() for keyword in note_keywords):
                    if not any(keyword in facility.lower() for keyword in credit_agreement_keywords):
                        facilities_to_move.append(facility)
            
            # Move incorrectly classified items
            for item in facilities_to_move:
                result["facilities"].remove(item)
                if item not in result["notes"]:
                    result["notes"].append(item)
            
            return result
        else:
            return {"facilities": [], "notes": [], "error": "No JSON found in first pass response"}
        
    except Exception as e:
        if debug:
            print(f"First pass LLM processing failed: {e}")
        return {"facilities": [], "notes": [], "error": str(e)}

def extract_facility_details_second_pass(text_content, facility_names, note_names, llm_client, model_name, debug=False, content_type="content"):
    """
    SECOND PASS: Extract detailed information about the specific facilities and notes identified in the first pass.
    """
    import json
    import re
    
    # Create a list of all facilities and notes to look for
    all_targets = facility_names + note_names
    
    if not all_targets:
        if debug:
            print("No facilities or notes identified in first pass")
        return {"facilities": [], "notes": []}
    
    # Build the target list for the prompt
    targets_text = "\n".join([f"- {target}" for target in all_targets])
    
    prompt = f"""
You are a financial document expert. Extract detailed information about SPECIFIC debt facilities and notes from this 10-Q filing.

CONTEXT: This is the second pass of a two-pass system. You are extracting details for these SPECIFIC facilities and notes:

TARGET FACILITIES AND NOTES:
{targets_text}

STEP-BY-STEP APPROACH:
1. For each target facility/note above, find its detailed information
2. Find MAXIMUM facility size (look for "up to $X million", "commitment of $X", "facility size of $X")
3. Extract interest rate information
4. Find maturity dates
5. Identify lead banks/lenders
6. Copy exact source text for verification
7. CRITICAL: Only use amounts that explicitly state the maximum facility size, not current usage
8. CRITICAL: Look for lead banks in the same paragraph/section as the facility description
9. CRITICAL: Look for maturity dates in the same paragraph/section as the facility description
10. CRITICAL: Separate credit agreements from individual notes - credit agreements go in "facilities", individual notes go in "notes"
11. CRITICAL: Search the ENTIRE document thoroughly for each facility/note - don't just look in one section

CRITICAL RULES:
- Use MAXIMUM FACILITY SIZE, never current outstanding balances
- CRITICAL: If you see "borrowed $X against the facility", this is USAGE, NOT the facility size - use "MISSING"
- CRITICAL: If you see "outstanding $X under the facility", this is USAGE, NOT the facility size - use "MISSING"
- CRITICAL: Only use amounts that explicitly state the maximum/commitment size of the facility
- Use exact facility names from the target list above
- If information missing, use "MISSING"
- CRITICAL: Look for specific bank names like "Bank of America", "JP Morgan", "Wells Fargo", "BofA", etc.
- CRITICAL: NEVER use "group of banks", "group of insurance companies", or any generic group terms for lead bank - use "MISSING" instead
- CRITICAL: Use ORIGINAL facility amounts, not amendment amounts
- CRITICAL: Look for interest rate information in the same paragraph/section as the facility description
- CRITICAL: Convert amounts to full dollar amounts - if you see "$1,250" in thousands context, convert to "$1,250,000"
- CRITICAL: Look for table footnotes or context that indicates amounts are in thousands (e.g., "in thousands", "except per share amounts")
- CRITICAL: NEVER use current outstanding balances as facility amounts - if you only see "outstanding" or "borrowed" amounts, use "MISSING" for max_amount
- CRITICAL: Look for phrases like "up to $X million", "commitment of $X", "facility size of $X" for maximum amounts
- CRITICAL: For credit agreements that provide multiple facilities (term loan + revolver), extract the TOTAL commitment amount
- CRITICAL: Look for maturity dates in formats like "due 2029", "maturing 2029", "expires 2029", "maturity 2029"
- CRITICAL: For notes, look for the full principal amount, not just partial amounts
- CRITICAL: Look for lead banks in phrases like "with [Bank Name]", "led by [Bank Name]", "arranged by [Bank Name]", "Bank of America", "BofA"
- CRITICAL: Credit agreements (like "2024 Amended and Restated Credit Agreement") go in "facilities" array
- CRITICAL: Individual notes (like "4.500% Notes due 2029") go in "notes" array
- CRITICAL: Search the ENTIRE document for each facility/note - don't stop after finding one mention

EXAMPLES:
- "revolving loans of up to $175.0 million" → Facility: Revolver, Amount: $175.0 million
- "term loan borrowings of up to $595.0 million" → Facility: Term Loan, Amount: $595.0 million
- "SOFR + 1.625%" → Interest Rate: SOFR + 1.625%
- "Bank of America" → Lead Bank: Bank of America
- "BofA" → Lead Bank: Bank of America
- "JP Morgan Chase Bank, N.A." → Lead Bank: JP Morgan Chase Bank, N.A.
- "group of banks" → Lead Bank: MISSING
- "amended to increase to $922,500" → Use ORIGINAL amount ($850,000), not amendment amount
- "$1,250" in thousands context → Amount: $1,250,000 (convert to full amount)
- "borrowed $750.0 million against the delayed draw term facility" → Amount: MISSING (this is usage, not facility size)
- "$1.6 billion of borrowings outstanding under its credit facility" → Amount: MISSING (this is outstanding, not facility size)
- "due 2029" → Maturity: 2029
- "maturing 2029" → Maturity: 2029
- "expires 2029" → Maturity: 2029
- "maturity 2029" → Maturity: 2029

AVOID:
- "outstanding on" amounts (current balances)
- "prepaid" amounts (payments made)
- Amendment amounts (use original facility size)
- ANY generic lead banks: "group of banks", "group of insurance companies", "group of lenders", etc.
- Current outstanding balances as facility amounts
- "borrowed $X against the facility" amounts (this is usage, not facility size)
- "remaining borrowing capacity" amounts (this is remaining, not total facility size)
- Any amounts that are clearly current usage rather than maximum facility size

CRITICAL: For credit agreements that provide both term loan and revolving facilities, extract the TOTAL commitment amount and look for lead banks that apply to the entire agreement.

CRITICAL: Credit agreements go in "facilities", individual notes go in "notes".

CRITICAL: Search the ENTIRE document thoroughly for each facility/note. Don't stop after finding one mention.

Return ONLY valid JSON:
{{
  "facilities": [
    {{
      "name": "exact credit agreement name from target list",
      "max_amount": "maximum facility size or MISSING",
      "currency": "USD",
      "interest_rate": "interest rate or MISSING",
      "maturity": "maturity date or MISSING",
      "lead_bank": "lead bank or MISSING",
      "source_text": "exact text where found"
    }}
  ],
  "notes": [
    {{
      "name": "exact note name from target list",
      "max_amount": "note amount or MISSING",
      "currency": "USD",
      "interest_rate": "interest rate or MISSING",
      "maturity": "maturity date or MISSING",
      "lead_bank": "lender or MISSING",
      "source_text": "exact text where found"
    }}
  ]
}}

Document text:
{text_content}
"""
    
    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Extract detailed information about specific debt facilities and notes. Be thorough and accurate. Look for specific bank names and maturity dates. Credit agreements go in facilities array, individual notes go in notes array. Search the ENTIRE document thoroughly for each item."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        if debug:
            print(f"Second pass raw response ({content_type}): {raw_response[:500]}")
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', raw_response)
        if json_match:
            result = json.loads(json_match.group(0))
            
            # Post-process to ensure proper separation and avoid duplicates
            if "facilities" in result and "notes" in result:
                # Remove any notes that appear in both arrays
                facility_names_set = {f["name"] for f in result["facilities"]}
                result["notes"] = [note for note in result["notes"] if note["name"] not in facility_names_set]
                
                # Ensure credit agreements are in facilities, individual notes are in notes
                credit_agreement_keywords = ["credit agreement", "loan agreement", "facility agreement"]
                note_keywords = ["notes", "bonds", "debentures"]
                
                # Move items to correct arrays based on their names
                facilities_to_move = []
                notes_to_move = []
                
                for facility in result["facilities"]:
                    if any(keyword in facility["name"].lower() for keyword in note_keywords):
                        if not any(keyword in facility["name"].lower() for keyword in credit_agreement_keywords):
                            notes_to_move.append(facility)
                            facilities_to_move.append(facility)
                
                for note in result["notes"]:
                    if any(keyword in note["name"].lower() for keyword in credit_agreement_keywords):
                        facilities_to_move.append(note)
                        notes_to_move.append(note)
                
                # Remove items from wrong arrays
                result["facilities"] = [f for f in result["facilities"] if f not in facilities_to_move]
                result["notes"] = [n for n in result["notes"] if n not in notes_to_move]
                
                # Add items to correct arrays
                result["facilities"].extend([item for item in facilities_to_move if any(keyword in item["name"].lower() for keyword in credit_agreement_keywords)])
                result["notes"].extend([item for item in notes_to_move if any(keyword in item["name"].lower() for keyword in note_keywords)])
            
        else:
            result = {"facilities": [], "notes": [], "error": "No JSON found in second pass response"}
        
        return result
        
    except Exception as e:
        if debug:
            print(f"Second pass LLM processing failed ({content_type}): {e}")
        return {"facilities": [], "notes": [], "error": str(e)}


def extract_facilities_robust(extracted_sections, llm_client, model_name, debug=False, output_file=None):
    """
    TWO-PASS GPT EXTRACTION: First pass identifies debt facility names, second pass extracts details
    This approach uses two LLM passes to ensure we only extract actual debt facilities.
    """
    import json
    import re
    
    # Prepare the full text for both passes
    full_text = "\n\n".join([f"=== {header} ===\n{content}" for header, content in extracted_sections.items()])
    
    if debug:
        print(f"📄 Two-pass extraction: Sending full content ({len(full_text)} characters) to GPT")
        print(f"Original sections: {len(extracted_sections)}")
    
    # FIRST PASS: Identify debt facility names only
    try:
        if debug:
            print("🔄 FIRST PASS: Identifying debt facility names...")
        
        first_pass_result = identify_debt_facilities_first_pass(full_text, llm_client, MODEL_NAME, debug)
        
        if first_pass_result.get("error"):
            if debug:
                print(f"❌ First pass failed: {first_pass_result['error']}")
            return first_pass_result
        
        facility_names = first_pass_result.get("facilities", [])
        note_names = first_pass_result.get("notes", [])
        
        if debug:
            print(f"✅ First pass identified {len(facility_names)} facilities and {len(note_names)} notes")
            print(f"Facilities: {facility_names}")
            print(f"Notes: {note_names}")
        
        # If no facilities or notes found, return empty result
        if not facility_names and not note_names:
            if debug:
                print("⚠️ No debt facilities or notes identified in first pass")
            return {"facilities": [], "notes": []}
        
        # SECOND PASS: Extract detailed information about identified facilities/notes
        if debug:
            print("🔄 SECOND PASS: Extracting detailed information...")
        
        second_pass_result = extract_facility_details_second_pass(
            full_text, facility_names, note_names, llm_client, SECONDPASS_MODEL, debug, "full content"
        )
        
        if debug:
            print("✅ Second pass completed")
        
        # Clean up the results
        cleaned_result = clean_facility_results(second_pass_result, debug)
        
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(cleaned_result, f, indent=2)
        
        return cleaned_result
        
    except Exception as e:
        if debug:
            print(f"❌ Two-pass extraction failed: {e}")
        
        # Fallback to filtered content if full content fails
        if debug:
            print("🔄 Falling back to filtered content due to token limits...")
        
        # AGGRESSIVE CONTENT FILTERING (FALLBACK)
        def filter_relevant_content(sections, max_chars=90000):
            """Filter sections aggressively to stay within token limits"""
            scored_sections = []
            
            # High priority keywords (debt/facility specific)
            high_priority_keywords = [
                'credit agreement', 'credit facility', 'revolving', 'term loan', 'debt', 
                'borrowings', 'notes payable', 'indebtedness', 'liquidity', 'capital resources',
                'financial condition', 'interest rate', 'maturity', 'lender', 'bank',
                'senior notes', 'convertible notes', 'notes due', 'indenture', 'bond'
            ]
            
            # Medium priority keywords (financial context)
            medium_priority_keywords = [
                'financial', 'capital', 'resources', 'cash', 'flow', 'obligations',
                'commitments', 'guarantees', 'indenture', 'senior notes', 'convertible',
                'debt securities', 'long-term debt', 'borrowings', 'principal amount'
            ]
            
            for header, content in sections.items():
                # Skip if section is too short (likely irrelevant)
                if len(content) < 50:
                    continue
                
                # Calculate relevance score
                score = 0
                header_lower = header.lower()
                content_lower = content.lower()
                
                # High priority scoring
                for keyword in high_priority_keywords:
                    if keyword in header_lower:
                        score += 15
                    if keyword in content_lower:
                        score += 8
                
                # Medium priority scoring
                for keyword in medium_priority_keywords:
                    if keyword in header_lower:
                        score += 5
                    if keyword in content_lower:
                        score += 2
                
                # Bonus for debt-specific headers
                debt_headers = ['debt', 'credit', 'facility', 'loan', 'borrowings', 'notes payable', 'senior notes', 'notes due', 'indenture']
                if any(dh in header_lower for dh in debt_headers):
                    score += 20
                
                # Bonus for tables (often contain facility details)
                if '<table>' in content or '|' in content:
                    score += 10
                
                # Heavy penalty for very long sections (likely contain irrelevant content)
                if len(content) > 15000:
                    score -= 10
                
                if score > 0:
                    scored_sections.append((score, header, content))
            
            # Sort by score (highest first)
            scored_sections.sort(key=lambda x: x[0], reverse=True)
            
            # Build prioritized content with strict character limit
            prioritized_content = []
            total_chars = 0
            
            for score, header, content in scored_sections:
                # Truncate content if it's too long
                max_section_chars = 12000  # Limit individual sections
                if len(content) > max_section_chars:
                    content = content[:max_section_chars] + "\n[CONTENT TRUNCATED]"
                
                section_text = f"=== {header} (score: {score}) ===\n{content}"
                
                # Check if adding this section would exceed limit
                if total_chars + len(section_text) > max_chars:
                    # Try to truncate the content to fit
                    remaining_chars = max_chars - total_chars - len(f"=== {header} (score: {score}) ===\n")
                    if remaining_chars > 500:  # Only add if we can fit meaningful content
                        truncated_content = content[:remaining_chars]
                        section_text = f"=== {header} (score: {score}) [TRUNCATED] ===\n{truncated_content}"
                        prioritized_content.append(section_text)
                        total_chars += len(section_text)
                    break
                else:
                    prioritized_content.append(section_text)
                    total_chars += len(section_text)
            
            return prioritized_content, total_chars
        
        # Filter content to only relevant sections
        relevant_content, total_chars = filter_relevant_content(extracted_sections)
        filtered_text = "\n\n".join(relevant_content)
        
        if debug:
            print(f"📄 Fallback: Sending filtered text ({len(filtered_text)} characters) to GPT")
            print(f"Relevant sections: {len(relevant_content)}")
            print(f"Filtered text length: {len(filtered_text)} characters")
        
        # Try two-pass approach with filtered content
        try:
            # First pass with filtered content
            first_pass_result = identify_debt_facilities_first_pass(filtered_text, llm_client, MODEL_NAME, debug)
            
            if first_pass_result.get("error"):
                if debug:
                    print(f"❌ First pass with filtered content failed: {first_pass_result['error']}")
                return first_pass_result
            
            facility_names = first_pass_result.get("facilities", [])
            note_names = first_pass_result.get("notes", [])
            
            if debug:
                print(f"✅ First pass with filtered content identified {len(facility_names)} facilities and {len(note_names)} notes")
            
            # Second pass with filtered content
            second_pass_result = extract_facility_details_second_pass(
                filtered_text, facility_names, note_names, llm_client, SECONDPASS_MODEL, debug, "filtered content"
            )
            
            # Clean up the results
            cleaned_result = clean_facility_results(second_pass_result, debug)
            
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(cleaned_result, f, indent=2)
            
            return cleaned_result
            
        except Exception as e:
            if debug:
                print(f"❌ Two-pass with filtered content also failed: {e}")
            return {"facilities": [], "notes": [], "error": str(e)}

def process_with_llm(text_content, llm_client, model_name, debug=False, content_type="content"):
    """Process text content with LLM and return structured result"""
    import json
    import re
    
    # OPTIMIZED PROMPT
    prompt = f"""
You are a financial document expert. Extract ALL credit facilities and notes from this 10-Q filing.

CONTEXT: This is {content_type} from the 10-Q filing.

STEP-BY-STEP APPROACH:
1. Scan for credit agreements, facilities, loans, or notes
2. Identify EXACT facility names as mentioned in the document
3. Find MAXIMUM facility size (look for "up to $X million", "commitment of $X", "facility size of $X")
4. Extract interest rate information
5. Find maturity dates
6. Identify lead banks/lenders
7. Copy exact source text for verification
8. CRITICAL: Look for senior notes, convertible notes, and any debt securities
9. CRITICAL: Ensure all facilities from the same credit agreement share the same lead bank
10. CRITICAL: Look for interest rate details in the same paragraph/section as facility descriptions
11. CRITICAL: If you only see "borrowed $X" or "outstanding $X", use "MISSING" for facility size
12. CRITICAL: Only use amounts that explicitly state the maximum facility size, not current usage

CRITICAL RULES:
- Use MAXIMUM FACILITY SIZE, never current outstanding balances
- CRITICAL: If you see "borrowed $X against the facility", this is USAGE, NOT the facility size - use "MISSING"
- CRITICAL: If you see "outstanding $X under the facility", this is USAGE, NOT the facility size - use "MISSING"
- CRITICAL: Only use amounts that explicitly state the maximum/commitment size of the facility
- If credit agreement mentions "Revolver" AND "Term Loan", create SEPARATE entries
- Use exact facility names from document
- If information missing, use "MISSING"
- IMPORTANT: If multiple facilities are part of the SAME credit agreement, they share the SAME interest rate AND lead bank
- CRITICAL: NEVER use "group of banks", "group of insurance companies", or any generic group terms for lead bank - use "MISSING" instead
- CRITICAL: For notes, create SEPARATE entries for each individual note, don't combine them
- CRITICAL: Use ORIGINAL facility amounts, not amendment amounts
- CRITICAL: Use EXACT note names from document (e.g., "4.500% Notes due 2029", not "2029 Notes")
- CRITICAL: Look for interest rate information in the same paragraph/section as the facility description
- CRITICAL: If you see "amended to increase", use the ORIGINAL amount, not the amendment amount
- CRITICAL: Look for phrases like "SOFR + applicable margin" or "interest rate" near facility descriptions
- CRITICAL: Search for senior notes, convertible notes, and debt securities throughout the document
- CRITICAL: If you find a credit agreement with multiple facilities, ensure they all share the same lead bank
- CRITICAL: Look for interest rate spreads in basis points (e.g., "SOFR + 112.5-175 bps")
- CRITICAL: If facilities are described as part of the same credit agreement, they share the same lead bank (e.g., "with a group of banks" applies to both facilities)
- CRITICAL: Convert amounts to full dollar amounts - if you see "$1,250" in thousands context, convert to "$1,250,000"
- CRITICAL: Look for table footnotes or context that indicates amounts are in thousands (e.g., "in thousands", "except per share amounts")
- CRITICAL: For notes and debt, look for the full principal amount, not just partial amounts
- CRITICAL: NEVER use current outstanding balances as facility amounts - if you only see "outstanding" or "borrowed" amounts, use "MISSING" for max_amount
- CRITICAL: Look for phrases like "up to $X million", "commitment of $X", "facility size of $X" for maximum amounts
- CRITICAL: If you see "borrowed $X against the facility", this is USAGE, not the facility size

EXAMPLES:
- "revolving loans of up to $175.0 million" → Facility: Revolver, Amount: $175.0 million
- "term loan borrowings of up to $595.0 million" → Facility: Term Loan, Amount: $595.0 million
- "SOFR + 1.625%" → Interest Rate: SOFR + 1.625%
- "SOFR + applicable margin (0.85% to 1.20%)" → Interest Rate: SOFR + applicable margin (0.85% to 1.20%)
- "JP Morgan Chase Bank, N.A." → Lead Bank: JP Morgan Chase Bank, N.A.
- "group of banks" → Lead Bank: MISSING
- "group of insurance companies" → Lead Bank: MISSING
- "amended to increase to $922,500" → Use ORIGINAL amount ($850,000), not amendment amount
- "4.500% Notes due 2029" → Note Name: 4.500% Notes due 2029 (use exact name)
- "5.600% Notes due 2028" → Note Name: 5.600% Notes due 2028 (use exact name)
- "The New Credit Agreement provides that the applicable margin...0.85% to 1.20%" → This applies to BOTH Term Loan Facility AND Revolving Facility under the same agreement
- "we entered into a $1,150,000 credit facility...which provides for a term loan...and a revolving credit facility" → Both facilities share the same interest rate structure
- "$1,250" in thousands context → Amount: $1,250,000 (convert to full amount)
- "$3,800" in thousands context → Amount: $3,800,000 (convert to full amount)
- "Note Payable due 2026" with amount in thousands → Look for full principal amount in nearby text
- "borrowed $750.0 million against the delayed draw term facility" → Amount: MISSING (this is usage, not facility size)
- "$1.6 billion of borrowings outstanding under its credit facility" → Amount: MISSING (this is outstanding, not facility size)
- "Remaining borrowing capacity under this facility was $2.7 billion" → Amount: MISSING (this is remaining, not total facility size)
- "the company borrowed $750.0 million against the delayed draw term facility" → Amount: MISSING (this is what they borrowed, not the facility size)
- "outstanding under the delayed draw term loan" → Amount: MISSING (this is current outstanding, not facility size)

AVOID:
- "outstanding on" amounts (current balances)
- "prepaid" amounts (payments made)
- Amendment amounts (use original facility size)
- Generic facility names
- ANY generic lead banks: "group of banks", "group of insurance companies", "group of lenders", etc.
- Combining multiple notes into one entry
- Shortened note names (use full names like "4.500% Notes due 2029")
- Wrong interest rates (double-check the rate matches the note name)
- Current outstanding balances as facility amounts
- "borrowed $X against the facility" amounts (this is usage, not facility size)
- "remaining borrowing capacity" amounts (this is remaining, not total facility size)
- Any amounts that are clearly current usage rather than maximum facility size

CONNECTING RELATED FACILITIES:
- If you see "we entered into a $X credit facility with [specific bank]" followed by multiple facility descriptions, ALL those facilities share the same interest rate structure
- Look for phrases like "which provides for" or "including" to identify facilities that are part of the same agreement
- CRITICAL: If multiple facilities are described as part of the same credit agreement (e.g., "the New Credit Agreement"), they ALL share the same interest rate structure
- CRITICAL: Look for interest rate information that applies to the entire credit agreement, not individual facilities
- CRITICAL: If you see "The [Agreement Name] provides that the applicable margin..." this applies to ALL facilities under that agreement
- For notes, look for individual note descriptions and create separate entries for each
- ALWAYS use original facility amounts, ignore amendment amounts
- Look for interest rate information in the same paragraph or nearby text as the facility description
- For notes with ranges (e.g., "2025-2027"), look for individual note descriptions in the document

Return ONLY valid JSON:
{{
  "facilities": [
    {{
      "name": "exact facility name",
      "max_amount": "maximum facility size or MISSING",
      "currency": "USD",
      "interest_rate": "interest rate or MISSING",
      "maturity": "maturity date or MISSING",
      "lead_bank": "lead bank or MISSING",
      "source_text": "exact text where found"
    }}
  ],
  "notes": [
    {{
      "name": "exact note name",
      "max_amount": "note amount or MISSING",
      "currency": "USD",
      "interest_rate": "interest rate or MISSING",
      "maturity": "maturity date or MISSING",
      "lead_bank": "lender or MISSING",
      "source_text": "exact text where found"
    }}
  ]
}}

Document text:
{text_content}
"""
    
    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise financial document analyzer. Extract credit facilities and notes in JSON format. Be thorough and include ALL facilities/notes mentioned. CRITICAL: Never use current usage amounts (like 'borrowed $X' or 'outstanding $X') as facility sizes - use 'MISSING' instead."},
                {"role": "user", "content": prompt}
            ]
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        if debug:
            print(f"Raw LLM response ({content_type}): {raw_response[:500]}")
        
        # Try to extract JSON from the response
        json_match = re.search(r'\{[\s\S]*\}', raw_response)
        if json_match:
            result = json.loads(json_match.group(0))
        else:
            result = {"facilities": [], "notes": [], "error": "No JSON found in response"}
        
        return result
        
    except Exception as e:
        if debug:
            print(f"LLM processing failed ({content_type}): {e}")
        return {"facilities": [], "notes": [], "error": str(e)}

def clean_facility_results(result, debug=False):
    """
    Post-process the facility extraction results to clean up and validate the data.
    """
    if not result or "facilities" not in result or "notes" not in result:
        return result
    
    cleaned_result = {"facilities": [], "notes": []}
    
    # Clean up facilities
    for facility in result["facilities"]:
        cleaned_facility = {
            "name": facility.get("name", "MISSING"),
            "max_amount": facility.get("max_amount", "MISSING"),
            "currency": facility.get("currency", "USD"),
            "interest_rate": facility.get("interest_rate", "MISSING"),
            "maturity": facility.get("maturity", "MISSING"),
            "lead_bank": facility.get("lead_bank", "MISSING"),
            "source_text": facility.get("source_text", "MISSING")
        }
        
        # Clean up amounts - remove any "MISSING" amounts that might have been incorrectly filled
        if cleaned_facility["max_amount"] == "MISSING" and "borrowed" in cleaned_facility["source_text"].lower():
            cleaned_facility["max_amount"] = "MISSING"
        
        # Clean up lead banks - ensure we don't have generic terms
        if cleaned_facility["lead_bank"] and any(generic in cleaned_facility["lead_bank"].lower() for generic in ["group of", "various", "multiple"]):
            cleaned_facility["lead_bank"] = "MISSING"
        
        cleaned_result["facilities"].append(cleaned_facility)
    
    # Clean up notes
    for note in result["notes"]:
        cleaned_note = {
            "name": note.get("name", "MISSING"),
            "max_amount": note.get("max_amount", "MISSING"),
            "currency": note.get("currency", "USD"),
            "interest_rate": note.get("interest_rate", "MISSING"),
            "maturity": note.get("maturity", "MISSING"),
            "lead_bank": note.get("lead_bank", "MISSING"),
            "source_text": note.get("source_text", "MISSING")
        }
        
        # Clean up amounts for notes
        if cleaned_note["max_amount"] == "MISSING" and "borrowed" in cleaned_note["source_text"].lower():
            cleaned_note["max_amount"] = "MISSING"
        
        cleaned_result["notes"].append(cleaned_note)
    
    if debug:
        print(f"Cleaned {len(cleaned_result['facilities'])} facilities and {len(cleaned_result['notes'])} notes")
    
    return cleaned_result


def test_facilities_json_extraction(ticker, output_json_file="facilities_json_test.json", output_llm_file="facilities_llm_raw.txt"):
    """
    Fetch the latest 10-Q for the given ticker, extract all relevant sections, run two-pass LLM extraction, and write the output to files.
    """
    link = get_latest_10q_link_for_ticker(ticker)
    if not link:
        print(f"No 10-Q link found for ticker {ticker}.")
        return
    response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    extracted = extract_all_relevant_sections(soup, debug=False)
    result = extract_facilities_robust(extracted, llm_client, MODEL_NAME, debug=True, output_file=output_llm_file)
    import json
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

#Local testing in IDE:
if __name__ == "__main__":
    # You can change the ticker here for testing
    test_ticker = "BRKR"
    
    # Usage for local testing (to test the JSON extraction):
    test_facilities_json_extraction(test_ticker)