# stm32-mcp

**Give Claude Code live, read/write access to a running STM32 firmware — no printf, no recompile.**

Claude connects to the MCU through GDB/MI and can read global variables, inspect state machines, dump memory, inject values, and set breakpoints — all while the firmware keeps running.

---

## Why this exists

When debugging embedded firmware the usual workflow is: add a `printf`, rebuild, flash, observe. That takes 30–60 seconds per iteration and pollutes the binary. With this bridge Claude can do in one call what would otherwise require a full rebuild cycle:

```
read_variable("my_config")
→ {magic=0xDEADBEEF, mode=1, timeout_ms=300}
```

It was extracted from a real industrial embedded project because nothing quite like it existed.

---

## How it works

```
Claude Code (client)
      │  MCP JSON-RPC over stdio
      ▼
server.py  (MCP server — 14 tools)
      │  Python method calls
      ▼
gdb_mi.py  (GDB/MI protocol — subprocess)
      │  arm-none-eabi-gdb --interpreter=mi
      ▼
ST-LINK_gdbserver : 61234   ← already running via CubeIDE debug session
      │  SWD
      ▼
STM32 target MCU   ← firmware keeps running; briefly paused on connect() to read
```

When `connect()` is called, the gdbserver automatically halts the MCU. After reading,
`disconnect()` detaches cleanly and the firmware resumes. The gdbserver stays alive
because `stop()` sends `-target-detach` before `-gdb-exit` (a kill packet would close it).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `python --version` |
| `mcp` library | `pip install mcp` (or `pip install -r requirements.txt`) |
| `arm-none-eabi-gdb` | Bundled with STM32CubeIDE; or install the [ARM GNU Toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads) |
| ST-LINK gdbserver | Comes with STM32CubeIDE. Must be running (step 1 below). |
| `.elf` with DWARF symbols | Build in **Debug** configuration — Release strips symbols |

---

## Setup

### 1. Adapt the two hardcoded paths in `gdb_mi.py`

Open `gdb_mi.py` and update:

```python
GDB_EXE = r"C:\ST\STM32CubeIDE_2.1.0\...\arm-none-eabi-gdb.exe"  # ← your path
GDBSERVER_HOST = "localhost"
GDBSERVER_PORT = 61234   # ST-LINK default; J-Link uses 2331, OpenOCD uses 3333
```

On Linux/macOS `GDB_EXE` is typically `/usr/bin/arm-none-eabi-gdb` or inside the toolchain you extracted.

### 2. Set the default ELF in `server.py`

```python
DEFAULT_ELF = str(_PROJECT_ROOT / "Debug" / "YourFirmware.elf")   # ← change to your .elf name
```

You can always override this at connect time by passing `elf_path` explicitly.

### 3. Wire up `.mcp.json` in your project root

```json
{
  "mcpServers": {
    "stm32-debug": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/stm32-mcp/server.py"],
      "description": "Live STM32 debug access via GDB/MI"
    }
  }
}
```

### 4. Start a debug session in CubeIDE and let the firmware run

**Critical:** the firmware must be **running** (not paused at a startup breakpoint) before calling `connect()`.

1. Press **F11** in CubeIDE to start a debug session
2. Press **F8** to resume past the initial breakpoint
3. Wait 2–3 seconds for firmware initialisation to complete
4. **Leave CubeIDE connected** — do not click Disconnect

> **Why not click Disconnect?** Without the `-k` flag in the gdbserver launch config,
> clicking Disconnect in CubeIDE kills the gdbserver. The bridge connects alongside
> CubeIDE's session — both GDB clients share the gdbserver. This works reliably as long
> as the firmware is running when `connect()` is called.

---

## Usage

### Primary pattern — connect → read → disconnect

The most reliable monitoring workflow. No `halt()` / `resume()` needed — the gdbserver
halts the MCU automatically on `connect()` and resumes it on `disconnect()`.

```
You:  "Show me the current state of all state machines"

Claude: calls connect()
        → firmware halts, stopped somewhere in the main loop
        calls read_variable("my_state.mode")          → RUNNING
        calls read_variable("my_config.timeout_ms")   → 300
        calls read_variable("g_error_count")          → 0
        calls disconnect()
        → firmware resumes, gdbserver stays alive
```

### Inject a value without recompiling

```
You:  "Enable verbose logging"
Claude: calls connect()
        calls write_variable("g_verbose", "2")
        calls disconnect()
```

### Catch a race condition

```
You:  "Set a breakpoint at state_machine.c:142 and show me the call stack when it hits"
Claude: calls connect()
        calls set_breakpoint("state_machine.c:142")
        calls resume()   ← resumes from within the session
        ... waits for breakpoint hit ...
        calls backtrace()
        calls disconnect()
```

---

