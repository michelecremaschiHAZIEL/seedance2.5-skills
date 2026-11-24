# Generating on Artlist

How a compiled prompt becomes a Seedance 2.5 job through the Artlist MCP server (tools named `mcp__artlist__*`), and how each Higgsfield request in [higgsfield.md](higgsfield.md) maps to it. The Artlist tool descriptions and server instructions are the source of truth for call mechanics, including what may be shown to the user; this page holds only what they do not say about this skill's task paths.

## Contents

- [Live model contract](#live-model-contract)
- [Correspondence table](#correspondence-table)
- [Task path to request](#task-path-to-request)
- [Local files](#local-files)
- [Generation sequence](#generation-sequence)
- [Drafts and rendering](#drafts-and-rendering)
- [Known gaps to verify](#known-gaps-to-verify)

## Live Model Contract

Before the first quote in a conversation, call `list_models` with `kind: "video"` and keep the entries whose name starts with `[ByteDance] - Seedance 2.5` (the full model) or `[ByteDance] - Seedance 2.5 Flash` (the cheaper one). Each family shares one `modelGroupId`; call `get_model_config` with it. Its settings and options override every value on this page. The list is long: filter it with a script rather than reading it whole.

Artlist splits Seedance 2.5 into one variant per input type and resolution: `I2V`, `T2V`, `R2V - Image`, `R2V - Audio`, `R2V - Video (all references)`, `R2V - Video edit`, each at 480p, 720p, 1080p, and 4K (Flash: 480p and 720p). Passing the `modelGroupId` lets Artlist route to the variant from the `input` and `settings.resolution`; the edit variant is the exception (see [Task path to request](#task-path-to-request)).

## Correspondence Table

Values observed on November 24, 2026. Build the same request on both platforms so the two quotes price the same video.

| Higgsfield | Artlist | Difference |
|---|---|---|
| `model: "seedance_2_5"` | `modelGroupId` of the Seedance 2.5 family | Flash: `seedance_2_5_flash` ↔ Flash family |
| `mode` | no field: the `input` shape and, for edits, the `modelId` select the variant | |
| `duration` 4–30, default 5 | `settings.duration` `"4"`–`"30"` (string), default `"10"` | Pass it explicitly on both |
| `resolution` `480p`/`720p`/`1080p`/`4k`, default `720p` | `settings.resolution` `480p`/`720p`/`1080p`/`4K`, default `480p` | Artlist writes `4K` in capitals; its 480p is always a draft |
| `aspect_ratio` | `settings.aspect_ratio`, same values | Edit variant: `auto` only |
| `generate_audio` | `settings.generate_audio` `"true"`/`"false"` | |
| `bitrate_mode` | none | |
| none | `settings.output_format` `mp4`/`mov` | Leave `mp4` unless the user asks |
| `video_extension` + `extension_mode` | none | Extension runs on Higgsfield only |
| `draft: true` | `settings.resolution: "480p"` | |
| finalize with `draft_job_id` at any resolution | `render_draft`, 1080p only | 720p or 4K finals on Artlist are generated directly, not from a draft |
| `start_image` | `input: { startFrame: ref }` | |
| `end_image` | `input: { startFrame: ref, endFrame: ref }` | A frames request carries no other reference |
| `image_references` / `video_references` / `audio_references` | `input: [ref, …]` mixed; the file type sets the role | No role field: the prompt alone says what each asset is for |
| reference limits 30 images, 10 videos, 10 audio | not stated by `get_model_config` | An over-limit request fails at generation time |
| media ID from `media_upload` | `assetId` from `upload_image` / `upload_video` / `upload_audio` | |
| job ID as media `value` | `input: { generationId, outputIndex? }` | |
| none | `input: { referenceId }`, `styleKitId` | Saved characters, props, locations, and style kits |
| `estimate_video_cost` → `quote_ref` | `get_generation_cost` with `kind: "video"` and the same arguments as `generate_video` | Artlist has no quote reference: the generate call re-prices |
| `balance` | `get_balance` | Credits are not interchangeable between platforms |
| `jobs_wait` | `get_generation_status`, called again while `pending` | Deadline 540 s |

## Task Path to Request

| Skill task path | Artlist request |
|---|---|
| Basic generation, text only | no `input` |
| Image-to-video, first frame | `input: { startFrame }` or `input: { assetId }` |
| First and last frames | `input: { startFrame, endFrame }`; supporting references need Higgsfield |
| Multimodal reference, keyframes, storyboard, blockout, one-click video, transition | `input: [ … ]` in the order the role map sets |
| Video edit | `modelId` of `[ByteDance] - Seedance 2.5 - R2V - Video edit - <resolution>` from `list_models`, the master video first in `input` |
| Forward or backward extension | not available: quote Higgsfield only and say why |
| Multi-clip production | one request per clip; `generate_batch` for several, after quoting each |

Write tokens as on Higgsfield (`@Image1`, `@Video1`, `@Audio1`), numbered per type in `input` order, and keep the role map, the `input` array, and the tokens in the same order.

## Local Files

1. `upload_image`, `upload_video`, or `upload_audio` with `mimeType` and the real `fileName`.
2. `curl -f -X PUT -H 'Content-Type: <type>' --upload-file '<path>' '<uploadUrl>'` from Bash.
3. `confirm_upload` with the same `uploadId`, `mimeType`, and `fileName`.

A public URL goes through the `imageUrl`, `videoUrl`, or `audioUrl` field of the same upload tools. When the PUT is blocked, use `upload_widget`.

## Generation Sequence

Steps 1–3 run for the platform comparison of SKILL.md step 7; steps 4–7 run only when the user picks Artlist.

1. **Lint** the final prompt (SKILL.md, step 6).
2. **Upload** the local files (see [Local files](#local-files)).
3. **Quote**: `get_generation_cost` with `kind: "video"`, the prompt, `modelGroupId` (or the edit `modelId`), `settings`, and `input`. For a draft, also quote the same request at the final resolution as the estimate of the render; the real render quote is `get_generation_cost` with `kind: "draftRender"` and the draft's `generationId`, once the draft exists.
4. **Generate**: `generate_video` with exactly the quoted arguments. When it returns `confirmation_required`, show the user that cost and stop; re-call with `confirmCost: true` only after the user approves in a new message.
5. **Wait**: `get_generation_status` with the `generationId`, again at once while `pending`. On a transport timeout, keep waiting on the same ID; never resubmit.
6. **Report** the terminal status; on a failure or moderation result, relay the reason and move to diagnosis.
7. **Verify**: download the result from the status URL and look at its frames before describing it; for an edit, compare it with the source as in [quality-and-repair.md](quality-and-repair.md#unchanged-edit). `download_generation` is for when the user asks to save the file.

## Drafts and Rendering

- A 480p Seedance 2.5 generation is a draft; `render_draft` with its `generationId` renders the same take at 1080p within seven days, billed at the 1080p price. State the deadline when delivering a draft.
- A draft for a final at 720p or 4K brings no render path on Artlist: say so in the comparison and quote the final directly, or point to Higgsfield for that draft.
- On `draft_unavailable`, generate again at 1080p; on `reference_expired`, upload the files again.

## Known Gaps to Verify

These points were not confirmed by Artlist documentation when this page was written. When a result contradicts them, tell the user and propose correcting this page.

- That Artlist passes `input` to Seedance in array order, so `@Image1` is the first image in `input`.
- How many references of each type the R2V variants accept.
- Whether the group routes a single video `assetId` to `R2V - Video (all references)` or rejects it without the edit `modelId`.
