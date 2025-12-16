"""Abstract base class for vision AI providers."""

from abc import ABC, abstractmethod
from typing import Optional
from PIL import Image


class VisionProvider(ABC):
    """Abstract base class for vision AI providers."""

    @abstractmethod
    def analyze_image(
        self,
        image: Image.Image,
        prompt: str,
        max_retries: int = 3
    ) -> Optional[dict]:
        """
        Analyze image and return structured JSON with bounding box.

        Args:
            image: PIL Image to analyze
            prompt: Text prompt describing the analysis task
            max_retries: Maximum number of retry attempts

        Returns:
            dict with 'box_2d' key containing [xmin, ymin, xmax, ymax]
            normalized coordinates (0-1 range), or None on failure
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name for logging purposes."""
        pass
