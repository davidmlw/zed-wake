"""Optional real-server smoke test; set WAKE_BIN to a complete Wake installation."""

import json
import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time
import unittest


@unittest.skipUnless(os.environ.get("WAKE_BIN"), "set WAKE_BIN to test a real Wake LSP")
class WakeLspTest(unittest.TestCase):
    def test_navigation_and_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="zed-wake-lsp-") as directory:
            root = Path(directory)
            (root / ".wakeroot").write_text("{}\n")
            source = "package smoke\ndef answer = 42\ndef result = answer\n"
            file = root / "main.wake"
            file.write_text(source)
            with tempfile.TemporaryFile() as stderr:
                process = subprocess.Popen(
                    [os.environ["WAKE_BIN"], "--lsp"],
                    cwd=root,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                )
                self.addCleanup(process.stdin.close)
                self.addCleanup(process.stdout.close)
                try:
                    self.buffer = b""
                    self.notifications = []
                    self.process = process
                    with selectors.DefaultSelector() as selector:
                        selector.register(process.stdout, selectors.EVENT_READ)
                        self.selector = selector
                        response = self.request(1, "initialize", {
                            "processId": os.getpid(),
                            "rootUri": root.as_uri(),
                            "workspaceFolders": [{"uri": root.as_uri(), "name": "smoke"}],
                            "capabilities": {},
                        })
                        capabilities = response["capabilities"]
                        self.assertTrue(capabilities.get("definitionProvider"))
                        self.assertTrue(capabilities.get("hoverProvider"))
                        self.send("initialized", {})
                        self.send("textDocument/didOpen", {"textDocument": {
                            "uri": file.as_uri(), "languageId": "wake",
                            "version": 1, "text": source,
                        }})
                        position = {
                            "textDocument": {"uri": file.as_uri()},
                            "position": {"line": 2, "character": 14},
                        }
                        hover = self.request(2, "textDocument/hover", position)
                        self.assertTrue(hover and hover.get("contents"), hover)
                        definition = self.request(3, "textDocument/definition", position)
                        locations = definition if isinstance(definition, list) else [definition]
                        self.assertTrue(any(
                            item and item.get("uri") == file.as_uri()
                            and item["range"]["start"]["line"] == 1
                            for item in locations
                        ), definition)
                        references = self.request(4, "textDocument/references", {
                            **position, "context": {"includeDeclaration": True},
                        })
                        self.assertTrue(references, references)
                        # Full-document synchronization should surface a new unknown symbol.
                        self.send("textDocument/didChange", {
                            "textDocument": {"uri": file.as_uri(), "version": 2},
                            "contentChanges": [{"text": source + "def broken = unknownSymbol\n"}],
                        })
                        self.request(5, "textDocument/hover", position)
                        self.assertTrue(any(
                            message.get("method") == "textDocument/publishDiagnostics"
                            and message["params"].get("uri") == file.as_uri()
                            and message["params"].get("diagnostics")
                            for message in self.notifications
                        ), self.notifications)
                        self.request(6, "shutdown", None)
                        self.send("exit", None)
                        process.wait(timeout=5)
                except Exception:
                    stderr.seek(0)
                    print(stderr.read().decode(errors="replace")[-8000:])
                    raise
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)

    def send(self, method, params, request_id=None):
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        body = json.dumps(message).encode()
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self.process.stdin.flush()

    def request(self, request_id, method, params):
        self.send(method, params, request_id)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            header, separator, body = self.buffer.partition(b"\r\n\r\n")
            if separator:
                fields = dict(line.split(b":", 1) for line in header.split(b"\r\n"))
                size = int(fields[b"Content-Length"])
                if len(body) >= size:
                    message = json.loads(body[:size])
                    self.buffer = body[size:]
                    if message.get("id") == request_id:
                        self.assertNotIn("error", message)
                        return message["result"]
                    self.notifications.append(message)
                    continue
            if not self.selector.select(timeout=max(0, deadline - time.monotonic())):
                break
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                self.fail(f"Wake LSP exited during {method}: {self.process.poll()}")
            self.buffer += chunk
        self.fail(f"Wake LSP timed out during {method}")
