#!/usr/bin/env python3
"""Load a named diff and render one review HTML file."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

CALLOUT_TAGS = ("Subtle", "Breaking", "Race condition", "Perf")
URL_RE = re.compile(
    r"https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)(?:/files)?/?"
)
NUMBER_RE = re.compile(r"#?(\d+)\Z")
REPO_NUMBER_RE = re.compile(r"([^/\s]+)/([^/\s]+)#(\d+)\Z")


class AskError(Exception):
    pass


class FailError(Exception):
    pass


@dataclass(frozen=True)
class DiffSpec:
    kind: str
    owner: str | None
    repo: str | None
    number: int | None
    url: str | None
    range_expr: str | None


@dataclass(frozen=True)
class DiffLine:
    kind: str
    text: str


@dataclass(frozen=True)
class Hunk:
    id: str
    header: str
    old_start: int
    new_start: int
    lines: tuple[DiffLine, ...]
    adds: int
    dels: int


@dataclass(frozen=True)
class RawFile:
    path: str
    old_path: str | None
    status: str
    binary: bool
    additions: int
    deletions: int
    hunks: tuple[Hunk, ...]


@dataclass(frozen=True)
class RawDiff:
    spec: DiffSpec
    title: str
    url: str | None
    author: str | None
    base: str | None
    head: str | None
    files: tuple[RawFile, ...]


@dataclass(frozen=True)
class Callout:
    tag: str
    why: str


@dataclass(frozen=True)
class Trace:
    input: str
    before: tuple[str, ...]
    after: tuple[str, ...]
    diverge_at: int
    outcome: str


@dataclass(frozen=True)
class HunkAids:
    hunk_id: str
    pseudocode: str | None
    trace: Trace | None
    callouts: tuple[Callout, ...]


@dataclass(frozen=True)
class CoreFile:
    path: str
    why: str
    aids: tuple[HunkAids, ...]


@dataclass(frozen=True)
class WiringFile:
    path: str
    why: str
    shown_hunks: tuple[str, ...]
    aids: tuple[HunkAids, ...]


@dataclass(frozen=True)
class BoilerplateEntry:
    path: str


@dataclass(frozen=True)
class ReviewDocument:
    why: str
    core: tuple[CoreFile, ...]
    wiring: tuple[WiringFile, ...]
    boilerplate: tuple[BoilerplateEntry, ...]


def parse_spec(spec_text: str) -> DiffSpec:
    text = spec_text.strip()
    if not text:
        raise AskError(
            "Name the diff: a GitHub PR URL, a PR number, or a git range with .. or ..."
        )

    urls = [
        (match.group(1), match.group(2), int(match.group(3)), match.group(0).rstrip("/"))
        for match in URL_RE.finditer(text)
    ]
    ranges = [
        token
        for token in text.split()
        if ("://" not in token) and (".." in token)
    ]
    exact = NUMBER_RE.fullmatch(text) or REPO_NUMBER_RE.fullmatch(text)
    found: list[str] = []
    found.extend(item[3] for item in urls)
    found.extend(ranges)
    if exact:
        found.append(text)

    if len(found) != 1:
        shown = ", ".join(found) if found else "none"
        raise AskError(f"Name one diff. Found: {shown}.")

    if urls:
        owner, repo, number, _url = urls[0]
        url = f"https://github.com/{owner}/{repo}/pull/{number}"
        return DiffSpec("github_pr", owner, repo, number, url, None)
    if exact and "/" in text:
        owner, repo, number = REPO_NUMBER_RE.fullmatch(text).groups()
        return DiffSpec("github_pr", owner, repo, int(number), None, None)
    if exact:
        return DiffSpec("github_pr", None, None, int(exact.group(1)), None, None)
    return DiffSpec("git_range", None, None, None, None, ranges[0])


def _parse_quoted(src: str) -> tuple[str, str]:
    if not src.startswith('"'):
        raise FailError("expected a quoted git path")
    index = 1
    chars: list[str] = []
    while index < len(src):
        char = src[index]
        if char == '"':
            return "".join(chars), src[index + 1 :]
        if char == "\\" and index + 1 < len(src):
            nxt = src[index + 1]
            if nxt in {'\\', '"'}:
                chars.append(nxt)
                index += 2
                continue
            if nxt == "n":
                chars.append("\n")
                index += 2
                continue
            if nxt == "t":
                chars.append("\t")
                index += 2
                continue
            octal = src[index + 1 : index + 4]
            if len(octal) == 3 and octal.isdigit() and all(c < "8" for c in octal):
                chars.append(chr(int(octal, 8)))
                index += 4
                continue
            chars.append(nxt)
            index += 2
            continue
        chars.append(char)
        index += 1
    raise FailError("unterminated quoted git path")


def _strip_ab(token: str) -> str:
    if token.startswith("a/") or token.startswith("b/"):
        return token[2:]
    return token


def _split_diff_git(line: str) -> tuple[str, str]:
    rest = line[len("diff --git ") :]
    # Unquoted paths may contain spaces when core.quotePath is false.
    # The destination token is the one that starts at " b/".
    if rest.startswith('"'):
        left, rest = _parse_quoted(rest)
        right, _rest = _parse_quoted(rest.lstrip())
    else:
        split_at = rest.find(" b/")
        if split_at < 1:
            raise FailError(f"cannot parse diff header: {line}")
        left = rest[:split_at]
        right = rest[split_at + 1 :]
    return _strip_ab(left), _strip_ab(right)


def _header_path(rest: str) -> str:
    rest = rest.strip()
    if rest.startswith('"'):
        path, _tail = _parse_quoted(rest)
        return path
    return rest


def _hunk_starts(header: str) -> tuple[int, int]:
    match = re.search(r"@@ -(\d+)(?:,\d+)? \+(\d+)", header)
    if not match:
        raise FailError(f"cannot parse hunk header: {header}")
    return int(match.group(1)), int(match.group(2))


def parse_unified_diff(text: str) -> tuple[RawFile, ...]:
    files: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    hunk: dict[str, object] | None = None
    skipping_binary = False

    def close_hunk() -> None:
        nonlocal hunk
        if current is None or hunk is None:
            hunk = None
            return
        lines = tuple(hunk["lines"])
        adds = sum(1 for line in lines if line.kind == "add")
        dels = sum(1 for line in lines if line.kind == "del")
        current["hunks"].append(
            Hunk(
                id=f"h{len(current['hunks']) + 1}",
                header=hunk["header"],
                old_start=hunk["old_start"],
                new_start=hunk["new_start"],
                lines=lines,
                adds=adds,
                dels=dels,
            )
        )
        hunk = None

    def close_file() -> None:
        nonlocal current, skipping_binary
        close_hunk()
        if current is None:
            return
        if not current["status"]:
            current["status"] = "modified"
        hunks = tuple(current["hunks"])
        files.append(
            {
                "path": current["path"],
                "old_path": current["old_path"],
                "status": current["status"],
                "binary": current["binary"],
                "hunks": () if current["binary"] else hunks,
            }
        )
        current = None
        skipping_binary = False

    for raw_line in text.splitlines():
        if raw_line.startswith("diff --git "):
            close_file()
            old_path, new_path = _split_diff_git(raw_line)
            path = new_path if new_path != "/dev/null" else old_path
            current = {
                "path": path,
                "old_path": None,
                "status": "",
                "binary": False,
                "hunks": [],
            }
            hunk = None
            skipping_binary = False
            continue
        if current is None or skipping_binary:
            continue
        if raw_line.startswith("rename from "):
            current["old_path"] = _header_path(raw_line[len("rename from ") :])
            current["status"] = "renamed"
            continue
        if raw_line.startswith("rename to "):
            current["path"] = _header_path(raw_line[len("rename to ") :])
            current["status"] = "renamed"
            continue
        if raw_line.startswith("copy from ") or raw_line.startswith("copy to "):
            current["status"] = "copied"
            if raw_line.startswith("copy to "):
                current["path"] = _header_path(raw_line[len("copy to ") :])
            continue
        if raw_line.startswith("new file mode"):
            if not current["status"]:
                current["status"] = "added"
            continue
        if raw_line.startswith("deleted file mode"):
            current["status"] = "deleted"
            continue
        if raw_line.startswith("Binary files ") or raw_line.startswith("GIT binary patch"):
            close_hunk()
            current["binary"] = True
            current["hunks"] = []
            skipping_binary = True
            continue
        if raw_line.startswith("@@"):
            close_hunk()
            old_start, new_start = _hunk_starts(raw_line)
            hunk = {
                "header": raw_line,
                "old_start": old_start,
                "new_start": new_start,
                "lines": [],
            }
            continue
        if hunk is None:
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---") or raw_line.startswith("\\"):
            continue
        if raw_line.startswith("+"):
            hunk["lines"].append(DiffLine("add", raw_line[1:]))
        elif raw_line.startswith("-"):
            hunk["lines"].append(DiffLine("del", raw_line[1:]))
        elif raw_line.startswith(" "):
            hunk["lines"].append(DiffLine("ctx", raw_line[1:]))
        elif raw_line == "":
            hunk["lines"].append(DiffLine("ctx", ""))

    close_file()
    built: list[RawFile] = []
    seen: set[str] = set()
    for item in files:
        path = str(item["path"])
        if path in seen:
            raise FailError(f"duplicate path in diff: {path}")
        seen.add(path)
        hunks = item["hunks"]
        built.append(
            RawFile(
                path=path,
                old_path=item["old_path"],
                status=str(item["status"]),
                binary=bool(item["binary"]),
                additions=sum(hunk.adds for hunk in hunks),
                deletions=sum(hunk.dels for hunk in hunks),
                hunks=hunks,
            )
        )
    return tuple(built)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as err:
        raise FailError(f"{cmd[0]} is not installed") from err


def _split_range(expr: str) -> tuple[str | None, str | None]:
    if "..." in expr:
        left, right = expr.split("...", 1)
    else:
        left, right = expr.split("..", 1)
    return left or None, right or None


def _slug(spec: DiffSpec) -> str:
    if spec.kind == "github_pr" and spec.owner and spec.repo and spec.number is not None:
        raw = f"{spec.owner}-{spec.repo}-{spec.number}"
    elif spec.kind == "github_pr" and spec.number is not None:
        raw = f"pr-{spec.number}"
    else:
        raw = "range-" + re.sub(r"[^A-Za-z0-9._-]+", "-", spec.range_expr or "diff")
    cleaned = raw.strip("-")[:80].strip("-")
    return cleaned or "diff"


def _dump(value: object) -> str:
    return json.dumps(asdict(value), indent=2) + "\n"


def load_diff(spec_text: str, cwd: Path, workdir: Path | None) -> Path:
    spec = parse_spec(spec_text)
    if spec.kind == "github_pr":
        if spec.url:
            target = [spec.url]
            repo_args: list[str] = []
        elif spec.owner and spec.repo:
            target = [str(spec.number)]
            repo_args = ["--repo", f"{spec.owner}/{spec.repo}"]
        else:
            target = [str(spec.number)]
            repo_args = []
        view_cmd = ["gh", "pr", "view", *target, *repo_args, "--json", "title,author,baseRefName,headRefName,url"]
        diff_cmd = ["gh", "pr", "diff", *target, *repo_args]
        viewed = _run(view_cmd, cwd)
        if viewed.returncode != 0:
            detail = (viewed.stderr or viewed.stdout).strip()
            raise FailError(detail or "gh pr view failed")
        try:
            meta = json.loads(viewed.stdout)
        except json.JSONDecodeError as err:
            raise FailError("gh pr view did not return JSON") from err
        differed = _run(diff_cmd, cwd)
        if differed.returncode != 0:
            detail = (differed.stderr or differed.stdout).strip()
            raise FailError(detail or "gh pr diff failed")
        author = meta.get("author") or {}
        raw = RawDiff(
            spec=spec,
            title=str(meta.get("title") or f"PR {spec.number}"),
            url=str(meta.get("url") or spec.url or "") or None,
            author=author.get("login"),
            base=meta.get("baseRefName"),
            head=meta.get("headRefName"),
            files=parse_unified_diff(differed.stdout),
        )
    else:
        assert spec.range_expr is not None
        differed = _run(
            [
                "git", "diff", "-U3", "--find-renames", "--no-ext-diff", "--no-color",
                spec.range_expr,
            ],
            cwd,
        )
        if differed.returncode != 0:
            detail = (differed.stderr or differed.stdout).strip()
            raise FailError(detail or "git diff failed")
        base, head = _split_range(spec.range_expr)
        raw = RawDiff(
            spec=spec,
            title=spec.range_expr,
            url=None,
            author=None,
            base=base,
            head=head,
            files=parse_unified_diff(differed.stdout),
        )

    destination = workdir or Path("/tmp/pr-review-html") / _slug(spec)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "raw.json").write_text(_dump(raw), encoding="utf-8")
    return destination


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise FailError(f"{label} must be an object")
    return value


def _require(obj: Mapping[str, object], label: str, allowed: set[str], required: set[str]) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise FailError(f"{label} has unknown keys: {', '.join(unknown)}")
    missing = sorted(required - set(obj))
    if missing:
        raise FailError(f"{label} is missing: {', '.join(missing)}")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise FailError(f"{label} must be non-empty text")
    return value


def _string_list(value: object, label: str, low: int, high: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise FailError(f"{label} must be a list")
    if not low <= len(value) <= high:
        raise FailError(f"{label} must have {low} to {high} entries")
    items: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or item.strip() == "":
            raise FailError(f"{label} entry {index} must be non-empty text")
        items.append(item)
    return tuple(items)


def _parse_trace(value: object) -> Trace:
    obj = _object(value, "trace")
    _require(obj, "trace", {"input", "before", "after", "diverge_at", "outcome"}, {"input", "before", "after", "diverge_at", "outcome"})
    before = _string_list(obj["before"], "trace before", 1, 8)
    after = _string_list(obj["after"], "trace after", 1, 8)
    diverge_at = obj["diverge_at"]
    if not isinstance(diverge_at, int) or isinstance(diverge_at, bool):
        raise FailError("trace diverge_at must be an integer")
    if not 0 <= diverge_at < min(len(before), len(after)):
        raise FailError("trace diverge_at is outside the trace")
    return Trace(_text(obj["input"], "trace input"), before, after, diverge_at, _text(obj["outcome"], "trace outcome"))


def _parse_aids(value: object, *, allow_pseudocode: bool) -> tuple[HunkAids, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise FailError("aids must be a list")
    aids: list[HunkAids] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        obj = _object(item, f"aid {index}")
        _require(
            obj,
            f"aid {index}",
            {"hunk_id", "pseudocode", "trace", "callouts"},
            {"hunk_id"},
        )
        hunk_id = _text(obj["hunk_id"], f"aid {index} hunk_id")
        if hunk_id in seen:
            raise FailError(f"duplicate aid for {hunk_id}")
        seen.add(hunk_id)
        pseudocode = obj.get("pseudocode")
        if pseudocode is not None:
            if not allow_pseudocode:
                raise FailError("pseudocode is only allowed on a core hunk")
            pseudocode = _text(pseudocode, f"aid {index} pseudocode")
        trace = _parse_trace(obj["trace"]) if "trace" in obj and obj["trace"] is not None else None
        raw_callouts = obj.get("callouts", [])
        if not isinstance(raw_callouts, list):
            raise FailError(f"aid {index} callouts must be a list")
        if len(raw_callouts) > 2:
            raise FailError(f"aid {index} has more than two callouts")
        callouts: list[Callout] = []
        for callout_index, callout in enumerate(raw_callouts, start=1):
            body = _object(callout, f"callout {callout_index}")
            _require(body, f"callout {callout_index}", {"tag", "why"}, {"tag", "why"})
            tag = body["tag"]
            if tag not in CALLOUT_TAGS:
                raise FailError(f"unknown callout tag: {tag}")
            callouts.append(Callout(str(tag), _text(body["why"], f"callout {callout_index} why")))
        if pseudocode is None and trace is None and not callouts:
            raise FailError(f"aid {index} is empty")
        aids.append(HunkAids(hunk_id, pseudocode, trace, tuple(callouts)))
    return tuple(aids)


def parse_review(value: object) -> ReviewDocument:
    obj = _object(value, "review")
    _require(obj, "review", {"why", "core", "wiring", "boilerplate"}, {"why", "core", "wiring", "boilerplate"})
    if not isinstance(obj["core"], list) or not isinstance(obj["wiring"], list) or not isinstance(obj["boilerplate"], list):
        raise FailError("core, wiring, and boilerplate must be lists")
    core: list[CoreFile] = []
    for index, item in enumerate(obj["core"], start=1):
        body = _object(item, f"core file {index}")
        _require(body, f"core file {index}", {"path", "why", "aids"}, {"path", "why"})
        core.append(CoreFile(_text(body["path"], f"core file {index} path"), _text(body["why"], f"core file {index} why"), _parse_aids(body.get("aids", []), allow_pseudocode=True)))
    wiring: list[WiringFile] = []
    for index, item in enumerate(obj["wiring"], start=1):
        body = _object(item, f"wiring file {index}")
        _require(body, f"wiring file {index}", {"path", "why", "shown_hunks", "aids"}, {"path", "why", "shown_hunks"})
        shown = body["shown_hunks"]
        if not isinstance(shown, list) or not all(isinstance(part, str) and part for part in shown):
            raise FailError(f"wiring file {index} shown_hunks must be a list of hunk ids")
        if len(shown) != len(set(shown)):
            raise FailError(f"wiring file {index} repeats a hunk id")
        wiring.append(
            WiringFile(
                _text(body["path"], f"wiring file {index} path"),
                _text(body["why"], f"wiring file {index} why"),
                tuple(shown),
                _parse_aids(body.get("aids", []), allow_pseudocode=False),
            )
        )
    boilerplate: list[BoilerplateEntry] = []
    for index, item in enumerate(obj["boilerplate"], start=1):
        body = _object(item, f"boilerplate file {index}")
        _require(body, f"boilerplate file {index}", {"path"}, {"path"})
        boilerplate.append(BoilerplateEntry(_text(body["path"], f"boilerplate file {index} path")))
    return ReviewDocument(_text(obj["why"], "review why"), tuple(core), tuple(wiring), tuple(boilerplate))


def _parse_raw_line(value: object, label: str) -> DiffLine:
    obj = _object(value, label)
    _require(obj, label, {"kind", "text"}, {"kind", "text"})
    if obj["kind"] not in {"add", "del", "ctx"} or not isinstance(obj["text"], str):
        raise FailError(f"{label} is not a diff line")
    return DiffLine(str(obj["kind"]), obj["text"])


def _parse_raw(value: object) -> RawDiff:
    obj = _object(value, "raw diff")
    _require(obj, "raw diff", {"spec", "title", "url", "author", "base", "head", "files"}, {"spec", "title", "url", "author", "base", "head", "files"})
    spec_obj = _object(obj["spec"], "spec")
    _require(spec_obj, "spec", {"kind", "owner", "repo", "number", "url", "range_expr"}, {"kind", "owner", "repo", "number", "url", "range_expr"})
    if spec_obj["kind"] not in {"github_pr", "git_range"}:
        raise FailError("spec kind is not github_pr or git_range")
    spec = DiffSpec(
        str(spec_obj["kind"]),
        spec_obj["owner"] if isinstance(spec_obj["owner"], str) else None,
        spec_obj["repo"] if isinstance(spec_obj["repo"], str) else None,
        spec_obj["number"] if isinstance(spec_obj["number"], int) and not isinstance(spec_obj["number"], bool) else None,
        spec_obj["url"] if isinstance(spec_obj["url"], str) else None,
        spec_obj["range_expr"] if isinstance(spec_obj["range_expr"], str) else None,
    )
    if not isinstance(obj["files"], list):
        raise FailError("raw diff files must be a list")
    files: list[RawFile] = []
    for index, item in enumerate(obj["files"], start=1):
        body = _object(item, f"raw file {index}")
        _require(body, f"raw file {index}", {"path", "old_path", "status", "binary", "additions", "deletions", "hunks"}, {"path", "old_path", "status", "binary", "additions", "deletions", "hunks"})
        if not isinstance(body["hunks"], list):
            raise FailError(f"raw file {index} hunks must be a list")
        hunks: list[Hunk] = []
        for hunk_index, hunk_value in enumerate(body["hunks"], start=1):
            hunk_obj = _object(hunk_value, f"hunk {hunk_index}")
            _require(hunk_obj, f"hunk {hunk_index}", {"id", "header", "old_start", "new_start", "lines", "adds", "dels"}, {"id", "header", "old_start", "new_start", "lines", "adds", "dels"})
            if not isinstance(hunk_obj["lines"], list):
                raise FailError(f"hunk {hunk_index} lines must be a list")
            lines = tuple(_parse_raw_line(line, f"hunk {hunk_index} line") for line in hunk_obj["lines"])
            hunks.append(
                Hunk(
                    _text(hunk_obj["id"], "hunk id"),
                    _text(hunk_obj["header"], "hunk header"),
                    int(hunk_obj["old_start"]),
                    int(hunk_obj["new_start"]),
                    lines,
                    int(hunk_obj["adds"]),
                    int(hunk_obj["dels"]),
                )
            )
        files.append(
            RawFile(
                _text(body["path"], f"raw file {index} path"),
                body["old_path"] if isinstance(body["old_path"], str) else None,
                _text(body["status"], f"raw file {index} status"),
                bool(body["binary"]),
                int(body["additions"]),
                int(body["deletions"]),
                tuple(hunks),
            )
        )
    return RawDiff(
        spec=spec,
        title=_text(obj["title"], "title"),
        url=obj["url"] if isinstance(obj["url"], str) else None,
        author=obj["author"] if isinstance(obj["author"], str) else None,
        base=obj["base"] if isinstance(obj["base"], str) else None,
        head=obj["head"] if isinstance(obj["head"], str) else None,
        files=tuple(files),
    )


def validate_review(raw: RawDiff, review: ReviewDocument) -> None:
    paths = [item.path for item in raw.files]
    by_path = {item.path: item for item in raw.files}
    if len(by_path) != len(paths):
        raise FailError("raw diff repeats a path")
    ordered = [item.path for item in review.core] + [item.path for item in review.wiring] + [item.path for item in review.boilerplate]
    if len(ordered) != len(set(ordered)):
        repeated = sorted({path for path in ordered if ordered.count(path) > 1})
        raise FailError("path is in more than one section: " + ", ".join(repeated))
    missing = sorted(set(paths) - set(ordered))
    unknown = sorted(set(ordered) - set(paths))
    if missing or unknown:
        parts = []
        if missing:
            parts.append("missing: " + ", ".join(missing))
        if unknown:
            parts.append("unknown: " + ", ".join(unknown))
        raise FailError("; ".join(parts))

    def check_aids(file: RawFile, aids: Sequence[HunkAids], shown: set[str] | None) -> None:
        ids = {hunk.id for hunk in file.hunks}
        for aid in aids:
            if aid.hunk_id not in ids:
                raise FailError(f"{file.path} has no hunk {aid.hunk_id}")
            if shown is not None and aid.hunk_id not in shown:
                raise FailError(f"{file.path} aid {aid.hunk_id} is not a shown hunk")

    for item in review.core:
        raw_file = by_path[item.path]
        if raw_file.binary or not raw_file.hunks:
            raise FailError(f"binary or empty files cannot be core; move {item.path} to boilerplate or wiring")
        check_aids(raw_file, item.aids, None)
    for item in review.wiring:
        raw_file = by_path[item.path]
        ids = {hunk.id for hunk in raw_file.hunks}
        for hunk_id in item.shown_hunks:
            if hunk_id not in ids:
                raise FailError(f"{item.path} has no hunk {hunk_id}")
        if raw_file.binary and item.shown_hunks:
            raise FailError(f"{item.path} is binary and cannot show hunks")
        check_aids(raw_file, item.aids, set(item.shown_hunks))


def detect_moves(lines: Sequence[DiffLine]) -> dict[int, str]:
    threshold = 3

    def collect(kind: str) -> list[list[int]]:
        found: list[list[int]] = []
        current: list[int] = []
        for index, line in enumerate(lines):
            if line.kind == kind:
                current.append(index)
            elif current:
                found.append(current)
                current = []
        if current:
            found.append(current)
        return found

    def norm(index: int) -> str:
        return re.sub(r"\s+", " ", lines[index].text).strip()

    marked: dict[int, str] = {}
    used_adds: set[int] = set()
    additions = collect("add")
    for deletion in collect("del"):
        if len(deletion) < threshold or any(index in marked for index in deletion):
            continue
        deleted_norm = [norm(index) for index in deletion]
        for add_index, addition in enumerate(additions):
            if add_index in used_adds or len(addition) < threshold:
                continue
            if any(index in marked for index in addition):
                continue
            added_norm = [norm(index) for index in addition]
            shared = min(len(deleted_norm), len(added_norm))
            matches = sum(1 for offset in range(shared) if deleted_norm[offset] == added_norm[offset])
            if matches >= threshold and matches >= shared * 0.7:
                for offset in range(shared):
                    state = "moved" if deleted_norm[offset] == added_norm[offset] else "moved-edited"
                    marked[deletion[offset]] = state
                    marked[addition[offset]] = state
                used_adds.add(add_index)
                break
    return marked


_CSS = """
:root {
  --bg: #161616;
  --surface: #212121;
  --raised: #2a2a2a;
  --line: #3a3a3a;
  --text: #c8c8c8;
  --bright: #f2f2f2;
  --muted: #8a8a8a;
  --accent: #8eb4ff;
  --ok: #7dcaa0;
  --bad: #f09898;
  --warn: #e2b56a;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.5 ui-sans-serif, system-ui, sans-serif;
}
header, main { max-width: 980px; margin: 0 auto; padding: 24px 16px; }
header { padding-bottom: 0; }
h1 { margin: 0 0 8px; font-size: 22px; color: var(--bright); }
h2 { margin: 28px 0 12px; font-size: 16px; color: var(--bright); border-bottom: 1px solid var(--line); padding-bottom: 6px; }
.meta { color: var(--muted); font-size: 13px; }
.meta a { color: var(--accent); }
.pills { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.pill { font: 12px/1.4 ui-monospace, monospace; padding: 1px 8px; border-radius: 999px; background: var(--raised); }
.pill.add { color: var(--ok); }
.pill.del { color: var(--bad); }
.why, .file-why, .callout, .outcome { white-space: pre-wrap; }
.why { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; margin: 0 0 12px; }
.file-hd, .file-why { position: sticky; background: var(--raised); }
.file-hd { top: 0; z-index: 2; display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 8px 12px; }
.file-why { top: 42px; z-index: 1; padding: 8px 12px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: var(--surface); }
button.toggle {
  font: 13px/1.4 ui-monospace, monospace;
  color: var(--accent);
  background: transparent;
  border: 0;
  padding: 0;
  text-align: left;
  cursor: pointer;
}
.stats { color: var(--muted); font: 12px/1.4 ui-monospace, monospace; white-space: nowrap; }
.hunk { padding: 8px 12px 12px; }
.hunk h3 { margin: 8px 0; font: 12px/1.4 ui-monospace, monospace; color: var(--muted); font-weight: 500; }
.callout { margin: 8px 0; padding: 8px 10px; border-left: 3px solid var(--warn); background: #2a2418; }
.tag { font: 11px/1.4 ui-monospace, monospace; color: var(--warn); margin-right: 8px; }
pre.pseudo { overflow-x: auto; padding: 10px; background: var(--bg); border-radius: 6px; font: 12px/1.45 ui-monospace, monospace; }
.trace, .diff { width: 100%; border-collapse: collapse; font: 12px/1.45 ui-monospace, monospace; }
.trace td { vertical-align: top; padding: 4px 8px; border-top: 1px solid var(--line); width: 50%; white-space: pre-wrap; }
.trace tr.diverge td { background: #2a2418; }
.diff-wrap { overflow-x: auto; }
.diff td { white-space: pre; vertical-align: top; }
.diff .ln { width: 1%; color: var(--muted); text-align: right; padding: 0 8px; user-select: none; }
.diff .code { padding: 0 10px; }
.diff tr.add .code, .diff tr.add .ln { background: #17261c; }
.diff tr.del .code, .diff tr.del .ln { background: #2a1818; }
.diff tr.moved-add .code, .diff tr.moved-add .ln { background: #17202a; }
.diff tr.moved-del .code, .diff tr.moved-del .ln { background: #24182a; }
.diff tr.moved-edited-add .code, .diff tr.moved-edited-add .ln { background: #20182a; }
.diff tr.moved-edited-del .code, .diff tr.moved-edited-del .ln { background: #281628; }
.diff tr.ctx .code { color: var(--muted); }
.plain { margin: 0; padding-left: 18px; }
.plain li { margin: 4px 0; }
.empty { color: var(--muted); }
""".strip()

_SCRIPT = """
document.querySelectorAll("button.toggle").forEach(function (button) {
  button.addEventListener("click", function () {
    var body = document.getElementById(button.getAttribute("aria-controls"));
    var hidden = body.hasAttribute("hidden");
    if (hidden) body.removeAttribute("hidden");
    else body.setAttribute("hidden", "");
    button.setAttribute("aria-expanded", hidden ? "true" : "false");
  });
});
""".strip()


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _render_hunk(hunk: Hunk, aid: HunkAids | None) -> str:
    parts = ["<div class=\"hunk\">", f"<h3>{_esc(hunk.header)}</h3>"]
    if aid is not None:
        for callout in aid.callouts:
            parts.append(
                f"<p class=\"callout\"><span class=\"tag\">{_esc(callout.tag)}</span> {_esc(callout.why)}</p>"
            )
        if aid.pseudocode is not None:
            parts.append(f"<pre class=\"pseudo\">{_esc(aid.pseudocode)}</pre>")
        if aid.trace is not None:
            parts.append("<table class=\"trace\">")
            rows = max(len(aid.trace.before), len(aid.trace.after))
            for index in range(rows):
                before = aid.trace.before[index] if index < len(aid.trace.before) else ""
                after = aid.trace.after[index] if index < len(aid.trace.after) else ""
                mark = " class=\"diverge\"" if index == aid.trace.diverge_at else ""
                parts.append(f"<tr{mark}><td>{_esc(before)}</td><td>{_esc(after)}</td></tr>")
            parts.append("</table>")
            parts.append(f"<p class=\"outcome\">{_esc(aid.trace.outcome)}</p>")
    moves = detect_moves(hunk.lines)
    old_line = hunk.old_start
    new_line = hunk.new_start
    parts.append("<div class=\"diff-wrap\"><table class=\"diff\">")
    for index, line in enumerate(hunk.lines):
        if line.kind == "add":
            old_cell, new_cell = "", str(new_line)
            new_line += 1
        elif line.kind == "del":
            old_cell, new_cell = str(old_line), ""
            old_line += 1
        else:
            old_cell, new_cell = str(old_line), str(new_line)
            old_line += 1
            new_line += 1
        state = moves.get(index)
        if state == "moved":
            row = f"moved-{line.kind}" if line.kind in {"add", "del"} else line.kind
        elif state == "moved-edited":
            row = f"moved-edited-{line.kind}" if line.kind in {"add", "del"} else line.kind
        else:
            row = line.kind
        parts.append(
            "<tr class=\"%s\"><td class=\"ln\">%s</td><td class=\"ln\">%s</td><td class=\"code\">%s</td></tr>"
            % (row, _esc(old_cell), _esc(new_cell), _esc(line.text))
        )
    parts.append("</table></div></div>")
    return "".join(parts)


def _render_card(raw_file: RawFile, why: str, hunks: Sequence[Hunk], aids: Sequence[HunkAids], card_id: str) -> str:
    aid_by_id = {aid.hunk_id: aid for aid in aids}
    stats = "binary" if raw_file.binary else f"+{raw_file.additions} -{raw_file.deletions}"
    name = raw_file.path if raw_file.old_path is None else f"{raw_file.old_path} to {raw_file.path}"
    body = "".join(_render_hunk(hunk, aid_by_id.get(hunk.id)) for hunk in hunks)
    return (
        "<article class=\"card\">"
        "<div class=\"file-hd\">"
        f"<button type=\"button\" class=\"toggle\" aria-expanded=\"true\" aria-controls=\"{card_id}\">Toggle {_esc(name)}</button>"
        f"<span class=\"stats\">{_esc(raw_file.status)} {_esc(stats)}</span>"
        "</div>"
        f"<p class=\"file-why\">{_esc(why)}</p>"
        f"<div id=\"{card_id}\">{body}</div>"
        "</article>"
    )


def render_page(raw: RawDiff, review: ReviewDocument) -> str:
    by_path = {item.path: item for item in raw.files}
    additions = sum(item.additions for item in raw.files)
    deletions = sum(item.deletions for item in raw.files)
    meta = []
    if raw.url and raw.url.startswith("https://"):
        meta.append(f"<a href=\"{_esc(raw.url)}\">{_esc(raw.url)}</a>")
    elif raw.url:
        meta.append(_esc(raw.url))
    if raw.author:
        meta.append(_esc(raw.author))
    if raw.base or raw.head:
        meta.append(_esc(f"{raw.base or ''}..{raw.head or ''}"))
    sections = ["<section><h2>Core logic</h2>"]
    if review.core:
        for index, item in enumerate(review.core):
            raw_file = by_path[item.path]
            sections.append(_render_card(raw_file, item.why, raw_file.hunks, item.aids, f"core-{index}"))
    else:
        sections.append("<p class=\"empty\">None in this diff.</p>")
    sections.append("</section><section><h2>Wiring</h2>")
    if review.wiring:
        for index, item in enumerate(review.wiring):
            raw_file = by_path[item.path]
            chosen = [hunk for hunk in raw_file.hunks if hunk.id in set(item.shown_hunks)]
            # Keep the order the agent listed, not the order in the diff.
            order = {hunk_id: pos for pos, hunk_id in enumerate(item.shown_hunks)}
            chosen.sort(key=lambda hunk: order[hunk.id])
            sections.append(_render_card(raw_file, item.why, chosen, item.aids, f"wiring-{index}"))
    else:
        sections.append("<p class=\"empty\">None in this diff.</p>")
    sections.append("</section><section><h2>Boilerplate</h2>")
    if review.boilerplate:
        rows = []
        for item in review.boilerplate:
            raw_file = by_path[item.path]
            label = item.path if raw_file.old_path is None else f"{raw_file.old_path} to {item.path}"
            stat = "binary" if raw_file.binary else f"+{raw_file.additions} -{raw_file.deletions}"
            rows.append(f"<li>{_esc(label)} {_esc(raw_file.status)} {_esc(stat)}</li>")
        sections.append("<ul class=\"plain\">" + "".join(rows) + "</ul>")
    else:
        sections.append("<p class=\"empty\">None in this diff.</p>")
    sections.append("</section>")
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_esc(raw.title)}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{_esc(raw.title)}</h1><p class=\"meta\">{' · '.join(meta)}</p>"
        "<div class=\"pills\">"
        f"<span class=\"pill add\">+{additions}</span><span class=\"pill del\">-{deletions}</span>"
        f"<span class=\"pill\">{len(raw.files)} files</span></div></header><main>"
        f"<p class=\"why\">{_esc(review.why)}</p>"
        + "".join(sections)
        + f"</main><script>{_SCRIPT}</script></body></html>\n"
    )


def _html_path(workdir: Path) -> Path:
    return workdir / f"{date.today().isoformat()}-pr-review.html"


def render_review(workdir: Path) -> Path:
    try:
        raw_text = (workdir / "raw.json").read_text(encoding="utf-8")
        review_text = (workdir / "review.json").read_text(encoding="utf-8")
    except OSError as err:
        raise FailError(f"cannot read review inputs: {err.strerror}") from err
    try:
        raw = _parse_raw(json.loads(raw_text))
        review = parse_review(json.loads(review_text))
    except json.JSONDecodeError as err:
        raise FailError(f"invalid JSON: {err}") from err
    validate_review(raw, review)
    page = render_page(raw, review)
    destination = _html_path(workdir)
    temporary = destination.with_suffix(".html.tmp")
    temporary.write_text(page, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review.py")
    sub = parser.add_subparsers(dest="command", required=True)
    load_parser = sub.add_parser("load")
    load_parser.add_argument("--spec", required=True)
    load_parser.add_argument("--workdir")
    render_parser = sub.add_parser("render")
    render_parser.add_argument("--workdir", required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "load":
            workdir = Path(args.workdir) if args.workdir else None
            print(load_diff(args.spec, Path.cwd(), workdir))
        else:
            print(render_review(Path(args.workdir)))
    except AskError as err:
        print(err, file=sys.stderr)
        return 2
    except FailError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
