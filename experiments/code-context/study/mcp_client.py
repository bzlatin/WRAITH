"""Bounded stdio MCP client for the local comparison, not a production client SDK."""
import json
import os
import queue
import signal
import subprocess
import threading
import time


class Client:
    def __init__(self, command, cwd, env):
        if os.name != 'posix':
            raise RuntimeError('Study controllers require POSIX process-group containment; the product CLI is separate.')
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        start_new_session=os.name == "posix")
        self.messages = queue.Queue()
        self.stderr = bytearray()
        self.serial = 0
        self.peak_rss = None
        self.closed = False
        self.threads = [threading.Thread(target=fn, daemon=True) for fn in
                        (self._stdout, self._stderr, self._memory)]
        for thread in self.threads:
            thread.start()

    def _stdout(self):
        try:
            while True:
                line = self.process.stdout.readline(10 * 1024 * 1024 + 1)
                if not line:
                    raise RuntimeError("MCP server closed stdout")
                if len(line) > 10 * 1024 * 1024:
                    raise RuntimeError("MCP response exceeded 10 MiB")
                self.messages.put(json.loads(line))
        except Exception as exc:
            self.messages.put(exc)

    def _stderr(self):
        try:
            while data := self.process.stderr.read(4096):
                self.stderr.extend(data[:max(0, 65536 - len(self.stderr))])
        except (OSError, ValueError):
            if not self.closed:
                raise

    def _memory(self):
        try:
            import psutil
            process = psutil.Process(self.process.pid)
            while not self.closed:
                total = 0
                for child in [process, *process.children(recursive=True)]:
                    try:
                        total += child.memory_info().rss
                    except psutil.Error:
                        pass
                self.peak_rss = max(self.peak_rss or 0, total)
                time.sleep(0.05)
        except (ImportError, Exception):
            # Absence/denial means unmeasured, never zero usage.
            pass

    def notify(self, method, params=None):
        message = dict(jsonrpc="2.0", method=method)
        if params is not None:
            message["params"] = params
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()

    def call(self, method, params=None, timeout=120):
        self.serial += 1
        message = dict(jsonrpc="2.0", id=self.serial, method=method)
        if params is not None:
            message["params"] = params
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                response = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise TimeoutError(f"{method} exceeded {timeout} seconds") from exc
            if isinstance(response, Exception):
                raise response
            if response.get("id") == self.serial:
                if "error" in response:
                    raise RuntimeError(json.dumps(response["error"]))
                return response["result"]

    def initialize(self):
        response = self.call("initialize", dict(protocolVersion="2025-11-25",
            capabilities={}, clientInfo=dict(name="wraith-context-study", version="0.1.0")))
        self.notify("notifications/initialized")
        return response

    def close(self):
        self.closed = True
        try:
            if os.name == "posix":
                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.kill()
            self.process.wait(timeout=5)
        except ProcessLookupError:
            self.process.wait()
        finally:
            for thread in self.threads:
                thread.join(timeout=1)
            for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
                pipe.close()


def clean_env(extra=None):
    """Do not pass provider credentials or capture an environment dump."""
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "LANG") if key in os.environ}
    env.update(extra or {})
    return env
