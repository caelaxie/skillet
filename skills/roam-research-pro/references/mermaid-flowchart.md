# Flowchart

One `{{mermaid}}` parent. Exactly one child. The whole diagram in that child as a single line, statements separated by `;`.

```
- {{mermaid}}
  - graph LR;agent(coding agent)==>cli(JSON CLI);cli==>broker(local broker)
```

- Parent text is exactly `{{mermaid}}`.
- Nodes are `id(label)` or `id("label")`. Never square brackets. `A[label]` is a Roam alias, so that label never reaches mermaid.
- Edges are `==>`.
- Quote a label that contains `)` or `;`. Colons and spaces inside parentheses are fine: `keep(verified: use fresh state)`.
- IDs are `[A-Za-z][A-Za-z0-9_]*`.

`create_block` / `create_page` markdown must nest that one child under `{{mermaid}}`. To fix a broken flowchart, `update_block` the existing child with the full one-line string. Do not `create_block` a second `{{mermaid}}` beside it.

GitHub flowchart source also fails when each source line becomes its own child. The diagram then shows only a fragment.

When reading a flowchart that already matches this dialect and renders, leave it.

## Verify

`get_block` the `{{mermaid}}` parent.

- Exactly one child.
- That child's string still contains `==>`.
- No `[` or `]` in the child.
- The child does not contain the two characters `\` and `n`.

If a flowchart was split into sibling bullets, collapse it back into one child with `update_block`, then `get_block` again.
