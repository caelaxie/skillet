# Pie

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

## Verify

`get_block` the `{{mermaid}}` parent.

- First child string is exactly `pie`.
- Each later child is one source line (`title ...` or `"Label" : N`).
- No child contains `showData`, a `;` joining statements, `[`, or `]`.

If a pie was packed into one child, split it into the shape above, then `get_block` again.
