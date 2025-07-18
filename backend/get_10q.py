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
load_dotenv()


TARGET_SECTIONS = {
    "debt": ["debt", "credit agreement", "credit facilities", "notes payable", "indebtedness", "long-term debt"],
    "liquidity": ["liquidity", "capital resources", "financial condition", "cash flows"]
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
    return False

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

#Local testing in IDE:
if __name__ == "__main__":
    # You can change the ticker here for testing
    test_ticker = "GIC"
    debug = False
    print(f"Testing get_latest_10q_link_for_ticker for ticker: {test_ticker}")
    link = get_latest_10q_link_for_ticker(test_ticker)
    print(f"Latest 10-Q link: {link}")
    if link:
        print("\nLaymanized Debt/Liquidity Summary:")
        summary = get_laymanized_debt_liquidity(link, debug=debug)
        if not debug:
            print(summary)
    else:
        print("No 10-Q link found.")

