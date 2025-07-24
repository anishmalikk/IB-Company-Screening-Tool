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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI
from ticker_utils import get_cik_for_ticker
from sec_edgar_api.EdgarClient import EdgarClient
from bs4 import Tag
from dotenv import load_dotenv
from itertools import islice
from difflib import SequenceMatcher
import collections

load_dotenv()


TARGET_SECTIONS = {
    "debt": ["debt", "credit agreement", "credit facilities", "notes payable", "indebtedness", "long-term debt", "term loan", "term facility", "revolving credit facility"],
    "liquidity": ["liquidity", "capital resources", "financial condition", "liquidity and capital resources"]
}

def fuzzy_match_score(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

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


def extract_clean_sections(soup: BeautifulSoup, min_len=300, max_len=10000, debug=False, debug_log=None):
    text = soup.get_text(separator="\n", strip=True)
    lines = text.splitlines()
    section_headers = []
    for i, line in enumerate(lines):
        if i < len(lines) * 0.1:  # ignore first 10% of document (cover, TOC, etc.)
            continue
        if is_section_header(line):
            section_headers.append((i, line.strip()))
    selected_sections = {}
    FUZZY_THRESHOLD = 0.7
    for target, keywords in TARGET_SECTIONS.items():
        matches = []
        for idx, heading in section_headers:
            for kw in keywords:
                score = fuzzy_match_score(heading.lower(), kw.lower())
                if kw in heading.lower():
                    score += 0.5  # exact boost
                if score >= FUZZY_THRESHOLD:
                    matches.append((idx, heading, score, kw))
        # Sort matches by their position in the document
        matches = sorted(matches, key=lambda x: x[0])
        if debug and matches:
            msg = f"Matched sections for '{target}':"
            if debug_log is not None:
                debug_log.append(msg)
            else:
                print(msg)
            for idx, heading, score, kw in matches:
                msg = f"  - '{heading}' (score={score:.2f}, keyword='{kw}') at line {idx}"
                if debug_log is not None:
                    debug_log.append(msg)
                else:
                    print(msg)
        # Extract all matched sections
        for i, (idx, header, score, kw) in enumerate(matches):
            next_idx = matches[i+1][0] if i+1 < len(matches) else len(lines)
            content = "\n".join(lines[idx+1:next_idx])
            if len(content) >= min_len:
                key = f"{target}_{i+1}" if len(matches) > 1 else target
                selected_sections[key] = f"=== {header} (score={score:.2f}, keyword='{kw}') ===\n{content[:max_len]}"
    return selected_sections


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

def safe_slice(val, n=500):
    s = str(val) if val is not None else ""
    return s[:n]

def extract_recent_facility_lines(text):
    # Look for lines with 'as of' or 'at' and facility keywords
    lines = text.splitlines()
    recent_lines = []
    facility_keywords = [
        'Term Facility', 'Revolving Credit Facility', 'Credit Facility', 'Term Loan', 'Revolver', 'Facility', 'Debt', 'Borrowings'
    ]
    date_pattern = r'(as of|at) [A-Z][a-z]+ \d{1,2}, \d{4}'
    for line in lines:
        if any(kw in line for kw in facility_keywords) and re.search(date_pattern, line):
            recent_lines.append(line.strip())
        # Also catch lines like 'At May 31, 2025, the outstanding balance of the Term Facility was $250.0 million.'
        elif re.search(r'outstanding balance of .*Facility.* (?:was|is) \$[\d,.]+', line):
            recent_lines.append(line.strip())
    return recent_lines

def get_laymanized_debt_liquidity(tenq_url: str, debug=False):
    """
    Given a 10-Q URL, fetch and parse the HTML, extract the text, and use the LLM to extract and list each credit facility or note in the specified format, in one step.
    Returns the LLM's output as a string.
    """
    debug_log = [] if debug else None
    try:
        if debug:
            msg = f"Fetching 10-Q from URL: {tenq_url}"
            print(msg)
            if debug_log is not None:
                debug_log.append(msg)
        response = requests.get(tenq_url, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        # Use improved section extraction
        sections = extract_clean_sections(soup, debug=debug, debug_log=debug_log)
        if sections:
            relevant_text = "\n\n".join(sections.values())
            if debug:
                msg = "\n=== Extracted Relevant Sections ===\n"
                print(msg)
                print(relevant_text)
                if debug_log is not None:
                    debug_log.append(msg)
                    debug_log.append(relevant_text)
        else:
            # Fallback: use first 120,000 chars
            text = soup.get_text(separator="\n", strip=True)
            relevant_text = text[:120000]
            if debug:
                msg = "No relevant sections found, using fallback text."
                print(msg)
                if debug_log is not None:
                    debug_log.append(msg)
        # Extract most recent facility lines
        recent_lines = extract_recent_facility_lines(relevant_text)
        if debug and recent_lines:
            msg = "\n=== Most Recent Facility Lines (for LLM context) ===\n"
            print(msg)
            if debug_log is not None:
                debug_log.append(msg)
            for l in recent_lines:
                print(l)
                if debug_log is not None:
                    debug_log.append(l)
        # Remove any context about 'most recent value' or 'current balance' and focus on full facility size
        context = ""
        prompt = (
            'Below are the "Debt" and "Liquidity and Capital Resources" sections from a company 10-Q.\n'
            'Your ONLY task is to extract and list each credit facility or note in the following format, one per line:\n'
            'facility amount facility name @ (interest rate) mat. mm/yyyy (Lead Bank)\n'
            '\n'
            'Instructions:\n'
            '- Use the **official, full facility name** as written in the 10-Q, not a generic or invented name.\n'
            '- ALWAYS use the **MAXIMIM FACILITY SIZE** or availability (NOT THE CURRENT OUTSTANDING/BORROWED AMOUNT). This is extremely important.\n'
            '- If the facility name is long, abbreviate only if the abbreviation is used in the 10-Q.\n'
            '- If the 10-Q provides a table, use the names and amounts from the table, not from narrative summaries (if they are complete facility amounts, not usage or debt owed).\n'
            '- If both committed and outstanding amounts are present, always prefer the committed/maximum size.\n'
            '- Use updated information from the newest credit agreements. If a facility amount was updated in a recent amendment, use the updated amount. Again, give the full facility amount, not the current usage or debt owed.\n'
            '- If the lead bank is not specified, omit the parentheses.\n'
            '- Use bps when describing interest rates. Most interest rates have a spread, try to use SOFR or LIBOR + x-y bps where possible.\n'
            '- If a field is missing, put "unknown" or skip it where appropriate, but do not guess or invent any information.\n'
            '- Do not combine or split facilities unless the 10-Q does so.\n'
            '- Look for information about: notes owed, revolvers, term loans, senior notes, credit agreements, borrowing capacity, and availability.\n'
            '- Your output should be organized from facilities coming due first to those coming due last.\n'
            '- Do NOT include any other information, bullets, or narrative.\n'
            'Examples:\n'
            '$350M HF-T1 Distribution Center Loan @ SOFR + 120 -185 bps mat. 3/2026 (BofA)\n'
            '$75M HF-T2 Distribuition Center Construction Loan @ SOFR + 40 - 185 bps mat. 4/2026 (JPM)\n'
            '$250M Revolving Credit Facility @ SOFR + 100–150 bps mat. 12/2026 (PNC)\n'
            '$130.8M China Operational Loans @ 2.00–2.60% mat. var. 2026 (BofChina)\n'
            '$1B China DC Expansion Loan @ 2.70%  mat. 12/2032 (BofChina)\n\n'
            '- Do NOT summarize liquidity, cash, or other financials. Only output the facilities in the format above.\n'
            '\n'
            'IMPORTANT: If the interest rate is described as \'SOFR plus 2.00%\', always convert the spread to basis points (e.g., 2.00% = 200 bps) and output as \'SOFR + 200 bps\'. Never use percent for the spread in your output.\n'
            'Examples:\n'
            "- If the 10-Q says 'SOFR plus 2.00%', output 'SOFR + 200 bps'\n"
            "- If the 10-Q says 'LIBOR plus 1.75%', output 'LIBOR + 175 bps'\n\n"
            'For notes (not facilities), use the following format:\n'
            'note name @ (interest rate) mat. mm/yyyy\n'
            'Examples:\n'
            '- $50M 2.60% Senior Notes – mat. 3/2027 \n'
            '- $100M 2.90% Senior Notes, Series B – mat. 7/2026 \n\n'
            '---\n'
            f"10-Q Text (extracted):\n{relevant_text}"
            "If the 10-Q lacks details, use reliable information from the 10-K to fill gaps, but do not make up any information. Ensure all output is concise and follows the specified formats."
        )
        try:
            response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": (
                        "You are a precise financial document extractor. "
                        "You always extract the maximum committed amount (not the current outstanding or historical amounts) for each facility, "
                        "deduplicate amendments, and output only the current total facility size. "
                        "You always convert interest rate spreads to basis points (bps) unless they are notes, and follow all formatting instructions exactly."
                    )},
                    {"role": "user", "content": prompt}
                ]
            )
            llm_output = response.choices[0].message.content.strip() if response.choices and response.choices[0].message and response.choices[0].message.content else ""
        except Exception as e:
            if debug:
                msg = f"Error processing with LLM: {e}"
                print(msg)
                if debug_log is not None:
                    debug_log.append(msg)
            llm_output = "Error processing with LLM."
        if debug:
            msg = "=== LLM OUTPUT ==="
            print(msg)
            print(safe_slice(llm_output, 1000))
            if debug_log is not None:
                debug_log.append(msg)
                debug_log.append(safe_slice(llm_output, 1000))
        # Write debug log to file if enabled
        if debug_log is not None:
            try:
                with open("debug_output.txt", "w", encoding="utf-8") as f:
                    if debug_log:
                        for entry in debug_log:
                            f.write(entry + "\n")
            except Exception as file_err:
                print(f"Failed to write debug log: {file_err}")
        return llm_output
    except Exception as e:
        if debug:
            msg = f"Error in get_laymanized_debt_liquidity: {e}"
            print(msg)
            if debug_log is not None:
                debug_log.append(msg)
            # Write debug log to file if enabled
            try:
                with open("debug_output.txt", "w", encoding="utf-8") as f:
                    if debug_log:
                        for entry in debug_log:
                            f.write(entry + "\n")
            except Exception as file_err:
                print(f"Failed to write debug log: {file_err}")
        return "Error in get_laymanized_debt_liquidity."

