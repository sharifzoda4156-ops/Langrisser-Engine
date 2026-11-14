"""Exercise the public content CLI, preview collection and external-player stand."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "content"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="new output directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)

    def cli(*arguments):
        result = subprocess.run([sys.executable, "-m", "apex_engine", *map(str, arguments)],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)

    for region in ("global", "cn"):
        cli("content", "build", "--catalog", DATA / "fixture_catalog.json", "--manifest",
            DATA / f"fixture_{region}_manifest.json", "--output", output / f"{region}.json")
    cli("content", "preview", "--baseline", output / "global.json", "--source", output / "cn.json",
        "--changes", DATA / "fixture_preview_changes.json", "--snapshot-id", "fixture-cli-preview",
        "--output", output / "preview.json")
    cli("content", "verify", output / "preview.json")
    snapshot = json.loads((output / "preview.json").read_text())
    scenario = json.loads((ROOT / "scenarios" / "protocol_fixture.json").read_text())
    candidate = next(e["payload"] for e in snapshot["entries"] if e["id"] == "fixture_vanguard")
    scenario["boxes"][0][0] = candidate
    (output / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n")
    report = cli("--db", output / "collection.sqlite3", "selfplay", "--scenario", output / "scenario.json",
                 "--snapshot", output / "preview.json", "--episodes", "2", "--seed", "17",
                 "--output", output / "collection")
    cli("verify", output / "collection" / "episode-00000.json")
    external = subprocess.run([sys.executable, "scripts/smoke_external.py", "--output", str(output / "external"),
                               "--scenario", str(output / "scenario.json"),
                               "--snapshot", str(output / "preview.json")],
                              cwd=ROOT, capture_output=True, text=True, timeout=45)
    if external.returncode:
        raise RuntimeError(external.stderr)
    print(json.dumps({"experiment": report["experiment"], "collection_episodes": report["episodes"],
                      "external": json.loads(external.stdout)}, indent=2))


if __name__ == "__main__":
    main()
