# Official release captures (P02-T02)

`pob2opt catalog export` resolves the live game patch from the files in this
directory and from nothing else. It never contacts a provider: an export that
could fetch a patch id could also fetch it wrong, and `tests/unit` runs with
outbound sockets blocked.

One file per captured official page, `capture_version: 1`, with:

| Field | Meaning |
|---|---|
| `provider`, `source_url` | Who published the page and where it is. |
| `captured_at`, `capture_method` | When it was read and by what. |
| `fidelity` | `verbatim` for a byte capture, `summary` for a reading of it. |
| `patch_id`, `patch_published_at` | The patch the page names and its post time. |
| `title`, `author` | The page's own title and poster, kept as attribution. |
| `excerpt` | A short attributed excerpt. Not a copy of the page. |
| `redistribution` | `restricted` for third-party pages. Review locally; do not republish. |
| `notes` | What the capture is and is not. |

A `summary` capture can name the patch and can never support `verified`
compatibility: the exporter records that as a gap every time. Replacing one
with a `verbatim` capture is a separate collection task, not an edit to this
file.

With no capture here the export records `patch_id: unknown`, compatibility
`unknown` and a blocking gap. That is the intended behaviour, not a failure.

## Current contents

| File | Patch | Fidelity | Source |
|---|---|---|---|
| `poe2-0.5.5e.json` | 0.5.5e | summary | Official Early Access Patch Notes thread, read 2026-10-06 |
