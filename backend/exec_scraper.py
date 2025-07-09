# backend/exec_scraper.py

import os
from typing import List
from dotenv import load_dotenv

from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

# Load environment variables from .env file
load_dotenv()

# Set up OpenAI client for either official OpenAI or OpenRouter API
USE_OPENROUTER = os.environ.get("USE_OPENROUTER", "False").lower() in ("1", "true", "yes")

if USE_OPENROUTER:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
    )
    MODEL = "morph/morph-v3-fast"  # Try this model
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
