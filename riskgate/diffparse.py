"""Minimal, dependency-free unified-diff parser.

Produces one FileChange per file with added/removed lines and the *new-file*
line numbers that were added or modified, which `testgaps` maps onto functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileChange:
    path: str
    old_path: str | None = None
    status: str = "modified"  # added | deleted | modified | renamed
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added_line_numbers: list[int] = field(default_factory=list)
    binary: bool = False

    @property
    def churn(self) -> int:
        return len(self.added) + len(self.removed)


def _strip_prefix(p: str) -> str:
    p = p.strip()
    if p == "/dev/null":
        return p
    if p.startswith(("a/", "b/")):
        return p[2:]
    return p


def parse_unified_diff(text: str) -> list[FileChange]:
    files: list[FileChange] = []
    cur: FileChange | None = None
    new_line = 0
    old_left = new_left = 0
    in_hunk = False
    headers_done = False

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            parts = raw.split(" ")
            b_path = _strip_prefix(parts[-1]) if len(parts) >= 4 else ""
            a_path = _strip_prefix(parts[-2]) if len(parts) >= 4 else None
            cur = FileChange(path=b_path, old_path=a_path)
            files.append(cur)
            in_hunk = False
            headers_done = False
            continue
        if cur is None:
            # Tolerate diffs without "diff --git" headers (plain `diff -u`).
            if raw.startswith("--- "):
                cur = FileChange(path="", old_path=_strip_prefix(raw[4:].split("\t")[0]))
                files.append(cur)
            else:
                continue
        if raw.startswith("new file mode"):
            cur.status = "added"
            continue
        if raw.startswith("deleted file mode"):
            cur.status = "deleted"
            continue
        if raw.startswith("rename from "):
            cur.status = "renamed"
            cur.old_path = raw[len("rename from "):].strip()
            continue
        if raw.startswith("rename to "):
            cur.path = raw[len("rename to "):].strip()
            continue
        if raw.startswith("Binary files "):
            cur.binary = True
            continue
        if not in_hunk and raw.startswith("--- "):
            old = _strip_prefix(raw[4:].split("\t")[0])
            if headers_done:  # plain `diff -u` output: next file starts
                cur = FileChange(path="", old_path=old)
                files.append(cur)
                headers_done = False
            if old == "/dev/null":
                cur.status = "added"
            continue
        if not in_hunk and raw.startswith("+++ "):
            new = _strip_prefix(raw[4:].split("\t")[0])
            if new == "/dev/null":
                cur.status = "deleted"
            else:
                cur.path = new
            headers_done = True
            continue
        m = _HUNK_RE.match(raw)
        if m:
            in_hunk = True
            new_line = int(m.group(3))
            old_left = int(m.group(2)) if m.group(2) is not None else 1
            new_left = int(m.group(4)) if m.group(4) is not None else 1
            continue
        if not in_hunk:
            continue
        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"
        if raw.startswith("+"):
            cur.added.append(raw[1:])
            cur.added_line_numbers.append(new_line)
            new_line += 1
            new_left -= 1
        elif raw.startswith("-"):
            cur.removed.append(raw[1:])
            old_left -= 1
        else:
            new_line += 1
            old_left -= 1
            new_left -= 1
        if old_left <= 0 and new_left <= 0:
            in_hunk = False

    for f in files:
        if not f.path and f.old_path:
            f.path = f.old_path
    return files
