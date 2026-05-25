"""
LightWMMaexObserver — bridges LightWM's ESSAAgent and Maex's CoherentEnv.

Implements env.lightwm_base.BaseEnvObserver (vendored from LightWM). Maex observation text is produced
by CoherentEnv.obs2text and uses the following grammar (see env/coherent_env.py):

  "I am <quadrotor>(22). Now my state is: LAND. I am ON the <childroom floor>(3)."
  "Now I am in the <kitchen>(2). In this room, I can see:"
  "I am ABOVE the <high kitchen table>(35)."

Action grammar (matches CoherentEnv.get_available_plans output):
  [takeoff_from] <surface_class>(<id>)
  [movetowards]  <X>(<id>)
  [land_on]      <surface_class>(<id>)
  [grab]         <X>(<id>)
  [putinto]      <X>(<id>) into <Y>(<id>)
  [puton]        <X>(<id>) on <Y>(<id>)
  [open]         <X>(<id>)
  [close]        <X>(<id>)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from env.lightwm_base import BaseEnvObserver


_VERBS = (
    "takeoff_from",
    "movetowards",
    "land_on",
    "putinto",
    "puton",
    "grab",
    "open",
    "close",
)

_RE_STATE = re.compile(r"Now my state is:\s*([A-Z]+)\b")
_RE_AGENT_IN_ROOM_TOP = re.compile(r"Now I am in the\s+<([^>]+)>\((\d+)\)")
_RE_AGENT_INSIDE_ROOM = re.compile(r"I am INSIDE the\s+<([^>]+)>\((\d+)\)")
_RE_AGENT_ON = re.compile(r"I am ON the\s+<([^>]+)>\((\d+)\)")
_RE_AGENT_ABOVE = re.compile(r"I am ABOVE the\s+<([^>]+)>\((\d+)\)")
_RE_VERB_BRACKET = re.compile(r"\[([a-zA-Z_]+)\]")


class LightWMMaexObserver(BaseEnvObserver):
    """Maex/COHERENT adapter for ESSAAgent."""

    # ------------------------------------------------------------------
    # Required: parse observation into macro task_state patch
    # ------------------------------------------------------------------

    def extract_state_patch(
        self,
        last_action: str,
        observation: str,
        *,
        task_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        patch: Dict[str, Any] = {}
        obs = observation or ""
        ts = task_state if isinstance(task_state, dict) else {}

        m = _RE_STATE.search(obs)
        if m:
            patch["agent_flight_state"] = m.group(1).strip()

        m_top = _RE_AGENT_IN_ROOM_TOP.search(obs)
        if m_top:
            patch["agent_current_room_id"] = int(m_top.group(2))
        else:
            m_inside = _RE_AGENT_INSIDE_ROOM.search(obs)
            if m_inside:
                patch["agent_current_room_id"] = int(m_inside.group(2))

        m_on = _RE_AGENT_ON.search(obs)
        m_above = _RE_AGENT_ABOVE.search(obs)
        if m_on:
            patch["agent_position"] = f"on <{m_on.group(1)}>({m_on.group(2)})"
        elif m_above:
            patch["agent_position"] = f"above <{m_above.group(1)}>({m_above.group(2)})"
        else:
            m_inside2 = _RE_AGENT_INSIDE_ROOM.search(obs)
            if m_inside2:
                patch["agent_position"] = f"inside <{m_inside2.group(1)}>({m_inside2.group(2)})"

        target_id = ts.get("target_receptacle_id")
        try:
            target_id_int = int(target_id) if target_id is not None else None
        except (TypeError, ValueError):
            target_id_int = None

        if target_id_int is not None:
            above_target = bool(m_above and int(m_above.group(2)) == target_id_int)
            patch["agent_above_target"] = above_target

            landed = bool(
                patch.get("agent_flight_state") == "LAND"
                and m_on
                and int(m_on.group(2)) == target_id_int
            )
            patch["landed_on_target"] = landed

        return patch

    # ------------------------------------------------------------------
    # Required: action normalization & verb detection
    # ------------------------------------------------------------------

    def normalize_action(self, action: str) -> str:
        text = (action or "").strip()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).rstrip(".").rstrip(",").strip()

        m = _RE_VERB_BRACKET.search(text)
        if not m:
            for v in _VERBS:
                if text.lower().startswith(v):
                    rest = text[len(v):].strip()
                    text = f"[{v}] {rest}"
                    break

        text = re.sub(r"(?<![<\w])([a-z][a-z_ ]*?)\((\d+)\)", r"<\1>(\2)", text)
        return text

    def detect_action_verb(self, action: str) -> str:
        text = (action or "").strip()
        m = _RE_VERB_BRACKET.search(text)
        if m:
            v = m.group(1).strip().lower()
            if v in _VERBS:
                return v
        low = text.lower().lstrip()
        for v in _VERBS:
            if low.startswith(v):
                return v
        return ""

    def get_full_action_space(self) -> List[Dict[str, str]]:
        return []

    # ------------------------------------------------------------------
    # Optional hooks
    # ------------------------------------------------------------------

    def default_fallback_action(self) -> str:
        return ""

    def macro_fields_to_subtask_core(self) -> List[str]:
        return ["agent_flight_state", "agent_position", "agent_current_room_id"]

    def macro_to_memory_prefill(
        self,
        memory: Dict[str, Any],
        task_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if not isinstance(memory, dict) or not isinstance(task_state, dict):
            return out
        if "takeoff_surface" in memory:
            pos = task_state.get("agent_position")
            if isinstance(pos, str) and pos.startswith("on "):
                out["takeoff_surface"] = pos
        return out

    def macro_init_fallback(
        self,
        *,
        task_type: str,
        task_state_schema: Dict[str, Any],
        goal_text: str,
        initial_observation: str,
    ) -> Dict[str, Any]:
        return {
            "task_type": task_type,
            "goal": goal_text,
            "agent_class": "quadrotor",
            "agent_id": None,
            "target_receptacle": "",
            "target_receptacle_id": None,
            "agent_flight_state": "LAND",
            "agent_current_room_id": None,
            "agent_position": None,
            "agent_above_target": False,
            "landed_on_target": False,
        }

    def finalize_task_state(
        self,
        task_state: Dict[str, Any],
        *,
        initial_observation: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task_state, dict):
            return {}
        ts = dict(task_state)

        ts.setdefault("agent_above_target", False)
        ts.setdefault("landed_on_target", False)

        for k in ("agent_id", "target_receptacle_id", "agent_current_room_id"):
            v = ts.get(k)
            if isinstance(v, str) and v.strip().isdigit():
                ts[k] = int(v.strip())

        obs = initial_observation if isinstance(initial_observation, str) else ""
        if obs:
            init_patch = self.extract_state_patch("(init)", obs, task_state=ts)
            for k, v in init_patch.items():
                if ts.get(k) is None or ts.get(k) == "" or ts.get(k) == []:
                    ts[k] = v
                elif k == "agent_flight_state" and ts.get(k) != v:
                    ts[k] = v

        return ts