## Tool reference

| Tool | Parameters | Description |
|---|---|---|
| `connect` | `elf_path` (optional) | Spawn GDB, load DWARF symbols, attach to gdbserver. MCU halts automatically. |
| `disconnect` | — | Detach cleanly; MCU resumes, gdbserver stays alive |
| `halt` | — | Pause the MCU explicitly (only needed after `resume()` within a session) |
| `resume` | — | Resume execution within an open session |
| `read_register` | `name` (`"all"`, `"pc"`, `"sp"`, `"r0"`…) | Read ARM Cortex-M registers |
| `read_variable` | `expr` | Read any C variable or expression via DWARF |
| `write_variable` | `name`, `value` | Inject a value at runtime (no recompile) |
| `read_memory` | `address` (hex), `count` (bytes) | Raw memory read |
| `write_memory` | `address` (hex), `hex_bytes` | Raw memory write (GPIO registers, etc.) |
| `set_breakpoint` | `location` (`"file.c:123"`, `"func_name"`, `"*0x08001234"`) | Set breakpoint |
| `remove_breakpoint` | `number` | Remove breakpoint by ID |
| `backtrace` | — | Current call stack |
| `list_locals` | — | Local variables in current stack frame |
| `raw_gdb` | `command` | Any GDB console command (blocked: quit/detach/-gdb-exit) |

### `read_variable` examples

```python
# Struct members
read_variable("my_state_machine.state")
read_variable("config.baud_rate")

# Array element
read_variable("rx_buffer[0]")

# Cast raw address
read_variable("*(uint32_t*)0x20000100")

# Full struct dump (GDB pretty-prints all fields)
read_variable("g_sensor_data")

# C assignment expression (same as write_variable)
read_variable("counter = 0")
```

---

## Real session output (STM32F767ZI)

Session recorded against running firmware, CubeIDE debug session active in parallel:

```
connect()
→ Connected to ST-LINK_gdbserver:61234
  ELF: Debug/MyFirmware.elf
  *stopped in uart_rfid_task() at uart_rfid.c:270
  (firmware was deep in main loop — init already complete)

read_variable("mqtt.connected")
→ true

read_variable("config")
→ {magic=0xA55A0002 ✓, mode=1, timeout_ms=300, max_retries=4}

read_variable("state_machines[0].state")
→ IDLE

read_variable("loop_stats.hz")
→ 27038   (27 000 main-loop iterations/second, avg 33 µs)

disconnect()
→ GDB disconnected. Firmware resumes.

netstat | grep 61234
→ 0.0.0.0:61234  LISTENING   ← gdbserver survived the disconnect ✓
```

All of this extracted without a single `printf`, without recompiling, without interrupting the running application.

---

## Known limitations

- **halt() after resume() fails in dual-client mode.** When CubeIDE's GDB is also connected, `-exec-interrupt` receives "Invalid remote reply" from the gdbserver. Workaround: use `disconnect()` + `connect()` instead of `resume()` + `halt()`.
- **Firmware must be running when connect() is called.** If stopped at a startup breakpoint, global structs are uninitialised — reads return zero or garbage.
- **IWDG/watchdog:** The ST-LINK freezes the watchdog counter when the MCU is halted — no spurious resets.
- **Release builds:** DWARF symbols are stripped. Always use Debug builds.

---

## Adapting to other projects

The GDB/MI layer (`gdb_mi.py`) is 100% project-agnostic — it speaks standard MI protocol and knows nothing about your firmware. Only three values need to change:

1. **`GDB_EXE`** in `gdb_mi.py` — path to your `arm-none-eabi-gdb` binary
2. **`GDBSERVER_PORT`** in `gdb_mi.py` — 61234 (ST-LINK), 2331 (J-Link), 3333 (OpenOCD)
3. **`DEFAULT_ELF`** in `server.py` — your `.elf` built with debug symbols

Works with any ARM Cortex-M project that produces a DWARF ELF and has a gdbserver on TCP. Tested with ST-LINK v2/v3 via STM32CubeIDE 2.1.0.

---

## File structure

```
stm32-mcp/
├── server.py          MCP server — 14 tools, stdio transport
├── gdb_mi.py          GDB/MI subprocess client — pure protocol, no firmware knowledge
├── requirements.txt   Single dependency: mcp>=1.0.0
├── test_live.py       Integration test against real hardware
└── verify.py          Pre-flight sanity checks
```

---

## Inspiration

- [cortex-mcp-bridge](https://github.com/paulopalaoro/cortex-mcp-bridge) — similar concept via VSCode DAP extension (TypeScript). This project takes a different approach: standalone Python, no IDE dependency, direct GDB/MI for lower-level access.

---

## License

MIT — do what you want with it. If you build something cool, a ⭐ is appreciated.
