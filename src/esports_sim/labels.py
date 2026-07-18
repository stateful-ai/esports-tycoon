"""Shared formatting for identifiers that cross into player-facing text."""

from __future__ import annotations

import re


_TOKEN_LABELS = {
    "acs": "ACS",
    "bo1": "BO1",
    "bo3": "BO3",
    "fa": "FA",
    "igl": "IGL",
    "kayo": "KAY/O",
    "kay/o": "KAY/O",
    "kd": "K/D",
    "kda": "K/D/A",
    "mvp": "MVP",
    "vod": "VOD",
    "xp": "XP",
}


def humanize_identifier(value: object) -> str:
    """Turn an internal identifier into a readable title-cased label."""

    if value is None:
        return ""
    text = re.sub(r"[_-]+", " ", str(value).strip())
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    return " ".join(
        _TOKEN_LABELS.get(word.casefold(), word[:1].upper() + word[1:])
        for word in text.split(" ")
    )


def humanize_phrase(value: object) -> str:
    """Format an identifier for use inside a sentence."""

    if value is None:
        return ""
    text = re.sub(r"[_-]+", " ", str(value).strip())
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    return " ".join(
        _TOKEN_LABELS.get(word.casefold(), word.casefold())
        for word in text.split(" ")
    )
