import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_SCRIPTS = (
    "run_remaining_tests.py",
    "test_string_utils.py",
    "test_timezone_utils.py",
    "test_system_metrics.py",
    "test_db_recovery.py",
)


def main() -> int:
    test_env = os.environ.copy()
    test_env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(PROJECT_ROOT), test_env.get("PYTHONPATH"))))
    for script_name in TEST_SCRIPTS:
        script = Path(__file__).with_name(script_name)
        print(f"\n=== Running {script_name} ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(script)],
            env=test_env,
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
