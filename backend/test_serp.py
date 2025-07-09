# test_serpapi.py
from serpapi.google_search import GoogleSearch

params = {
  "engine": "google",
  "q": "Apple Inc. leadership team",
  "api_key": "YOUR_SERPAPI_KEY",  # Replace this or set via .env
  "num": 3
}

search = GoogleSearch(params)
results = search.get_dict()
print(results)
