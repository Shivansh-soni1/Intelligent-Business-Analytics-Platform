import os
import json
import urllib.request
import urllib.error

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class LLMService:
    """Environment-configured HTTP client for LLM chat completions."""

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")

        # Updated default to a standard supported Groq production model
        self.model = os.getenv(
            "LLM_MODEL",
            "llama-3.3-70b-versatile"
        )

        self.base_url = os.getenv(
            "LLM_BASE_URL",
            "https://api.groq.com/openai/v1/chat/completions"
        )

    def completion(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False
    ) -> str:
        """Send a chat completion request to the configured LLM."""

        if not self.api_key:
            raise ValueError(
                "LLM_API_KEY environment variable is missing."
            )

        # Groq requires the string 'json' inside prompt messages when json_mode is active
        final_system_prompt = system_prompt
        if json_mode and "json" not in system_prompt.lower() and "json" not in user_prompt.lower():
            final_system_prompt += "\nRespond strictly in valid JSON format."

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "DataAnalystBot/1.0"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": final_system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "temperature": 0.1 if json_mode else 0.4
        }

        if json_mode:
            payload["response_format"] = {
                "type": "json_object"
            }

        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                response_data = response.read().decode("utf-8")
                result = json.loads(response_data)

                # Null-safe content extraction
                message_content = result["choices"][0]["message"].get("content")
                if message_content is None:
                    return ""
                
                return message_content.strip()

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(
                f"LLM API Error ({e.code}): {error_body}"
            ) from e

        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Network error while connecting to LLM: {e.reason}"
            ) from e

        except json.JSONDecodeError as e:
            raise RuntimeError(
                "LLM returned an invalid JSON response payload."
            ) from e

        except (KeyError, IndexError) as e:
            raise RuntimeError(
                f"Unexpected LLM response structure: missing key {e}"
            ) from e

        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to LLM provider: {str(e)}"
            ) from e