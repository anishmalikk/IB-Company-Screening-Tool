from sec_edgar_api.EdgarClient import EdgarClient
from ticker_utils import get_cik_for_ticker
import requests
import os
from bs4 import BeautifulSoup
import re

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
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

def extract_section_by_header(text, header_keywords, debug=False):
    """
    Extract section based on header keywords with improved pattern matching.
    For debt, will also match any 'Note X. ...' section whose header contains a debt-related keyword.
    """
    import re
    patterns = []
    for keyword in header_keywords:
        # Pattern 1: Item X. Header (standard format)
        patterns.append(rf"(?:\n|^)[ \t]*(?:Item\s*\d+[A-Z]?\.\s*)?{re.escape(keyword)}\s*(?:\n|$)")
        # Pattern 2: Just the header at line start (case insensitive)
        patterns.append(rf"(?:\n|^)[ \t]*{re.escape(keyword)}\s*(?:\n|$)")
        # Pattern 3: Header with some flexibility (punctuation, spacing)
        flexible_keyword = re.escape(keyword).replace(' ', r'\s+')
        patterns.append(rf"(?:\n|^)[ \t]*(?:Item\s*\d+[A-Z]?\.\s*)?{flexible_keyword}\s*[\.\:]?\s*(?:\n|$)")
    # For notes: match any 'Note X. ...' where ... contains a debt keyword
    note_pattern = rf"(?:\n|^)[ \t]*Note\s*\d+[A-Z]?\.\s*([A-Za-z0-9 ,&\-/]+)"
    note_regex = re.compile(note_pattern, re.IGNORECASE)
    note_matches = list(note_regex.finditer(text))
    debt_note_idx = None
    for match in note_matches:
        header = match.group(1).lower()
        if any(kw.lower() in header for kw in header_keywords):
            debt_note_idx = match.start()
            break
    # Combine all patterns
    combined_pattern = "|".join(f"({pattern})" for pattern in patterns)
    header_regex = re.compile(combined_pattern, re.IGNORECASE | re.MULTILINE)
    matches = list(header_regex.finditer(text))
    if debug:
        print(f"Looking for headers: {header_keywords}")
        print(f"Found {len(matches)} matches")
        for i, match in enumerate(matches):
            context_start = max(0, match.start() - 50)
            context_end = min(len(text), match.end() + 50)
            print(f"Match {i+1}: '{text[context_start:context_end]}'")
        print("\nAll note headers:")
        for match in note_matches:
            print(text[match.start():match.end()].strip())
    # Use the last match (most likely the real section, not TOC)
    start = None
    if debt_note_idx is not None:
        start = debt_note_idx
    elif matches:
        start = matches[-1].start()
    if start is None:
        return ""
    # Find the next major section header after this one
    next_section_patterns = [
        r"(?:\n|^)[ \t]*(?:Item\s*\d+[A-Z]?\.\s*)[A-Z][A-Za-z\s]{10,}(?:\n|$)",
        r"(?:\n|^)[ \t]*(?:Note\s*\d+[A-Z]?\.\s*)[A-Z][A-Za-z\s]{10,}(?:\n|$)",
        r"(?:\n|^)[ \t]*[A-Z][A-Z\s]{15,}(?:\n|$)",
        r"(?:\n|^)[ \t]*PART\s+[IVX]+",
        r"(?:\n|^)[ \t]*SIGNATURES?\s*(?:\n|$)",
    ]
    next_header = None
    for pattern in next_section_patterns:
        next_header = re.search(pattern, text[start+1:], re.IGNORECASE | re.MULTILINE)
        if next_header:
            break
    end = start + 1 + next_header.start() if next_header else None
    extracted = text[start:end].strip() if end else text[start:].strip()
    if debug:
        print(f"Extracted section length: {len(extracted)}")
        print(f"First 200 chars: {extracted[:200]}")
    return extracted

def extract_10q_sections(tenq_url: str, debug=False):
    """
    Extract debt and liquidity sections from 10-Q with improved parsing
    """
    try:
        resp = requests.get(tenq_url, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator="\n", strip=True)
        if debug:
            print(f"Total text length: {len(text)}")
            print(f"First 500 chars: {text[:500]}")
        # Comprehensive debt-related keywords
        debt_keywords = [
            "Debt", "Indebtedness", "Long-term Debt", "Short-term Debt", "Borrowings", "Credit Facilities", "Term Loans", "Revolving Credit", "Notes Payable", "Debt and Credit Facilities", "Credit Agreement"
        ]
        liquidity_keywords = [
            "Liquidity and Capital Resources", "Liquidity", "Capital Resources", "Cash and Cash Equivalents", "Working Capital", "Sources and Uses of Cash", "Cash Flow"
        ]
        debt_section = extract_section_by_header(text, debt_keywords, debug)
        liquidity_section = extract_section_by_header(text, liquidity_keywords, debug)
        return debt_section, liquidity_section
    except requests.RequestException as e:
        print(f"Error fetching 10-Q: {e}")
        return "", ""
    except Exception as e:
        print(f"Error parsing 10-Q: {e}")
        return "", ""

