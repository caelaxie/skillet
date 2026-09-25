---
name: roam-research-pro
description: Write and edit Roam Research graphs without producing mermaid that Roam cannot render. Use when creating or updating Roam pages or blocks, embedding diagrams in Roam, or the user mentions Roam, {{mermaid}}, roam mermaid, or /roam-research-pro. Flowcharts are one child with statements joined by `;`, edges `==>`, and nodes `id(label)`. Pie charts are one child per source line, first child exactly `pie`. `pie showData`, a one-line `pie; ...`, and a newline inside one block all fail. A bar chart needs `[]`, which Roam consumes before mermaid runs.
---

# Roam Research

## Graph ops

Call `get_graph_guidelines` once per graph per session before the first read or write. Use the connected `roam` or `roam_research` MCP tools. Honor that graph's `roamSyntax` for ordinary blocks.

When a write includes a diagram, pick the shape below. Do not paste a mermaid fenced code block into Roam.

## Why MCP mermaid breaks

`create_page` and `create_block` parse a nested `- ` bullet tree. A newline is a new block. `update_block` writes one block's string literally and does not create children. A newline in that string is stored as the two characters `\` and `n`, so mermaid still sees one line.

`{{mermaid}}` turns its children into mermaid source. Those children are still Roam blocks, so this markup is consumed before mermaid runs: `[alias]`, `[[page]]`, `{{component}}`, `((uid))`.

GitHub flowchart source fails two ways:

1. Each source line becomes its own child, and a flowchart then shows only a fragment.
2. `A[label]` is an alias, so node text never reaches mermaid. Bar and xy charts need those brackets. Write a pie instead.

Roam's UI docs nest `-->` bullets under `{{mermaid}}`. That path is not the flowchart dialect below. Do not copy UI flowchart examples into `create_block` markdown.

## Flowchart

One `{{mermaid}}` parent. Exactly one child. The whole diagram in that child as a single line, statements separated by `;`.

```
- {{mermaid}}
  - graph LR;agent(coding agent)==>cli(JSON CLI);cli==>broker(local broker)
```

- Parent text is exactly `{{mermaid}}`.
- Nodes are `id(label)` or `id("label")`. Never square brackets.
- Edges are `==>`.
- Quote a label that contains `)` or `;`. Colons and spaces inside parentheses are fine: `keep(verified: use fresh state)`.
- IDs are `[A-Za-z][A-Za-z0-9_]*`.

`create_block` / `create_page` markdown must nest that one child under `{{mermaid}}`. To fix a broken flowchart, `update_block` the existing child with the full one-line string. Do not `create_block` a second `{{mermaid}}` beside it.

When reading a flowchart that already matches this dialect and renders, leave it.

## Pie

A pie is not a one-line flowchart. These all fail to render:

- `pie showData` — unexpected character `s` at offset 4.
- `pie; title ...; "Task" : 7` — the parser skips `pie;` and then expects the token `pie`.
- One block whose string contains newlines — those are stored as `\` + `n`.

One `{{mermaid}}` parent. One child per source line. The first child is exactly `pie`. No `showData`. No `;` between statements.

```
- {{mermaid}}
  - pie
  - title gRPC methods by resource
  - "Task" : 7
  - "Workspace" : 4
  - "Model" : 4
```

Slice lines keep mermaid's quotes: `"Label" : 7`. A colon in the title is fine.

If the user asked for a pie, write this shape. A flowchart of the same numbers is a different diagram.

To fix a one-line pie, `update_block` the existing child to `pie`, then `create_block` the title and slices as later children of that same `{{mermaid}}` parent. Do not add a second `{{mermaid}}`.

When reading a pie whose children are already one source line each and whose first child is `pie`, leave it. Do not collapse it into one line.

## Verify before you stop

`get_block` the `{{mermaid}}` parent.

Flowchart:

- Exactly one child.
- That child's string still contains `==>`.
- No `[` or `]` in the child.
- The child does not contain the two characters `\` and `n`.

Pie:

- First child string is exactly `pie`.
- Each later child is one source line (`title ...` or `"Label" : N`).
- No child contains `showData`, a `;` joining statements, `[`, or `]`.

If a flowchart was split into sibling bullets, collapse it back into one child with `update_block`, then `get_block` again. If a pie was packed into one child, split it into the pie shape above, then `get_block` again.

A successful MCP write is not a rendered diagram. If the picture is truncated or shows a parse error, the stored source is wrong or the render is stale. Clicking out of the `{{mermaid}}` block and back in refreshes a stale picture. Do not rewrite a child that already matches its dialect.
