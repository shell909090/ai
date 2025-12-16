"""Google Gemini vision provider implementation."""

import os
import json
import logging
from typing import Optional
import google.generativeai as genai
import typing_extensions as typing
from PIL import Image
from .base import VisionProvider


class CropResult(typing.TypedDict):
    """Type definition for Gemini structured output."""
    box_2d: list[float]


class GeminiProvider(VisionProvider):
    """Google Gemini vision API provider."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        """
        Initialize Gemini provider.

        Args:
            model_name: Gemini model to use (default: gemini-2.5-flash)

        Raises:
            ValueError: If GEMINI_API_KEY environment variable is not set
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set. "
                "Please set it with your Gemini API key."
            )

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name

    def analyze_image(
        self,
        image: Image.Image,
        prompt: str,
        max_retries: int = 3
    ) -> Optional[dict]:
        """
        Analyze image using Gemini's structured output.

        Args:
            image: PIL Image to analyze
            prompt: Text prompt describing the analysis task
            max_retries: Maximum number of retry attempts

        Returns:
            dict with 'box_2d' key containing [xmin, ymin, xmax, ymax]
            normalized coordinates, or None on failure
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logging.warning(f"重试第 {attempt} 次...")

                response = self.model.generate_content(
                    [prompt, image],
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=CropResult
                    ))

                result_json = json.loads(response.text)
                return result_json

            except Exception as e:
                logging.error(f"Gemini 分析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return None

        return None

    def get_provider_name(self) -> str:
        """Return provider name for logging."""
        return f"Gemini ({self.model_name})"
