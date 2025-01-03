import os
import asyncio
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from sanic.log import logger
import google.generativeai as genai
import logging
import json
from ..Prompt.dom_vision_prompts import DomVisionPrompts

# Configure the logger
logger = logging.getLogger('gemini_generator_logger')
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s **[%(levelname)s]**|| %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class GeminiGenerator:
    def __init__(self, model=None, system_instruction=None):
        self.model = model
        self.system_instruction = system_instruction
        self.pool = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)

    async def request(self, messages: list = None, max_tokens: int = 500, temperature: float = 0.7) -> (str, str):
       
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                self.pool,
                partial(self.chat, messages, max_tokens, temperature)
            )
            return response, ""
        except Exception as e:
            logger.error(f"Error in GeminiGenerator.request: {e}")
            return "", str(e)

    def chat(self, messages, max_tokens=500, temperature=0.7):
        """
        Process messages and interact with the Gemini API.

        :param messages: List of messages to send.
        :param max_tokens: Maximum number of tokens in the response.
        :param temperature: Sampling temperature.
        :return: Response text from the API.
        """
        systemPlanningMessage = DomVisionPrompts.d_v_planning_prompt_system
        systemRewardMessage = DomVisionPrompts.current_d_vision_reward_prompt_system
        try:
            logger.debug("Entering chat method.")
            if not messages:
                logger.debug("No messages provided to the chat method.")
                return ""

            chat_history = []

            # If system instructions are provided, include them in the chat history as a special user message
            if self.system_instruction:
                chat_history.append({
                    "role": "user",
                    "parts": [{"text": self.system_instruction}]
                })

            for idx, message in enumerate(messages):
                role = message.get("role")
                content = message.get("content")
                

                if role not in ["user", "assistant"]:
                    logger.warning(f"Unsupported role: {role}. Skipping this message.")
                    continue
                

                if isinstance(content, str):
                    # Simple text message
                    parts = [{"text": content}]
                elif isinstance(content, list):
                    # List of parts (e.g., text and images)
                    parts = []
                    for part in content:
                        part_type = part.get("type")
                        part_text = part.get("text")
                        if part_type == "text":
                            parts.append({"text": part_text})
                        elif part_type == "image_url":
                            # Handle image data using 'inline_data'
                            # if part_text and part_text.startswith("data:"):
                            if part_text:
                                # Parse data URL
                                try:
                                    header, data = part_text.split(",", 1)
                                    mime_type = header.split(";")[0][5:]  # Extract MIME type
                                    parts.append({
                                        "inline_data": {
                                            "mime_type": mime_type,
                                            "data": data
                                        }
                                    })
                                except Exception as e:
                                    logger.error(f"Failed to parse image data URL: {e}")
                            else:
                                # If not a data URL, log a warning
                                logger.warning("Image URL is not a data URL. Skipping this image.")
                        else:
                            logger.warning(f"Unsupported part type: {part_type}. Skipping this part.")
                else:
                    logger.warning(f"Unsupported content type: {type(content)}. Skipping this message.")
                    continue

                chat_history.append({
                    "role": role,
                    "parts": parts
                })

            try:
                running_model = genai.GenerativeModel(self.model,system_instruction=systemPlanningMessage)
                chat = running_model.start_chat(history=chat_history)
                latest_user_message = self._extract_latest_user_message(messages)

                response = chat.send_message(
                    latest_user_message,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature
                    )
                )

                # Access the response text directly
                response_text = getattr(response, 'text', '')  # Adjust based on actual attribute
                return response_text  # Return the text instead of the dictionary

            except Exception as e:
                logger.error(f"Exception after chat_history: {e}")
                return ""

        except Exception as e:
            logger.error(f"Exception in chat method: {e}")
            return ""

    def _extract_latest_user_message(self, messages):
        """
        Extracts the latest user message content.
        Assumes the last message in the list is the latest.

        :param messages: List of messages.
        :return: Latest user message content as a string.
        """
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Return the last text part
                    for part in reversed(content):
                        if part.get("type") == "text":
                            return part.get("text")
        return ""
