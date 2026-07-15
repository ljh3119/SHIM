import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPTS = (
    ("run_remaining_tests.py",),
    ("test_string_utils.py",),
    ("test_timezone_utils.py",),
    ("test_system_metrics.py",),
    ("test_db_recovery.py",),
    ("test_secret_key_security.py",),
    ("test_leave_service_improvements.py",),
    ("test_auth_password_limits.py",),
    ("test_ops_safety.py",),
)
RELEASE_ONLY_SCRIPTS = (
    ("test_graceful_shutdown.py",),
    ("test_duplicate_execution.py",),
    ("test_memory_leak.py", "--iterations", "1000"),
)


def _check_required_assets() -> bool:
    asset = PROJECT_ROOT / "src" / "static" / "js" / "time.js"
    template = PROJECT_ROOT / "src" / "templates" / "base.html"
    if not asset.is_file() or '/static/js/time.js' not in template.read_text(encoding="utf-8"):
        print("[ERROR] Required static asset is missing or not referenced: src/static/js/time.js")
        return False
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", asset.relative_to(PROJECT_ROOT).as_posix()],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )
    if tracked.returncode != 0:
        print("[ERROR] src/static/js/time.js must be tracked by Git.")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SHIM smoke or release checks.")
    parser.add_argument("mode", nargs="?", choices=("smoke", "release"), default="smoke")
    args = parser.parse_args(argv)

    if not _check_required_assets():
        return 1

    scripts = SMOKE_SCRIPTS + (RELEASE_ONLY_SCRIPTS if args.mode == "release" else ())
    base_env = os.environ.copy()
    base_env.pop("SHIM_SECRET_KEY", None)
    base_env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(PROJECT_ROOT), base_env.get("PYTHONPATH")))
    )

    for command in scripts:
        script_name, *script_args = command
        script = Path(__file__).with_name(script_name)
        print(f"\n=== Running {script_name} {' '.join(script_args)} ===", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"shim_{script.stem}_") as data_dir:
            test_env = base_env.copy()
            test_env["SHIM_DATA_DIR"] = data_dir
            result = subprocess.run(
                [sys.executable, str(script), *script_args],
                env=test_env,
                cwd=PROJECT_ROOT,
                check=False,
            )
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
