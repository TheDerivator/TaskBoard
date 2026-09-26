"""One-command quality gate: lint, format, types, architecture contracts, codemap, all tests.

uv run python scripts/check.py          # everything except browser (e2e) tests
uv run python scripts/check.py --e2e    # also run Playwright browser tests
uv run python scripts/check.py --fix    # apply ruff fixes and formatting first
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    py = sys.executable
    steps: list[tuple[str, list[str]]] = []
    if args.fix:
        steps += [
            ("ruff fix", ["ruff", "check", "--fix", "--exit-zero", "."]),
            ("ruff format", ["ruff", "format", "."]),
            ("codemap", [py, "scripts/gen_codemap.py"]),
        ]
    steps += [
        ("ruff lint", ["ruff", "check", "."]),
        ("ruff format", ["ruff", "format", "--check", "."]),
        ("pyright", ["pyright"]),
        ("import contracts", ["lint-imports"]),
        ("codemap fresh", [py, "scripts/gen_codemap.py", "--check"]),
        ("pytest", [py, "-m", "pytest", "-q", "-m", "e2e or not e2e" if args.e2e else "not e2e"]),
    ]
    js_tests = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
    if js_tests:
        if shutil.which("node"):
            steps.append(("js unit tests", ["node", "--test", *js_tests]))
        else:
            print("! node not found: skipping JS unit tests")
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--e2e", action="store_true", help="include Playwright browser tests")
    parser.add_argument("--fix", action="store_true", help="apply automatic fixes first")
    args = parser.parse_args()

    failures: list[str] = []
    for name, command in _steps(args):
        print(f"\n=== {name}: {' '.join(command)}", flush=True)
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
        status = "ok" if result.returncode == 0 else f"FAILED ({result.returncode})"
        print(f"--- {name}: {status} in {time.perf_counter() - started:.1f}s", flush=True)
        if result.returncode != 0:
            failures.append(name)

    print("\n" + ("All checks passed." if not failures else f"Failed: {', '.join(failures)}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
