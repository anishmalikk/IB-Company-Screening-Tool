import os
from dotenv import load_dotenv
from openai import OpenAI
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    logger.error("OPENAI_API_KEY not found in environment variables.")
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)
model = "gpt-4o-mini"

# Test prompt
test_prompt = "Hello, can you confirm this API is working by responding with a simple greeting? and tell me what model you are"

try:
    logger.info(f"Sending test prompt to {model}: {test_prompt[:50]}...")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": test_prompt}],
        max_tokens=100,
        temperature=0.7
    )
    content = response.choices[0].message.content
    result = content.strip() if content else "None"
    logger.info("API test successful.")
    print(f"API Response: {result}")

except Exception as e:
    logger.error(f"Error testing API: {str(e)}")
    print(f"Test failed: {str(e)}")