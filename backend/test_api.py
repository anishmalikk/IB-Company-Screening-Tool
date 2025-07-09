import os
from exec_scraper import get_execs_via_gpt

# Test the API call
def test_api():
    try:
        result = get_execs_via_gpt("AAPL", "Apple Inc.")
        print("Success!")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_api() 