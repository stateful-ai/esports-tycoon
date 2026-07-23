"""LLM-driven manager playtests over the public headless action contract.

The campaign remains deterministic for a given seed and action trace.  An LLM
is deliberately outside that contract, so this module records its raw replies,
parsed choices, and the resolver's outcome as reviewable JSONL artifacts.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from http.client import HTTPException
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import request

from esports_sim.manager import analytics
from esports_sim.manager.campaign import new_campaign
from esports_sim.manager.decision_env import HeadlessManagerEnv, InvalidManagerAction
from esports_sim.registry import GameData


SYSTEM_PROMPT = """You are running an esports organization in a deterministic management simulation.
Use only the JSON observation and legal_actions supplied by the game. Never invent player ids,
action kinds, or parameters. Respond with exactly one JSON object: {\"kind\": string,
\"params\": object}. Choose one decision at a time. Make at most three non-advance decisions
in a campaign week, then advance if it is legal; if advancing is blocked, resolve the listed
blocker first (legal_actions.advance.reason names it). Never repeat an action you already took
this week with the same params — if nothing new needs deciding, advance. Be practical about
roster legality, finances, and upcoming fixtures."""


class LLMClient(Protocol):
    """Minimal transport seam, intentionally easy to fake in deterministic tests."""

    def complete(self, *, system: str, user: str) -> str: ...


class OpenAICompatibleClient:
    """Small standard-library client for local vLLM, Ollama, or OpenAI-style servers.

    Transient transport failures (connection drops, timeouts, 429/5xx) are
    retried with a linear backoff so a single blip cannot kill a multi-hour
    season run. The retry loop lives outside the determinism contract — the
    campaign only ever sees the final reply text.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        retries: int = 3,
        retry_delay: float = 2.0,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.retries = max(1, retries)
        self.retry_delay = retry_delay
        self._sleep = sleeper if sleeper is not None else time.sleep

    def complete(self, *, system: str, user: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                body = self._transport(payload, headers)
                break
            # OSError covers URLError, SSL alerts, and connection resets —
            # raw ssl.SSLError escapes urllib's URLError wrapping when the
            # failure happens while READING the response, not opening it.
            except (OSError, HTTPException, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt == self.retries:
                    raise RuntimeError(f"LLM request failed after {attempt} attempts: {exc}") from exc
                self._sleep(self.retry_delay * attempt)
        else:  # pragma: no cover - loop always breaks or raises
            raise RuntimeError(f"LLM request failed: {last_exc}")
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not contain choices[0].message.content") from exc

    def _transport(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
        """One HTTP round-trip; overridable in tests to fake the network."""
        req = request.Request(self.url, data=payload, headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


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
    season_critiques: list[dict[str, Any]] = field(default_factory=list)

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


def _decision_prompt(
    observation: dict[str, Any], rejections: list[str] | None = None
) -> str:
    prompt = "Manager-visible state and action contract:\n" + json.dumps(
        observation, sort_keys=True, separators=(",", ":")
    )
    if rejections:
        # Each week's prompt is stateless, so without this a model repeats
        # the same malformed action every week and relearns it via retry.
        prompt += (
            "\nEarlier replies this run were rejected for these reasons — "
            "do not repeat these mistakes: " + json.dumps(rejections)
        )
    return prompt


def _sampled_decisions(traces: list[dict[str, Any]], cap: int = 40) -> list[dict[str, Any]]:
    """Even-stride sample so a long run's digest covers the whole arc, not
    just the tail (the last 30 of a 10-season run is a fraction of one
    season)."""
    keys = ("season", "week", "action", "message", "recovered")
    if len(traces) <= cap:
        picked = traces
    else:
        stride = len(traces) / cap
        picked = [traces[int(i * stride)] for i in range(cap)]
    return [{key: trace[key] for key in keys} for trace in picked]


def _critique_prompt(result: LLMPlaytestResult) -> str:
    digest = {
        "summary": result.summary() | {"critique": ""},
        "sampled_decisions": _sampled_decisions(result.traces),
    }
    return (
        "Review this completed esports-manager playtest. Give a concise, grounded critique: "
        "what was legible, what was confusing, which legal decisions felt missing or low-value, "
        "and up to three concrete product improvements. Do not invent results.\n"
        + json.dumps(digest, sort_keys=True)
    )


def _season_critique_prompt(
    season: int, report: dict[str, Any], season_traces: list[dict[str, Any]]
) -> str:
    digest = {
        "season": season,
        "season_report": report,
        "action_counts": dict(
            sorted(Counter(t["action"]["kind"] for t in season_traces).items())
        ),
        "sampled_decisions": _sampled_decisions(season_traces, cap=25),
    }
    return (
        f"Review season {season} of an ongoing esports-manager playtest. In a short paragraph "
        "each: what the manager-visible state made legible, what was confusing or low-signal, "
        "and which decisions felt unrewarded. Do not invent results.\n"
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
    trace_sink: Callable[[dict[str, Any]], None] | None = None,
    critique_each_season: bool = False,
) -> LLMPlaytestResult:
    """Run a bounded LLM-managed campaign and retain every model-facing trace.

    Exactly one of ``weeks`` or ``seasons`` is required. Season mode ends after
    the requested number of rollovers and includes a report per completed season.
    ``trace_sink`` (if given) receives each trace as it is recorded, so long
    runs stream to disk instead of holding artifacts hostage to a crash.
    ``critique_each_season`` asks the client for a short critique at every
    season rollover in addition to the end-of-run critique.
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
    recovery_grace = 0
    recent_rejections: list[str] = []
    season_reports: list[dict[str, Any]] = []
    season_critiques: list[dict[str, Any]] = []
    season_start_trace = 0
    target_season = gs.season + (seasons or 0)

    while (weeks is not None and advanced < weeks) or (seasons is not None and gs.season < target_season):
        observation = env.observe()
        budget_forced = decisions_this_week >= max_decisions_per_week - 1
        reply: str | None = None
        recovered = budget_forced
        error_text = None
        retry_reply: str | None = None
        corrected = False
        if budget_forced:
            action = _recovery_action(observation)
            step = env.step(action)
            recoveries += 1
        else:
            reply = client.complete(
                system=SYSTEM_PROMPT,
                user=_decision_prompt(observation, recent_rejections),
            )
            try:
                action = _response_action(reply)
                step = env.step(action)
            except (ValueError, json.JSONDecodeError, InvalidManagerAction) as exc:
                invalid += 1
                error_text = str(exc)
                recent_rejections.append(str(exc))
                del recent_rejections[:-3]
                # One corrective attempt with the rejection named — most
                # models fix a bad param when told what was wrong. Only then
                # fall back to the deterministic recovery action.
                retry_reply = client.complete(
                    system=SYSTEM_PROMPT,
                    user=_decision_prompt(observation)
                    + f"\nYour previous reply was rejected: {error_text}. "
                    "Reply with exactly one corrected JSON action.",
                )
                try:
                    action = _response_action(retry_reply)
                    step = env.step(action)
                    corrected = True
                except (ValueError, json.JSONDecodeError, InvalidManagerAction) as exc2:
                    error_text = f"{error_text}; retry also rejected: {exc2}"
                    recovered = True
                    action = _recovery_action(observation)
                    step = env.step(action)
                    recoveries += 1
        trace = {
            "trace_version": 1,
            "seed": seed,
            "season": observation["season"],
            "week": observation["week"],
            "observation": observation,
            "raw_reply": reply,
            "retry_reply": retry_reply,
            "action": action,
            "recovered": recovered,
            "corrected": corrected,
            "budget_forced": budget_forced,
            "error": error_text,
            "message": step.message,
            "reward": step.reward,
            "advanced": step.advanced,
        }
        traces.append(trace)
        if trace_sink is not None:
            trace_sink(trace)
        decisions_this_week += 1
        if step.advanced:
            advanced += 1
            rewards.append(step.reward)
            decisions_this_week = 0
            recovery_grace = 0
            if gs.season > observation["season"]:
                report = analytics.season_report(gs, observation["season"])
                season_reports.append(report)
                if critique_each_season:
                    season_traces = traces[season_start_trace:]
                    entry: dict[str, Any] = {"season": observation["season"]}
                    try:
                        entry["critique"] = client.complete(
                            system="You are a rigorous game-playtest analyst.",
                            user=_season_critique_prompt(
                                observation["season"], report, season_traces
                            ),
                        )
                        entry["error"] = None
                    except Exception as exc:  # keep the run alive; note the miss
                        entry["critique"] = ""
                        entry["error"] = str(exc)
                    season_critiques.append(entry)
                season_start_trace = len(traces)
        elif decisions_this_week >= max_decisions_per_week:
            # A budget-forced recovery may legitimately need several steps —
            # e.g. sign a fifth player, THEN advance. Give the deterministic
            # recovery path a bounded grace window before declaring a wedge.
            recovery_grace += 1
            if recovery_grace > 8:
                raise RuntimeError(
                    f"LLM failed to advance after {max_decisions_per_week} decisions "
                    f"and {recovery_grace - 1} recovery steps "
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
        season_critiques=season_critiques,
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
    critique_text = result.critique.rstrip() + "\n"
    if result.season_critiques:
        sections = [
            f"\n\n## Season {entry['season']}\n\n"
            + (entry["critique"].rstrip() or f"(critique failed: {entry['error']})")
            for entry in result.season_critiques
        ]
        critique_text = critique_text.rstrip() + "".join(sections) + "\n"
    critique_path.write_text(critique_text, encoding="utf-8")
    return {"traces": traces_path, "summary": summary_path, "critique": critique_path}
