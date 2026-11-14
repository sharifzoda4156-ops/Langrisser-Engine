"""CLI for the external-player stand and baseline self-play."""
import argparse
import json
from pathlib import Path
import sys

from .agents import run_selfplay
from .errors import EngineError
from .game import ROOT, integer
from .stand import Stand, verify_replay


def read_json(path):
    return json.loads(sys.stdin.read() if path == "-" else Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="runs/stand.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create a synthetic fixture match")
    create.add_argument("--scenario", default=str(ROOT / "scenarios" / "protocol_fixture.json"))
    create.add_argument("--snapshot", help="sealed content snapshot; exact scenario binding is checked")
    request = commands.add_parser("request", help="fetch a player's pending decision")
    request.add_argument("match_id")
    request.add_argument("--player", type=int, choices=(0, 1), required=True)
    submit = commands.add_parser("submit", help="submit an exact decision response")
    submit.add_argument("match_id")
    submit.add_argument("--response", required=True, help="JSON file, or - for stdin")
    replay = commands.add_parser("replay", help="export the complete event replay")
    replay.add_argument("match_id")
    verify = commands.add_parser("verify", help="recompute a replay and verify events and hashes")
    verify.add_argument("path")
    selfplay = commands.add_parser("selfplay", help="collect baseline games; no neural training")
    selfplay.add_argument("--scenario", default=str(ROOT / "scenarios" / "protocol_fixture.json"))
    selfplay.add_argument("--snapshot", help="sealed content snapshot")
    selfplay.add_argument("--episodes", type=int, default=2)
    selfplay.add_argument("--seed", type=int, default=1)
    selfplay.add_argument("--players", nargs=2, choices=("random", "heuristic"),
                          default=["heuristic", "random"])
    selfplay.add_argument("--output", required=True, help="a new directory")
    serve = commands.add_parser("serve", help="start loopback-only JSON HTTP stand")
    serve.add_argument("--port", type=int, default=8765)
    content = commands.add_parser("content", help="build, compose and verify regional content snapshots")
    content_commands = content.add_subparsers(dest="content_command", required=True)
    build = content_commands.add_parser("build", help="freeze exact catalog revisions for a regional date")
    build.add_argument("--catalog", required=True)
    build.add_argument("--manifest", required=True)
    build.add_argument("--output", help="new output file; otherwise print the snapshot")
    preview = content_commands.add_parser("preview", help="explicit changes over a frozen Global baseline")
    preview.add_argument("--baseline", required=True)
    preview.add_argument("--source", required=True)
    preview.add_argument("--changes", required=True, help="JSON list of exact id/revision references")
    preview.add_argument("--snapshot-id", required=True)
    preview.add_argument("--output", help="new output file; otherwise print the snapshot")
    content_verify = content_commands.add_parser("verify", help="validate a sealed snapshot and its lineage")
    content_verify.add_argument("path")
    args = parser.parse_args()
    try:
        if args.command == "content":
            from .content import build_preview, build_snapshot, verify_snapshot
            if args.content_command == "verify":
                result = {"verified": True, **verify_snapshot(read_json(args.path))}
            else:
                if args.content_command == "build":
                    snapshot = build_snapshot(read_json(args.catalog), read_json(args.manifest))
                else:
                    snapshot = build_preview(read_json(args.baseline), read_json(args.source),
                                             read_json(args.changes), args.snapshot_id)
                if args.output:
                    target = Path(args.output)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("x") as output:
                        output.write(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
                    result = {"output": str(target), **verify_snapshot(snapshot)}
                else:
                    result = snapshot
        elif args.command == "verify":
            result = verify_replay(read_json(args.path))
        elif args.command == "serve":
            from .http_server import make_server
            integer(args.port, "port", 0, 65535)
            server = make_server(args.db, args.port)
            print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}",
                              "fidelity": "synthetic_fixture"}), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        else:
            stand = Stand(args.db)
            if args.command == "create":
                config = read_json(args.scenario)
                if args.snapshot:
                    from .content import bind_snapshot
                    config = bind_snapshot(config, read_json(args.snapshot))
                result = stand.create_match(config)
            elif args.command == "request":
                result = stand.get_decision_request(args.match_id, args.player)
            elif args.command == "submit":
                result = stand.submit_action(args.match_id, read_json(args.response))
            elif args.command == "replay":
                result = stand.get_replay(args.match_id)
            else:
                config = read_json(args.scenario)
                if args.snapshot:
                    from .content import bind_snapshot
                    config = bind_snapshot(config, read_json(args.snapshot))
                result = run_selfplay(stand, config, args.episodes,
                                      args.seed, args.players, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (EngineError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
