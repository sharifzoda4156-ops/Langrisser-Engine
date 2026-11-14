"""Exercise a server and two external players as separate local processes."""
import argparse
import json
from pathlib import Path
import select
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apex_engine.stand import verify_replay  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new output directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    players, logs = [], []
    server = subprocess.Popen([sys.executable, "-m", "apex_engine", "--db",
                               str(output / "stand.sqlite3"), "serve", "--port", "0"],
                              cwd=ROOT, stdout=subprocess.PIPE, text=True)
    try:
        if not select.select([server.stdout], [], [], 10)[0]:
            raise RuntimeError("stand startup timeout")
        base = json.loads(server.stdout.readline())["url"]
        config = (ROOT / "scenarios" / "protocol_fixture.json").read_bytes()
        request = Request(base + "/matches", data=config,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            match_id = json.load(response)["match_id"]
        for side, agent in [(0, "heuristic"), (1, "random")]:
            log = (output / f"player-{side}.jsonl").open("w")
            logs.append(log)
            players.append(subprocess.Popen([
                sys.executable, "examples/external_player.py", "--base-url", base,
                "--match-id", match_id, "--player", str(side), "--agent", agent,
                "--idle-timeout", "10"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
        codes = [p.wait(timeout=20) for p in players]
        if codes != [0, 0]:
            raise RuntimeError(f"external players failed: {codes}; inspect {output}")
        with urlopen(base + f"/matches/{match_id}/replay", timeout=5) as response:
            replay = json.load(response)
        (output / "replay.json").write_text(json.dumps(replay, indent=2) + "\n")
        result = verify_replay(replay)
        if not result["finished"]:
            raise RuntimeError("external match did not finish")
        print(json.dumps({"external_player_exit_codes": codes, **result}, indent=2))
    finally:
        for process in [*players, server]:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        if server.stdout:
            server.stdout.close()


if __name__ == "__main__":
    main()
