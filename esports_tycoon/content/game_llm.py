"""Swappable, OpenAI-compatible LLM client for games (CompanyOS gaming pack).

Drop this into a game and talk to ANY OpenAI-compatible endpoint via env — no
provider lock-in. Dev points at your local GPU; prod points at a cheap hosted
Qwen (DeepInfra / Together / Fireworks) or any API. Same code, different env.

    from game_llm import GameLLM, get_llm
    llm = get_llm()                       # configured from env
    text = llm.complete("Greet the player as a gruff tavern keeper.")

    from pydantic import BaseModel
    class NpcLine(BaseModel):
        text: str
        mood: str
    line = llm.structured("The player insults the keeper. Reply.", NpcLine)

Env (see .env.example):
    GAME_LLM_BASE_URL   e.g. http://localhost:8000/v1 (dev) or a hosted /v1 (prod)
    GAME_LLM_MODEL      e.g. qwen2.5-7b-instruct  (right-size: 7B beats 32B on cost)
    GAME_LLM_API_KEY    "local" for vLLM; a real key for a hosted provider
    GAME_LLM_MAX_TOKENS / GAME_LLM_TEMPERATURE / GAME_LLM_TIMEOUT

Deps:  pip install openai pydantic
Cost:  right-size the model, cap output tokens, cache repeated prompts. Self-
       hosting a GPU only beats per-token APIs at high sustained load — start on
       a cheap hosted Qwen and flip the env when you scale.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_DEFAULTS = {
    "GAME_LLM_BASE_URL": "http://localhost:8000/v1",
    "GAME_LLM_MODEL": "qwen2.5-7b-instruct",
    "GAME_LLM_API_KEY": "local",
    "GAME_LLM_MAX_TOKENS": "512",
    "GAME_LLM_TEMPERATURE": "0.8",
    "GAME_LLM_TIMEOUT": "60",
}


def _env(key: str) -> str:
    return os.environ.get(key, _DEFAULTS[key])


def extract_json(text: str) -> dict | None:
    """Best-effort: pull the first JSON object out of a model reply."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class GameLLM:
    """A thin, retrying wrapper over an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
    ):
        from openai import OpenAI  # lazy so importing this module is cheap

        self.model = model or _env("GAME_LLM_MODEL")
        self.max_tokens = int(max_tokens or _env("GAME_LLM_MAX_TOKENS"))
        self.temperature = (
            temperature if temperature is not None else float(_env("GAME_LLM_TEMPERATURE"))
        )
        self._max_retries = max_retries
        self._client = OpenAI(
            base_url=base_url or _env("GAME_LLM_BASE_URL"),
            api_key=api_key or _env("GAME_LLM_API_KEY"),
            timeout=float(timeout or _env("GAME_LLM_TIMEOUT")),
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=self.temperature if temperature is None else temperature,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:  # noqa: BLE001 - retry transient failures
                last_err = exc
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"GameLLM.complete failed after retries: {last_err}")

    def structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Return a validated pydantic model. Prompted JSON (+ repair retry) so it
        works on any endpoint, including local servers without tool-calling."""
        guide = (system or "").strip()
        guide += (
            "\n\nReturn ONLY a JSON object matching this schema — no prose, no code "
            f"fences:\n{json.dumps(schema.model_json_schema())}"
        )
        for _ in range(self._max_retries + 1):
            raw = self.complete(prompt, system=guide.strip(), max_tokens=max_tokens)
            data = extract_json(raw)
            if data is not None:
                try:
                    return schema.model_validate(data)
                except ValidationError:
                    continue
        raise ValueError(
            f"GameLLM.structured could not parse {schema.__name__} from the model"
        )


_default: GameLLM | None = None


def get_llm() -> GameLLM:
    """A process-wide default client, configured from env."""
    global _default
    if _default is None:
        _default = GameLLM()
    return _default
