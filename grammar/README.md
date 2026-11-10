# Wake grammar

Derived from SiFive tree-sitter-wake at
`9ddd83116cca543af6806fe7316a6686fa868231`, under Apache-2.0.
The upstream repository does not contain a generated parser, which Zed needs.
We keep the grammar here to ship reproducible parser sources in the same repo.

Generate using Node.js and the pinned Tree-sitter CLI:

```sh
cd grammar
npx --yes --package tree-sitter-cli@0.20.8 tree-sitter generate --no-bindings
npx --yes --package tree-sitter-cli@0.20.8 tree-sitter test
```

Keep generated `src/parser.c`, `src/node-types.json`, `src/grammar.json`, and
`src/tree_sitter/` in Git. The extension pins a commit containing these files.
When changing the grammar, commit it first, then update `grammars.wake.rev`
in `extension.toml` to that commit.

Local changes from upstream:

- Accept modern `->` match arms alongside legacy `=` arms.
- Parse `require ... = ...` / `else` expressions.
- Accept explicit function/target result types and semicolon tuple operators.
- Accept multiline parenthesized patterns.
- Initialize scanner state and stop scanning unterminated strings at EOF
  so incomplete edits cannot hang the editor.
- Set the scanner's EOL token explicitly; update one invalid-input corpus
  expectation for the modern generator's error recovery.

This is an editor parser, not Wake's compiler. Syntax introduced after the
upstream version may need additional coverage. Report a minimal example
when a valid Wake file is parsed incorrectly.
