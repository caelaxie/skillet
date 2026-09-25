---
name: roam-research-pro
description: Write and edit Roam Research graphs without producing mermaid that Roam cannot render. Use when creating or updating Roam pages or blocks, embedding diagrams in Roam, or the user mentions Roam, {{mermaid}}, roam mermaid, or /roam-research-pro. Flowcharts are one child with statements joined by `;`, edges `==>`, and nodes `id(label)`. Pie charts are one child per source line, first child exactly `pie`. `pie showData`, a one-line `pie; ...`, and a newline inside one block all fail. A bar chart needs `[]`, which Roam consumes before mermaid runs.
---

# Roam Research

## Graph ops

Call `get_graph_guidelines` once per graph per session before the first read or write. Use the connected `roam` or `roam_research` MCP tools. Honor that graph's `roamSyntax` for ordinary blocks.

When a write includes a diagram, load the matching reference below. Do not paste a mermaid fenced code block into Roam.

## Why MCP mermaid breaks

`create_page` and `create_block` parse a nested `- ` bullet tree. A newline is a new block. `update_block` writes one block's string literally and does not create children. A newline in that string is stored as the two characters `\` and `n`, so mermaid still sees one line.

`{{mermaid}}` turns its children into mermaid source. Those children are still Roam blocks, so this markup is consumed before mermaid runs: `[alias]`, `[[page]]`, `{{component}}`, `((uid))`.

A bar or xy chart needs `[]`. Roam consumes those brackets before mermaid runs. Write a pie instead.

Roam's UI docs nest `-->` bullets under `{{mermaid}}`. That path is not either dialect below. Do not copy UI flowchart examples into `create_block` markdown.

A successful MCP write is not a rendered diagram. If the picture is truncated or shows a parse error, the stored source is wrong or the render is stale. Clicking out of the `{{mermaid}}` block and back in refreshes a stale picture. Do not rewrite a child that already matches its dialect.

## References

Load only the reference for the diagram you are writing or fixing.

- `references/mermaid-flowchart.md`: one `{{mermaid}}` child, statements joined by `;`, edges `==>`, nodes `id(label)`.
- `references/mermaid-pie.md`: one child per source line, first child exactly `pie`. `pie showData` and a one-line `pie; ...` both fail.
