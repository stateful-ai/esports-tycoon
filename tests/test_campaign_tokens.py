"""Season-level campaign token corpus (Track C): vocab pin + determinism.

Mirrors the match-token contract tests in test_telemetry.py: the vocabulary
is a data contract for trained models — changing it must be a deliberate
VOCAB_VERSION bump with a re-blessed digest, never drift.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="module")
def tokens_mod():
    spec = importlib.util.spec_from_file_location(
        "dump_campaign_tokens", SCRIPTS / "dump_campaign_tokens.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_campaign_vocab_is_pinned(tokens_mod):
    vocab = tokens_mod.build_vocab()
    assert tokens_mod.VOCAB_VERSION == 1
    assert len(vocab) == 38
    assert vocab == sorted(vocab)
    assert "CHRON_OTHER" in vocab  # chronicle kinds are open-ended by design
    digest = hashlib.blake2b(
        "|".join(vocab).encode("ascii"), digest_size=8
    ).hexdigest()
    assert digest == "bf37c377ae1b8901", (
        "campaign vocab drifted - if intentional, bump VOCAB_VERSION and re-bless"
    )


def test_campaign_token_dump_deterministic_and_well_formed(tokens_mod, tmp_path):
    stats1 = tokens_mod.dump_campaign(1, 11, tmp_path / "a")
    stats2 = tokens_mod.dump_campaign(1, 11, tmp_path / "b")
    assert stats1 == stats2
    assert (tmp_path / "a.tokens.jsonl").read_bytes() == (
        tmp_path / "b.tokens.jsonl"
    ).read_bytes()

    vocab = json.loads((tmp_path / "a.vocab.json").read_text())
    lines = [
        json.loads(ln)
        for ln in (tmp_path / "a.tokens.jsonl").read_text().splitlines()
    ]
    assert lines, "no team-season streams emitted"
    seasons = {ln["season"] for ln in lines}
    assert seasons == {1}
    names = vocab["tokens"]
    place = {"PLACE_TITLE", "PLACE_STRONG", "PLACE_MID", "PLACE_WEAK"}
    for ln in lines:
        assert all(0 <= t < len(names) for t in ln["tokens"])
        text = [names[t] for t in ln["tokens"]]
        assert text[0] == "SEASON_START" and text[-1] == "SEASON_END"
        assert text[-2] in place
        # A real season: weekly ticks, played fixtures, a playoffs entry.
        assert text.count("WEEK") >= 10
        assert sum(1 for t in text if t.startswith("RESULT_")) >= 5
        assert "PHASE_PLAYOFFS" in text
        assert ln["wins"] + ln["losses"] == sum(
            1 for t in text if t.startswith("RESULT_")
        )
    # Exactly one champion arc per region-season at minimum one league-wide.
    titled = [ln for ln in lines if names[ln["tokens"][-2]] == "PLACE_TITLE"]
    assert titled, "no team-season stream carried a title bucket"
