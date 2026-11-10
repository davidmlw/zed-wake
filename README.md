# Wake for Zed

Syntax highlighting and code outlines for the
[SiFive Wake build language](https://github.com/sifiveinc/wake).

## Features

- Automatic detection of `.wake` files.
- Highlighting for keywords, comments, literals, interpolation, operators,
  function declarations/calls, types, constructors, and tuple fields.
- Outline entries for packages, definitions, targets, data types, tuples,
  fields, and topics, including nested definitions.
- Parenthesis matching and quote/parenthesis auto-closing.
- Two-space indentation defaults and `#` line comments.

This initial version does not provide completion, diagnostics, formatting,
or definition/reference navigation. Those require Wake language-server
integration, which is planned separately. The parser is derived from an older
Wake grammar with selected modern syntax additions, not a complete replacement
for the Wake compiler. Please report unsupported syntax with a minimal example.

## Install locally

On the machine running the Zed desktop application (for example, your Mac):

```sh
git clone https://github.com/davidmlw/zed-wake.git
```

1. Open Zed's command palette (`Cmd-Shift-P` on macOS).
2. Run **zed: install dev extension**.
3. Select the cloned `zed-wake` directory.
4. Open a `.wake` file. The language selector should display **Wake**.
5. Open `examples/syntax.wake` and the Outline panel to inspect the result.

Zed compiles the grammar using its WASI SDK, downloading the SDK when needed.
Follow [Zed's development prerequisites](https://zed.dev/docs/extensions/developing-extensions)
if prompted for additional tools. No Wake executable or language server is
required for highlighting. No custom Rust extension module is needed.

For SSH projects, install the extension in the local Zed application; there is
no manual copy into the remote project. Keep the local checkout updated with
`git pull --ff-only`, then rebuild it from Zed's Extensions page. If the language
does not update, reopen the file/window and inspect **zed: open log**.

This repository is not yet published in Zed's extension gallery.

## Development and validation

Python 3.11+ and a C compiler are needed for the query tests:

```sh
uv venv
uv pip install -r tests/requirements.txt
uv run --no-project python -m unittest discover -s tests -v
```

Tests compile the shipped C parser and check error-free example parsing,
highlight captures, outline names, bracket pairs, and incomplete-input recovery.
Initial compatibility checks also parsed all 34 files in a local Wake 42.3.0
standard library and two project files without errors. Those external project
files are not included in this public repository.
They do not launch the Zed GUI; theme rendering and SSH behavior need a manual
check in Zed.

See [grammar/README.md](grammar/README.md) for parser regeneration and grammar
revision updates. The extension fetches the parser from a pinned commit of this
repository, so that commit must be pushed before installing on another machine.

## License

MIT for the extension's original configuration, queries, documentation, and
tests. The vendored SiFive grammar and derived parser are Apache-2.0 licensed.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [grammar/LICENSE](grammar/LICENSE).
This is an independent community extension, not an official SiFive or Zed product.

## 中文安装说明

在运行 Zed 桌面端的电脑（例如 Mac）上克隆此仓库，打开命令面板，
执行 `zed: install dev extension`，选择仓库目录。
打开本地或 SSH 项目里的 `.wake` 文件即可使用。
本版支持语法高亮、Outline 和括号匹配；跳转定义、类型提示等 LSP 功能暂未接入。
