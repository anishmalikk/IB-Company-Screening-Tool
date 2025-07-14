import json
import os

def get_cik_for_ticker(ticker: str) -> str:
    with open(os.path.join(os.path.dirname(__file__), "company_tickers.json")) as f:
        data = json.load(f)
    ticker = ticker.upper()
    for entry in data.values():
        if entry["ticker"].upper() == ticker:
            return str(entry["cik_str"])
    return ""