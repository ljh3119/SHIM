from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path


INSECURE_DEFAULT_SECRET_KEY = "shim_change_this_secret_key_before_operation"
AUTO_GENERATED_MARKER = "# AUTO-GENERATED"
PLAINTEXT_FINGERPRINT = "PLAINTEXT_MODE"


def _validated_environment_secret() -> str | None:
    value = os.getenv("SHIM_SECRET_KEY", "").strip()
    if not value:
        return None
    if value == INSECURE_DEFAULT_SECRET_KEY:
        raise RuntimeError("SHIM_SECRET_KEY uses a known insecure default.")
    return value


def read_secret_file(secret_file: Path) -> tuple[str | None, bool]:
    """파일을 만들지 않고 첫 실제 키와 자동 생성 marker 여부를 반환합니다."""
    if not secret_file.exists():
        return None, False
    content = secret_file.read_text(encoding="utf-8")
    actual_keys = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return (actual_keys[0] if actual_keys else None), content.lstrip().startswith(AUTO_GENERATED_MARKER)


def resolve_encryption_key(data_dir: Path) -> bytes | None:
    """부수 효과 없이 현재 개인정보 암호화 키를 판정합니다."""
    key_source = _validated_environment_secret()
    if key_source is None:
        key_source, is_auto_generated = read_secret_file(data_dir / "secret.key")
        if is_auto_generated:
            return None
    if not key_source:
        return None
    return base64.urlsafe_b64encode(hashlib.sha256(key_source.encode("utf-8")).digest())


def key_fingerprint(encryption_key: bytes | None) -> str:
    if encryption_key is None:
        return PLAINTEXT_FINGERPRINT
    return hashlib.sha256(encryption_key).hexdigest()


def resolve_key_fingerprint(data_dir: Path) -> str:
    return key_fingerprint(resolve_encryption_key(data_dir))
