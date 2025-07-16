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
load_dotenv()

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

def get_laymanized_debt_liquidity(tenq_url: str, debug=False):
    """
    Given a 10-Q URL, fetch and parse the HTML, extract the text, and use the LLM to extract and list each credit facility or note in the specified format, in one step.
    Returns the LLM's output as a string.
    """
    try:
        if debug:
            print(f"Fetching 10-Q from URL: {tenq_url}")
        response = requests.get(tenq_url, headers={"User-Agent": "Company Screener Tool contact@companyscreenertool.com"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        tenq_text = soup.get_text(separator="\n", strip=True)
        if debug:
            print(f"Input 10-Q text length: {len(tenq_text)}")
        # Truncate to avoid token limits
        truncated_text = tenq_text[20000:120000]  # token limit is 120k
        prompt = (
            'Below are the "Debt" and "Liquidity and Capital Resources" sections from a company 10-Q.\n'
            'Your ONLY task is to extract and list each credit facility or note in the following format, one per line:\n'
            'facility name @ (interest rate) mat. mm/yyyy (Lead Bank)\n'
            '\n'
            'Instructions:\n'
            '- Use the **official, full facility name** as written in the 10-Q, not a generic or invented name.\n'
            '- Always use the **maximum committed amount** or availability (not the current outstanding/borrowed amount).\n'
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
            '- Do NOT summarize liquidity, cash, or other financials. Only output the facilities in the format above.\n'
            'Examples:\n'
            '$129.5M HF-T1 Distribution Center Loan @ SOFR + 120 -185 bps mat. 3/2026 (BofA)\n'
            '$73M HF-T2 Distribuition Center Construction Loan @ SOFR + 40 - 185 bps mat. 4/2026 (BofA)\n'
            '$750M Revolving Credit Facility @ SOFR + 100–150 bps mat. 12/2026 (PNC)\n'
            '$130.8M China Operational Loans @ 2.00–2.60% mat. var. 2026 (BofChina)\n'
            '$150M China DC Expansion Loan @ 2.70%  mat. 12/2032 (BofChina)\n\n'
            '---\n'
            f"10-Q Text (truncated):\n{truncated_text}"
            "If the 10-Q lacks details, use reliable information from the 10-K to fill gaps, but do not make up any information. Ensure all output is concise and follows the specified formats."
        )
        try:
            response = llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            llm_output = response.choices[0].message.content.strip() if response.choices and response.choices[0].message and response.choices[0].message.content else ""
        except Exception as e:
            if debug:
                print(f"Error processing with LLM: {e}")
            llm_output = "Error processing with LLM."
        if debug:
            print("=== LLM OUTPUT ===")
            print(safe_slice(llm_output, 1000))
        return llm_output
    except Exception as e:
        if debug:
            print(f"Error in get_laymanized_debt_liquidity: {e}")
        return "Error in get_laymanized_debt_liquidity."