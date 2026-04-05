import re
import os
from pathlib import Path


SUSPICIOUS_NATIVE_MARKERS = (
    "speedups.cpython",
    "_helpers_c.cpython",
    "_multidict.cpython",
    "mask.cpython",
)
NATIVE_EXTENSIONS = {".so", ".dylib", ".pyd"}
IGNORED_DIRECTORIES = {
    "node_modules",
    "__pycache__",
    ".git",
    "logs",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "dist-packages",
    ".mypy_cache",
    ".pytest_cache",
}

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([A-Za-z0-9_\-]{8,})"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(api[_-]?secret\s*[=:]\s*)([A-Za-z0-9_\-]{8,})"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(token\s*[=:]\s*)([A-Za-z0-9_\-\.]{8,})"), r"\1***REDACTED***"),
    (re.compile(r"(?i)(secret\s*[=:]\s*)([A-Za-z0-9_\-]{8,})"), r"\1***REDACTED***"),
]


def _is_ignored_path(path: Path):
    parts = {part.lower() for part in path.parts}
    return any(name in parts for name in IGNORED_DIRECTORIES)


def scan_workspace_security_issues(root_path: Path):
    root = Path(root_path).resolve()
    findings = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRECTORIES]
        for filename in files:
            file_path = Path(current_root) / filename
            suffix = file_path.suffix.lower()
            name = file_path.name.lower()
            if suffix in NATIVE_EXTENSIONS:
                findings.append(
                    f"Native binary found in workspace: {file_path.relative_to(root)}"
                )
                continue
            if any(marker in name for marker in SUSPICIOUS_NATIVE_MARKERS):
                findings.append(
                    f"Suspicious marker in filename: {file_path.relative_to(root)}"
                )
    return findings


def redact_sensitive_text(message: str):
    text = str(message or "")
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized
