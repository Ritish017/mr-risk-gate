"""Risk policy: what the team considers risky. Versioned in-repo as riskgate.json."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_POLICY: dict = {
    "thresholds": {"medium": 35, "high": 65},
    "size": {"points_per_100_lines": 6, "max_points": 25},
    "sensitive_paths": [
        {"glob": "tinyledger/billing*.py", "points": 25, "reason": "money calculation"},
        {"glob": "**/migrations/**", "points": 25, "reason": "schema migration"},
        {"glob": ".gitlab-ci.yml", "points": 15, "reason": "CI/CD pipeline definition"},
        {"glob": ".gitlab/duo/**", "points": 15, "reason": "agent/flow configuration"},
        {"glob": "Dockerfile", "points": 10, "reason": "runtime image"},
        {"glob": "riskgate.json", "points": 20, "reason": "risk policy itself"},
        {"glob": "pyproject.toml", "points": 10, "reason": "dependencies / packaging"},
        {"glob": "requirements*.txt", "points": 10, "reason": "dependencies"},
    ],
    "source_globs": ["tinyledger/**/*.py", "riskgate/**/*.py", "*.py"],
    "test_globs": ["tests/**", "**/test_*.py", "**/*_test.py"],
    "mutation": {"min_kill_ratio": 0.8, "max_mutants": 40, "timeout_s": 60},
    "untested_source_points": 20,
    "deleted_test_points": 20,
    "smells": [
        {"id": "secret-aws-key", "regex": "AKIA[0-9A-Z]{16}", "points": 60, "severity": "critical"},
        {"id": "secret-private-key", "regex": "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "points": 60, "severity": "critical"},
        {"id": "secret-gitlab-pat", "regex": "glpat-[0-9A-Za-z_\\-]{20,}", "points": 60, "severity": "critical"},
        {"id": "hardcoded-password", "regex": "(?i)(password|passwd|secret|api_key)\\s*=\\s*['\"][^'\"]{6,}['\"]", "points": 30, "severity": "high"},
        {"id": "eval-call", "regex": "\\beval\\(", "points": 15, "severity": "high"},
        {"id": "shell-true", "regex": "shell\\s*=\\s*True", "points": 15, "severity": "high"},
        {"id": "bare-except", "regex": "^\\s*except\\s*:", "points": 8, "severity": "medium"},
        {"id": "float-money", "regex": "float\\(.*(amount|price|total|tax)", "points": 10, "severity": "medium"},
        {"id": "todo", "regex": "\\b(TODO|FIXME|XXX)\\b", "points": 2, "severity": "low"},
    ],
}


def load_policy(path: str | Path | None = None) -> dict:
    """Load riskgate.json if present; fall back to DEFAULT_POLICY for missing keys."""
    policy = json.loads(json.dumps(DEFAULT_POLICY))  # deep copy
    if path is None:
        candidate = Path("riskgate.json")
        path = candidate if candidate.exists() else None
    if path is not None:
        user = json.loads(Path(path).read_text(encoding="utf-8"))
        policy.update(user)
    return policy
