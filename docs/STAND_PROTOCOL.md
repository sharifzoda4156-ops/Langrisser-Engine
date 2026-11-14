# External-player stand protocol v1

## Scope

Supported fidelities: `synthetic_fixture` and `mechanics_lab`, selected by ruleset.
Neither includes hidden information or chance, real Apex damage or trained AI.
HTTP is a loopback development interface with no authentication, not a public API.
CLI and HTTP call the same Stand implementation and the same SQLite database.

Scenarios may optionally include a sealed `content_snapshot`; CLI create/selfplay
also accept `--snapshot FILE`. The stand checks availability, explicit preview
lineage and exact hero/map/draft payload binding before committing a match. A
compact `experiment` label is returned at creation and in player observations;
the full snapshot stays in the replay's config and participates in state hashes.
Only synthetic snapshots can execute today. Real release metadata cannot run as
fixture combat. See [content snapshots](CONTENT_SNAPSHOTS.md).

`action-lifecycle-lab-v1` has a separate strict scenario and reports `mechanics_lab`
in creation responses, observations, replays and collection summaries. Snapshot
binding is unsupported there and rejected. While `act_again` or `post_move` is
pending, the same side retains the request and only that unit may act. A post-move
request exposes only `finish_move`, including a zero-distance finish. It consumes
the same request/version protocol and survives restart. See
[the lifecycle contract](ACTION_LIFECYCLE.md).

Health/startup metadata retains `fidelity` for the default fixture and additionally
lists `default_ruleset` and `supported_rulesets`. Match fidelity comes from the
selected ruleset, not the server's default.

## Routes

| Method | Path | Input / result |
| --- | --- | --- |
| GET | `/health` | Status, protocol and fidelity |
| POST | `/matches` | Entire validated scenario → match id/version |
| GET | `/matches/{id}/request?player=0` | Decision envelope for side 0 or 1 |
| POST | `/matches/{id}/actions` | Exact decision submission → receipt |
| GET | `/matches/{id}/replay` | Consistent full replay snapshot |

POST requires `Content-Type: application/json`, a Content-Length and a body of at
most 1 MiB. Send Host `127.0.0.1:PORT`; browser Origin headers are rejected.
No remote hosting, TLS, user accounts, seat tokens or production rate limiting
is provided. The full replay is a local debugging export, not a player-filtered
observation. Add separate authorization before any remote or hidden-info use.

## Decision envelope

Every envelope includes match id, version, current player and finished status.
If it is another side's decision, `waiting=true` and `request=null`. At completion,
`finished=true`, `waiting=false`, `current_player=null`, `request=null` for both.

A pending request contains:

- `protocol_version`: currently 1.
- `request_id`: SHA-256 of match id, version, actor and state hash.
- `state_hash`: canonical state plus immutable scenario and protocol version.
- `player`: actor 0 or 1.
- `observation`: map, fixture hero boxes and public logical state.
- `legal_actions`: complete allowed fixture actions with stable action ids.

Draft actions have kind `ban` or `pick` and hero id. Battle actions have kind
`wait` or `attack`, numeric unit id, destination `to`, numeric `target` (-1 for
wait), and canonical movement `path`. Unit ids match pick order and are distinct
from hero ids. The observation's picked lists map units back to selected heroes.

## Submission and atomicity

```json
{
  "request_id": "<64 lowercase hexadecimal characters>",
  "state_hash": "<64 lowercase hexadecimal characters>",
  "expected_version": 0,
  "player": 0,
  "action_id": "<64 lowercase hexadecimal characters>"
}
```

The five fields are required; unknown fields are rejected. The engine validates
the pending request and recomputes legal actions. A successful transition stores
state and receipt atomically and increments version once.

Receipts contain request/action ids, actor, resulting version, before/after hashes,
ordered events and finished status. Identical retries return the exact original
receipt. A differing submission reusing that request id is rejected, including
after restart. Stale requests never silently apply against a newer position.

HTTP 400 = invalid schema/action; 404 = unknown match/route; 409 = conflict;
413 = invalid body size; 415 = wrong content type; 403 = non-local/browser origin.

## Replay

`python -m apex_engine replay MATCH_ID > runs/replay.json`

`python -m apex_engine verify runs/replay.json`

Replay export is a consistent database snapshot. Verification checks actor,
request, version, action, event sequence and final state/hash by executing the
rules again. Both unfinished prefixes and complete games can be verified; inspect
the returned `finished` flag. Tamper detection is not cryptographic authorship.

## Replacing the baseline with an LLM

See `examples/external_player.py`. Replace `choose_action` with an external model's
decision while retaining observation limits and the exact submission contract.
An agent already using terminal tools can use CLI request/submit directly.
Keep each side's gameplay context separate for meaningful model comparisons.
Persistent autonomous LLM play requires a separately running authorized model
adapter; starting this stand does not create an API subscription or background chat.
