from pathlib import Path
from typing import Any

from ..core.base import Extractor
from ..core.registry import registry

_IMAGE_MIMES = (
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/bmp",
    "image/webp",
    "image/gif",
)

_DEFAULT_EXTRACT_PROMPT = (
    "Extract all text visible in this image verbatim. "
    "Output only the extracted text, no commentary."
)
_DEFAULT_DESCRIBE_PROMPT = "Describe the content of this image in detail."


@registry.register(*_IMAGE_MIMES)
class OpenAIVisionExtractor(Extractor):
    """Extract text or describe image content via OpenAI Vision API.

    Config keys:
      mode   (str): "extract_text" (default) | "describe".
                    "extract_text" → OCR-style text extraction.
                    "describe"     → natural-language description of image content.
      model  (str): OpenAI model with vision support. Default: "gpt-4o".
      prompt (str): Override the default system prompt for the chosen mode.
    """

    name = "openai_vision"
    priority = 50

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._mode: str = self._cfg.get("mode", "extract_text")
        self._model: str = self._cfg.get("model", "gpt-4o")
        default_prompt = (
            _DEFAULT_EXTRACT_PROMPT if self._mode == "extract_text" else _DEFAULT_DESCRIBE_PROMPT
        )
        self._prompt: str = self._cfg.get("prompt", default_prompt)

    def available(self) -> bool:
        """Check that the openai package is installed."""
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def extract(self, path: Path) -> str:
        """Base64-encode image, send to OpenAI Vision API, return text response."""
        import base64

        import openai

        image_data = base64.standard_b64encode(path.read_bytes()).decode()
        img_mime = self._cfg.get("_mime", "image/png")
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{img_mime};base64,{image_data}"},
                        },
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""
