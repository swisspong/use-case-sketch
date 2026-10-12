"""OcrReader port over real loopback HTTP; does not prove the real LiteLLM/model accepts it."""

import base64
import json
from threading import Event

import pytest

from contexts.document_processing.v3.application.model_presets import VisionPreset
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.errors import OcrProviderError
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.ports import (
    OcrText, OcrUnreadable, PageImage,
)
from contexts.document_processing.v3.infrastructure.openai_compatible_ocr_reader import OpenAICompatibleOcrReader

from .conftest import completion

IMAGE = PageImage("image/png", b"\x89PNG\r\n\x1a\nsynthetic-page")


def preset(endpoint, key="synthetic-api-key"):
    return VisionPreset("mfec", endpoint, "gemini-3.8-flash", key)


def test_one_page_image_is_sent_to_the_selected_preset_and_text_is_returned(ocr_provider):
    result = OpenAICompatibleOcrReader().read(image=IMAGE, preset=preset(ocr_provider.endpoint))

    assert result == OcrText("ข้อความจากภาพ")
    assert len(ocr_provider.requests) == 1
    path, headers, body = ocr_provider.requests[0]
    assert path == "/litellm/chat/completions"
    assert headers["Authorization"] == "Bearer synthetic-api-key"
    assert body["model"] == "gemini-3.8-flash"
    assert body["stream"] is False
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 8192
    system, user = body["messages"]
    assert system["role"] == "system" and "untrusted" in system["content"]
    assert user["role"] == "user"
    image_parts = [part for part in user["content"] if part["type"] == "image_url"]
    assert image_parts == [{"type": "image_url", "image_url": {
        "url": "data:image/png;base64," + base64.b64encode(IMAGE.data).decode("ascii"),
    }}]


def test_model_reporting_an_unreadable_page_is_not_a_failure(ocr_provider):
    ocr_provider.replies = [completion(json.dumps({"outcome": "unreadable"}))]

    assert OpenAICompatibleOcrReader().read(image=IMAGE, preset=preset(ocr_provider.endpoint)) == OcrUnreadable()


def test_each_invocation_authenticates_with_its_own_preset_key(ocr_provider):
    reader = OpenAICompatibleOcrReader()
    for key in ("synthetic-first-key", "synthetic-second-key"):
        reader.read(image=IMAGE, preset=preset(ocr_provider.endpoint, key))

    assert [headers["Authorization"] for _, headers, _ in ocr_provider.requests] == [
        "Bearer synthetic-first-key", "Bearer synthetic-second-key",
    ]


SECRET = "provider-secret-detail"


@pytest.mark.parametrize("status,reply", [
    (401, completion(SECRET)), (429, completion(SECRET)), (500, b"{}"),
    (200, b"not json " + SECRET.encode()),
    (200, b'{"choices": []}'),
    (200, completion("not json " + SECRET)),
    (200, completion(json.dumps({"outcome": "text", "text": "partial"}), finish_reason="length")),
    (200, completion(json.dumps({"outcome": "text"}))),
    (200, completion(json.dumps({"outcome": "text", "text": 7}))),
    (200, completion(json.dumps({"outcome": "unreadable", "text": "x"}))),
    (200, completion(json.dumps({"outcome": "maybe", "text": "x"}))),
    (200, completion(json.dumps(["text"]))),
    (200, completion("x" * 3 * 1024 * 1024)),
])
def test_failed_or_malformed_provider_reply_is_a_recoverable_provider_error(ocr_provider, status, reply):
    ocr_provider.status = status
    ocr_provider.replies = [reply]

    with pytest.raises(OcrProviderError) as caught:
        OpenAICompatibleOcrReader().read(image=IMAGE, preset=preset(ocr_provider.endpoint))

    assert str(caught.value) == "OCR provider unavailable"
    assert len(ocr_provider.requests) == 1  # no automatic retry


def test_timeout_is_a_provider_error_without_retry(ocr_provider):
    ocr_provider.block = Event()

    with pytest.raises(OcrProviderError):
        OpenAICompatibleOcrReader(timeout_seconds=0.2).read(image=IMAGE, preset=preset(ocr_provider.endpoint))

    assert len(ocr_provider.requests) == 1


@pytest.mark.parametrize("ocr_provider", ["https"], indirect=True)
def test_untrusted_tls_certificate_is_refused(ocr_provider):
    with pytest.raises(OcrProviderError):
        OpenAICompatibleOcrReader().read(image=IMAGE, preset=preset(ocr_provider.endpoint))

    assert ocr_provider.requests == []


@pytest.mark.parametrize("endpoint,key", [
    ("http://ocr.example/litellm", "synthetic-api-key"),          # plain HTTP off loopback
    ("{loopback}?redirect=x", "synthetic-api-key"),
    ("{loopback}", "key with\nheader injection"),
])
def test_unsafe_endpoint_or_key_fails_before_any_request(ocr_provider, endpoint, key):
    with pytest.raises(OcrProviderError):
        OpenAICompatibleOcrReader().read(
            image=IMAGE, preset=preset(endpoint.format(loopback=ocr_provider.endpoint), key),
        )

    assert ocr_provider.requests == []


def test_oversized_page_image_is_not_uploaded(ocr_provider):
    with pytest.raises(OcrProviderError):
        OpenAICompatibleOcrReader(max_request_bytes=1024).read(
            image=PageImage("image/png", b"\x89PNG" + b"0" * 2048), preset=preset(ocr_provider.endpoint),
        )

    assert ocr_provider.requests == []


@pytest.mark.parametrize("settings", [
    {"timeout_seconds": 0}, {"timeout_seconds": float("inf")}, {"max_tokens": 0},
    {"max_tokens": True}, {"max_request_bytes": 0},
])
def test_invalid_transport_limits_are_rejected_at_construction(settings):
    with pytest.raises(ValueError):
        OpenAICompatibleOcrReader(**settings)
