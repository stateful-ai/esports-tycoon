"""LLM-written social posts — flavor at the SERVING layer, never state.

The deterministic social feed (manager/social.py) stays the only truth:
every post's template text is generated from real outcomes and saved in
GameState. This module rewrites those posts in-voice with an LLM and
overlays the result AT SERVE TIME (/api/social). The rewrites live in a
sidecar cache keyed by post id — never in the save — so:

- campaign determinism is untouched (same seed -> byte-identical
  GameState, with or without a model running);
- a post is written once and stays written (the cache is the memory);
- no key, no server, no problem: the template text serves as-is.

Providers (both speak the OpenAI chat API, so one client covers both):
- OpenRouter  — needs OPENROUTER_API_KEY in .env / the environment
- local       — any OpenAI-compatible server (Ollama, LM Studio, ...)

Env knobs (all optional):
- SOCIAL_LLM        = auto | openrouter | local | off   (default auto:
                      openrouter if a key exists, else local if a base
                      url is set, else off)
- SOCIAL_LLM_MODEL  = OpenRouter model id
                      (default meta-llama/llama-3.3-70b-instruct)
- SOCIAL_LLM_BASE_URL    = local endpoint (e.g. http://localhost:11434/v1)
- SOCIAL_LLM_LOCAL_MODEL = local model name (default llama3.2)

Grounding rule (same as the narrative layer): the model REPHRASES facts
we hand it; it may add voice, never events. Prompts carry the fact line,
the author's personality, and the save's media-outlet personas.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
from pathlib import Path

# One in-flight enrichment per world + a lock around cache file IO.
_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()
_ATTEMPTED: dict[str, set[str]] = {}  # code -> post ids we already tried

CACHE_DIR = Path("saves")
BATCH_MAX = 14  # posts per LLM call (one call per advanced week, roughly)
TIMEOUT_S = 60
MAX_TOKENS = 1400

_ENV_LOADED = False


def _load_env() -> None:
    """Read repo-root .env into os.environ (existing vars win). The web
    server is launched from the repo root; quiet no-op otherwise."""
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
            # Rewriting grounded facts is a light task, so default to a cheap,
            # fast model (~20-30x lower output cost than a 70B) to stretch the
            # budget. Override with SOCIAL_LLM_MODEL for higher-quality prose.
            "model": os.environ.get(
                "SOCIAL_LLM_MODEL", "google/gemini-2.5-flash"
            ),
        }
    if mode == "local" or (mode == "auto" and base):
        if not base:
            return None
        return {
            "url": base.rstrip("/") + "/chat/completions",
            "key": "",  # local servers usually need none
            "model": os.environ.get("SOCIAL_LLM_LOCAL_MODEL", "llama3.2"),
        }
    return None


# -- cache ---------------------------------------------------------------------


def _cache_path(code: str) -> Path:
    return CACHE_DIR / f"social_llm_{code}.json"


def load_cache(code: str) -> dict[str, str]:
    with _LOCK:
        try:
            return json.loads(_cache_path(code).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}


def _save_cache(code: str, cache: dict[str, str]) -> None:
    with _LOCK:
        _cache_path(code).parent.mkdir(parents=True, exist_ok=True)
        _cache_path(code).write_text(
            json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8"
        )


# -- prompt --------------------------------------------------------------------

_SYSTEM = (
    "You ghost-write social media posts inside an esports-manager game "
    "(Valorant-style). You will receive posts as JSON: each has an id, "
    "an author persona, and a FACT line describing what actually "
    "happened. Rewrite each post in the author's voice.\n"
    "Rules:\n"
    "- The fact is the whole truth: never invent results, stats, names, "
    "or events that are not in the fact line.\n"
    "- Stay under 200 characters per post. No hashtags unless the "
    "persona is a hype account. No emoji spam (one is fine).\n"
    "- Players sound like players (first person, terse); news outlets "
    "sound like their persona; keep it dry, never melodramatic.\n"
    "- ASCII only.\n"
    'Answer with STRICT JSON: {"posts": [{"id": "...", "text": "..."}]} '
    "and nothing else."
)


def _persona(post: dict, gs) -> str:
    """A one-line persona for the post's author, grounded in game state."""
    kind = post.get("author_kind", "")
    if kind == "player":
        p = gs.players.get(post.get("author_id", ""))
        if p is None:
            return "a retired pro"
        from esports_sim.manager import personality

        ax = personality.axes(p)
        moods = []
        if ax["ego"] >= 62:
            moods.append("cocky")
        if ax["ego"] <= 38:
            moods.append("humble")
        if ax["sociability"] >= 62:
            moods.append("chatty")
        if ax["sociability"] <= 38:
            moods.append("terse")
        if ax["professionalism"] >= 62:
            moods.append("professional")
        tone = ", ".join(moods) or "even-keeled"
        return f"pro player {p.handle} ({tone}; tags: {', '.join(p.personality_tags) or 'none'})"
    if kind == "team":
        t = gs.teams.get(post.get("author_id", ""))
        return f"the official account of {t.name}" if t else "a team account"
    # media
    author = post.get("author", "an outlet")
    if "clip" in author.lower() or "frag" in author.lower() or "tap" in author.lower():
        return f"{author}, a highlights/hype account (energetic, short)"
    if any(w in author.lower() for w in ("patch", "meta", "balance", "nerf")):
        return f"{author}, a balance-analysis account (analytical, dry)"
    return f"{author}, an esports news wire (dry, factual, a little wry)"


