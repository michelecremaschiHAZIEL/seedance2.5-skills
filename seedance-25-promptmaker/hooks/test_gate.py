#!/usr/bin/env python3
"""Regression tests for gate.py: python3 -I seedance-25-promptmaker/hooks/test_gate.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parent / "gate.py"
HF = "mcp__claude_ai_Higgsfield__"
AL = "mcp__artlist__"
GOOD_PROMPT = ("Photoreal drama. A man crosses a street; one slow tracking shot.\n"
               "0-3s: he steps off the curb. End state: he is mid-street.\n"
               "3-5s: he reaches the far curb. End state: he stands on the sidewalk.")
BAD_PROMPT = ("Photoreal drama. A man crosses a street.\n"
              "0-4s: he steps off the curb. End state: mid-street.\n"
              "2-5s: he reaches the far curb. End state: on the sidewalk.")
HF_PARAMS = {"model": "seedance_2_5", "mode": "t2v", "duration": 5, "draft": True, "prompt": GOOD_PROMPT}
AL_REQUEST = {"prompt": GOOD_PROMPT, "modelGroupId": 515,
              "settings": {"duration": "5", "resolution": "480p", "aspect_ratio": "16:9"}}


def said(role, text):
    """One transcript entry, as Claude Code writes it."""
    return {"type": role, "message": {"role": role, "content": [{"type": "text", "text": text}]}}


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "test-session"

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, mode, tool_name, tool_input, tool_response=None, transcript=None):
        event = {"session_id": self.session, "tool_name": tool_name, "tool_input": tool_input}
        if transcript is not None:
            path = Path(self.tmp.name) / "transcript.jsonl"
            path.write_text("".join(json.dumps(entry) + "\n" for entry in transcript))
            event["transcript_path"] = str(path)
        if tool_response is not None:
            event["tool_response"] = tool_response
        env = dict(os.environ, TMPDIR=self.tmp.name)
        result = subprocess.run([sys.executable, "-I", str(GATE), mode], input=json.dumps(event),
                                capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None, ""
        out = json.loads(result.stdout)["hookSpecificOutput"]
        return out["permissionDecision"], out["permissionDecisionReason"]

    def pre(self, tool, tool_input, transcript=None):
        return self.run_gate("pre", tool, tool_input, transcript=transcript)

    def post(self, tool, tool_input, response):
        return self.run_gate("post", tool, tool_input, response)

    def asked(self):
        self.post("AskUserQuestion", {}, {"answers": {}})

    def quote_higgsfield(self, ref="quote:abc", credits=45):
        # MCP results may arrive as content blocks holding JSON text.
        self.post(HF + "estimate_video_cost", {"params": HF_PARAMS},
                  [{"type": "text", "text": json.dumps({"cost": {"credits": credits}, "quote_ref": ref})}])

    def quote_artlist(self, request=AL_REQUEST, cost=3000):
        self.post(AL + "get_generation_cost", dict(request, kind="video"),
                  {"status": "quoted", "cost": cost})

    # -- unrelated tools pass through
    def test_unrelated_tool_passes(self):
        self.assertEqual(self.pre("Bash", {"command": "ls"}), (None, ""))
        self.assertEqual(self.pre(HF + "generate_image", {"params": {}}), (None, ""))

    # -- gate 3: linter
    def test_quote_with_lint_error_is_denied(self):
        self.asked()
        decision, reason = self.pre(HF + "estimate_video_cost", {"params": dict(HF_PARAMS, prompt=BAD_PROMPT)})
        self.assertEqual(decision, "deny")
        self.assertIn("overlap", reason)
        decision, _ = self.pre(AL + "get_generation_cost", dict(AL_REQUEST, prompt=BAD_PROMPT, kind="video"))
        self.assertEqual(decision, "deny")

    def test_quote_without_intake_asks_then_passes_after_intake(self):
        decision, reason = self.pre(HF + "estimate_video_cost", {"params": HF_PARAMS})
        self.assertEqual(decision, "ask")
        self.assertIn("intake", reason)
        self.asked()
        self.assertEqual(self.pre(HF + "estimate_video_cost", {"params": HF_PARAMS}), (None, ""))

    # -- gate 4: the quoted prompt was shown to the user
    def test_quote_of_prompt_never_shown_is_denied(self):
        self.asked()
        transcript = [said("assistant", "Here is the plan, quoting now.")]
        decision, reason = self.pre(HF + "estimate_video_cost", {"params": HF_PARAMS}, transcript)
        self.assertEqual(decision, "deny")
        self.assertIn("code block", reason)
        decision, _ = self.pre(AL + "get_generation_cost", dict(AL_REQUEST, kind="video"), transcript)
        self.assertEqual(decision, "deny")

    def test_quote_of_prompt_shown_in_code_block_passes(self):
        self.asked()
        # Whitespace and a language tag on the fence do not matter.
        shown = "Updated prompt:\n\n```text\n" + GOOD_PROMPT.replace("\n", "\n\n  ") + "\n```\nQuoting."
        transcript = [said("assistant", shown)]
        self.assertEqual(self.pre(HF + "estimate_video_cost", {"params": HF_PARAMS}, transcript), (None, ""))
        self.assertEqual(self.pre(AL + "get_generation_cost", dict(AL_REQUEST, kind="video"), transcript),
                         (None, ""))

    def test_quote_of_changed_prompt_after_showing_old_one_is_denied(self):
        self.asked()
        transcript = [said("assistant", "```\n" + GOOD_PROMPT + "\n```")]
        changed = dict(HF_PARAMS, prompt=GOOD_PROMPT.replace("slow", "fast"))
        self.assertEqual(self.pre(HF + "estimate_video_cost", {"params": changed}, transcript)[0], "deny")

    def test_prompt_only_in_user_message_or_outside_code_block_is_denied(self):
        self.asked()
        transcript = [said("user", "```\n" + GOOD_PROMPT + "\n```"), said("assistant", GOOD_PROMPT)]
        self.assertEqual(self.pre(HF + "estimate_video_cost", {"params": HF_PARAMS}, transcript)[0], "deny")

    # -- gate 2: generate only from a quote
    def test_higgsfield_raw_params_denied(self):
        decision, reason = self.pre(HF + "generate_video", {"params": HF_PARAMS})
        self.assertEqual(decision, "deny")
        self.assertIn("quote_ref", reason)

    def test_higgsfield_unknown_or_overridden_ref_denied(self):
        self.quote_higgsfield()
        self.assertEqual(self.pre(HF + "generate_video", {"params": {"ref": "quote:other"}})[0], "deny")
        self.assertEqual(self.pre(HF + "generate_video", {"params": {"ref": "quote:abc", "duration": 10}})[0],
                         "deny")

    def test_higgsfield_batch_items_need_quotes(self):
        self.quote_higgsfield()
        requests = [{"index": 0, "params": {"ref": "quote:abc"}}, {"index": 1, "params": HF_PARAMS}]
        self.assertEqual(self.pre(HF + "generate_video_batch", {"requests": requests})[0], "deny")

    def test_artlist_unquoted_or_changed_request_denied(self):
        self.assertEqual(self.pre(AL + "generate_video", AL_REQUEST)[0], "deny")
        self.quote_artlist()
        changed = dict(AL_REQUEST, settings=dict(AL_REQUEST["settings"], resolution="1080p"))
        self.assertEqual(self.pre(AL + "generate_video", changed)[0], "deny")

    def test_artlist_render_draft_needs_draft_quote(self):
        self.assertEqual(self.pre(AL + "render_draft", {"generationId": "g1"})[0], "deny")
        self.post(AL + "get_generation_cost", {"kind": "draftRender", "generationId": "g1"},
                  {"status": "quoted", "cost": 15000})
        decision, reason = self.pre(AL + "render_draft", {"generationId": "g1"})
        self.assertEqual(decision, "ask")
        self.assertIn("15000", reason)

    # -- gate 1: confirmation with skipped steps
    def test_quoted_generation_asks_and_lists_skipped_steps(self):
        self.quote_higgsfield()
        decision, reason = self.pre(HF + "generate_video", {"params": {"ref": "quote:abc"}})
        self.assertEqual(decision, "ask")
        self.assertIn("Higgsfield", reason)
        self.assertIn("45 credits", reason)
        self.assertIn("Artlist was not quoted", reason)
        self.assertIn("no intake question", reason)
        self.assertIn("balances", reason)

    def test_full_workflow_asks_without_skipped_steps(self):
        self.asked()
        self.quote_higgsfield()
        self.quote_artlist()
        self.post(HF + "balance", {}, {"credits": 2618.77})
        self.post(AL + "get_balance", {}, {"status": "ok", "creditsLeft": 491551})
        decision, reason = self.pre(AL + "generate_video", dict(AL_REQUEST, confirmCost=True))
        self.assertEqual(decision, "ask")
        self.assertIn("Artlist", reason)
        self.assertIn("3000 credits", reason)
        self.assertNotIn("Skipped", reason)

    def test_claude_ai_artlist_connector_name_is_covered(self):
        self.assertEqual(self.pre("mcp__claude_ai_Artiist__generate_video", AL_REQUEST)[0], "deny")


if __name__ == "__main__":
    unittest.main(verbosity=1)