def print_note_headers(text):
    import re
    print("All note headers in document:")
    for match in re.finditer(r"(?:\n|^)[ \t]*Note\s*\d+[A-Z]?\.\s*[^\n]{3,50}", text, re.IGNORECASE):
        print(match.group(0).strip())

def get_laymanized_debt_liquidity(tenq_url: str, llm_client, debug=False):
    debt, liquidity = extract_10q_sections(tenq_url, debug)
    
    if debug:
        print(f"Debt section length: {len(debt)}")
        print(f"Liquidity section length: {len(liquidity)}")
    
    if not debt and not liquidity:
        return "No debt or liquidity sections found in the 10-Q filing."
    
    max_chars_per_section = 6000
    
    if len(debt) > max_chars_per_section:
        debt = debt[:max_chars_per_section] + "... [truncated]"
    if len(liquidity) > max_chars_per_section:
        liquidity = liquidity[:max_chars_per_section] + "... [truncated]"
    
    if debug:
        print("=== DEBT SECTION ===")
        print(debt[:500] if debt else "No debt section found")
        print("\n=== LIQUIDITY SECTION ===")
        print(liquidity[:500] if liquidity else "No liquidity section found")
    
    if not debt and not liquidity:
        return "No relevant sections found in the 10-Q filing."
    
    prompt = (
    'Below are the "Debt" and "Liquidity and Capital Resources" sections from a company 10-Q. '
    'Your ONLY task is to extract and list each credit facility or note in the following format, one per line:\n'
    'facility name @ (interest rate) mat. mm/yyyy (Lead Bank)\n'
    'For each facility, use the MAXIMUM COMMITTED AMOUNT or AVAILABILITY (not the current outstanding/borrowed amount), and use the OFFICIAL FACILITY NAME as listed in the 10-Q. '
    'If both are present, always prefer the commitment/maximum size. '
    'If the facility is a revolver, use the word "Revolver" if the 10-Q uses it. '
    'If the lead bank is not specified, omit the parentheses. '
    'If a field is missing, leave it blank but do not guess or invent. '
    'Do NOT include any other information, bullets, or narrative. '
    'Do NOT summarize liquidity, cash, or other financials. Only output the facilities in the format above. '
    'If no facilities are found, output: "No credit facilities disclosed."\n\n'
    'Examples of the exact format:\n'
    '$132M Revolver @ SOFR + 161–242 bps – mat. 12/2026 (Citibank)\n'
    '$350M Senior Secured Notes @ 7.875% – mat. 12/2028\n'
    '$200M Term Loan @ SOFR + 87.5-162.5 bps – mat. 6/2028 (WFC)\n'
    '$600M revolver @ SOFR + 79.5-137.5 bps – mat. 6/2030 (WFC)\n'
    '$20M – 3.79% Senior Notes – mat. 6/2025\n'
    '$600M revolver @ SOFR + 250-300 bps mat. 8/2026 (JPMorgan)\n'
    '$100M – 2.90% Senior Notes, Series B – mat. 7/2026\n'
    '$50M – 2.60% Senior Notes – mat. 3/2027\n'
    '$50M – 5.73% Senior Notes – mat. 4/2027\n\n'
    '---\n'
    f'DEBT SECTION:\n{debt}\n\nLIQUIDITY AND CAPITAL RESOURCES SECTION:\n{liquidity}'
)
    
    try:
        response = llm_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error processing with LLM: {e}"

# Helper function for debugging
def debug_10q_parsing(ticker: str):
    """
    Debug function to print only the extracted debt and liquidity sections and their lengths.
    """
    url = get_latest_10q_link_for_ticker(ticker)
    if url:
        debt, liquidity = extract_10q_sections(url, debug=False)
        print(f"Debt section ({len(debt)} chars):\n{'='*40}\n{debt}\n{'='*40}")
        print(f"Liquidity and Capital Resources section ({len(liquidity)} chars):\n{'='*40}\n{liquidity}\n{'='*40}")
    else:
        print("No 10-Q URL found")

#debug_10q_parsing("HCC")