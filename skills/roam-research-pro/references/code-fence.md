# Code fence

A snippet is one block. Opening backticks, the language id glued on, a newline, the code, then closing backticks glued to the last code line.

`create_block` and `create_page` parse the fence below into that block. Put the closing fence on its own line. The parser drops the newline in front of it.

````
- ```javascript
  const label = "[[Not A Page]]";
  if (ok) {
    return 1;
  }
  ```
````

Indent the fence under a label when the snippet needs one. Relative indent inside the fence is kept. A line that starts with `- ` stays in the code. `[[Not A Page]]` stays text in the block string.

`update_block` stores the string you pass. Use newline characters between lines, and glue the closing fence to the last line:

````
```javascript
const label = "[[Not A Page]]";
if (ok) {
  return 1;
}```
````

`get_block` prints each newline as the two characters `\` and `n`. Passing that pair to `update_block` stores the pair, and the snippet collapses to one line.

One snippet per block. The newline the parser drops joins a line of only backticks, or a second fence in that block, onto the closing fence (` `````` `). A newline before the closing fence keeps that line intact. `update_block` stores that newline, and the fence does not render.

Roam's highlighter uses `shell` for shell. No space between the backticks and the language id.

When a fence's raw string already has newline characters and the closing fence is glued to the last line, leave it.

## Verify

`datalog_query` the fence block. `create_block` returns the top block's uid. If you wrapped the fence under a label, `get_block` that uid and query the child whose string starts with the fence.

```
[:find ?s :in $ ?uid :where [?b :block/uid ?uid] [?b :block/string ?s]]
```

Pass the uid in `inputs`.

- The string starts with ``` and the language id, then a newline.
- The string ends with ``` glued to the last code character.
- In the tool result a line break is JSON `\n`. The two characters `\` and `n` are JSON `\\n`. `\\n` on a code line is source, as in `split("\n")`. The fence is flattened when `\\n` is the separator between the opening fence, the code lines, and the closing fence. Rewrite that block with `create_block`, or `update_block` the glued string above.
- One fence in the block. A run of six backticks is two fences joined. Split them into one block each.
- `get_block` only shows that the snippet is one block. A collapsed fence looks the same there.
