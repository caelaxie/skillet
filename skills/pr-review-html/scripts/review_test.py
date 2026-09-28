#!/usr/bin/env python3
"""Call review.py the way an agent does."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REVIEW = Path(__file__).resolve().parent / "review.py"
SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REVIEW), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReviewCliTest(unittest.TestCase):
    def test_frontmatter_is_one_line(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: pr-review-html\n"))
        description = ""
        for line in text.splitlines():
            if line.startswith("description:"):
                description = line[len("description:") :].strip()
                break
        self.assertTrue(description)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("\n", description)

    def test_empty_spec_asks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["load", "--spec", "   ", "--workdir", tmp])
        self.assertEqual(result.returncode, 2)
        self.assertIn("Name the diff", result.stderr)

    def test_single_ref_asks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["load", "--spec", "HEAD", "--workdir", tmp])
        self.assertEqual(result.returncode, 2)
        self.assertIn("Name one diff", result.stderr)

    def test_two_pull_urls_ask(self) -> None:
        spec = "https://github.com/a/b/pull/1 https://github.com/c/d/pull/2"
        with tempfile.TemporaryDirectory() as tmp:
            result = run(["load", "--spec", spec, "--workdir", tmp])
        self.assertEqual(result.returncode, 2)
        self.assertIn("Name one diff", result.stderr)

    def test_range_renders_grouped_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            work = root / "work"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "t@example.com")
            git(repo, "config", "user.name", "T")
            git(repo, "config", "commit.gpgsign", "false")
            write(
                repo / "core.txt",
                "header\nMOVE_A\nMOVE_B\nMOVE_C\nmid1\nmid2\nmid3\nmid4\nfooter\n",
            )
            write(repo / "wire.txt", "keep\nWIRE_H1_TOKEN\n" + ("pad\n" * 20) + "WIRE_H2_TOKEN\nend\n")
            write(repo / "noise.txt", "plain\n")
            write(repo / "old name.txt", "same\n" * 20)
            (repo / "pic.bin").write_bytes(b"\x00\x01")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "base")
            git(repo, "branch", "base")
            write(
                repo / "core.txt",
                "header\nmid1\nmid2\nmid3\nmid4\nMOVE_A\nMOVE_B\nMOVE_C\nCORE_TOKEN\n</script>\nfooter\n",
            )
            write(repo / "wire.txt", "keep\nWIRE_H1_TOKEN changed\n" + ("pad\n" * 20) + "WIRE_H2_TOKEN changed\nend\n")
            write(repo / "noise.txt", "plain\nNOISE_TOKEN\n")
            git(repo, "mv", "old name.txt", "new name.txt")
            write(repo / "new name.txt", ("same\n" * 20) + "RENAME_BODY_TOKEN\n")
            (repo / "pic.bin").write_bytes(b"\x00\x02")
            git(repo, "add", ".")
            git(repo, "commit", "-q", "-m", "change")

            loaded = run(["load", "--spec", "base..HEAD", "--workdir", str(work)], cwd=repo)
            self.assertEqual(loaded.returncode, 0, loaded.stderr)
            self.assertEqual(Path(loaded.stdout.strip()), work)
            raw = json.loads((work / "raw.json").read_text(encoding="utf-8"))
            by_path = {item["path"]: item for item in raw["files"]}
            self.assertIn("core.txt", by_path)
            self.assertEqual(by_path["core.txt"]["hunks"][0]["id"], "h1")
            self.assertTrue(any(line["text"] == "CORE_TOKEN" for line in by_path["core.txt"]["hunks"][0]["lines"]))
            self.assertEqual(by_path["new name.txt"]["status"], "renamed")
            self.assertEqual(by_path["new name.txt"]["old_path"], "old name.txt")
            self.assertTrue(by_path["pic.bin"]["binary"])
            self.assertGreaterEqual(len(by_path["wire.txt"]["hunks"]), 2)

            review = {
                "why": "The move and the new token are the behavior under review.",
                "core": [
                    {
                        "path": "core.txt",
                        "why": "CORE_TOKEN is the new result. The three MOVE lines changed position.",
                        "aids": [
                            {
                                "hunk_id": "h1",
                                "pseudocode": "move the block\nappend CORE_TOKEN",
                                "trace": {
                                    "input": "before",
                                    "before": ["MOVE block", "after"],
                                    "after": ["after", "MOVE block", "CORE_TOKEN"],
                                    "diverge_at": 0,
                                    "outcome": "CORE_TOKEN is now the last line.",
                                },
                                "callouts": [
                                    {"tag": "Breaking", "why": "Readers of the old order now see CORE_TOKEN."}
                                ],
                            }
                        ],
                    }
                ],
                "wiring": [
                    {
                        "path": "wire.txt",
                        "why": "Only the first wiring hunk connects the core change.",
                        "shown_hunks": ["h1"],
                        "aids": [],
                    }
                ],
                "boilerplate": [
                    {"path": "noise.txt"},
                    {"path": "new name.txt"},
                    {"path": "pic.bin"},
                ],
            }
            (work / "review.json").write_text(json.dumps(review), encoding="utf-8")
            rendered = run(["render", "--workdir", str(work)])
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            page = Path(rendered.stdout.strip())
            self.assertTrue(page.name.endswith("-pr-review.html"))
            html = page.read_text(encoding="utf-8")
            again = run(["render", "--workdir", str(work)])
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(page.read_bytes(), Path(again.stdout.strip()).read_bytes())

            self.assertIn("CORE_TOKEN", html)
            self.assertIn("WIRE_H1_TOKEN changed", html)
            self.assertNotIn("WIRE_H2_TOKEN", html)
            self.assertNotIn("NOISE_TOKEN", html)
            self.assertNotIn("RENAME_BODY_TOKEN", html)
            self.assertIn("noise.txt", html)
            self.assertIn("old name.txt to new name.txt", html)
            self.assertIn("pic.bin", html)
            self.assertIn("binary", html)
            self.assertIn('class="moved-add"', html)
            self.assertIn("&lt;/script&gt;", html)
            self.assertEqual(html.count("</script>"), 1)
            self.assertIn("Core logic", html)
            self.assertIn("Wiring", html)
            self.assertIn("Boilerplate", html)
            self.assertIn('aria-controls="core-0"', html)

            original = page.read_bytes()
            bad = json.loads((work / "review.json").read_text(encoding="utf-8"))
            bad["boilerplate"] = [row for row in bad["boilerplate"] if row["path"] != "pic.bin"]
            (work / "review.json").write_text(json.dumps(bad), encoding="utf-8")
            failed = run(["render", "--workdir", str(work)])
            self.assertEqual(failed.returncode, 1)
            self.assertIn("missing: pic.bin", failed.stderr)
            self.assertEqual(page.read_bytes(), original)

            bad["boilerplate"].append({"path": "pic.bin"})
            bad["core"][0]["aids"][0]["callouts"][0]["tag"] = "Weird"
            (work / "review.json").write_text(json.dumps(bad), encoding="utf-8")
            tagged = run(["render", "--workdir", str(work)])
            self.assertEqual(tagged.returncode, 1)
            self.assertIn("unknown callout tag", tagged.stderr)
            self.assertEqual(page.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
