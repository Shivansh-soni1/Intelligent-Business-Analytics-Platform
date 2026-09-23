from services.llm_service import LLMService

print("Testing LLM connection...")

try:
    llm = LLMService()

    print("Model:", llm.model)
    print("API Key available:", bool(llm.api_key))
    print("Base URL:", llm.base_url)

    print("\nSending request...")

    response = llm.completion(
        system_prompt="You are a helpful AI assistant.",
        user_prompt="Say hello in one short sentence."
    )

    print("\nLLM Response:")
    print(response)

except Exception as e:
    print("\nERROR:")
    print(e)