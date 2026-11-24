#!/usr/bin/env python3
"""Generation gates for the seedance-25-promptmaker skill.

Registered by the skill's frontmatter. `pre` runs before a quote or a paid
generation and returns a PreToolUse decision; `post` runs after intake
questions, quotes, and balance reads, and records them in a per-session state
file that `pre` reads.

Gates:
1. Every paid generation asks the user, showing platform, settings, quoted
   credits, and any skipped workflow step (intake questions, the other
   platform's quote, the balances).
2. A Higgsfield generation must be `params: {"ref": "quote:..."}` naming a
   quote made in this session; an Artlist generation must match an Artlist
   quote made in this session.
3. A quote or an unquoted generation whose prompt fails lint_prompt.py with an
   error is denied.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LINTER = Path(__file__).resolve().parent.parent / "scripts" / "lint_prompt.py"
STATE_DIR = Path(tempfile.gettempdir()) / "seedance-25-promptmaker-hooks"

QUOTE_TOOLS = {"estimate_video_cost", "get_generation_cost"}
GENERATE_TOOLS = {"generate_video", "generate_video_batch", "generate_batch", "render_draft"}
BALANCE_TOOLS = {"balance", "get_balance"}
# Keys that do not change what Artlist generates or charges.
ARTLIST_NON_REQUEST_KEYS = {"confirmCost", "approvedPrice", "folderId", "folderName", "projectId", "kind", "type"}
PLATFORM_LABEL = {"higgsfield": "Higgsfield", "artlist": "Artlist"}


# ---------------------------------------------------------------- helpers

def platform_of(tool_name: str) -> str | None:
    name = tool_name.lower()
    if "higgsfield" in name:
        return "higgsfield"
    if re.search(r"art(l|i)i?st", name):
        return "artlist"
    return None


def short_name(tool_name: str) -> str:
    return tool_name.rsplit("__", 1)[-1]


def state_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")
    return STATE_DIR / f"{safe}.json"


def load_state(session_id: str) -> dict:
    try:
        return json.loads(state_path(session_id).read_text())
    except (OSError, ValueError):
        return {"asked": False, "quotes": {"higgsfield": {}, "artlist": {}}, "balances": []}


def save_state(session_id: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path(session_id).write_text(json.dumps(state))


def walk_values(obj):
    """Yield every dict found in obj, parsing JSON held in strings."""
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_values(value)
    elif isinstance(obj, str):
        text = obj.strip()
        if text[:1] in "{[":
            try:
                yield from walk_values(json.loads(text))
            except ValueError:
                pass


def find_key(obj, key):
    for d in walk_values(obj):
        if key in d:
            return d[key]
    return None


def artlist_hash(tool_input: dict) -> str:
    request = {k: v for k, v in tool_input.items() if k not in ARTLIST_NON_REQUEST_KEYS}
    settings = request.get("settings") or {}
    request["settings"] = {k: str(v).lower() for k, v in settings.items()}
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


def lint(prompt: str, duration) -> str | None:
    """Return the linter report when the prompt has an error, else None."""
    if not isinstance(prompt, str) or not prompt.strip() or not LINTER.exists():
        return None
    args = [sys.executable, "-I", str(LINTER), "-", "--mode", "auto"]
    if str(duration).isdigit():
        args += ["--duration", str(duration)]
    result = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        return None
    return (result.stdout + result.stderr).strip()


def decide(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


# ---------------------------------------------------------------- pre

def higgsfield_params(tool_input: dict) -> list:
    if "requests" in tool_input:
        requests = tool_input.get("requests")
        return [r.get("params") for r in requests] if isinstance(requests, list) else [requests]
    return [tool_input.get("params")]


def settings_summary(platform: str, tool: str, tool_input: dict, state: dict) -> tuple[str, list]:
    """Describe the request for the confirmation and collect its quoted credits."""
    quotes = state["quotes"][platform]
    lines, credits = [], []
    if platform == "higgsfield":
        for params in higgsfield_params(tool_input):
            ref = params.get("ref") if isinstance(params, dict) else None
            quote = quotes.get(ref, {}) if ref else {}
            source = quote.get("params") or (params if isinstance(params, dict) else {})
            lines.append(describe(source.get("model"), source.get("duration"),
                                  "draft 480p" if source.get("draft") else source.get("resolution"),
                                  source.get("aspect_ratio")))
            credits.append(quote.get("credits"))
    elif tool == "render_draft":
        quote = quotes.get("draft:" + str(tool_input.get("generationId")), {})
        lines.append("draft render to 1080p")
        credits.append(quote.get("credits"))
    else:
        jobs = tool_input.get("jobs") if tool == "generate_batch" else [tool_input]
        for job in jobs or []:
            s = job.get("settings") or {}
            lines.append(describe("Seedance group " + str(job.get("modelGroupId") or job.get("modelId") or "?"),
                                  s.get("duration"), s.get("resolution"), s.get("aspect_ratio")))
            credits.append(quotes.get(artlist_hash(job), {}).get("credits"))
    return "; ".join(lines), credits


def describe(model, duration, resolution, aspect) -> str:
    parts = [str(model or "model ?"), f"{duration or 'default'} s", str(resolution or "default resolution"),
             str(aspect or "default aspect")]
    return ", ".join(parts)


def unquoted_reason(platform: str, tool: str, tool_input: dict, state: dict) -> str | None:
    quotes = state["quotes"][platform]
    if platform == "higgsfield":
        for params in higgsfield_params(tool_input):
            if not isinstance(params, dict) or set(params) != {"ref"}:
                return ("Higgsfield generations must be exactly params: {\"ref\": \"<quote_ref>\"} from "
                        "estimate_video_cost (SKILL.md step 7). Quote the request, show the platform "
                        "comparison, and generate with the accepted quote_ref only.")
            if params["ref"] not in quotes:
                return (f"{params['ref']} is not a quote made in this session. Quote the request with "
                        "estimate_video_cost and use its quote_ref.")
        return None
    if tool == "render_draft":
        if "draft:" + str(tool_input.get("generationId")) not in quotes:
            return ("Quote the draft render first: get_generation_cost with kind \"draftRender\" and the "
                    "draft's generationId.")
        return None
    jobs = tool_input.get("jobs") if tool == "generate_batch" else [tool_input]
    for job in jobs or []:
        if artlist_hash(job) not in quotes:
            return ("This Artlist request does not match any get_generation_cost quote made in this "
                    "session. Quote exactly these prompt, model, settings, and input first (SKILL.md "
                    "step 7); any change needs a new quote.")
    return None


def pre(event: dict) -> None:
    tool_name = event.get("tool_name", "")
    platform = platform_of(tool_name)
    tool = short_name(tool_name)
    tool_input = event.get("tool_input") or {}
    if platform is None:
        return
    state = load_state(event.get("session_id", ""))

    if tool in QUOTE_TOOLS:
        if tool == "get_generation_cost" and tool_input.get("kind") not in ("video", None):
            return
        params = tool_input.get("params") if platform == "higgsfield" else tool_input
        if not isinstance(params, dict):
            return
        prompt = params.get("prompt")
        duration = params.get("duration") or (params.get("settings") or {}).get("duration")
        report = lint(prompt, duration)
        if report:
            decide("deny", "The prompt fails the skill linter (SKILL.md step 6). Fix the errors, then "
                           "quote again.\n" + report)
            return
        if not state["asked"]:
            decide("ask", "No intake question was asked in this session (SKILL.md step 1 asks every open "
                          "decision with options). Quote anyway?")
        return

    if tool not in GENERATE_TOOLS:
        return
    if platform == "artlist" and tool == "generate_batch":
        if not any(job.get("type") == "video" for job in tool_input.get("jobs") or []):
            return
    reason = unquoted_reason(platform, tool, tool_input, state)
    if reason:
        decide("deny", reason)
        return

    summary, credits = settings_summary(platform, tool, tool_input, state)
    known = [c for c in credits if isinstance(c, (int, float))]
    cost = f"{sum(known):g} credits" if known else "credits unknown"
    warnings = []
    other = "artlist" if platform == "higgsfield" else "higgsfield"
    if not state["quotes"][other]:
        warnings.append(f"{PLATFORM_LABEL[other]} was not quoted, so no platform comparison was shown")
    if not set(state["balances"]) >= {"higgsfield", "artlist"}:
        warnings.append("the balances of both platforms were not read")
    if not state["asked"]:
        warnings.append("no intake question was asked")
    text = f"Paid Seedance generation on {PLATFORM_LABEL[platform]}: {summary}; {cost}."
    if warnings:
        text += " Skipped steps: " + "; ".join(warnings) + "."
    decide("ask", text)


# ---------------------------------------------------------------- post

def post(event: dict) -> None:
    tool_name = event.get("tool_name", "")
    session = event.get("session_id", "")
    state = load_state(session)
    tool_input = event.get("tool_input") or {}
    response = event.get("tool_response")

    if tool_name == "AskUserQuestion":
        state["asked"] = True
        save_state(session, state)
        return

    platform = platform_of(tool_name)
    tool = short_name(tool_name)
    if platform is None:
        return
    if tool in BALANCE_TOOLS:
        if platform not in state["balances"]:
            state["balances"].append(platform)
    elif tool == "estimate_video_cost" and platform == "higgsfield":
        ref = find_key(response, "quote_ref")
        if not ref:
            return
        cost = find_key(response, "credits")
        params = tool_input.get("params") if isinstance(tool_input.get("params"), dict) else {}
        state["quotes"]["higgsfield"][ref] = {
            "credits": cost,
            "params": {k: params.get(k) for k in ("model", "duration", "resolution", "aspect_ratio", "draft")},
        }
    elif tool == "get_generation_cost" and platform == "artlist":
        if find_key(response, "status") != "quoted":
            return
        cost = find_key(response, "cost")
        if tool_input.get("kind") == "draftRender":
            key = "draft:" + str(tool_input.get("generationId"))
        else:
            key = artlist_hash(tool_input)
        state["quotes"]["artlist"][key] = {"credits": cost}
    else:
        return
    save_state(session, state)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("pre", "post"):
        print("usage: gate.py pre|post < hook-event.json", file=sys.stderr)
        return 2
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    (pre if sys.argv[1] == "pre" else post)(event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
