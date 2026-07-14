"""LLM-driven manager playtests over the public headless action contract.

The campaign remains deterministic for a given seed and action trace.  An LLM
is deliberately outside that contract, so this module records its raw replies,
parsed choices, and the resolver's outcome as reviewable JSONL artifacts.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from esports_sim.manager import analytics
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv, InvalidManagerAction
from esports_sim.registry import GameData


SYSTEM_PROMPT = """You are running an esports organization in a deterministic management simulation.
Use only the JSON observation and legal_actions supplied by the game. Never invent player ids,
action kinds, or parameters. Respond with exactly one JSON object: {\"kind\": string,
\"params\": object}. Choose one decision at a time. Make at most three non-advance decisions
in a campaign week, then advance if it is legal; if advancing is blocked, resolve the listed
blocker first. Be practical about roster legality, finances, and upcoming fixtures."""


class LLMClient(Protocol):
    """Minimal transport seam, intentionally easy to fake in deterministic tests."""

    def complete(self, *, system: str, user: str) -> str: ...


class OpenAICompatibleClient:
    """Small standard-library client for local vLLM, Ollama, or OpenAI-style servers."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 60.0):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, *, system: str, user: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not contain choices[0].message.content") from exc


@dataclass
class LLMPlaytestResult:
    seed: int
    initial_team_id: str
    team_id: str
    weeks: int | None
    seasons_requested: int | None
    seasons_completed: int
    decisions: int
    invalid_responses: int
    recovery_actions: int
    total_reward: float
    action_counts: dict[str, int]
    final_features: dict[str, float]
    playtest_summary: dict[str, Any]
    season_reports: list[dict[str, Any]]
    traces: list[dict[str, Any]]
    critique: str
    critique_error: str | None

    def summary(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("traces")
        return data


def _response_action(reply: str) -> dict[str, Any]:
    """Parse a strict reply while tolerating a markdown fence from local models."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    action = json.loads(text)
    if not isinstance(action, dict):
        raise ValueError("reply must be a JSON object")
    return action


def _recovery_action(observation: dict[str, Any]) -> dict[str, Any]:
    """Choose a deterministic legal action that unblocks the current week."""
    legal = observation["legal_actions"]
    if legal["advance"]["enabled"]:
        return {"kind": "advance", "params": {}}
    for kind in ("resolve_flavor", "resolve_media"):
        contract = legal[kind]
        if contract["enabled"]:
            return {
                "kind": kind,
                "params": {"event_id": contract["event_id"], "choice_id": contract["choice_ids"][0]},
            }
    if legal["accept_job"]["enabled"]:
        return {"kind": "accept_job", "params": {"team_id": legal["accept_job"]["team_ids"][0]}}
    if legal["sign"]["enabled"]:
        return {"kind": "sign", "params": {"player_id": legal["sign"]["player_ids"][0]}}
    raise RuntimeError(
        "LLM playtest cannot recover this blocked week; no deterministic legal "
        "advance, event-resolution, job, or signing action is available"
    )


def _decision_prompt(observation: dict[str, Any]) -> str:
    return "Manager-visible state and action contract:\n" + json.dumps(
        observation, sort_keys=True, separators=(",", ":")
    )


def _critique_prompt(result: LLMPlaytestResult) -> str:
    digest = {
        "summary": result.summary() | {"critique": ""},
        "recent_decisions": [
            {key: trace[key] for key in ("season", "week", "action", "message", "recovered")}
            for trace in result.traces[-30:]
        ],
    }
    return (
        "Review this completed esports-manager playtest. Give a concise, grounded critique: "
        "what was legible, what was confusing, which legal decisions felt missing or low-value, "
        "and up to three concrete product improvements. Do not invent results.\n"
        + json.dumps(digest, sort_keys=True)
    )


def run_llm_playtest(
    gd: GameData,
    client: LLMClient,
    *,
    seed: int,
    weeks: int | None = None,
    seasons: int | None = None,
    user_team_id: str = "team_nexus",
    max_decisions_per_week: int = 16,
) -> LLMPlaytestResult:
    """Run a bounded LLM-managed campaign and retain every model-facing trace.

    Exactly one of ``weeks`` or ``seasons`` is required. Season mode ends after
    the requested number of rollovers and includes a report per completed season.
    """
    if (weeks is None) == (seasons is None):
        raise ValueError("specify exactly one of weeks or seasons")
    if weeks is not None and weeks < 1:
        raise ValueError("weeks must be positive")
    if seasons is not None and seasons < 1:
        raise ValueError("seasons must be positive")
    gs = new_campaign(gd, seed=seed, user_team_id=user_team_id)
    env = HeadlessManagerEnv(gs, gd, user_team_id, policy_version="llm-playtest-v1")
    traces: list[dict[str, Any]] = []
    rewards: list[float] = []
    invalid = recoveries = advanced = decisions_this_week = 0
    season_reports: list[dict[str, Any]] = []
    target_season = gs.season + (seasons or 0)

    while (weeks is not None and advanced < weeks) or (seasons is not None and gs.season < target_season):
        observation = env.observe()
        budget_forced = decisions_this_week >= max_decisions_per_week - 1
        reply: str | None = None
        recovered = budget_forced
        error_text = None
        if budget_forced:
            action = _recovery_action(observation)
            step = env.step(action)
            recoveries += 1
        else:
            reply = client.complete(system=SYSTEM_PROMPT, user=_decision_prompt(observation))
            try:
                action = _response_action(reply)
                step = env.step(action)
            except (ValueError, json.JSONDecodeError, InvalidManagerAction) as exc:
                invalid += 1
                recovered = True
                error_text = str(exc)
                action = _recovery_action(observation)
                step = env.step(action)
                recoveries += 1
        traces.append({
            "trace_version": 1,
            "seed": seed,
            "season": observation["season"],
            "week": observation["week"],
            "observation": observation,
            "raw_reply": reply,
            "action": action,
            "recovered": recovered,
            "budget_forced": budget_forced,
            "error": error_text,
            "message": step.message,
            "reward": step.reward,
            "advanced": step.advanced,
        })
        decisions_this_week += 1
        if step.advanced:
            advanced += 1
            rewards.append(step.reward)
            decisions_this_week = 0
            if gs.season > observation["season"]:
                season_reports.append(analytics.season_report(gs, observation["season"]))
        elif decisions_this_week >= max_decisions_per_week:
            raise RuntimeError(
                f"LLM failed to advance after {max_decisions_per_week} decisions "
                f"in season {gs.season} week {gs.week}"
            )

    result = LLMPlaytestResult(
        seed=seed,
        initial_team_id=user_team_id,
        team_id=env.team_id,
        weeks=weeks,
        seasons_requested=seasons,
        seasons_completed=len(season_reports),
        decisions=len(traces),
        invalid_responses=invalid,
        recovery_actions=recoveries,
        total_reward=round(sum(rewards), 4),
        action_counts=dict(sorted(Counter(t["action"]["kind"] for t in traces).items())),
        final_features=env.observe()["features"],
        playtest_summary=analytics.playtest_summary(gs),
        season_reports=season_reports,
        traces=traces,
        critique="",
        critique_error=None,
    )
    try:
        result.critique = client.complete(
            system="You are a rigorous game-playtest analyst.", user=_critique_prompt(result)
        )
    except Exception as exc:  # retain the completed decision trace for diagnosis
        result.critique_error = str(exc)
        result.critique = "Critique generation failed; inspect the trace and summary artifacts."
    return result


def write_artifacts(result: LLMPlaytestResult, output_dir: Path) -> dict[str, Path]:
    """Write stable, reviewable artifacts without changing the campaign save."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"llm-playtest-seed-{result.seed}"
    traces_path = output_dir / f"{stem}.traces.jsonl"
    summary_path = output_dir / f"{stem}.summary.json"
    critique_path = output_dir / f"{stem}.critique.md"
    traces_path.write_text(
        "".join(json.dumps(trace, sort_keys=True) + "\n" for trace in result.traces),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(result.summary(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    critique_path.write_text(result.critique.rstrip() + "\n", encoding="utf-8")
    return {"traces": traces_path, "summary": summary_path, "critique": critique_path}
