"""Optional serving-layer prose enrichment for campaign flavor events.

The deterministic event and hidden consequences live in ``manager/flavor_events``.
This sidecar only rewrites visible fallback copy into a cache outside saves, so
OpenRouter availability can never change a career's state or choice result.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from pathlib import Path

from esports_sim.web import llm_social


_LOCK = threading.Lock()
_IN_FLIGHT: set[tuple[str, str]] = set()
_ATTEMPTED: set[tuple[str, str]] = set()
_CACHE_DIR = Path("saves")
_TIMEOUT_S = 30


def _provider() -> dict | None:
    """Flavor-specific OpenRouter/local configuration, disabled by default
    only when explicitly requested. ``OPENROUTER_API_KEY`` is shared with the
    social writer so one opt-in enables both kinds of ambient prose."""
    llm_social._load_env()
    mode = os.environ.get("FLAVOR_LLM", "auto").lower()
    if mode == "off":
        return None
    key = os.environ.get("OPENROUTER_API_KEY", "")
    base = os.environ.get("FLAVOR_LLM_BASE_URL", "")
    if mode == "openrouter" or (mode == "auto" and key):
        if not key:
            return None
        return {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "key": key,
            "model": os.environ.get(
                "FLAVOR_LLM_MODEL", "google/gemini-2.5-flash"
            ),
        }
    if mode == "local" or (mode == "auto" and base):
        if not base:
            return None
        return {
            "url": base.rstrip("/") + "/chat/completions",
            "key": "",
            "model": os.environ.get("FLAVOR_LLM_LOCAL_MODEL", "llama3.2"),
        }
    return None


def _path(code: str) -> Path:
    return _CACHE_DIR / f"flavor_llm_{code}.json"


def _load(code: str) -> dict[str, dict]:
    with _LOCK:
        try:
            raw = json.loads(_path(code).read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}


def _save(code: str, cache: dict[str, dict]) -> None:
    with _LOCK:
        p = _path(code)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")


def overlay(code: str, event: dict) -> dict:
    """Return cached visible prose over the deterministic fallback event."""
    cached = _load(code).get(str(event["id"]), {})
    out = dict(event)
    if isinstance(cached.get("title"), str):
        out["title"] = cached["title"]
    if isinstance(cached.get("prompt"), str):
        out["prompt"] = cached["prompt"]
    labels = cached.get("choices")
    if isinstance(labels, list) and len(labels) == len(out.get("choices", [])):
        out["choices"] = [
            {**choice, "label": label}
            if isinstance(label, str) and label.strip()
            else choice
            for choice, label in zip(out["choices"], labels)
        ]
    out["ai"] = bool(cached)
    return out


_SYSTEM = """You write a short decision prompt for a grounded esports manager game.
Rewrite ONLY the supplied fallback title, prompt, and choice labels. Do not add
facts, outcomes, rewards, penalties, names, teams, or choices. Keep the choices
meaningfully distinct, neutral about their hidden consequences, under 100 words
total, and ASCII only. Return strict JSON with title, prompt, and choices (an
array of labels in exactly the supplied order)."""


def _call(cfg: dict, event: dict) -> dict:
    visible = {
        "id": event["id"],
        "title": event["title"],
        "prompt": event["prompt"],
        "choices": [c["label"] for c in event.get("choices", [])],
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(visible, ensure_ascii=False)},
        ],
        "temperature": 0.9,
        "max_tokens": 350,
    }
    req = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}),
            "HTTP-Referer": "https://github.com/stateful-ai/esports-tycoon",
            "X-Title": "esports-sim",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as response:
        text = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    choices = parsed.get("choices")
    if (
        not isinstance(parsed.get("title"), str)
        or not isinstance(parsed.get("prompt"), str)
        or not isinstance(choices, list)
        or len(choices) != len(visible["choices"])
        or not all(isinstance(c, str) and c.strip() for c in choices)
    ):
        return {}
    return {
        "title": parsed["title"].strip()[:160],
        "prompt": parsed["prompt"].strip()[:700],
        "choices": [c.strip()[:100] for c in choices],
    }


def enqueue(code: str, event: dict) -> None:
    """Best-effort background rewrite. No provider/cache failure reaches UI."""
    cfg = _provider()
    key = (code, str(event["id"]))
    if cfg is None:
        return
    with _LOCK:
        if key in _IN_FLIGHT or key in _ATTEMPTED:
            return
        _IN_FLIGHT.add(key)
        _ATTEMPTED.add(key)

    def work() -> None:
        try:
            rewrite = _call(cfg, event)
            if rewrite:
                cache = _load(code)
                cache[str(event["id"])] = rewrite
                _save(code, cache)
        except Exception:
            pass
        finally:
            with _LOCK:
                _IN_FLIGHT.discard(key)

    threading.Thread(target=work, daemon=True, name="flavor-llm").start()
