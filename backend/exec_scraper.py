# backend/exec_scraper.py

import os
from typing import List
from dotenv import load_dotenv

from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from serpapi import GoogleSearch

# Load environment variables from .env file
load_dotenv()

# Set up OpenAI client for either official OpenAI or OpenRouter API
USE_OPENROUTER = os.environ.get("USE_OPENROUTER", "False").lower() in ("1", "true", "yes")

if USE_OPENROUTER:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
    )
    MODEL = os.getenv("MODEL_NAME", "openrouter/quasar-alpha")
else:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    MODEL = "gpt-4o"

SYSTEM_PROMPT: ChatCompletionSystemMessageParam = {
    "role": "system",
    "content": (
        "You are a helpful assistant that extracts executive information for public companies. "
        "When asked about a company's executives, provide the current CEO, CFO, and Treasurer. "
        "If they don't have a Treasurer on their site, put 'same' under Treasurer. "
        "Make sure you are looking at the latest news (for example if a new person was appointed recently) "
        "and give the result in this exact format:\n"
        "CEO: [Name]\n"
        "CFO: [Name]\n"
        "Treasurer (or closest): [Name or 'same']"
    ),
}

def get_execs_via_gpt(ticker: str, company_name: str) -> List[str]:
    try:
        query = (
            f"I need to do a public screen on {company_name} ({ticker}). "
            f"Tell me their current CEO, CFO, and Treasurer. "
            f"If they don't have a treasurer on their site, just put 'same' under treasurer. "
            f"Make sure you are looking at the latest news (for ex if a new person was appointed recently) "
            f"and give me the result as:\n"
            f"CEO: ...\n"
            f"CFO: ...\n"
            f"Treasurer (or closest): ..."
        )

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": query},
            ],
            temperature=0.2,
        )
        print("LLM raw response:", response)
        text = response.choices[0].message.content
        if not text:
            print(f"No response content for {ticker}")
            return []

        lines = [line.strip("- ").strip() for line in text.split("\n") if line.strip()]
        return lines
    except Exception as e:
        print(f"Error getting executives for {ticker}: {e}")
        return []

import requests

def get_executives_from_api(ticker):
    # Example using a finance API or scraping Yahoo Finance
    # Or use SerpAPI to search "CEO of {company}"
    # Fallback to LLM if not found
    pass

def get_executives_via_llm(company, ticker):
    prompt = f"""I need to do a public screen on {company} ({ticker}). Tell me their current CEO, CFO, and Treasurer. If they don't have a treasurer on their site, just put "same" under treasurer. I want just the information I’m asking for in this format, no extra words or info. Make sure you are looking at the latest news (for ex if a new person was appointed recently) and give me the result as:
CFO: ...
Treasurer (or closest): ...
CEO: ..."""
    # Call your LLM here
    pass

# Combine both for best results

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def get_executives_from_serpapi(company):
    query = f"{company} executive team"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    # Try to extract names from the organic results/snippets
    execs = []
    for result in results.get("organic_results", []):
        snippet = result.get("snippet", "")
        # Simple heuristic: look for CEO, CFO, Treasurer in snippet
        for role in ["CEO", "CFO", "Treasurer"]:
            if role in snippet:
                execs.append(snippet)
    return execs

def format_executives_with_llm(company, ticker, exec_snippets):
    prompt = (
        f"Given the following information about {company} ({ticker}):\n"
        + "\n".join(exec_snippets) +
        "\nExtract the current CEO, CFO, and Treasurer. "
        "If Treasurer is not found, put 'same' under Treasurer. "
        "Format the answer as:\n"
        "CFO: ...\nTreasurer (or closest): ...\nCEO: ..."
    )
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",  # or your preferred model
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""

def get_executives(company, ticker):
    exec_snippets = get_executives_from_serpapi(company)
    if not exec_snippets:
        return "No executive info found in search results."
    return format_executives_with_llm(company, ticker, exec_snippets)

# Example usage:
if __name__ == "__main__":
    print(get_executives("Amazon", "AMZN"))
