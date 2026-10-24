"""Minimal client for LM Studio's OpenAI-compatible server.

Works with any OpenAI-compatible local server (LM Studio, llama.cpp server,
Ollama's /v1 endpoint). Nothing ever leaves your machine unless you point
base_url somewhere else."""
import re
import time
from dataclasses import dataclass

import httpx

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    pass


@dataclass
class Reply:
    text: str
    tokens: int
    seconds: float


def strip_reasoning(text: str) -> str:
    """Remove the hidden chain-of-thought that reasoning models emit."""
    text = THINK_RE.sub("", text)
    if "</think>" in text:  # opening tag sometimes omitted
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


class LLM:
    def __init__(self, settings: dict):
        self.base_url = settings["base_url"].rstrip("/")
        self.model = settings.get("model") or ""
        self.temperature = float(settings.get("temperature", 0.3))
        self.reasoning_budget = int(settings.get("reasoning_budget", 0))
        self.timeout = float(settings.get("request_timeout", 900))

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=10)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"Can't reach LM Studio at {self.base_url} ({e}). "
                           "Is the server started in LM Studio's Developer tab?") from e
        return [m["id"] for m in r.json().get("data", []) if "embed" not in m["id"]]

    def chat(self, system: str, user: str, max_tokens: int, temperature: float | None = None) -> Reply:
        payload = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens + self.reasoning_budget,
            "stream": False,
        }
        if self.model:
            payload["model"] = self.model

        reply = self._post(payload)
        if reply is None:
            # Thinking models sometimes spend the whole budget reasoning. Give it one more go with double room.
            payload["max_tokens"] *= 2
            reply = self._post(payload)
        if reply is None:
            raise LLMError("The model used its whole token budget thinking and returned no text. "
                           "Raise 'reasoning budget' in Settings or use a non-thinking model.")
        return reply

    def _post(self, payload: dict) -> Reply | None:
        last_error = None
        for attempt in range(3):
            start = time.monotonic()
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last_error = e
                time.sleep(3 * (attempt + 1))
        else:
            raise LLMError(f"LM Studio request failed: {last_error}")

        choice = data["choices"][0]
        text = strip_reasoning(choice["message"].get("content") or "")
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        if not text and choice.get("finish_reason") == "length":
            return None
        return Reply(text=text, tokens=tokens, seconds=time.monotonic() - start)
