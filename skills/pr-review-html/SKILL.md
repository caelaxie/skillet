---
name: pr-review-html
description: Build one self-contained HTML walkthrough of a diff the user names, either a GitHub pull request URL or number or a local git range. Use for a PR review, a diff walkthrough, or a change-set overview. The page leads with full core diffs, then condensed wiring, then boilerplate as a list, with short why notes and rare risk callouts. Do not use it for a teaching explanation, and do not guess a branch.
---

# PR review HTML

Build one HTML file a reviewer can open. The page orders the diff by review value. It is not `explain-diff-html`.

## Name the diff

If the user did not name a diff, ask for one and stop.

Accept one of these.

- A GitHub pull request URL, such as `https://github.com/acme/payments/pull/482`
- `owner/repo#482`
- A bare pull request number, such as `482`, when the current checkout is that repository
- One git range token that contains `..` or `...`, such as `main...fix-token`

Do not infer the current branch.
Do not run `git diff` with no range.
Do not switch from `gh` to `git`, or from `git` to `gh`, when a fetch fails.

## Load the diff

`SKILL_DIR` is the directory that contains this file.

```bash
DIR=$(python3 "$SKILL_DIR/scripts/review.py" load --spec 'SPEC')
```

The command prints a directory and writes `$DIR/raw.json`.
Exit 2 means the name was not one diff. Ask the user, and use the sentence on stderr.
Exit 1 means the fetch failed. Show the stderr text, then stop.
Do not fetch the diff again. `raw.json` is the diff.

## Write the review

Write `$DIR/review.json`.
Unknown keys fail.
Do not order files by name or by directory.
Put the riskiest core file first.
Put each path in one section.
Include every path from `raw.json`.

`core` shows every hunk, with the surrounding context lines. Use it for new behavior, algorithm changes, state transitions, and API changes. A file that contains that kind of change stays in `core` even when it also changes imports.
`wiring` lists only the hunks in `shown_hunks`. Use it for route registration, dependency injection, and config that connects the core change. List only the hunks a reviewer needs in order to confirm that connection. An empty `shown_hunks` list keeps the why and omits the diff.
`boilerplate` is a path. Use it for import reordering, renames, generated code, formatting, and type re-exports. The page shows the name and the stats, not the diff. If one hunk in that file actually matters, put the file in `wiring` and list only that hunk.

Hunk ids are `h1`, `h2`, and so on, in the order `raw.json` lists them for that file.

```json
{
  "why": "Retries now fail fast when the circuit is open, instead of waiting out a provider that is already down.",
  "core": [
    {
      "path": "src/retry.ts",
      "why": "The open-breaker short-circuit is the behavior to trust. payments.ts only constructs this client.",
      "aids": [
        {
          "hunk_id": "h2",
          "pseudocode": "if breaker is open:\n  fail fast\nfor attempt in 1..n:\n  try fetch with timeout\n  on retryable: sleep backoff\n  else: throw",
          "trace": {
            "input": "breaker open, GET /charge",
            "before": ["enter fetch", "send request", "time out"],
            "after": ["enter fetch", "see open breaker", "return error"],
            "diverge_at": 1,
            "outcome": "The caller gets an error and no request is sent."
          },
          "callouts": [
            {
              "tag": "Breaking",
              "why": "Callers that treated a timeout as retryable now see an immediate open-breaker error."
            }
          ]
        }
      ]
    }
  ],
  "wiring": [
    {
      "path": "src/payments.ts",
      "why": "This is the only call site that now passes a breaker into the client.",
      "shown_hunks": ["h1"],
      "aids": []
    }
  ],
  "boilerplate": [
    {"path": "src/index.ts"}
  ]
}
```

Add pseudocode only on a core hunk, and only when the diff is hard to scan. Nested conditions, a state machine, retry or backoff, and a multi-step transformation qualify. Drop the language syntax, the error handling, and the mechanical lines. A straightforward change gets no pseudocode.
Add a trace only when the new behavior is hard to predict. Reordered effects, a new short-circuit, and a changed edge case qualify. Use one small realistic input. `diverge_at` is the step where the old path and the new path split. `outcome` is what a caller can observe.
Add a callout only when the tag is earned. The tags are `Subtle`, `Breaking`, `Race condition`, and `Perf`. Write one sentence. The page places that sentence directly above the hunk. Most hunks get no callout.
Write each why as one or two sentences. Say why it changed. Name the other file it calls, or the file that calls it. Mention anything the diff itself hides.

The breaker callout above is a good aid. It names a caller-visible change the diff does not spell out.
A `Subtle` callout on an import rename is a bad aid. Put that file in `boilerplate` and omit the aid.

## Render

```bash
python3 "$SKILL_DIR/scripts/review.py" render --workdir "$DIR"
```

The command prints the HTML path. Give that path to the user.
Do not start a server.
Do not edit the HTML.
If render exits 1, the previous HTML file is unchanged. Fix `review.json` and run render again.
