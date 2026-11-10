# Wake for Zed

Syntax highlighting, code outlines, and language-server support for the
[SiFive Wake build language](https://github.com/sifiveinc/wake).

## Features

- Automatic detection of `.wake` files.
- Highlighting for keywords, comments, literals, interpolation, operators,
  function declarations/calls, types, constructors, and tuple fields.
- Outline entries for packages, definitions, targets, data types, tuples,
  fields, and topics, including nested definitions.
- Parenthesis matching and quote/parenthesis auto-closing.
- Two-space indentation defaults and `#` line comments.
- Wake LSP integration for hover, diagnostics, go-to-definition, references,
  symbols, and rename, subject to the installed Wake version's capabilities.

Completion and formatting are not provided by this extension; available LSP
features depend on Wake itself. The parser is derived from an older
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
required for highlighting. The LSP module requires Rust installed via rustup.

For SSH projects, install the extension in the local Zed application; there is
no manual copy into the remote project. Keep the local checkout updated with
`git pull --ff-only`, then rebuild it from Zed's Extensions page. If the language
does not update, reopen the file/window and inspect **zed: open log**.

This repository is not yet published in Zed's extension gallery.

## Language server

Install a Wake distribution that includes `lsp-wake` and its standard library
on the **project host**. By default the extension finds `wake` in that host's
shell PATH and starts `wake --lsp`. For SSH projects, this is the remote machine,
not the desktop running Zed. The extension does not download Wake or guess
which versioned installation to use.

To select a specific installation, add this to Zed user settings, remote
settings, or the project's `.zed/settings.json`, as appropriate:

```json
{
  "lsp": {
    "wake": {
      "binary": {
        "path": "/opt/wake/current/bin/wake"
      }
    }
  }
}
```

Use an absolute path on the project host; `~` and shell expressions are not
expanded. A stable symlink or wrapper can follow Wake upgrades without changing
Zed settings. Machine-specific paths normally belong in user/remote settings,
not committed project settings. An explicit path is used as-is; failures do not
silently select a different Wake installation.

Optional settings supported under `lsp.wake`:

```json
{
  "lsp": {
    "wake": {
      "binary": {
        "path": "/opt/wake/current/bin/wake",
        "arguments": ["--lsp"],
        "env": {"EXAMPLE_VARIABLE": "value"}
      },
      "initialization_options": {
        "stdLibPath": "/opt/wake/current/share/wake/lib"
      }
    }
  }
}
```

Arguments replace the default `--lsp` list, rather than appending to it. To run
`lsp-wake` directly, set its path and `"arguments": []`. Environment overrides
are merged with the project host's shell environment. The default stdlib is
located by Wake itself; only set `stdLibPath` for a custom installation.
After changing settings or upgrading Wake, run **editor: restart language server**
from the command palette.

If Wake is missing, highlighting still works; inspect **zed: open log** for the
startup error. To use highlighting without attempting LSP startup:

```json
{"languages": {"Wake": {"enable_language_server": false}}}
```

Use a real Wake workspace (with its `.wakeroot`) for semantic features.
`examples/syntax.wake` is a parser showcase, not a type-checked Wake project.

## Development and validation

Python 3.11+ and a C compiler are needed for the query tests:

```sh
uv venv
uv pip install -r tests/requirements.txt
uv run --no-project python -m unittest discover -s tests -v
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
rustup target add wasm32-wasip2
cargo build --locked --release --target wasm32-wasip2
```

Rust unit tests cover binary selection, argument replacement, environment
merging, and missing-executable errors. To additionally test a real Wake LSP
with a temporary workspace (skipped unless `WAKE_BIN` is set):

```sh
WAKE_BIN=/opt/wake/current/bin/wake uv run --no-project python -m unittest discover -s tests -p test_lsp.py -v
```

The real-server test passed with Wake 49.0.0 and 52.0.0. It checks initialization,
hover, definitions, references, diagnostics after edits, and clean shutdown.

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

MIT for the extension's original code, configuration, queries, documentation, and
tests. The vendored SiFive grammar and derived parser are Apache-2.0 licensed.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [grammar/LICENSE](grammar/LICENSE).
This is an independent community extension, not an official SiFive or Zed product.

## 中文安装说明

在运行 Zed 桌面端的电脑（例如 Mac）上克隆此仓库，打开命令面板，
执行 `zed: install dev extension`，选择仓库目录。
打开本地或 SSH 项目里的 `.wake` 文件即可使用。
本版支持语法高亮、Outline、括号匹配，以及 Wake LSP 的跳转、悬浮提示和诊断等功能。
LSP 默认从项目所在机器的 PATH 查找 `wake`；也可通过 Zed 的
`lsp.wake.binary.path` 设置绝对路径。SSH 项目使用远端 Wake，无需在 Mac 上安装。
升级插件后，在 Extensions 页面重新构建；修改 Wake 路径后重启 language server。
