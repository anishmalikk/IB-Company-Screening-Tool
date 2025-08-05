import os
import json
from typing import Optional, List, Dict, Any
from serpapi.google_search import GoogleSearch
from dotenv import load_dotenv
from llm_client import get_llm_client, get_model_name

load_dotenv()

def search_company_credit_rating(company_name: str) -> List[Dict[str, Any]]:
    """
    Search for a company's S&P credit rating using SerpAPI.
    
    Args:
        company_name: The name of the company to search for
        
    Returns:
        List of search results with snippets
    """
    try:
        # Configure the search parameters
        search_params = {
            "q": f"{company_name} S&P credit rating",
            "api_key": os.getenv("SERPAPI_API_KEY"),
            "engine": "google",
            "num": 10,  # Get up to 10 results
            "gl": "us",  # Search in US
            "hl": "en"   # English language
        }
        
        # Perform the search
        search = GoogleSearch(search_params)
        results = search.get_dict()
        
        # Extract organic results
        organic_results = results.get("organic_results", [])
        
        # Extract snippets and titles
        snippets = []
        for result in organic_results:
            snippet_data = {
                "title": result.get("title", ""),
                "snippet": result.get("snippet", ""),
                "link": result.get("link", ""),
                "date": result.get("date", "")
            }
            snippets.append(snippet_data)
            
        return snippets
        
    except Exception as e:
        print(f"Error searching for credit rating: {e}")
        return []

def extract_credit_rating_from_snippets(company_name: str, snippets: List[Dict[str, Any]]) -> str:
    """
    Use GPT to extract the latest S&P credit rating from search snippets.
    
    Args:
        company_name: The name of the company
        snippets: List of search result snippets
        
    Returns:
        The latest credit rating or "N/A" if not found
    """
    if not snippets:
        return "N/A"
    
    try:
        client = get_llm_client()
        model_name = get_model_name()
        
        # Prepare the snippets for GPT
        snippets_text = ""
        for i, snippet in enumerate(snippets, 1):
            snippets_text += f"Result {i}:\n"
            snippets_text += f"Title: {snippet.get('title', '')}\n"
            snippets_text += f"Snippet: {snippet.get('snippet', '')}\n"
            snippets_text += f"Link: {snippet.get('link', '')}\n"
            if snippet.get('date'):
                snippets_text += f"Date: {snippet.get('date', '')}\n"
            snippets_text += "\n"
        
        # Create the prompt for GPT
        prompt = f"""Based on the following search results for {company_name}'s S&P credit rating, determine the latest credit rating.

Search Results:
{snippets_text}

Instructions:
1. Look for the most recent S&P credit rating for {company_name}
2. Focus on official S&P ratings (e.g., BBB+, AA-, etc.)
3. If multiple ratings are found, choose the most recent one
4. If no S&P credit rating is found, return "N/A"
5. Return ONLY the rating (e.g., "BBB+", "AA-", "N/A") without any additional text

Latest S&P Credit Rating:"""

        # Make the API call
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial analyst specializing in credit ratings. Extract only the latest S&P credit rating from the provided search results. Return only the rating or 'N/A' if not found."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,  # Low temperature for more consistent results
            max_tokens=50
        )
        
        # Extract the response
        rating = response.choices[0].message.content.strip()
        
        # Clean up the response to ensure it's just the rating
        if rating.lower() in ["n/a", "not available", "none found", "no rating"]:
            return "N/A"
        
        # Remove any extra text and return just the rating
        rating = rating.replace("Latest S&P Credit Rating:", "").strip()
        if not rating or rating == "":
            return "N/A"
            
        return rating
        
    except Exception as e:
        print(f"Error extracting credit rating: {e}")
        return "N/A"

def get_company_credit_rating(company_name: str) -> str:
    """
    Main function to get a company's S&P credit rating.
    
    Args:
        company_name: The name of the company to search for
        
    Returns:
        The latest S&P credit rating or "N/A" if not found
    """
    print(f"Searching for {company_name}'s S&P credit rating...")
    
    # Search for credit rating information
    snippets = search_company_credit_rating(company_name)
    
    if not snippets:
        print("No search results found.")
        return "N/A"
    
    print(f"Found {len(snippets)} search results. Analyzing with GPT...")
    
    # Extract the credit rating using GPT
    rating = extract_credit_rating_from_snippets(company_name, snippets)
    
    print(f"Credit rating for {company_name}: {rating}")
    return rating

def main():
    """
    Main function for testing the credit rating functionality.
    """
    # Check if SERPAPI_API_KEY is set
    if not os.getenv("SERPAPI_API_KEY"):
        print("Error: SERPAPI_API_KEY environment variable is not set.")
        print("Please set your SerpAPI key to use this functionality.")
        return
    
    # Test with a sample company
    test_company = "Outfront Media Capital Inc"
    rating = get_company_credit_rating(test_company)
    print(f"\nFinal result: {test_company} - {rating}")

if __name__ == "__main__":
    main()
