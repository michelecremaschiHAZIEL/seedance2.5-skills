# Generating on Higgsfield

How a compiled prompt becomes a Seedance 2.5 job through the Higgsfield MCP server (tools named `mcp__claude_ai_Higgsfield__*`). The Higgsfield tool descriptions are the source of truth for call mechanics; this page holds only what they do not say about this skill's task paths.

## Contents

- [Live model contract](#live-model-contract)
- [Task path to request](#task-path-to-request)
- [Reference tokens and media order](#reference-tokens-and-media-order)
- [Local files](#local-files)
- [Generation sequence](#generation-sequence)
- [Drafts and finalizing](#drafts-and-finalizing)
- [Retries](#retries)
- [Known gaps to verify](#known-gaps-to-verify)

## Live Model Contract

Before the first quote in a conversation, call `models_explore` with `action: "get"`, `model_id: "seedance_2_5"`. Its parameters, roles, ranges, and aspect ratios override every value on this page and in [capabilities-and-limits.md](capabilities-and-limits.md). When the model ID is missing, run `models_explore` with `action: "search"`, `query: "seedance 2.5"`, `type: "video"`, and tell the user what changed.

At the time of writing, Higgsfield exposed:

| Parameter | Values | Note |
|---|---|---|
| `mode` | `t2v`, `omni_reference`, `video_edit`, `video_extension` | Default `t2v` |
| `duration` | 4–30, whole seconds | Default 5: always pass it explicitly |
| `resolution` | `480p`, `720p`, `1080p`, `4k` | Default `720p`; Higgsfield exceeds the Dreamina 480p/720p list |
| `aspect_ratio` | `auto`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16` | Ignored by `video_edit` and `video_extension` |
| `generate_audio` | boolean | Default true; set false when the brief wants silence or the sound comes from post |
| `extension_mode` | `forward`, `backward` | Required with `video_extension`, rejected otherwise |
| `draft`, `draft_job_id` | boolean, job ID | 480p draft, finalized within seven days |

Media roles: `start_image`, `end_image` (only in `omni_reference`), `image_references` (max 30 including start and end images), `video_references` (max 10), `audio_references` (max 10). `video_edit` is billed by the source video's length.

## Task Path to Request

| Skill task path | `mode` | Media roles |
|---|---|---|
| Basic generation, text only | `t2v` | none |
| Image-to-video, first frame | `omni_reference` | `start_image` |
| First and last frames | `omni_reference` | `start_image`, `end_image` |
| Multimodal reference | `omni_reference` | `image_references`, `video_references`, `audio_references` as the role map says |
| Multiple keyframes | `omni_reference` | `image_references` in keyframe order; the prompt states the order |
| Storyboard grid | `omni_reference` | the grid in `image_references` |
| Blockout | `omni_reference` | the blockout render in `video_references` (or `image_references` for stills) |
| One-click video | `omni_reference` | `image_references` in asset order |
| Seamless transition | `omni_reference` | both clips in `video_references`, outgoing clip first |
| Video edit | `video_edit` | the sole master in `video_references`; supporting images in `image_references` |
| Forward or backward extension | `video_extension` + `extension_mode` | the accepted take in `video_references` |
| Multi-clip production | one request per clip | each clip follows its own path |

Keyframes, storyboards, blockouts, one-click video, and transitions have no dedicated Higgsfield mode: they run as `omni_reference`, and the prompt alone carries the order and roles. Say so in the risks when the user expects the Dreamina dedicated workflow.

For extensions and edits of a take generated in this conversation, pass its job ID as the media `value`; no re-upload is needed.

## Reference Tokens and Media Order

Higgsfield inserts no tokens: this skill writes them. Use the Higgsfield form, without a space: `@Image1`, `@Video1`, `@Audio1`. Convert the `@Image 1` form used in [task-patterns.md](task-patterns.md) templates when compiling.

- Number tokens per media type in upload order, which on Higgsfield is the order of the items in `medias`: the first `image_references` item is `@Image1`, the first `video_references` item is `@Video1`. The [BytePlus Seedance 2.5 prompt guide](https://docs.byteplus.com/en/docs/modelark/seedance-2-5-prompt-guide) states that numbering follows upload order, per type.
- Put the items in `medias` in the order their subjects first appear in the video. The guide documents swapped characters when the order differs.
- Refer to `start_image` and `end_image` in prose ("the first frame", "the last frame"), not by token.
- Keep the role map, the `medias` array, and the tokens in the prompt in the same order; check all three before the quote.

## Local Files

A local image, video, or audio file needs a `media_id` before it can be used:

1. `media_upload` with the file name (or `files[]` for several).
2. `curl -f -X PUT -H 'Content-Type: <type>' --upload-file '<path>' '<upload_url>'` for each file, from Bash.
3. `media_confirm` with the IDs and their `type`, only after every PUT succeeded.

A web URL goes through `media_import_url`. `medias[].value` takes only media IDs or job IDs, never URLs.

## Generation Sequence

1. **Lint** the final prompt (SKILL.md, step 6).
2. **Quality**: ask the user, in one question, how to render, unless they already named a resolution or a draft in this conversation. Ask it in the last intake round of SKILL.md step 1, before the prompt is written. Offer, in this order:
   - **Draft first (recommended)**: `draft: true`, 480p, cheaper; review the take, then finalize the accepted draft at the chosen resolution (see [Drafts and finalizing](#drafts-and-finalizing)).
   - **Final directly**: `resolution` `720p`, `1080p`, or `4k`, for a prompt already proven or a simple shot.
   Name the final resolution the draft will be finalized at, so the user sees both steps.
3. **Quote**: `estimate_video_cost` with the exact `params` of the request. For a draft, also quote the same request without `draft` at the chosen final resolution, and present it as an estimate of the finalize, so the user sees the cost of both steps; the real finalize quote comes once the draft job exists.
4. **Confirm**: show the user the model, mode, duration, resolution, aspect ratio, audio, media count, and credits, then stop. Generate only after the user explicitly accepts this quote. A new quote is needed whenever any parameter or the prompt changes.
5. **Generate**: `generate_video` with `params: {"ref": "<quote_ref>"}`, so the request is exactly the quoted one. Follow the tool's own rules on `folder_id`, `use_unlim`, and `unlim_choice`: when an `unlim_choice` comes back, put its question to the user.
6. **Wait**: `jobs_wait` with the job ID until it is terminal. On a transport timeout the outcome is unknown: wait on the returned job ID; never resubmit.
7. **Report**: state the terminal status. On `failed`, `nsfw`, or `ip_detected`, relay the reason and move to diagnosis; never resubmit with a changed prompt to get past a moderation result.

One request per generation by default (`count: 1`). Use `count` 2–4 only when the user asks for variants of the same request; use `generate_video_batch` for several independent clips of a multi-clip plan, after quoting each.

## Drafts and Finalizing

- A draft is a `draft: true` request: Seedance renders it at 480p. Iterate on drafts until the take is accepted; each retry is a new draft.
- Finalize an accepted draft with a request carrying `draft_job_id` and the chosen `resolution`. The final renders the draft's full duration, is billed for it, and ignores `duration`. It needs its own quote and acceptance.
- A draft can be finalized only within seven days. When delivering a draft, state the deadline.
- Finalizing re-renders the draft through Seedance at the higher resolution; it is the path to use for an accepted draft. `upscale_video` is a separate post-process on a finished file: offer it only when the user asks for a plain upscale or the draft has expired.

## Retries

- A retry follows [quality-and-repair.md](quality-and-repair.md): one changed variable, a new quote, a new confirmation.
- Judge a take only from what you can inspect. When the result video cannot be viewed in this client, ask the user for the observed defects and label them user-reported.

## Known Gaps to Verify

These points were not confirmed by Higgsfield documentation when this page was written. When a result contradicts them, tell the user and propose correcting this page.

- That Higgsfield passes `medias` to Seedance in array order (the guide confirms upload-order numbering for the BytePlus API only).
- Whether `start_image` and `end_image` count in `@Image` numbering.
- Whether a transition between two `video_references` behaves like the Dreamina Seamless Video Transition.
