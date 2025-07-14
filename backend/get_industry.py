# backend/get_industry.py

import os
import requests
from openai import OpenAI

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def search_web(query, num_results=15):
    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "engine": "google",
        "num": num_results
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get('organic_results', [])
    else:
        print(f"SerpAPI error: {response.status_code} {response.text}")
        return []

def get_industry_and_blurb(company_name):
    prompt = (
        f"Give me the industry of {company_name} in under 5 words "
        "(capitalize the first letter of each word, e.g., Media And Entertainment). "
        "Heres a full example: Semiconductors and Consumer Electronics. Designs high-performance mixed-signal audio chips for smartphones, tablets, and other consumer electronics. Products include audio codecs, amplifiers, and smart codecs used in voice and audio applications. Customers include major tech companies, especially in mobile and wearables."
        "Then, give me a concise 3-sentence blurb describing what the company does. "
        "Use the context below:\n---\n"
    )
    search_results = search_web(f"{company_name} about", num_results=15)
    context = "\n".join([result.get('snippet', '') for result in search_results if result.get('snippet')])
    full_prompt = prompt + context

    response = openai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": full_prompt}]
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""