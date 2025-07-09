from openai import OpenAI
import os

def test_openrouter_call():
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key="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"
    )

    response = client.chat.completions.create(
        model="morph/morph-v3-fast",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Who is the treasurer of Amazon?"}
        ]
    )

    print(response.choices[0].message.content)
    assert response.choices[0].message.content != ""