def build_payload(posts: list[dict], gs, model: str) -> dict:
    """The chat request body for a batch of feed posts."""
    items = [
        {
            "id": p["id"],
            "persona": _persona(p, gs),
            "kind": p.get("kind", ""),
            "fact": p.get("text", ""),
        }
        for p in posts
    ]
    user = (
        f"Season {gs.season}, week {gs.week} of the league. "
        "Rewrite these posts:\n"
        + json.dumps({"posts": items}, indent=0, ensure_ascii=False)
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        "temperature": 0.9,
        "max_tokens": MAX_TOKENS,
    }


def parse_response(raw: str) -> dict[str, str]:
    """Pull {id: text} out of a chat response's content — defensively:
    strict JSON first, then the largest {...} block. Anything unparsable
    yields {} (the template text simply keeps serving)."""
    def _extract(obj) -> dict[str, str]:
        out = {}
        for item in (obj or {}).get("posts", []):
            pid, text = item.get("id"), item.get("text")
            if isinstance(pid, str) and isinstance(text, str) and text.strip():
                out[pid] = text.strip()[:220]
        return out

    try:
        return _extract(json.loads(raw))
    except ValueError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return _extract(json.loads(m.group(0)))
            except ValueError:
                pass
    return {}


def _call(cfg: dict, payload: dict) -> dict[str, str]:
    req = urllib.request.Request(
        cfg["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}),
            # OpenRouter attribution headers (harmless elsewhere).
            "HTTP-Referer": "https://github.com/stateful-ai/esports-tycoon",
            "X-Title": "esports-sim",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return parse_response(content)


# -- the entry points the server uses -------------------------------------------


def overlay(code: str, feed: list[dict]) -> list[dict]:
    """Merge cached rewrites into a serialized feed. Each post keeps its
    grounded template in "fact" and gains "ai": True when rewritten."""
    cache = load_cache(code)
    out = []
    for p in feed:
        text = cache.get(p["id"])
        if text:
            p = {**p, "fact": p["text"], "text": text, "ai": True}
        else:
            p = {**p, "ai": False}
        out.append(p)
    return out


def enqueue(game) -> bool:
    """Kick a background enrichment pass for a world's newest posts.
    Non-blocking; at most one in flight per world; silently a no-op with
    no provider. Returns True when a worker was started."""
    cfg = provider()
    if cfg is None or game.gs is None:
        return False
    code = game.code
    with _LOCK:
        if code in _IN_FLIGHT:
            return False
        _IN_FLIGHT.add(code)

    # Snapshot the batch UNDER the caller's game lock (we're called from
    # the advance endpoint, which holds it): newest unwritten posts.
    cache = load_cache(code)
    attempted = _ATTEMPTED.setdefault(code, set())
    gs = game.gs
    todo = [
        p.model_dump()
        for p in gs.social_feed[-BATCH_MAX * 2:]
        if p.id not in cache and p.id not in attempted
    ][-BATCH_MAX:]
    if not todo:
        with _LOCK:
            _IN_FLIGHT.discard(code)
        return False
    attempted.update(p["id"] for p in todo)
    payload = build_payload(todo, gs, cfg["model"])

    def worker() -> None:
        try:
            written = _call(cfg, payload)
            if written:
                fresh = load_cache(code)
                fresh.update(written)
                _save_cache(code, fresh)
        except Exception:
            pass  # flavor must never take the server down
        finally:
            with _LOCK:
                _IN_FLIGHT.discard(code)

    threading.Thread(target=worker, name=f"llm-social-{code}", daemon=True).start()
    return True
