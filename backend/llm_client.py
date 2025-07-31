# llm_client.py

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def get_llm_client() -> OpenAI:
    """
    Returns an OpenAI client instance configured for OpenAI or OpenRouter.
    """
    use_openrouter = os.getenv("USE_OPENROUTER", "false").lower() == "true"
    if use_openrouter:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENROUTER_API_KEY.")
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY.")
        return OpenAI(api_key=api_key)

def get_model_name() -> str:
    """
    Returns the model name to use for the LLM call.
    Defaults to 'gpt-4.1-nano' if not specified.
    """
    return os.getenv("MODEL_NAME", "gpt-4.1-nano")
