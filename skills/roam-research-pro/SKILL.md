---
name: roam-research-pro
description: Write and edit Roam Research graphs without producing mermaid that Roam cannot render. Use when creating or updating Roam pages or blocks, embedding diagrams in Roam, or the user mentions Roam, {{mermaid}}, roam mermaid, or /roam-research-pro. GitHub-style mermaid (--> arrows, [bracket] nodes, one statement per bullet) is invalid through MCP writes because create_block parses newlines into new blocks and Roam markup in those blocks is consumed before mermaid runs.
---

# Roam Research

## Graph ops

Call `get_graph_guidelines` once per graph per session before the first read or write. Use the connected `roam` or `roam_research` MCP tools. Honor that graph's `roamSyntax` for ordinary blocks.

When a write includes a diagram, encode it with the dialect below. Do not paste a mermaid fenced code block into Roam.

## Why MCP mermaid breaks

`create_page` and `create_block` parse a nested `- ` bullet tree. A newline is a new block. `update_block` writes one block's string literally and does not create children.

`{{mermaid}}` turns its children into mermaid source. Those children are still Roam blocks, so this markup is consumed before mermaid runs: `[alias]`, `[[page]]`, `{{component}}`, `((uid))`.

Two failures follow if you paste GitHub mermaid:

1. Each source line becomes a sibling under `{{mermaid}}`. The picture then shows only a fragment.
2. `A[label]` is an alias, so node text never reaches mermaid.

Roam's UI docs nest `-->` bullets under `{{mermaid}}`. That path is not what MCP `create_block` does with a multi-line string. Do not copy UI examples into `create_block` markdown.

## Dialect

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

`create_block` / `create_page` markdown must nest that one child under `{{mermaid}}`. To fix a broken graph, `update_block` the existing child with the full one-line string. Do not `create_block` a second `{{mermaid}}` beside it.

When reading a diagram that already matches this dialect and renders, leave it.

## Verify before you stop

`get_block` the `{{mermaid}}` parent:

- Exactly one child.
- That child's string still contains `==>`.
- No `[` or `]` in the child.

If Roam split the source into sibling bullets, collapse it back into one child with `update_block`, then `get_block` again.

A successful MCP write is not a rendered diagram. If the picture is truncated, the stored source is wrong or the render is stale. Clicking out of the `{{mermaid}}` block and back in refreshes a stale picture. Do not rewrite a child that already matches this dialect.
