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
    selfplay.add_argument("--episodes", type=int, default=2)
    selfplay.add_argument("--seed", type=int, default=1)
    selfplay.add_argument("--players", nargs=2, choices=("random", "heuristic"),
                          default=["heuristic", "random"])
    selfplay.add_argument("--output", required=True, help="a new directory")
    serve = commands.add_parser("serve", help="start loopback-only JSON HTTP stand")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "verify":
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
                result = stand.create_match(read_json(args.scenario))
            elif args.command == "request":
                result = stand.get_decision_request(args.match_id, args.player)
            elif args.command == "submit":
                result = stand.submit_action(args.match_id, read_json(args.response))
            elif args.command == "replay":
                result = stand.get_replay(args.match_id)
            else:
                result = run_selfplay(stand, read_json(args.scenario), args.episodes,
                                      args.seed, args.players, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (EngineError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
