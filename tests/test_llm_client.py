import json

import httpx
import pytest

from appeals.llm.client import LLMError, OllamaClient


def _response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"message": {"content": content}},
    )


def _http_error(request):
    return httpx.Response(500, text="server error")


def _connect_error(request):
    raise httpx.ConnectError("connection refused", request=request)


def _invalid_json(request):
    return _response("not JSON")


def test_json_request_payload_and_response_parsing():
    requests = []

    def handle(request):
        requests.append(request)
        return _response('{"ok": true}')

    client = OllamaClient(
        "qwen2.5:3b",
        "http://ollama.test/",
        None,
        transport=httpx.MockTransport(handle),
    )
    schema = {"type": "object"}

    assert client.generate_json("system prompt", "user prompt", schema) == {"ok": True}
    payload = json.loads(requests[0].content)
    assert str(requests[0].url) == "http://ollama.test/api/chat"
    assert payload == {
        "model": "qwen2.5:3b",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
        "stream": False,
        "options": {"temperature": 0, "seed": 42},
        "format": schema,
    }


@pytest.mark.parametrize(
    "handler",
    [
        _http_error,
        _connect_error,
        _invalid_json,
    ],
    ids=("http-error", "connection-error", "invalid-json"),
)
def test_json_request_errors_are_wrapped(handler):
    client = OllamaClient(
        "qwen2.5:3b",
        "http://ollama.test",
        None,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMError):
        client.generate_json("system", "user", {"type": "object"})


def test_cache_hit_skips_second_request(tmp_path):
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return _response("cached text")

    client = OllamaClient(
        "qwen2.5:3b",
        "http://ollama.test",
        tmp_path,
        transport=httpx.MockTransport(handle),
    )

    assert client.generate_text("system", "user") == "cached text"
    assert client.generate_text("system", "user") == "cached text"
    assert calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 1
