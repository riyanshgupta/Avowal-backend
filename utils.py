import asyncio
import traceback
from typing import Any, Dict
import logging
import aiohttp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
class LLM_analyzer:
    def __init__(self, system_prompt: str, gemini_api_key: str, open_router_api_key: str):
        self.system_prompt = system_prompt
        self.allowed_models = [
            "gemini-2.5-flash",
            "openai/gpt-oss-120b",
            "sarvamai/sarvam-m",
            "gemini-2.0-flash",
            "deepseek/deepseek-chat-v3.1",
            "gemini-2.5-flash-lite",
            "z-ai/glm-4.5-air", 
            "moonshotai/kimi-k2",
            "tngtech/deepseek-r1t2-chimera", 
            "deepseek/deepseek-r1-0528-qwen3-8b",  
            "tngtech/deepseek-r1t-chimera", 
            "microsoft/mai-ds-r1",
            "gemini-2.0-flash-lite",
            "gemini-2.5-pro",
            "venice/uncensored"
        ]
        self.max_retries = 5
        
        # Validate API keys
        if not gemini_api_key or gemini_api_key == "None":
            logging.warning("Gemini API key is not set or is None")
            self.gemini_api_key = None
        else:
            self.gemini_api_key = gemini_api_key
            
        if not open_router_api_key or open_router_api_key == "None":
            logging.warning("OpenRouter API key is not set or is None")
            self.open_router_api_key = None
        else:
            self.open_router_api_key = open_router_api_key
            
        # Check if at least one API key is available
        if not self.gemini_api_key and not self.open_router_api_key:
            logging.error("No API keys available for LLM analysis")
            raise ValueError("At least one API key (Gemini or OpenRouter) must be provided")

    def _extract_text(self, json_str: Dict[str, Any]) -> str | None:
        try:
            return json_str["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            # try with open-router response format
            try:
                return json_str['choices'][0]['message']['content']
            except Exception as e:
                logging.error(f"Error extracting text from response: {e}")
            return None
    
    async def _llm_call(
        self,
        user_prompt: str, model: str):
        try:
            if model.startswith("gemini"):
                if not self.gemini_api_key:
                    raise ValueError(f"Gemini API key not available for model {model}")
                    
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.gemini_api_key,
                }
                data = {
                    "systemInstruction": {
                        "parts": [
                            {"text": self.system_prompt}
                        ]
                    },
                    "contents": [
                        {
                            "parts": [
                                {"text": user_prompt}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "text/x.enum",
                        "responseSchema": {
                        "type": "STRING",
                        "enum": ["APPROVE", "REJECT"]
                        }
                    }
                }
                response = await self._api_call(url, data, headers)
                return response
            else:
                if not self.open_router_api_key:
                    raise ValueError(f"OpenRouter API key not available for model {model}")
                    
                # Using open-router for non-Gemini models
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.open_router_api_key}",
                }
                data = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": self.system_prompt + "\nRemember, your final output is ONLY `APPROVE` or `REJECT`.\n",
                        },
                        {
                            "role": "user",
                            "content": user_prompt,
                        }
                    ]
                }
                response = await self._api_call(url, data, headers)
                return response
        except Exception as e:
            logging.error(f"Error occurred at analyze_confession_with_llm: {e}")
            raise e

    async def _api_call(self, url: str, data: Dict[str, str], headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Placeholder function simulating a call to an LLM API (like Gemini).

        Args:
            data (Dict[str, str]): The payload for the API request.
            url (str): The API endpoint URL.
            headers (Dict[str, str]): Headers for the API request.

        Returns:
            dict: Simulated response from the LLM API.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as resp:
                    resp.raise_for_status()
                    res = await resp.json()
                    return res
        except Exception as e:
            logging.error(f"Error occurred while calling LLM API: {e}")
            raise e

    async def analyze_confession(self, user_prompt: str):
        """ Analyzes a confession using the specified LLM model."""
        i, max_retries = 0, self.max_retries
        available_models = []
        
        # Filter available models based on API keys
        for model in self.allowed_models:
            if model.startswith("gemini") and self.gemini_api_key:
                available_models.append(model)
            elif not model.startswith("gemini") and self.open_router_api_key:
                available_models.append(model)
        
        if not available_models:
            raise ValueError("No models available due to missing API keys")
        
        tasks = []
        for i in range(4):
            try:
                model = available_models[i % len(available_models)]
                tasks.append(asyncio.create_task(self._llm_call(user_prompt=user_prompt, model=model)))
            except Exception as e:
                logger.error(f"Error occurred at analyze_confession: {e}")
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        flag, all_failed = False, True
        for res in results:
            if isinstance(res, dict):
                all_failed = False
                flag |= self._extract_text(res)=="APPROVE"      # If any model approves, we approve
                logger.info(f"Model {model} response: {res}")

        if flag==False and not all_failed:
            return "REJECT"
        elif all_failed:
            logger.error(f"All model calls failed {results}")
            return "APPROVE"
        
        return "APPROVE"
    
        # while max_retries != i:
        #     try:
        #         model = available_models[i % len(available_models)]
        #         res = await self._llm_call(
        #             user_prompt=user_prompt,
        #             model=model,
        #         )
        #         return self._extract_text(res)
        #     except Exception as e:
        #         logging.error(f"Error occurred at analyze_confession: {e}")
        #         i += 1
        #         if max_retries == i:
        #             raise e
