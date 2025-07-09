from serpapi.google_search import GoogleSearch

params = {
    "engine": "google",
    "q": "CEO Nvidia site:linkedin.com/in",
    "api_key": "your_api_key_here"
}

search = GoogleSearch(params)
print(search.get_dict())