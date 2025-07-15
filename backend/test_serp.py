import requests
from bs4 import BeautifulSoup
import re
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI
from ticker_utils import get_cik_for_ticker  # Your existing utility
from sec_edgar_api.EdgarClient import EdgarClient
from bs4 import Tag
from dotenv import load_dotenv
from itertools import islice
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
llm_client = OpenAI(api_key=OPENAI_API_KEY)
edgar = EdgarClient(user_agent="Company Screener Tool contact@companyscreenertool.com")


def safe_slice(val, n=500):
    s = str(val) if val is not None else ""
    return s[:n]


def get_latest_10q_link_for_ticker(ticker: str) -> str:
    """Fetch the latest 10-Q URL from SEC EDGAR."""
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


def extract_10q_sections(tenq_text: str, debug=False):
    """
    Given the full text of a 10-Q, use the LLM to extract and list each credit facility or note in the specified format, in one step.
    Returns the LLM's output as a string.
    """
    try:
        if debug:
            print(f"Input 10-Q text length: {len(tenq_text)}")
        # Truncate to avoid token limits
        truncated_text = tenq_text[20000:120000]  # token limit is 120k
        prompt = (
            'Below are the "Debt" and "Liquidity and Capital Resources" sections from a company 10-Q. '
            'Your ONLY task is to extract and list each credit facility or note in the following format, one per line:\n'
            'facility name @ (interest rate) mat. mm/yyyy (Lead Bank)\n'
            'IMPORTANT: Look carefully through the ENTIRE text for credit facilities. The information may be in tables, footnotes, or narrative sections. '
            'For each facility, use the MAXIMUM COMMITTED AMOUNT or AVAILABILITY (not the current outstanding/borrowed amount), and use the OFFICIAL FACILITY NAME as listed in the 10-Q. '
            'If both are present, always prefer the commitment/maximum size. '
            'If the facility is a revolver, use the word "Revolver" if the 10-Q uses it. '
            'If the lead bank is not specified, omit the parentheses. '
            'If a field is missing, put "unknown" or skip it where appropriate, but do not guess or invent. '
            'Look for information about: ABL facilities, revolvers, term loans, senior notes, credit agreements, borrowing capacity, and availability. '
            'Do NOT include any other information, bullets, or narrative. '
            'Do NOT summarize liquidity, cash, or other financials. Only output the facilities in the format above. '
            'If no facilities are found, output: "No credit facilities disclosed."\n\n'
            'Examples of the format:\n'
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
            f"10-Q Text (truncated):\n{truncated_text}"
            "If the 10-Q lacks details, use reliable sources to fill gaps, but do not make up any information. Ensure all output is concise and follows the specified formats."
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
            print(f"Error in extract_10q_sections: {e}")
        return "Error in extract_10q_sections."