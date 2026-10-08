---
name: roam-research-pro
description: Write and edit Roam Research graphs without producing mermaid that Roam cannot render. Use when creating or updating Roam pages or blocks, embedding diagrams or code snippets in Roam, or the user mentions Roam, {{mermaid}}, roam mermaid, a code fence, or /roam-research-pro. Flowcharts are one child with statements joined by `;`, edges `==>`, and nodes `id(label)`. Pie charts are one child per source line, first child exactly `pie`. `pie showData`, a one-line `pie; ...`, and the two characters `\` and `n` between statements all fail. A bar chart needs `[]`, which Roam consumes before mermaid runs. A mermaid diagram is a `{{mermaid}}` block. A code fence shows that source and does not render the picture. Any other code snippet is one fenced block. Its line breaks are newline characters in that block, and the language id is glued to the opening fence.
---

# Roam Research

## Graph ops

Call `get_graph_guidelines` once per graph per session before the first read or write. Use the connected `roam` or `roam_research` MCP tools. Honor that graph's `roamSyntax` for ordinary blocks.

When a write includes a mermaid diagram, load the matching reference below and write a `{{mermaid}}` block. A code fence shows the mermaid source and does not render the picture.

When a write includes any other code snippet, load the code fence reference.

## Why MCP mermaid breaks

`create_page` and `create_block` parse a nested `- ` bullet tree. A newline outside a code fence is a new block. `update_block` writes one block's string literally and does not create children. The two characters `\` and `n` are not a line break. `get_block` prints that pair where a newline is, and passing the pair to `update_block` stores it. Mermaid does not treat the pair as a new statement.

`{{mermaid}}` turns its children into mermaid source. Those children are still Roam blocks, so this markup is consumed before mermaid runs: `[alias]`, `[[page]]`, `{{component}}`, `((uid))`.

A bar or xy chart needs `[]`. Roam consumes those brackets before mermaid runs. Write a pie instead.

Roam's UI docs nest `-->` bullets under `{{mermaid}}`. That path is not either reference dialect. Do not copy UI flowchart examples into `create_block` markdown.

A successful MCP write is not a rendered diagram. If the picture is truncated or shows a parse error, the stored source is wrong or the render is stale. Clicking out of the `{{mermaid}}` block and back in refreshes a stale picture. Do not rewrite a child that already matches its dialect.

## References

Load only the reference for the diagram or snippet you are writing or fixing. After the write, run that file's Verify section before stopping.

- Code fence: `references/code-fence.md`
- Flowchart: `references/mermaid-flowchart.md`
- Pie: `references/mermaid-pie.md`
