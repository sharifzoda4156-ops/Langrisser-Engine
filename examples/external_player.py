"""An external HTTP player. Replace choose_action with a model adapter.

Start one process per side against a running local stand and an existing match.
"""
import argparse
import json
from pathlib import Path
import random
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apex_engine.agents import choose_action, submission  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--player", type=int, choices=(0, 1), required=True)
    parser.add_argument("--agent", choices=("random", "heuristic"), default="heuristic")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--idle-timeout", type=float, default=60)
    parser.add_argument("--once", action="store_true", help="make at most one decision")
    args = parser.parse_args()
    parts = urlsplit(args.base_url)
    if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.path not in ("", "/")
            or parts.query or parts.fragment or parts.username or parts.password):
        parser.error("only the local HTTP stand is supported")
    if args.idle_timeout <= 0:
        parser.error("idle-timeout must be positive")
    if len(args.match_id) != 32 or any(c not in "0123456789abcdef" for c in args.match_id):
        parser.error("match-id must be a lowercase 32-character hexadecimal id")
    base = args.base_url.rstrip("/")
    rng = random.Random(args.seed)

    def call(path, payload=None):
        request = Request(base + path, headers={"Content-Type": "application/json"},
                          data=None if payload is None else json.dumps(payload).encode())
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    idle_since = time.monotonic()
    while True:
        envelope = call(f"/matches/{args.match_id}/request?player={args.player}")
        if envelope["finished"]:
            print(json.dumps({"finished": True, "version": envelope["version"]}))
            return 0
        if envelope["request"] is None:
            if args.once:
                print(json.dumps({"waiting": True}))
                return 0
            if time.monotonic() - idle_since > args.idle_timeout:
                print("opponent idle timeout", file=sys.stderr)
                return 2
            time.sleep(0.1)
            continue
        action = choose_action(envelope["request"], args.agent, rng)
        receipt = call(f"/matches/{args.match_id}/actions", submission(envelope, action["action_id"]))
        print(json.dumps(receipt), flush=True)
        idle_since = time.monotonic()
        if args.once or receipt["finished"]:
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
