"""Build the dependency-free C++ protocol fixture with the local compiler."""
from pathlib import Path
import argparse
import os
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    target = ROOT / "build" / "apex_fixture"
    target.parent.mkdir(exist_ok=True)
    flags = ["-std=c++20", "-Wall", "-Wextra", "-Wpedantic", "-Werror"]
    flags += (["-O1", "-g", "-fsanitize=undefined", "-fno-sanitize-recover=all"]
              if args.sanitize else ["-O2"])
    subprocess.run([*shlex.split(os.environ.get("CXX", "g++")), *flags,
                    str(ROOT / "native" / "engine.cpp"), "-o", str(target)], check=True)
    print(target)


if __name__ == "__main__":
    main()
