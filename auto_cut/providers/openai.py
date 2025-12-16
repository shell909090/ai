"""OpenAI vision provider implementation."""

import os
import json
import logging
import base64
from typing import Optional
from io import BytesIO
from PIL import Image
from openai import OpenAI
from .base import VisionProvider


class OpenAIProvider(VisionProvider):
    """OpenAI vision API provider using GPT-4o."""

    def __init__(self, model_name: str = "gpt-4o"):
        """
        Initialize OpenAI provider.

        Environment variables:
        - OPENAI_API_KEY (required): OpenAI API key
        - OPENAI_ENDPOINT (optional): Custom API endpoint (e.g., for Azure OpenAI or local models)

        Args:
            model_name: OpenAI model to use (default: gpt-4o)

        Raises:
            ValueError: If OPENAI_API_KEY environment variable is not set
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Please set it with your OpenAI API key."
            )

        # Support custom endpoint (e.g., Azure OpenAI, local models, proxies)
        base_url = os.getenv("OPENAI_ENDPOINT")

        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.endpoint = base_url
            logging.info(f"Using custom OpenAI endpoint: {base_url}")
        else:
            self.client = OpenAI(api_key=api_key)
            self.endpoint = "https://api.openai.com/v1"

        self.model_name = model_name

    def _encode_image_to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL Image to base64 string for OpenAI API.

        Args:
            image: PIL Image to encode

        Returns:
            Base64 encoded string
        """
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def analyze_image(
        self,
        image: Image.Image,
        prompt: str,
        max_retries: int = 3
    ) -> Optional[dict]:
        """
        Analyze image using OpenAI's structured output.

        Args:
            image: PIL Image to analyze
            prompt: Text prompt describing the analysis task
            max_retries: Maximum number of retry attempts

        Returns:
            dict with 'box_2d' key containing [xmin, ymin, xmax, ymax]
            normalized coordinates, or None on failure
        """
        base64_image = self._encode_image_to_base64(image)

        # Define JSON schema for structured output
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "crop_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "box_2d": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 4,
                            "maxItems": 4,
                            "description": "Normalized bounding box [xmin, ymin, xmax, ymax]"
                        }
                    },
                    "required": ["box_2d"],
                    "additionalProperties": False
                }
            }
        }

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logging.warning(f"重试第 {attempt} 次...")

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    response_format=response_format,
                    max_tokens=8192
                )

                for c in response.choices:
                    print(c.message)

                result_json = json.loads(response.choices[0].message.content)
                return result_json

            except Exception as e:
                logging.error(f"OpenAI 分析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return None

        return None

    def get_provider_name(self) -> str:
        """Return provider name for logging."""
        return f"OpenAI ({self.model_name})"
