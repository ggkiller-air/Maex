"""
LightWMRunner — runs the vendored ESSA control flow on Maex's CoherentEnv.

Per env step:
  Call-1  StateUpdater  → patch_ops on subtask_state
  Call-2  Executor      → next action → select_legal_action → env.step

Specs are loaded from Maex/memory/ESSA/ (overrides the in-tree ESSAAgent defaults).

Usage:
  # 1. start the local vLLM server (2-GPU TP on port 8000 by default)
  bash experiment_scripts/start_2gpu_server.sh

  # 2. run a Maex task end-to-end (auto-detects model from /v1/models)
  python -m run_lightwm --env env0 --task 0
  # or override the port / model:
  python -m run_lightwm --env env0 --task 0 --port 9000 --model-name qwen3-4b-instruct-2507
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make Maex/ itself importable as a top-level dir, so `from env.coherent_env
# import ...` (the existing Maex convention used by runner.py / react_agent.py)
# keeps working regardless of cwd.
_MAEX_ROOT = Path(__file__).resolve().parents[0]
if str(_MAEX_ROOT) not in sys.path:
    sys.path.insert(0, str(_MAEX_ROOT))

from agent.essa_agent import ESSAAgent  # noqa: E402

from env.coherent_env import CoherentEnv  # noqa: E402
from env.lightwm_maex_observer import LightWMMaexObserver  # noqa: E402


_MAEX_ROOT_PATH = Path(__file__).resolve().parents[0]
_SPEC_DIR = _MAEX_ROOT_PATH / "memory" / "ESSA"
_ENV_DATA_DIR = _MAEX_ROOT_PATH / "env" / "data"
_LOG_DIR = _MAEX_ROOT_PATH / "logs" / "lightwm_verify"


def _build_task_data(raw: Dict[str, Any], task_id: int, env_id: int) -> Dict[str, Any]:
    graph = raw["init_graph"]
    agent_list = [
        [n["class_name"], n["id"]]
        for n in graph["nodes"]
        if n["category"] == "Agents"
    ]
    return {
        "task_id": task_id,
        "env_id": env_id,
        "task_name": raw["task_name"],
        "graph": graph,
        "task_goal": raw["task_goal"],
        "goal_instruction": raw["goal_instruction"],
        "ground_truth_step_num": raw["ground_truth_step_num"],
        "agent": agent_list,
        "num_agent": len(agent_list),
    }


def _find_quadrotor_agent(env: CoherentEnv) -> Tuple[int, str, int]:
    for idx, pair in env.id_name_dict.items():
        cls = pair[0]
        if cls == "quadrotor":
            return idx, cls, int(pair[1])
    raise RuntimeError("No quadrotor agent found in env — land_on_receptacle requires a quadrotor.")


class LightWMRunner:
    """Thin wrapper around ESSAAgent that runs one Maex/COHERENT task end-to-end."""

    def __init__(
        self,
        model_name: str = "qwen3-4b-instruct-2507",
        action_space_mode: str = "base",
        state_update_mode: str = "patch",
    ) -> None:
        self.essa = ESSAAgent(
            model_name=model_name,
            action_space_mode=action_space_mode,
            state_update_mode=state_update_mode,
            env_observer=LightWMMaexObserver(),
        )

        task_specs_path = _SPEC_DIR / "task_specs.json"
        subtask_specs_path = _SPEC_DIR / "subtask_specs.json"
        if not task_specs_path.exists() or not subtask_specs_path.exists():
            raise FileNotFoundError(
                f"Maex ESSA specs not found under {_SPEC_DIR}. "
                "Expected task_specs.json and subtask_specs.json."
            )

        maex_task_specs = json.loads(task_specs_path.read_text(encoding="utf-8"))
        maex_subtask_specs = json.loads(subtask_specs_path.read_text(encoding="utf-8"))

        merged_task = dict(self.essa.task_specs or {})
        merged_subtask = dict(self.essa.subtask_specs or {})
        for k, v in maex_task_specs.items():
            if isinstance(k, str) and k and not k.startswith("__"):
                merged_task[k] = v
        for k, v in maex_subtask_specs.items():
            if isinstance(k, str) and k and not k.startswith("__"):
                merged_subtask[k] = v
        self.essa.task_specs = merged_task
        self.essa.subtask_specs = merged_subtask

    # ------------------------------------------------------------------
    # Episode runner
    # ------------------------------------------------------------------

    def run_episode(
        self,
        env: CoherentEnv,
        *,
        task_type: str,
        goal_text: str,
        max_steps: int,
        max_subtask_steps: int,
        trace_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        agent_idx, agent_class, agent_node_id = _find_quadrotor_agent(env)

        obs_dict = env.get_observations()
        observation = env.obs2text(obs_dict, agent_idx)
        _plans_str, _n, admissible = env.get_available_plans(agent_idx, obs_dict)
        prev_room_id: Optional[int] = None
        current_room_id: Optional[int] = _parse_current_room_id(observation)

        self.essa.reset(goal_text=goal_text, initial_observation=observation, task_type=task_type)

        trace: Dict[str, Any] = {
            "task_type": task_type,
            "goal_text": goal_text,
            "task_id": env.task_id,
            "env_id": env.env_id,
            "agent_class": agent_class,
            "agent_node_id": agent_node_id,
            "gt_steps": env.ground_truth_step_num,
            "initial_observation": observation,
            "subtask_flow": [dict(s) for s in self.essa.subtask_flow],
            "macro_init": self.essa.last_macro_init_call,
            "steps": [],
            "result": {},
        }

        total_env_steps = 0
        task_done = False
        last_action = "(init)"

        subtask_flow = self.essa.subtask_flow
        for subtask_index, subtask_spec in enumerate(subtask_flow):
            subtask_spec["status"] = "running"
            subtask_state = self.essa.subtask_states.get(subtask_index, {})
            try:
                subtask_state = self.essa.subtask_caller_prepare(
                    subtask_spec=subtask_spec, subtask_state=subtask_state
                )
                self.essa.subtask_states[subtask_index] = subtask_state
            except Exception as exc:
                trace["steps"].append({
                    "phase": "subtask_caller_prepare_error",
                    "subtask_index": subtask_index,
                    "error": f"{type(exc).__name__}: {exc}",
                })

            for _ in range(max_subtask_steps):
                if total_env_steps >= max_steps:
                    task_done = True
                    break

                update = self.essa.state_update(
                    subtask_spec=subtask_spec,
                    subtask_state=subtask_state,
                    last_action=last_action,
                    observation=observation,
                )
                subtask_state = update.get("subtask_state", subtask_state)
                if not isinstance(subtask_state, dict):
                    subtask_state = {}
                subtask_state.setdefault("core", {})
                try:
                    prev = int(subtask_state["core"].get("step_count", 0) or 0)
                except Exception:
                    prev = 0
                subtask_state["core"]["step_count"] = prev + 1
                subtask_state["core"]["latest_observation"] = observation
                self.essa.subtask_states[subtask_index] = subtask_state

                step_record: Dict[str, Any] = {
                    "subtask_index": subtask_index,
                    "subtask_type": subtask_spec.get("type"),
                    "subtask_step": subtask_state["core"]["step_count"],
                    "state_update": {
                        "raw_response": update.get("raw_response", ""),
                        "done": bool(update.get("done", False)),
                        "patch_ops": (update.get("meta", {}) or {}).get("applied_ops", []),
                        "warnings": (update.get("meta", {}) or {}).get("warnings", []),
                        "stats": update.get("stats", {}),
                    },
                    "subtask_state_after_update": _safe_jsonish(subtask_state),
                }

                if update.get("done"):
                    try:
                        macro_patch = self.essa.macro_status_update(
                            subtask_spec=subtask_spec, subtask_state=subtask_state
                        )
                        step_record["macro_status_update"] = macro_patch
                    except Exception as exc:
                        step_record["macro_status_update_error"] = (
                            f"{type(exc).__name__}: {exc}"
                        )
                    subtask_spec["status"] = "done"
                    step_record["subtask_done"] = True
                    trace["steps"].append(step_record)
                    break

                filtered_admissible = _filter_admissible_no_backtrack(
                    admissible, prev_room_id=prev_room_id
                )
                exec_result = self.essa.executor(
                    subtask_state=subtask_state,
                    goal_text=goal_text,
                    admissible_commands=filtered_admissible,
                    last_action=last_action,
                    observation=observation,
                )
                raw_action = exec_result.get("action", "")
                action_intent = exec_result.get("action_intent", {})
                action, select_meta = self.essa.select_legal_action(
                    executor_action=raw_action,
                    action_intent=action_intent if isinstance(action_intent, dict) else {},
                    admissible_commands=filtered_admissible,
                )

                step_record["executor"] = {
                    "raw_response": exec_result.get("raw_response", ""),
                    "raw_action": raw_action,
                    "selected_action": action,
                    "select_meta": select_meta,
                    "stats": exec_result.get("stats", {}),
                }

                try:
                    done, _results, _sat, _unsat, _steps = env.step(
                        agent_class, agent_node_id, action, env.task_goal
                    )
                except Exception as exc:
                    step_record["env_step_error"] = f"{type(exc).__name__}: {exc}"
                    trace["steps"].append(step_record)
                    print(f"[lightwm_agent] env.step error: {exc}")
                    traceback.print_exc()
                    task_done = True
                    break

                obs_dict = env.get_observations()
                observation = env.obs2text(obs_dict, agent_idx)
                _ps, _n, admissible = env.get_available_plans(agent_idx, obs_dict)
                last_action = action
                total_env_steps += 1

                new_room_id = _parse_current_room_id(observation)
                if (
                    new_room_id is not None
                    and current_room_id is not None
                    and new_room_id != current_room_id
                ):
                    prev_room_id = current_room_id
                if new_room_id is not None:
                    current_room_id = new_room_id

                try:
                    macro_change = self.essa.observe(last_action=action, observation=observation)
                    step_record["observe_macro_changes"] = macro_change.get("changes", {})
                except Exception as exc:
                    step_record["observe_error"] = f"{type(exc).__name__}: {exc}"

                step_record["env_result"] = {
                    "done": bool(done),
                    "observation": observation,
                    "total_env_steps": total_env_steps,
                }
                step_record["task_state_after_step"] = _safe_jsonish(
                    self.essa.task_spec.get("task_state", {})
                )

                print(
                    f"[step {total_env_steps:02d}] subtask={subtask_spec.get('type')} "
                    f"action={action} | done={done}"
                )
                if observation:
                    print(f"          obs: {observation[:200].strip()}")

                trace["steps"].append(step_record)

                if done:
                    task_done = True
                    break

            if task_done:
                break
            if subtask_spec.get("status") != "done":
                subtask_spec["status"] = "failed"
                trace["steps"].append({
                    "phase": "subtask_step_cap",
                    "subtask_index": subtask_index,
                    "subtask_type": subtask_spec.get("type"),
                })
                task_done = True
                break

        trace["result"] = {
            "success": bool(task_done) and any(
                step.get("env_result", {}).get("done") for step in trace["steps"]
            ),
            "total_env_steps": total_env_steps,
            "subtask_flow": [dict(s) for s in self.essa.subtask_flow],
            "final_task_state": _safe_jsonish(self.essa.task_spec.get("task_state", {})),
        }

        if trace_path is not None:
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                json.dumps(trace, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            html_path = trace_path.with_suffix(".html")
            try:
                html_path.write_text(_render_html_report(trace), encoding="utf-8")
            except Exception as exc:
                print(f"[lightwm_agent] HTML render failed: {exc}")

        return trace


import re as _re


_RE_ROOM_LINE = _re.compile(r"Now I am in the\s+<([^>]+)>\((\d+)\)")
_RE_MOVE_TO_ROOM_ID = _re.compile(r"\[movetowards\]\s*<[^>]+>\((\d+)\)")


def _parse_current_room_id(observation: str) -> Optional[int]:
    """Pull the 'Now I am in the <room>(<id>)' marker from a Maex obs."""
    if not observation:
        return None
    m = _RE_ROOM_LINE.search(observation)
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            return None
    return None


def _filter_admissible_no_backtrack(
    admissible: List[str],
    *,
    prev_room_id: Optional[int],
) -> List[str]:
    """Hide '[movetowards] <X>(prev_room_id)' from the Executor's view.

    Maex enumerates every adjacent room reachable through an open door, so an
    agent that just moved into RoomX always sees the room it came from as a
    legal next destination. Small LLMs frequently pick it back — wasting a step
    in a 2-room loop. This is purely a runtime filter on what we show the LLM;
    env.step / select_legal_action still operate on the original list semantics
    via the filtered subset, and we only remove backtracks when alternative
    actions remain.
    """
    if not prev_room_id or not admissible:
        return list(admissible)
    suffix = f"({prev_room_id})"
    kept = [
        a
        for a in admissible
        if not (a.startswith("[movetowards]") and a.endswith(suffix))
    ]
    return kept if kept else list(admissible)


def _html_escape(s: Any) -> str:
    text = "" if s is None else str(s)
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


_HTML_CSS = """
body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #0f172a; background: #f1f5f9; line-height: 1.5; }
.hdr { background: linear-gradient(135deg, #1e40af 0%, #0369a1 100%); color: #fff; padding: 14px 22px; }
.hdr h1 { margin: 0 0 4px 0; font-size: 17px; }
.hdr .sub { opacity: 0.85; font-size: 12px; }
.hdr .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; margin-left: 8px; vertical-align: middle; }
.hdr .badge.ok { background: #dcfce7; color: #15803d; }
.hdr .badge.no { background: #fee2e2; color: #b91c1c; }
.metrics { display: flex; gap: 8px; padding: 10px 22px; background: #fff; border-bottom: 1px solid #e2e8f0; overflow-x: auto; }
.metric { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 5px 12px; }
.metric .k { font-size: 9px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }
.metric .v { font-size: 14px; font-weight: 700; }
.metric .v.green { color: #15803d; }
.metric .v.red { color: #b91c1c; }
.wrap { max-width: 980px; margin: 0 auto; padding: 18px 22px 30px; }
.step { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
.step.done { border-color: #86efac; }
.step.err { border-color: #fca5a5; }
.step-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
.step-num { font-weight: 700; font-size: 13px; min-width: 26px; }
.step-subtask { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #ede9fe; color: #6d28d9; font-weight: 700; }
.step-action { font-family: ui-monospace, 'SF Mono', Consolas, monospace; color: #1d4ed8; flex: 1; font-size: 12px; word-break: break-word; }
.step-action.done { color: #15803d; font-weight: 700; }
.step-tag { font-size: 10px; padding: 1px 6px; border-radius: 6px; }
.tag-ok { background: #dcfce7; color: #15803d; }
.tag-err { background: #fee2e2; color: #b91c1c; }
.tag-gray { background: #f1f5f9; color: #475569; }
.step-body { padding: 10px 14px; display: grid; grid-template-columns: 1fr; gap: 8px; }
details { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 10px; }
details > summary { cursor: pointer; font-weight: 600; font-size: 12px; color: #334155; padding: 2px 0; user-select: none; }
details > summary::marker { color: #94a3b8; }
details[open] > summary { color: #1e3a8a; margin-bottom: 6px; }
pre { margin: 0; padding: 8px 10px; background: #0f172a; color: #e2e8f0; font-family: ui-monospace, 'SF Mono', Consolas, monospace; font-size: 11px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
pre.light { background: #f1f5f9; color: #0f172a; }
.kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 12px; padding: 2px 0; }
.kv .k { color: #64748b; }
.kv .v { font-family: ui-monospace, 'SF Mono', Consolas, monospace; color: #0f172a; word-break: break-word; }
.macro-init { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; }
.macro-init h3 { margin: 0 0 8px 0; font-size: 13px; color: #1e3a8a; }
.subtask-flow { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; font-size: 12px; }
.subtask-flow h3 { margin: 0 0 6px 0; font-size: 13px; color: #1e3a8a; }
.subtask-flow ol { margin: 0; padding-left: 22px; }
.subtask-flow li { padding: 2px 0; }
.subtask-flow .sf-name { font-weight: 600; }
.subtask-flow .sf-status { padding: 0 6px; border-radius: 4px; font-size: 10px; margin-left: 6px; font-weight: 700; }
.subtask-flow .sf-status.done { background: #dcfce7; color: #15803d; }
.subtask-flow .sf-status.failed { background: #fee2e2; color: #b91c1c; }
.subtask-flow .sf-status.pending { background: #f1f5f9; color: #64748b; }
"""


def _render_html_report(trace: Dict[str, Any]) -> str:
    result = trace.get("result", {}) or {}
    success = bool(result.get("success"))
    steps = trace.get("steps", []) or []
    task_type = trace.get("task_type", "")
    env_id = trace.get("env_id", "")
    task_id = trace.get("task_id", "")
    goal_text = trace.get("goal_text", "")
    gt_steps = trace.get("gt_steps", "")
    total_steps = result.get("total_env_steps", "")
    badge_html = (
        '<span class="badge ok">SUCCESS</span>'
        if success
        else '<span class="badge no">FAIL</span>'
    )

    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="UTF-8"/>')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1"/>')
    parts.append(f"<title>LightWM verify · env{env_id} task{task_id}</title>")
    parts.append(f"<style>{_HTML_CSS}</style>")
    parts.append("</head><body>")

    parts.append('<div class="hdr">')
    parts.append(
        f"<h1>env{_html_escape(env_id)} · task {_html_escape(task_id)} · "
        f"{_html_escape(task_type)}{badge_html}</h1>"
    )
    parts.append(f'<div class="sub">goal: {_html_escape(goal_text)}</div>')
    parts.append("</div>")

    parts.append('<div class="metrics">')
    steps_class = "green" if (gt_steps and total_steps and total_steps <= gt_steps) else ""
    parts.append(
        f'<div class="metric"><div class="k">env steps</div>'
        f'<div class="v {steps_class}">{_html_escape(total_steps)}</div></div>'
    )
    parts.append(
        f'<div class="metric"><div class="k">gt steps</div>'
        f'<div class="v">{_html_escape(gt_steps)}</div></div>'
    )
    parts.append(
        f'<div class="metric"><div class="k">subtasks</div>'
        f'<div class="v">{len(trace.get("subtask_flow", []) or [])}</div></div>'
    )
    parts.append(
        f'<div class="metric"><div class="k">agent</div>'
        f'<div class="v">{_html_escape(trace.get("agent_class", ""))}({_html_escape(trace.get("agent_node_id", ""))})</div></div>'
    )
    parts.append("</div>")

    parts.append('<div class="wrap">')

    # Macro init
    mi = trace.get("macro_init")
    if isinstance(mi, dict) and mi:
        parts.append('<div class="macro-init">')
        parts.append("<h3>MacroStateInitializer</h3>")
        ts0 = mi.get("task_state") or {}
        parts.append('<details><summary>initial macro task_state</summary>')
        parts.append(f'<pre class="light">{_html_escape(_pretty(ts0))}</pre>')
        parts.append("</details>")
        raw = mi.get("raw_response") or ""
        if raw:
            parts.append('<details><summary>LLM raw response</summary>')
            parts.append(f'<pre>{_html_escape(raw)}</pre>')
            parts.append("</details>")
        parts.append("</div>")

    # Final subtask_flow summary
    sf = result.get("subtask_flow") or trace.get("subtask_flow") or []
    if sf:
        parts.append('<div class="subtask-flow">')
        parts.append("<h3>subtask flow</h3>")
        parts.append("<ol>")
        for s in sf:
            status = (s.get("status") or "pending").lower()
            css = status if status in ("done", "failed", "pending") else "pending"
            parts.append(
                f"<li><span class='sf-name'>{_html_escape(s.get('type') or s.get('subtask_type'))}</span>"
                f" <span class='sf-status {css}'>{_html_escape(status.upper())}</span>"
                f" <span style='color:#64748b'>{_html_escape(s.get('goal') or '')}</span></li>"
            )
        parts.append("</ol>")
        parts.append("</div>")

    # Steps
    for i, st in enumerate(steps, start=1):
        if "executor" not in st and "state_update" not in st:
            phase = st.get("phase") or "event"
            parts.append('<div class="step err">')
            parts.append('<div class="step-head">')
            parts.append(f'<div class="step-num">·</div>')
            parts.append(f'<div class="step-subtask">{_html_escape(st.get("subtask_type", ""))}</div>')
            parts.append(f'<div class="step-action">[{_html_escape(phase)}] {_html_escape(st.get("error", ""))}</div>')
            parts.append("</div></div>")
            continue

        env_res = st.get("env_result") or {}
        env_done = bool(env_res.get("done"))
        css_step = "done" if env_done else ""
        executor = st.get("executor") or {}
        action = executor.get("selected_action") or "—"
        action_css = "done" if env_done else ""

        parts.append(f'<div class="step {css_step}">')
        parts.append('<div class="step-head">')
        parts.append(f'<div class="step-num">{i}</div>')
        parts.append(f'<div class="step-subtask">{_html_escape(st.get("subtask_type") or "")}</div>')
        parts.append(f'<div class="step-action {action_css}">{_html_escape(action)}</div>')
        if env_done:
            parts.append('<div class="step-tag tag-ok">env done</div>')
        if st.get("subtask_done"):
            parts.append('<div class="step-tag tag-gray">subtask done</div>')
        parts.append("</div>")

        parts.append('<div class="step-body">')

        # StateUpdater section
        su = st.get("state_update") or {}
        if su:
            parts.append("<details><summary>StateUpdater</summary>")
            parts.append('<div class="kv">')
            parts.append(f'<div class="k">done</div><div class="v">{_html_escape(su.get("done"))}</div>')
            ops = su.get("patch_ops") or []
            if ops:
                parts.append(f'<div class="k">patch_ops</div><div class="v"><pre class="light">{_html_escape(_pretty(ops))}</pre></div>')
            warns = su.get("warnings") or []
            if warns:
                parts.append(f'<div class="k">warnings</div><div class="v"><pre class="light">{_html_escape(_pretty(warns))}</pre></div>')
            parts.append("</div>")
            raw = su.get("raw_response") or ""
            if raw:
                parts.append('<details><summary>raw LLM response</summary>')
                parts.append(f'<pre>{_html_escape(raw)}</pre>')
                parts.append("</details>")
            sas = st.get("subtask_state_after_update")
            if sas:
                parts.append('<details><summary>subtask_state after update</summary>')
                parts.append(f'<pre class="light">{_html_escape(_pretty(sas))}</pre>')
                parts.append("</details>")
            parts.append("</details>")

        # Executor section
        if executor:
            parts.append("<details><summary>Executor</summary>")
            parts.append('<div class="kv">')
            parts.append(f'<div class="k">selected</div><div class="v">{_html_escape(executor.get("selected_action"))}</div>')
            parts.append(f'<div class="k">raw action</div><div class="v">{_html_escape(executor.get("raw_action"))}</div>')
            sm = executor.get("select_meta") or {}
            parts.append(f'<div class="k">select_meta</div><div class="v">{_html_escape(_pretty(sm))}</div>')
            parts.append("</div>")
            raw = executor.get("raw_response") or ""
            if raw:
                parts.append('<details open><summary>raw LLM response</summary>')
                parts.append(f'<pre>{_html_escape(raw)}</pre>')
                parts.append("</details>")
            parts.append("</details>")

        # Observation after step
        if env_res:
            parts.append("<details><summary>Observation after step</summary>")
            parts.append(f'<pre class="light">{_html_escape(env_res.get("observation", ""))}</pre>')
            parts.append("</details>")

        # Macro changes + task state after step
        macro_changes = st.get("observe_macro_changes")
        if macro_changes:
            parts.append("<details><summary>macro task_state changes (observe)</summary>")
            parts.append(f'<pre class="light">{_html_escape(_pretty(macro_changes))}</pre>')
            parts.append("</details>")
        ts_after = st.get("task_state_after_step")
        if ts_after:
            parts.append("<details><summary>full macro task_state after step</summary>")
            parts.append(f'<pre class="light">{_html_escape(_pretty(ts_after))}</pre>')
            parts.append("</details>")

        # macro_status_update applied at subtask close
        msu = st.get("macro_status_update")
        if msu:
            parts.append("<details><summary>macro_status_update</summary>")
            parts.append(f'<pre class="light">{_html_escape(_pretty(msu))}</pre>')
            parts.append("</details>")

        parts.append("</div>")  # step-body
        parts.append("</div>")  # step

    parts.append("</div>")  # wrap
    parts.append("</body></html>")

    return "".join(parts)


def _safe_jsonish(obj: Any) -> Any:
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except Exception:
        return str(obj)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LightWM ESSA on Maex/COHERENT")
    p.add_argument("--env", default="env0",
                   choices=["env0", "env1", "env2", "env3", "env4"])
    p.add_argument("--task", type=int, default=0,
                   help="Task index inside <env>.json (env0 task 0 = land on high kitchen table)")
    p.add_argument("--task-type", default="land_on_receptacle",
                   help="Family name in Maex/memory/ESSA/task_specs.json")
    p.add_argument("--model-name", default=None,
                   help="Model id served by vLLM. If empty, auto-detect via /v1/models.")
    p.add_argument("--port", type=int, default=8000,
                   help="Local vLLM port. Ignored if --base-url is set.")
    p.add_argument("--base-url", default=None,
                   help="OpenAI-compatible endpoint. Default: http://127.0.0.1:<port>/v1.")
    p.add_argument("--api-key", default="local",
                   help="API key forwarded to the LLM client (local vLLM ignores it).")
    p.add_argument("--seed", type=int, default=1,
                   help="LLM sampling seed; exported as LLM_SEED.")
    p.add_argument("--action-space-mode", default="base", choices=["base", "full"])
    p.add_argument("--state-update-mode", default="patch", choices=["patch", "full_state"])
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--max-subtask-steps", type=int, default=15)
    p.add_argument("--log-dir", default=str(_LOG_DIR),
                   help="Directory to write per-run JSON traces.")
    return p.parse_args()


def _auto_detect_model() -> Optional[str]:
    base_url = os.environ.get("DASH_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("DASH_API_KEY") or os.environ.get("OPENAI_API_KEY") or "local"
    if not base_url:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        models = client.models.list()
        ids = [m.id for m in (models.data or [])]
        return ids[0] if ids else None
    except Exception as exc:
        print(f"[lightwm_agent] auto-detect model failed: {exc}", flush=True)
        return None


def main() -> int:
    args = parse_args()

    base_url = args.base_url or f"http://127.0.0.1:{args.port}/v1"
    os.environ["DASH_BASE_URL"] = base_url
    os.environ["DASH_API_KEY"] = args.api_key
    os.environ["LLM_SEED"] = str(args.seed)

    model_name = args.model_name or _auto_detect_model()
    if not model_name:
        print(
            f"❌ No model name provided and auto-detect via {base_url}/models failed.\n"
            "   Either pass --model-name <id>, or start the vLLM server first "
            "(e.g. bash experiment_scripts/start_2gpu_server.sh)."
        )
        return 1
    print(f"[run_lightwm] base_url={base_url}  model={model_name}  seed={args.seed}")

    env_file = _ENV_DATA_DIR / f"{args.env}.json"
    if not env_file.exists():
        print(f"❌ env file not found: {env_file}")
        return 1
    data = json.loads(env_file.read_text(encoding="utf-8"))
    if args.task < 0 or args.task >= len(data):
        print(f"❌ task index {args.task} out of range (env has {len(data)} tasks)")
        return 1

    raw = data[args.task]
    env_id = int(args.env.lstrip("env")) if args.env.startswith("env") else raw["env_id"]
    task_data = _build_task_data(raw, task_id=args.task, env_id=env_id)
    env = CoherentEnv(task_data)

    goal_instr = raw.get("goal_instruction") or env.goal_instruction
    if isinstance(goal_instr, list):
        goal_instr = " ".join(goal_instr)

    print("=" * 60)
    print(f"  env={args.env}  task={args.task}  task_type={args.task_type}")
    print(f"  goal: {goal_instr}")
    print(f"  gt_steps: {env.ground_truth_step_num}")
    print("=" * 60)

    agent = LightWMRunner(
        model_name=model_name,
        action_space_mode=args.action_space_mode,
        state_update_mode=args.state_update_mode,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_path = Path(args.log_dir) / f"{args.env}_task{args.task}_{ts}.json"

    try:
        result = agent.run_episode(
            env=env,
            task_type=args.task_type,
            goal_text=goal_instr,
            max_steps=args.max_steps,
            max_subtask_steps=args.max_subtask_steps,
            trace_path=trace_path,
        )
    except Exception as exc:
        print(f"[lightwm_agent] run_episode raised: {exc}")
        traceback.print_exc()
        return 2

    print("=" * 60)
    print(f"  success: {result['result']['success']}")
    print(f"  total_env_steps: {result['result']['total_env_steps']}")
    print(f"  trace: {trace_path}")
    print("=" * 60)

    return 0 if result["result"]["success"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
