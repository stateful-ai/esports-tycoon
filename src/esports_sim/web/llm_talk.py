"""LLM-Powered 1:1 Talk Module 2.0 (R3) for Esports Simulator.

This module handles LLM-powered 1:1 talk sessions, mirroring provider resolution
and configuration settings from llm_social.py.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
import logging
from pathlib import Path

from esports_sim.manager.state import GameState
from esports_sim.manager import talk

logger = logging.getLogger(__name__)

_ENV_LOADED = False
_LOCK = threading.Lock()
CACHE_DIR = Path("saves")
TIMEOUT_S = 60

MAPPING = {
    "reassure": ["reassure", "morale", "slump", "public", "support", "worry", "ok", "fine"],
    "challenge": ["challenge", "blunt", "improve", "better", "standard", "step it up"],
    "listen": ["listen", "ask", "hear", "talk to me", "understand", "going on"],
    "promise_playtime": ["playtime", "play", "start", "time", "weeks", "play_time"],
    "promise_captain": ["captain", "lead", "leader"],
    "commit": ["commit", "renew", "deal", "contract", "extend", "talks"],
    "honest": ["honest", "truth", "straight", "sincere", "end"],
    "deflect": ["deflect", "subject", "change", "light", "topic"],
    "rest": ["rest", "stamina", "break", "sleep", "fumes", "lighter"],
    "push": ["push", "hard", "grind", "week"],
    "routine": ["routine", "review", "normal"],
    "film": ["film", "video", "session", "losses", "match", "demo", "vod"],
    "back": ["back", "safe", "spot", "bench", "regardless"],
    "bench_threat": ["bench", "threat", "earn", "reserve"],
    "praise": ["praise", "well", "good job", "great", "excellent", "proud"],
    "goals": ["goals", "goal", "concrete", "target", "future"],
    "banter": ["banter", "social", "joke", "laugh", "fun"],
    "streaming": ["streaming", "stream", "twitch", "youtube", "hours", "cut back"]
}


def _load_env() -> None:
    """Read repo-root .env into os.environ (existing vars win)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def provider() -> dict | None:
    """Resolve the active provider config, or None when off."""
    _load_env()
    mode = os.environ.get("SOCIAL_LLM", "auto").lower()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    base = os.environ.get("SOCIAL_LLM_BASE_URL", "")
    if mode == "off":
        return None
    if mode == "openrouter" or (mode == "auto" and key):
        if not key:
            return None
        return {
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "key": key,
            "model": os.environ.get(
                "SOCIAL_LLM_MODEL", "google/gemini-2.5-flash"
            ),
        }
    if mode == "local" or (mode == "auto" and base):
        if not base:
            return None
        return {
            "url": base.rstrip("/") + "/chat/completions",
            "key": "",
            "model": os.environ.get("SOCIAL_LLM_LOCAL_MODEL", "llama3.2"),
        }
    return None


def deterministic_intent(text: str, candidate_ids: list[str]) -> str:
    """Classify the text into one of candidate_ids based on keywords."""
    if not candidate_ids:
        return ""
    text_lower = text.lower()
    for cid in candidate_ids:
        keywords = MAPPING.get(cid, [])
        for kw in keywords:
            if kw in text_lower:
                return cid
    return candidate_ids[0]


def parse_llm_response(raw: str) -> dict | None:
    """Extract intent, reply_positive, and reply_negative from raw text."""
    def _validate(obj) -> dict | None:
        if not isinstance(obj, dict):
            return None
        intent = obj.get("intent")
        pos = obj.get("reply_positive")
        neg = obj.get("reply_negative")
        if isinstance(intent, str) and isinstance(pos, str) and isinstance(neg, str):
            return {
                "intent": intent.strip(),
                "reply_positive": pos.strip(),
                "reply_negative": neg.strip()
            }
        return None

    try:
        return _validate(json.loads(raw))
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return _validate(json.loads(m.group(0)))
            except ValueError:
                pass
    return None


def _call(cfg: dict, payload: dict) -> dict | None:
    """Synchronously call the provider endpoint and return the parsed result."""
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
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return parse_llm_response(content)


def _talk_cache_path(save_code: str) -> Path:
    return CACHE_DIR / f"talk_llm_{save_code}.json"


