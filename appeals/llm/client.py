import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

import httpx


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    model: str

    def generate_json(self, system: str, user: str, schema: dict) -> dict: ...

    def generate_text(self, system: str, user: str) -> str: ...


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str,
        cache_dir: Path | None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.cache_dir = cache_dir
        self._http = httpx.Client(transport=transport, timeout=180)

    def _cache_path(self, system: str, user: str, schema: dict | None) -> Path | None:
        if self.cache_dir is None:
            return None
        key = hashlib.sha256(
            json.dumps([self.model, system, user, schema], sort_keys=True).encode()
        ).hexdigest()
        return self.cache_dir / f"{key}.json"

    def _content(self, system: str, user: str, schema: dict | None) -> str:
        cache_path = self._cache_path(system, user, schema)
        if cache_path is not None and cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and isinstance(cached.get("content"), str):
                    return cached["content"]
            except (OSError, ValueError):
                pass

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0, "seed": 42},
        }
        if schema is not None:
            payload["format"] = schema
        try:
            response = self._http.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            content = response.json()["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("Ollama message.content is not a string")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        if cache_path is not None:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({"content": content}, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
        return content

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        content = self._content(system, user, schema)
        try:
            result = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError(f"Ollama returned invalid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise LLMError("Ollama JSON response must be an object")
        return result

    def generate_text(self, system: str, user: str) -> str:
        return self._content(system, user, None)


def _configuration() -> tuple[bool, str, str]:
    enabled = os.environ.get("APPEALS_AI") == "ollama"
    model = os.environ.get("APPEALS_LLM_MODEL", "qwen2.5:3b")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    return enabled, model, host


def get_client() -> LLMClient | None:
    enabled, model, host = _configuration()
    if not enabled:
        return None
    cache_enabled = os.environ.get("APPEALS_LLM_CACHE", "1") != "0"
    cache_dir = (
        Path(__file__).resolve().parents[2] / ".cache" / "llm" if cache_enabled else None
    )
    return OllamaClient(model, host, cache_dir)


def status() -> dict:
    enabled, model, host = _configuration()
    reachable = False
    if enabled:
        try:
            response = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=2)
            response.raise_for_status()
            reachable = True
        except httpx.HTTPError:
            pass
    return {
        "enabled": enabled,
        "model": model if enabled else None,
        "reachable": reachable,
    }
