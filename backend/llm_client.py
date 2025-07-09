# backend/llm_client.py
import os
import openai
from dotenv import load_dotenv

load_dotenv()

# Switch base_url and model here only
USE_OPENROUTER = True

if USE_OPENROUTER:
    openai.base_url = "https://openrouter.ai/api/v1"
    openai.api_key = os.environ["OPENROUTER_API_KEY"]
    DEFAULT_MODEL = "mistralai/mistral-small-3.2-24b-instruct:free"
else:
    openai.api_key = os.environ["OPENAI_API_KEY"]
    DEFAULT_MODEL = "gpt-4o"

client = openai.OpenAI()

print("USE_OPENROUTER:", USE_OPENROUTER)

def get_execs_via_llm(ticker: str, company_name: str) -> str:
    system_prompt = "You are a helpful AI that extracts executive team members from a public company."
    user_prompt = f"Who are the CEO, CFO, and Treasurer of {company_name} ({ticker})? Please include their full name and role."

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content
    return content.strip() if content else ""