def load_talk_cache(save_code: str) -> dict:
    with _LOCK:
        try:
            return json.loads(_talk_cache_path(save_code).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def _save_talk_cache(save_code: str, cache: dict) -> None:
    with _LOCK:
        _talk_cache_path(save_code).parent.mkdir(parents=True, exist_ok=True)
        _talk_cache_path(save_code).write_text(
            json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
        )


def process_chat(gs: GameState, player_id: str, text: str, save_code: str) -> dict:
    """Process a 1:1 chat message, calling the LLM provider if configured."""
    ok, why = talk.can_talk(gs, player_id)
    if not ok:
        raise ValueError(why)

    topic = talk.topic_for(gs, player_id)
    candidate_ids = [o.id for o in topic.options]
    if talk.can_rein_streaming(gs, player_id)[0]:
        candidate_ids.append("streaming")

    cfg = provider()
    ai_success = False
    intent = None
    reply_positive = ""
    reply_negative = ""

    if cfg is not None:
        # Build system and user prompt
        from esports_sim.manager import personality
        p = gs.players[player_id]
        ax = personality.axes(p)
        moods = []
        if ax["ego"] >= 62: moods.append("cocky")
        if ax["ego"] <= 38: moods.append("humble")
        if ax["sociability"] >= 62: moods.append("chatty")
        if ax["sociability"] <= 38: moods.append("terse")
        if ax["professionalism"] >= 62: moods.append("professional")
        tone = ", ".join(moods) or "even-keeled"
        persona = f"{p.handle} (personality: {tone}; tags: {', '.join(p.personality_tags) or 'none'})"

        options_desc = []
        for cid in candidate_ids:
            if cid == "streaming":
                label = "Ask the player to cut back on streaming and focus on practice"
            else:
                opt = next((o for o in topic.options if o.id == cid), None)
                label = opt.label if opt else ""
            options_desc.append(f"- {cid}: {label}")

        system_msg = (
            "You are an AI classifier and writer for an esports manager game.\n"
            "Your task is to classify the manager's chat message into one of the available options (intent).\n"
            "Then, write two character-accurate replies from the player's perspective:\n"
            "- reply_positive: prose if they take the approach well or if the outcome is positive.\n"
            "- reply_negative: prose if they bristle or if the outcome is negative/bristled.\n"
            "Respond with STRICT JSON format matching this schema:\n"
            '{"intent": "option_id", "reply_positive": "prose if accepted/positive", "reply_negative": "prose if bristled/negative"}\n'
            "Do not include any other text or formatting. Only return valid JSON."
        )

        user_msg = (
            f"Player: {persona}\n"
            f"Topic context: {topic.text}\n"
            f"Available options/intents:\n"
            + "\n".join(options_desc) + "\n\n"
            f"Manager's message: \"{text}\"\n\n"
            f"Select the option ID that best matches the manager's message from the available options. "
            f"Then write the player's response for both positive and negative outcomes."
        )

        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.2,
        }

        try:
            parsed = _call(cfg, payload)
            if parsed is not None:
                intent = parsed["intent"]
                reply_positive = parsed["reply_positive"]
                reply_negative = parsed["reply_negative"]
                ai_success = True
        except Exception as e:
            logger.warning("LLM talk request failed: %s. Falling back to deterministic.", e)

    if ai_success:
        if intent not in candidate_ids:
            intent = candidate_ids[0]
    else:
        intent = deterministic_intent(text, candidate_ids)

    if intent == "streaming":
        ok, resolve_msg, effects = talk.rein_in_streaming(gs, player_id)
    else:
        ok, resolve_msg, effects = talk.resolve(gs, player_id, intent)

    if not ok:
        raise ValueError(resolve_msg)

    if ai_success:
        is_negative = effects.get("morale", 0.0) < 0 or effects.get("chemistry", 0.0) < 0 or "bristle" in resolve_msg.lower()
        chosen_message = reply_negative if is_negative else reply_positive
        ai = True
    else:
        chosen_message = resolve_msg
        ai = False

    # Sidecar Caching
    cache_key = f"{gs.season}_{gs.week}_{gs.acting_team_id}_{player_id}"
    history_dict = {
        "intent": intent,
        "message": chosen_message,
        "effects": effects,
        "ai": ai
    }
    with _LOCK:
        try:
            cache = json.loads(_talk_cache_path(save_code).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        cache[cache_key] = history_dict
        _talk_cache_path(save_code).parent.mkdir(parents=True, exist_ok=True)
        _talk_cache_path(save_code).write_text(
            json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
        )

    return {
        "ok": True,
        "message": chosen_message,
        "effects": effects,
        "intent": intent,
        "ai": ai
    }