def test_section_extraction(ticker, output_file="section_extraction_test.txt"):
    """
    Fetch the latest 10-Q for the given ticker, extract all relevant sections, and write them to a file.
    """
    link = get_latest_10q_link_for_ticker(ticker)
    if not link:
        print(f"No 10-Q link found for ticker {ticker}.")
        return
    print(f"Testing section extraction for ticker: {ticker}")
    print(f"10-Q link: {link}")
    response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    extracted = extract_all_relevant_sections(soup, debug=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for header, content in extracted.items():
            f.write(f"\n==== {header} ====" + "\n")
            f.write(content if isinstance(content, str) else str(content))
            f.write("\n\n")
    print(f"Extracted sections written to {output_file}")

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
    def filter_relevant_content(sections, max_chars=80000):
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
3. Find MAXIMUM facility size (look for "up to $X million", "commitment of $X")
4. Extract interest rate information
5. Find maturity dates
6. Identify lead banks/lenders
7. Copy exact source text for verification
8. CRITICAL: Look for senior notes, convertible notes, and any debt securities
9. CRITICAL: Ensure all facilities from the same credit agreement share the same lead bank
10. CRITICAL: Look for interest rate details in the same paragraph/section as facility descriptions

CRITICAL RULES:
- Use MAXIMUM FACILITY SIZE, never current outstanding balances
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

AVOID:
- "outstanding on" amounts (current balances)
- "prepaid" amounts (payments made)
- Amendment amounts (use original facility size)
- Generic facility names
- ANY generic lead banks: "group of banks", "group of insurance companies", "group of lenders", etc.
- Combining multiple notes into one entry
- Shortened note names (use full names like "4.500% Notes due 2029")
- Wrong interest rates (double-check the rate matches the note name)

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
                {"role": "system", "content": "You are a precise financial document analyzer. Extract credit facilities and notes in JSON format. Be thorough and include ALL facilities/notes mentioned."},
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
    print(f"Testing robust facilities extraction for ticker: {ticker}")
    print(f"10-Q link: {link}")
    response = requests.get(link, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    extracted = extract_all_relevant_sections(soup, debug=True)
    result = extract_facilities_robust(extracted, llm_client, MODEL_NAME, debug=True, output_file=output_llm_file)
    import json
    with open(output_json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Facilities JSON written to {output_json_file}")
    print(f"Raw LLM output written to {output_llm_file}")

#Local testing in IDE:
if __name__ == "__main__":
    # You can change the ticker here for testing
    test_ticker = "NDSN"
    # debug = False
    # print(f"Testing get_latest_10q_link_for_ticker for ticker: {test_ticker}")
    # link = get_latest_10q_link_for_ticker(test_ticker)
    # print(f"Latest 10-Q link: {link}")
    # if link:
    #     print("\nLaymanized Debt/Liquidity Summary:")
    #     summary = get_laymanized_debt_liquidity(link, debug=debug)
    #     if not debug:
    #         print(summary)
    # else:
    #     print("No 10-Q link found.")

    # Usage for local testing (specifically to test the section extraction algorithm):
    test_section_extraction(test_ticker)
    # Usage for local testing (to test the JSON extraction):
    test_facilities_json_extraction(test_ticker)