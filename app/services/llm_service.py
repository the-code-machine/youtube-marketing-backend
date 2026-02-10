import os
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMService:
    def __init__(self):
        # LOAD DEEPSEEK CONFIG
        self.api_key = os.getenv("DEEPSEEK_API_KEY") 
        self.base_url = os.getenv("DEEPSEEK_BASE_URL")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

        # Initialize Client with Custom Base URL
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url  # <--- CRITICAL: Points to DeepSeek servers
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_outreach(self, system_prompt: str, user_context: str):
        """
        Generates personalized email/DM content.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_context}
                ],
                temperature=0.7,
                max_tokens=300,
                stream=False
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"LLM Error: {e}")
            raise e
# llm = LLMService()
# msg = llm.generate_outreach("You are a sponsor...", "Channel: TechGuy, Video: Python Tutorial")