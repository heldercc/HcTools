## @file gdb_mi.py
# @brief GDB/MI subprocess client — pure protocol layer, no firmware knowledge.
#
# @author  Hélder Costa <heldermoreiracosta@gmail.com>
# @date    2026-06-25
# @license MIT
# @copyright Copyright (c) 2026 Hélder Costa
#
"""
GDB/MI client — spawns arm-none-eabi-gdb as a subprocess and drives it via
the Machine Interface (MI) protocol over stdin/stdout pipes.

Connects to the ST-LINK_gdbserver already started by STM32CubeIDE (port 61234).
The gdbserver uses -k (keep-alive) so it stays running after CubeIDE's GDB
disconnects, giving us a clean window to attach.

Protocol sketch:
  TX:  {token}-exec-interrupt\n
  RX:  lines until {token}^done or {token}^error appears.
       Async records (*stopped, =thread-...) may appear before the result.

Windows path note: GDB expects forward slashes even on Windows. All paths
passed to GDB commands must use '/' not '\\'.
"""
import subprocess
import threading
import queue
import time
from pathlib import PurePosixPath, Path
from typing import Optional

GDB_EXE = (
    r"C:\ST\STM32CubeIDE_2.1.0\STM32CubeIDE\plugins"
    r"\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740"
    r"\tools\bin\arm-none-eabi-gdb.exe"
)
GDBSERVER_HOST = "localhost"
GDBSERVER_PORT = 61234


def _to_gdb_path(p: str) -> str:
    """Convert Windows path to forward-slash form GDB understands."""
    return Path(p).as_posix()


def _mi_quote(s: str) -> str:
    """Wrap string in double quotes, escaping internal double quotes and backslashes."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class GdbMiClient:
    def __init__(self, gdb_exe: str = GDB_EXE):
        self._exe = gdb_exe
        self._proc: Optional[subprocess.Popen] = None
        self._token = 0
        self._lock = threading.Lock()
        self._q: queue.Queue[str] = queue.Queue()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Spawn GDB in MI mode and wait until it's ready."""
        self._proc = subprocess.Popen(
            [self._exe, "--interpreter=mi", "--quiet", "--nx"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._reader, daemon=True).start()
        self._drain(timeout=2.0)  # consume GDB startup banner

    def stop(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("-gdb-exit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _reader(self):
        for line in self._proc.stdout:
            stripped = line.rstrip("\n")
            if stripped:
                self._q.put(stripped)

    def _drain(self, timeout: float):
        """Consume queued lines until GDB is silent for 150 ms."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._q.get(timeout=0.15)
            except queue.Empty:
                break

    def _next_token(self) -> str:
        with self._lock:
            self._token += 1
            return str(self._token)

    def _send_cmd(self, mi_cmd: str) -> str:
        tok = self._next_token()
        self._proc.stdin.write(f"{tok}{mi_cmd}\n")
        self._proc.stdin.flush()
        return tok

    def _collect(self, token: str, timeout: float) -> list[str]:
        """Accumulate output lines until the result record for `token` arrives."""
        lines: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._q.get(timeout=0.1)
                lines.append(line)
                if line.startswith(f"{token}^"):
                    break
            except queue.Empty:
                continue
        return lines

    # ------------------------------------------------------------------
    # Core command
    # ------------------------------------------------------------------

    def cmd(self, mi_command: str, timeout: float = 8.0) -> dict:
        """
        Send one MI command and return:
          {"ok": bool, "data": str | None, "error": str | None, "raw": [lines]}
        """
        tok = self._send_cmd(mi_command)
        lines = self._collect(tok, timeout)
        return _parse(lines, tok)

    # ------------------------------------------------------------------
    # High-level operations
    # ------------------------------------------------------------------

    def connect(self, elf_path: Optional[str],
                host: str = GDBSERVER_HOST,
                port: int = GDBSERVER_PORT) -> dict:
        if elf_path:
            gdb_path = _to_gdb_path(elf_path)
            # -file-exec-and-symbols sets BOTH the executable context and debug symbols.
            # -file-symbol-file alone is not enough: GDB loses global variable context
            # ("No symbol X in current context") without the exec file being set.
            r = self.cmd(f"-file-exec-and-symbols {_mi_quote(gdb_path)}")
            if not r["ok"]:
                return {"ok": False, "error": "ELF load failed", "raw": r["raw"], "data": None}
        return self.cmd(f"-target-select remote {host}:{port}", timeout=10)

    def halt(self) -> dict:
        r = self.cmd("-exec-interrupt")
        if r["ok"]:
            # Wait for *stopped async record so the target is definitely
            # halted before the caller attempts to read variables/memory.
            # Without this, -data-evaluate-expression may return "Target is running."
            self._drain(timeout=0.5)
        return r

    def resume(self) -> dict:
        return self.cmd("-exec-continue")

    def read_registers(self) -> dict:
        return self.cmd("-data-list-register-values x")

    def read_variable(self, expr: str) -> dict:
        # -data-evaluate-expression handles reads AND C assignment expressions (e.g. "x = 5")
        return self.cmd(f"-data-evaluate-expression {_mi_quote(expr)}")

    def read_memory(self, addr: str, count: int = 4) -> dict:
        return self.cmd(f"-data-read-memory-bytes {addr} {count}")

    def write_memory(self, addr: str, hex_bytes: str) -> dict:
        # GDB expects a single hex string with no spaces: "01000000"
        # Accept both "01000000" and "01 00 00 00" from the caller.
        normalized = hex_bytes.replace(" ", "").replace("0x", "").replace("0X", "")
        return self.cmd(f"-data-write-memory-bytes {addr} {normalized}")

    def set_breakpoint(self, location: str) -> dict:
        return self.cmd(f"-break-insert {location}")

    def remove_breakpoint(self, bp_num: int) -> dict:
        return self.cmd(f"-break-delete {bp_num}")

    def backtrace(self) -> dict:
        return self.cmd("-stack-list-frames")

    def list_locals(self) -> dict:
        # '1' = --all-values: include both names and values.
        # Correct MI positional syntax: -stack-list-variables <print-values>
        return self.cmd("-stack-list-variables 1")

    def console(self, gdb_cmd: str) -> dict:
        """Run an arbitrary GDB console command and capture its output."""
        return self.cmd(f"-interpreter-exec console {_mi_quote(gdb_cmd)}", timeout=10)


# ------------------------------------------------------------------
# MI result parser
# ------------------------------------------------------------------

def _parse(lines: list[str], token: str) -> dict:
    result: dict = {"ok": False, "data": None, "error": None, "raw": lines}
    for line in lines:
        if line.startswith(f"{token}^done"):
            result["ok"] = True
            result["data"] = line[len(f"{token}^done"):]  # e.g. ',value="5"'
        elif line.startswith(f"{token}^running"):
            result["ok"] = True
        elif line.startswith(f"{token}^connected"):
            result["ok"] = True
        elif line.startswith(f"{token}^error"):
            result["error"] = line
    return result
