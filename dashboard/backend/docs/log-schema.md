# `messages.jsonl` Schema (verified)

> Verified against `/dev-booth/sessions/test-awg/log/messages.jsonl` on 2026-05-14.

The plan's original spec listed `{time, agent, input, output}`, but the **actual**
AWG message format on disk is:

```json
{
  "id": "2502518c-370b-445c-be9d-45a45b8f8d40",
  "kind": "instruction",
  "from": "conductor",
  "to": "architect",
  "body": "프로젝트 분석을 시작해주세요.",
  "refs": {},
  "priority": 50,
  "createdAt": "2026-05-11T11:38:59Z",
  "createdAtMs": 1778499539282
}
```

## Field reference

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID v4) | Unique per message |
| `kind` | string | `instruction`, `response`, ... |
| `from` | string | Sender agent: `conductor` \| `architect` \| `executor` |
| `to` | string | Recipient agent (same enum) |
| `body` | string | Message text (Korean + English) |
| `refs` | object | Free-form, may contain `receivedAt`, `receivedAtMs`, references to other ids |
| `priority` | integer | Lower = higher priority in AWG semantics |
| `createdAt` | string (ISO8601 UTC) | Wallclock |
| `createdAtMs` | integer (epoch ms) | High-resolution sort key |

The Pydantic model `LogEntry` (in `services/models.py`) uses `from_` for the
Python-reserved word with `alias="from"`. The convenience `.agent` property
returns the `from_` value so UI code can read "who sent it" without thinking
about the rename.

## Notes for UI

- Sender identity (`from`) is used for the agent dot/color.
- `kind == "instruction"` typically flows Conductor → Architect/B.
- `kind == "response"` typically flows Hermes → Conductor.
- The dashboard does NOT mutate or write these files.
