"""Tests for OCR and vision extraction backends."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.test_backends._helpers import _make_module

# ===========================================================================
# TesseractExtractor
# ===========================================================================


class TestTesseractExtractor:
    def test_available_returns_false_when_pytesseract_not_importable(self) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        with patch.dict(sys.modules, {"pytesseract": None}):
            assert TesseractExtractor().available() is False

    def test_available_returns_true_when_pytesseract_importable(self) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_pt = _make_module("pytesseract")
        with (
            patch.dict(sys.modules, {"pytesseract": fake_pt}),
            patch("all2txt.backends.ocr.shutil.which", return_value="/usr/bin/tesseract"),
        ):
            assert TesseractExtractor().available() is True

    def test_available_returns_false_when_tesseract_cli_missing(self) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_pt = _make_module("pytesseract")
        with (
            patch.dict(sys.modules, {"pytesseract": fake_pt}),
            patch("all2txt.backends.ocr.shutil.which", return_value=None),
        ):
            assert TesseractExtractor().available() is False

    def test_extract_uses_config_lang_and_psm(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_img = MagicMock()

        fake_pt = _make_module("pytesseract")
        fake_pt.image_to_string = MagicMock(return_value="OCR result")

        fake_pil_image = MagicMock()
        fake_pil_image.open = MagicMock(return_value=fake_img)
        fake_pil = _make_module("PIL")
        fake_pil.Image = fake_pil_image
        fake_pil_image_mod = _make_module("PIL.Image")
        fake_pil_image_mod.open = fake_pil_image.open

        with patch.dict(
            sys.modules,
            {"pytesseract": fake_pt, "PIL": fake_pil, "PIL.Image": fake_pil_image_mod},
        ):
            extractor = TesseractExtractor(config={"lang": "chi_sim", "psm": 6})
            result = extractor.extract(fake_path)

        fake_pt.image_to_string.assert_called_once_with(fake_img, lang="chi_sim", config="--psm 6")
        assert result == "OCR result"

    def test_extract_uses_default_lang_and_psm(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import TesseractExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_img = MagicMock()

        fake_pt = _make_module("pytesseract")
        fake_pt.image_to_string = MagicMock(return_value="text")

        fake_pil_image = MagicMock()
        fake_pil_image.open = MagicMock(return_value=fake_img)
        fake_pil = _make_module("PIL")
        fake_pil.Image = fake_pil_image
        fake_pil_image_mod = _make_module("PIL.Image")
        fake_pil_image_mod.open = fake_pil_image.open

        with patch.dict(
            sys.modules,
            {"pytesseract": fake_pt, "PIL": fake_pil, "PIL.Image": fake_pil_image_mod},
        ):
            extractor = TesseractExtractor()
            extractor.extract(fake_path)

        fake_pt.image_to_string.assert_called_once_with(fake_img, lang="eng", config="--psm 3")


# ===========================================================================
# EasyOCRExtractor
# ===========================================================================


class TestEasyOCRExtractor:
    def test_available_returns_false_when_easyocr_not_importable(self) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        with patch.dict(sys.modules, {"easyocr": None}):
            assert EasyOCRExtractor().available() is False

    def test_available_returns_true_when_easyocr_importable(self) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_easyocr = _make_module("easyocr")
        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            assert EasyOCRExtractor().available() is True

    def test_extract_uses_configured_langs(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_reader_instance = MagicMock()
        fake_reader_instance.readtext.return_value = ["line one", "line two"]

        fake_easyocr = _make_module("easyocr")
        fake_easyocr.Reader = MagicMock(return_value=fake_reader_instance)

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            extractor = EasyOCRExtractor(config={"langs": ["en", "ch_sim"]})
            result = extractor.extract(fake_path)

        fake_easyocr.Reader.assert_called_once_with(["en", "ch_sim"])
        fake_reader_instance.readtext.assert_called_once_with(str(fake_path), detail=0)
        assert result == "line one\nline two"

    def test_extract_uses_default_langs(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import EasyOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_reader_instance = MagicMock()
        fake_reader_instance.readtext.return_value = []

        fake_easyocr = _make_module("easyocr")
        fake_easyocr.Reader = MagicMock(return_value=fake_reader_instance)

        with patch.dict(sys.modules, {"easyocr": fake_easyocr}):
            extractor = EasyOCRExtractor()
            extractor.extract(fake_path)

        fake_easyocr.Reader.assert_called_once_with(["en"])


# ===========================================================================
# PaddleOCRExtractor
# ===========================================================================


class TestPaddleOCRExtractor:
    def test_available_returns_false_when_paddleocr_not_importable(self) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        with patch.dict(sys.modules, {"paddleocr": None}):
            assert PaddleOCRExtractor().available() is False

    def test_available_returns_true_when_paddleocr_importable(self) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock()
        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            assert PaddleOCRExtractor().available() is True

    def test_extract_uses_configured_lang_and_joins_lines(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        # Each line in result: [bbox, (text, confidence)]
        fake_result = [
            [
                [None, ("Hello", 0.99)],
                [None, ("World", 0.95)],
            ]
        ]

        fake_ocr_instance = MagicMock()
        fake_ocr_instance.ocr.return_value = fake_result

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock(return_value=fake_ocr_instance)

        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            extractor = PaddleOCRExtractor(config={"lang": "en"})
            result = extractor.extract(fake_path)

        fake_paddleocr_mod.PaddleOCR.assert_called_once_with(use_angle_cls=True, lang="en")
        fake_ocr_instance.ocr.assert_called_once_with(str(fake_path), cls=True)
        assert result == "Hello\nWorld"

    def test_extract_uses_default_lang(self, tmp_path: Path) -> None:
        from all2txt.backends.ocr import PaddleOCRExtractor

        fake_path = tmp_path / "image.png"
        fake_path.touch()

        fake_ocr_instance = MagicMock()
        fake_ocr_instance.ocr.return_value = [[]]

        fake_paddleocr_mod = _make_module("paddleocr")
        fake_paddleocr_mod.PaddleOCR = MagicMock(return_value=fake_ocr_instance)

        with patch.dict(sys.modules, {"paddleocr": fake_paddleocr_mod}):
            extractor = PaddleOCRExtractor()
            extractor.extract(fake_path)

        fake_paddleocr_mod.PaddleOCR.assert_called_once_with(use_angle_cls=True, lang="ch")


# ===========================================================================
# OpenAIVisionExtractor
# ===========================================================================


class TestOpenAIVisionExtractor:
    def test_available_returns_false_when_openai_not_importable(self) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        with patch.dict(sys.modules, {"openai": None}):
            assert OpenAIVisionExtractor().available() is False

    def test_available_returns_true_when_openai_importable(self) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock()
        with patch.dict(sys.modules, {"openai": fake_openai}):
            assert OpenAIVisionExtractor().available() is True

    def test_extract_base64_encodes_and_sends_to_openai(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_path = tmp_path / "photo.png"
        image_bytes = b"\x89PNG\r\n\x1a\n"
        fake_path.write_bytes(image_bytes)

        expected_b64 = base64.standard_b64encode(image_bytes).decode()

        mock_message = MagicMock()
        mock_message.content = "extracted text from image"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor()
            result = extractor.extract(fake_path)

        assert result == "extracted text from image"
        create_call = mock_client_instance.chat.completions.create.call_args
        messages = create_call[1]["messages"]
        image_url = messages[0]["content"][1]["image_url"]["url"]
        assert expected_b64 in image_url
        assert "image/png" in image_url

    def test_extract_uses_configured_model_and_prompt(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_path = tmp_path / "photo.png"
        fake_path.write_bytes(b"data")

        mock_message = MagicMock()
        mock_message.content = "described"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor(
                config={"mode": "describe", "model": "gpt-4-turbo", "prompt": "Custom prompt"}
            )
            extractor.extract(fake_path)

        create_call = mock_client_instance.chat.completions.create.call_args
        assert create_call[1]["model"] == "gpt-4-turbo"
        messages = create_call[1]["messages"]
        text_part = messages[0]["content"][0]
        assert text_part["text"] == "Custom prompt"

    def test_extract_uses_describe_mode_default_prompt(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import (
            _DEFAULT_DESCRIBE_PROMPT,
            OpenAIVisionExtractor,
        )

        fake_path = tmp_path / "photo.png"
        fake_path.write_bytes(b"data")

        mock_message = MagicMock()
        mock_message.content = ""
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client_instance)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor(config={"mode": "describe"})
            extractor.extract(fake_path)

        create_call = mock_client_instance.chat.completions.create.call_args
        messages = create_call[1]["messages"]
        text_part = messages[0]["content"][0]
        assert text_part["text"] == _DEFAULT_DESCRIBE_PROMPT


# ===========================================================================
# OpenAIVision uses injected _mime (R007)
# ===========================================================================


class TestOpenAIVisionUsesInjectedMime:
    def test_extract_uses_cfg_mime_not_extension(self, tmp_path: Path) -> None:
        from all2txt.backends.openai_vision import OpenAIVisionExtractor

        fake_path = tmp_path / "photo.tif"  # .tif extension but override to jpeg
        fake_path.write_bytes(b"data")

        mock_message = MagicMock()
        mock_message.content = "ok"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        fake_openai = _make_module("openai")
        fake_openai.OpenAI = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            extractor = OpenAIVisionExtractor(config={"_mime": "image/jpeg"})
            extractor.extract(fake_path)

        create_call = mock_client.chat.completions.create.call_args
        image_url = create_call[1]["messages"][0]["content"][1]["image_url"]["url"]
        assert "image/jpeg" in image_url
        assert "image/tiff" not in image_url
