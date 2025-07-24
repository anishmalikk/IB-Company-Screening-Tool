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
llm_client = OpenAI(api_key=OPENAI_API_KEY)
edgar = EdgarClient(user_agent="Company Screener Tool contact@companyscreenertool.com")

def get_latest_10q_link_for_ticker(ticker: str) -> str:
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










def extract_facilities_robust(extracted_sections, llm_client, model_name, debug=False, output_file=None):
    """
    OPTIMIZED GPT EXTRACTION: Try full content first, use filtering as fallback for token limits
    This approach sends the full 10-Q content first, and only filters if we hit token limits.
    """
    import json
    import re
    
    # First, try with the full extracted content
    full_text = "\n\n".join([f"=== {header} ===\n{content}" for header, content in extracted_sections.items()])
    
    if debug:
        print(f"📄 First attempt: Sending full content ({len(full_text)} characters) to GPT")
        print(f"Original sections: {len(extracted_sections)}")
    
    # Try with full content first
    try:
        result = process_with_llm(full_text, llm_client, model_name, debug, "full content")
        if result and not result.get("error"):
            if debug:
                print("✅ Success with full content!")
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)
            return result
    except Exception as e:
        if debug:
            print(f"❌ Full content failed: {e}")
    
    # If full content fails, fall back to filtering
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
    
    # Try with filtered content
    try:
        result = process_with_llm(filtered_text, llm_client, model_name, debug, "filtered content")
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        return result
    except Exception as e:
        if debug:
            print(f"❌ Filtered content also failed: {e}")
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



def test_facilities_json_extraction(ticker, output_json_file="facilities_json_test.json", output_llm_file="facilities_llm_raw.txt"):
    """
    Fetch the latest 10-Q for the given ticker, extract all relevant sections, run robust multi-pass LLM extraction, and write the output to files.
    """
    link = get_latest_10q_link_for_ticker(ticker)
    if not link:
        print(f"No 10-Q link found for ticker {ticker}.")
        return
    response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    extracted = extract_all_relevant_sections(soup, debug=False)
    result = extract_facilities_robust(extracted, llm_client, MODEL_NAME, debug=False, output_file=output_llm_file)
    import json
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

#Local testing in IDE:
if __name__ == "__main__":
    # You can change the ticker here for testing
    test_ticker = "MIDD"
    
    # Usage for local testing (to test the JSON extraction):
    test_facilities_json_extraction(test_ticker)