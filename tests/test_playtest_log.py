"""The sidecar log preserves expectations and earlier runs across appends."""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def logger(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/playtest_log.py"
    spec = importlib.util.spec_from_file_location("playtest_log", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "LOG_DIR", tmp_path / "docs/playtests")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.0.1"\n')
    monkeypatch.setattr(module.subprocess, "check_output", lambda args, **kw: "abc123\n" if "rev-parse" in args else " M existing.py\n")

    def run(operation, step=1, **fields):
        args = ["playtest_log.py", operation, "--session", "test-session", "--step", str(step)]
        for key, value in fields.items():
            args += ["--" + key.replace("_", "-"), str(value)]
        monkeypatch.setattr(sys, "argv", args)
        module.main()

    return module, run


def begin(run, step=1):
    run("begin", step, model="unknown", effort="unknown", surface="browser", intent='Find "rest", safely', action="Choose rest", expected_outcome="Recovery\nnext week")


def test_append_roundtrips_quotes_newlines_and_preserves_prior_rows(logger):
    module, run = logger
    begin(run)
    run("finish", actual_outcome="Selected rest", result="met")
    log = module.LOG_DIR / "actions.csv"
    prior = log.read_bytes()
    begin(run, 2)
    run("finish", 2, actual_outcome="Unexpected warning", result="partial")
    assert log.read_bytes().startswith(prior)
    with log.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["intent"] == 'Find "rest", safely'
    assert rows[0]["expected_outcome"] == "Recovery\nnext week"
    assert rows[0]["commit"] == "abc123"
    assert rows[0]["working_tree_dirty"] == "true"
    assert rows[0]["started_at_utc"] <= rows[0]["finished_at_utc"]


def test_duplicate_does_not_change_history_or_discard_pending(logger):
    module, run = logger
    begin(run)
    run("finish", actual_outcome="Done", result="met")
    before = (module.LOG_DIR / "actions.csv").read_bytes()
    begin(run)
    with pytest.raises(SystemExit):
        run("finish", actual_outcome="Repeated", result="met")
    assert (module.LOG_DIR / "actions.csv").read_bytes() == before
    pending = module.ROOT / "runs/playtests/test-session/pending-1.json"
    assert json.loads(pending.read_text())["expected_outcome"] == "Recovery\nnext week"


def test_schema_mismatch_refuses_append(logger):
    module, run = logger
    begin(run)
    module.LOG_DIR.mkdir(parents=True)
    log = module.LOG_DIR / "actions.csv"
    log.write_text("old_schema\nprior_data\n")
    with pytest.raises(SystemExit):
        run("finish", actual_outcome="Done", result="met")
    assert log.read_text() == "old_schema\nprior_data\n"
