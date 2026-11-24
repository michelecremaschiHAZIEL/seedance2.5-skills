# Seedance 2.5 Director

A Claude Code skill that turns an idea, a script, or a set of images, videos, and audio clips into a Seedance 2.5 prompt, then generates the video on **Higgsfield** or **Artlist** through their MCP servers, on the platform you choose after seeing both quotes.

## What it does

1. **Asks before writing.** Every open decision (references, format, look, setting and light, camera, sound, render quality) comes as a question with concrete options and a recommended one.
2. **Directs the prompt.** It picks the task path (text-to-video, references, first/last frames, edit, extension, timeline, multi-clip, storyboard, blockout, transition), gives every reference one role and its exclusions, and writes the prompt as summary, whole-second timeline, and constant notes.
3. **Checks it.** A bundled linter flags overlapping or overlong time ranges, missing task triggers, and other structural risks.
4. **Quotes both platforms.** It prices the same request on Higgsfield and Artlist, reads the remaining credits on each, and asks which platform to use.
5. **Generates and verifies.** It generates only the accepted quote, waits for the job, and looks at the result before describing it. A failed take goes through one-variable diagnosis, not a reworded retry.

## Requirements

- Claude Code.
- For generation, the Higgsfield connector, the Artlist connector, or both. With one, the skill quotes that platform alone; with neither, it still writes prompts and production plans.

## Installation

Personal skill:

```bash
git clone https://github.com/michelecremaschiHAZIEL/seedance2.5-skills.git
mkdir -p ~/.claude/skills
ln -s "$PWD/seedance2.5-skills/seedance-25-promptmaker" ~/.claude/skills/seedance-25-promptmaker
```

Project skill, from the project that uses it:

```bash
mkdir -p .claude/skills
ln -s /path/to/seedance2.5-skills/seedance-25-promptmaker .claude/skills/seedance-25-promptmaker
```

Keep the skill at one of these two paths: the hooks look for their script there. Start a new Claude Code session after installing or updating.

## Usage

Invoke `/seedance-25-promptmaker` with the brief, or describe a Seedance 2.5 task and Claude loads the skill:

```text
/seedance-25-promptmaker A man and a woman collide on a crowded sidewalk while on their phones.
His phone falls and a taxi crushes it; she throws hers into the street and they
walk off hand in hand.
```

Local files are named in the brief with their role, for example `./refs/a.png for Character A's identity`.

## Guardrails

The skill's hooks turn the generation rules into checks. They register when the skill is invoked and stay active for the rest of the session:

| Before                | Check                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| A quote               | Denied when the prompt fails the linter or was not shown to you, exactly as sent, in a code block; asks you when no intake question was asked |
| A generation          | Denied when it does not match a quote made in this session (Higgsfield: the `quote_ref`; Artlist: the same prompt, settings, and references)  |
| Every paid generation | Asks you, showing platform, settings, credits, and any skipped step: the other platform not quoted, balances not read, no intake questions    |

A generation made without invoking the skill is outside these hooks. To cover it, add an equivalent hook to `~/.claude/settings.json`.

## Structure

```text
seedance-25-promptmaker/
├── SKILL.md                       entry point: workflow, output contract, hooks
├── hooks/
│   ├── gate.py                    quote and generation guardrails
│   └── test_gate.py               guardrail tests
├── references/
│   ├── capabilities-and-limits.md verified Seedance 2.5 values and limits
│   ├── task-patterns.md           prompt patterns per task path
│   ├── quality-and-repair.md      take review, diagnosis, one-variable retries
│   ├── higgsfield.md              Higgsfield requests, uploads, drafts, gaps
│   └── artlist.md                 Higgsfield-to-Artlist correspondence, Artlist requests
└── scripts/
    └── lint_prompt.py             structural prompt linter
```

## Tests

```bash
python3 seedance-25-promptmaker/scripts/lint_prompt.py --self-test
python3 -I seedance-25-promptmaker/hooks/test_gate.py
```

## Status

| Part                           | Status                                                                   |
| ------------------------------ | ------------------------------------------------------------------------ |
| Prompt workflow and references | Ready                                                                    |
| Linter                         | Ready; heuristic, it does not judge aesthetics                           |
| Higgsfield generation          | Ready                                                                    |
| Artlist generation             | Quotes verified; generation not yet tested end to end                    |
| Hooks                          | Tested, and verified live on a Higgsfield quote and a blocked generation |

Open points: whether each platform passes references to Seedance in the order sent, and how many references Artlist accepts. Each platform page lists its gaps.

The skill does not treat uploaded media as proof of rights. Real people, voices, brands, music, and protected characters need authorization or an original replacement.

## Sources

Seedance 2.5 facts come from the official [Dreamina Seedance 2.5 User Guide](https://bytedance.larkoffice.com/wiki/NjnWwvf4BiFYFLk2RzrcEgaunGf), the [Dreamina Seedance 2.5 Prompt Guide](https://bytedance.larkoffice.com/docx/A88jd0B47oAd8zxWp5ycZFMfnxh), and the [BytePlus Seedance 2.5 prompt guide](https://docs.byteplus.com/en/docs/modelark/seedance-2-5-prompt-guide). Platform parameters come from each platform's live model contract, which overrides the values written in the skill.

## Credits

- [sjinn-ai/seedance2.5-skills](https://github.com/sjinn-ai/seedance2.5-skills): the original Seedance 2.5 Director skill, its references, and the prompt linter, on which this repository builds.
- [Emily2040/seedance-2.0](https://github.com/Emily2040/seedance-2.0) (MIT): mode routing, reference contracts, continuity truth, and the one-variable retake method that informed the original skill.
- Higgsfield and Artlist integration, platform comparison, and hooks: Michele Cremaschi.
