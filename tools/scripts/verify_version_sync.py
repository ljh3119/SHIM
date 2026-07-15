import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def main() -> int:
    version = str(json.loads(read_text("package.json"))["version"])
    errors: list[str] = []

    package_lock = json.loads(read_text("package-lock.json"))
    if str(package_lock.get("version")) != version:
        errors.append(f"package-lock.json: root version must equal package.json ({version}).")
    if str(package_lock.get("packages", {}).get("", {}).get("version")) != version:
        errors.append(f"package-lock.json: root package version must equal package.json ({version}).")

    constants = read_text("src/app/constants.py")
    if f'APP_VERSION = "{version}"' not in constants:
        errors.append(f"src/app/constants.py: APP_VERSION must equal package.json ({version}).")

    for relative_path in (
        "infra/docker/docker-compose.yml",
        "infra/docker/docker-compose.dev.yml",
        "infra/docker/docker-compose.test.yml",
    ):
        if f"shim:{version}" not in read_text(relative_path):
            errors.append(f"{relative_path}: default image must include shim:{version}")

    readme = read_text("README.md")
    if not re.search(r"\*\*[^*]+\*\*\s+" + re.escape(version) + r"(?:\s|$)", readme):
        errors.append(f"README.md: release version must equal package.json ({version}).")

    portable_readme = PROJECT_ROOT / "portable" / "README_PORTABLE.md"
    if portable_readme.exists() and f"v{version}" not in portable_readme.read_text(encoding="utf-8"):
        errors.append(f"portable/README_PORTABLE.md: must mention v{version}.")

    design_docs = list((PROJECT_ROOT / "docs").glob("4-1_*.md"))
    if design_docs:
        design_text = design_docs[0].read_text(encoding="utf-8")
        if not re.search(r"\*\*([^*]+)\*\*\s*:?\s*" + re.escape(version), design_text):
            errors.append(f"{design_docs[0].name}: version must equal package.json ({version}).")

    release_docs = list((PROJECT_ROOT / "docs").glob("2-1_*.md"))
    if release_docs:
        release_text = release_docs[0].read_text(encoding="utf-8")
        latest_release = re.search(r"^### v(\d+\.\d+\.\d+)", release_text, re.MULTILINE)
        if not latest_release or latest_release.group(1) != version:
            errors.append(f"{release_docs[0].name}: latest release heading must be v{version}.")
    maintenance_docs = list((PROJECT_ROOT / "docs").glob("1-2_*.md"))
    if maintenance_docs:
        maintenance_text = maintenance_docs[0].read_text(encoding="utf-8")
        if not re.search(r"-Version\s+" + re.escape(version), maintenance_text):
            errors.append(f"{maintenance_docs[0].name}: release command must use {version}.")

    for relative_path in (
        "README.md",
        "docs/1-1_초심자_구동_가이드.md",
        "docs/1-2_백업_복구_유지보수_가이드.md",
        "portable/README_PORTABLE.md",
    ):
        path = PROJECT_ROOT / relative_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for found in re.findall(r"shim:(\d+\.\d+\.\d+)", content):
            if found != version:
                errors.append(
                    f"{relative_path}: obsolete docker tag shim:{found} (expected shim:{version})."
                )
        for found in re.findall(r"release\.ps1\s+-Version\s+(\d+\.\d+\.\d+)", content):
            if found != version:
                errors.append(
                    f"{relative_path}: obsolete release argument {found} (expected {version})."
                )

    if errors:
        print(f"verify_version_sync: expected version from package.json = {version}")
        for error in errors:
            print(f"  - {error}")
        print(f"verify_version_sync: FAILED ({len(errors)} issue(s))")
        return 1

    print(f"verify_version_sync: OK (package.json = {version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
