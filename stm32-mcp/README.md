# stm32-mcp

**Give Claude Code live, read/write access to a running STM32 firmware — no printf, no recompile.**

Claude connects to the MCU through GDB/MI and can read global variables, inspect state machines, dump memory, inject values, and set breakpoints — all while the firmware keeps running.

---

## Why this exists

When debugging embedded firmware the usual workflow is: add a `printf`, rebuild, flash, observe. That takes 30–60 seconds per iteration and pollutes the binary. With this bridge Claude can do in one call what would otherwise require a full rebuild cycle:

```
read_variable("ai_drives[0]")
→ {sm=SRVAC_SM_READY, homed=0, speed_rpm=300, step_counts=95876}
```

It was built during development of the [ShopStocker](https://pibra.com) industrial conveyor system firmware (STM32F767ZI) and extracted here because nothing quite like it existed.

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
ST-LINK_gdbserver : 61234   ← already running, kept alive by CubeIDE -k flag
      │  SWD
      ▼
STM32 target MCU   ← firmware keeps running; only paused briefly to read variables
```

The key insight: STM32CubeIDE's ST-LINK gdbserver uses `-k` (keep-alive), which means it stays running after the IDE disconnects its own GDB session. This bridge attaches a second GDB in that window.

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

Open `gdb_mi.py` and update lines 24–30:

```python
GDB_EXE = r"C:\ST\STM32CubeIDE_2.1.0\...\arm-none-eabi-gdb.exe"  # ← your path
GDBSERVER_HOST = "localhost"
GDBSERVER_PORT = 61234   # ST-LINK default; J-Link uses 2331, OpenOCD uses 3333
```

On Linux/macOS `GDB_EXE` is typically `/usr/bin/arm-none-eabi-gdb` or inside the toolchain you extracted.

### 2. Set the default ELF in `server.py`

Line 29 resolves the ELF relative to the project root (two levels above `stm32-mcp/`):

```python
DEFAULT_ELF = str(_PROJECT_ROOT / "Debug" / "SS-HUB-FW.elf")   # ← change to your .elf name
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

### 4. Start a debug session in CubeIDE, then click **Disconnect**

The gdbserver stays alive (due to `-k`). Claude can now attach.

---

## Usage

All interaction happens through natural language in Claude Code. The tools are called automatically.

**Typical session:**

```
You:  "Connect to the STM32 and show me the SRVAC state machine"

Claude: calls connect()
        calls halt()
        calls read_variable("ai_drives[0]")
        calls resume()
        → Reports: sm=18 (READY), homed=0, speed_rpm=300
```

**Inject a value without recompiling:**

```
You:  "Set g_verbose to 2 so I can see the Modbus frames"
Claude: calls write_variable("g_verbose", "2")
```

**Catch a race condition:**

```
You:  "Set a breakpoint at servo_control.c:142 and show me the call stack when it hits"
Claude: calls set_breakpoint("servo_control.c:142")
        calls resume()
        ... waits ...
        calls backtrace()
```

---

## Tool reference

All tools require an active session (`connect` first). `halt`/`resume` bracket variable reads.

| Tool | Parameters | Description |
|---|---|---|
| `connect` | `elf_path` (optional) | Spawn GDB, load DWARF symbols, attach to gdbserver |
| `disconnect` | — | Detach cleanly so CubeIDE can reconnect |
| `halt` | — | Pause the MCU (required before reading variables) |
| `resume` | — | Resume execution |
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

# Full struct dump
read_variable("g_sensor_data")

# C expression (write via assignment)
read_variable("counter = 0")   # same as write_variable
```

---

## Real session output

Below is a snapshot from a live STM32F767ZI session (ShopStocker SS-HUB firmware):

```
connect()
→ Connected to ST-LINK_gdbserver:61234
  ELF: C:/GitHub/.../Debug/SS-HUB-FW.elf
  *stopped at AiMotor/src/ss-srvac-motion.c:686

read_variable("s_hw_cfg")
→ {magic=0xA55A0002, srvac_max=1, bloq_max=1, desv_max=0,
   varrac_max=1, rfid_max=1, inductive_max=4, rfid_poll_ms=300}

read_variable("ai_drives[0]")
→ {sm=18 (READY), homed=0, speed_rpm=300, step_counts=95876,
   accel_ms=200, home_timeout_ms=60000}

read_variable("mqtt.tx_buf")   # last published MQTT payload visible in RAM
→ "ss/HUB_00-30-51-19-36-39/sys/perf
   {"loop_hz":27038,"loop_us_avg":33,"loop_us_max":4057,"uptime_s":90}"

read_variable("mqtt.connected")
→ true
```

`loop_hz = 27 038` — over 27 000 main-loop iterations per second, average 33 µs, worst-case 4 ms (a Modbus RTU transaction). All extracted without a single `printf`.

---

## Adapting to other projects

The GDB/MI layer (`gdb_mi.py`) is 100% project-agnostic — it speaks standard MI protocol and knows nothing about your firmware. The MCP tools are generic GDB operations. Only three values need to change:

1. **`GDB_EXE`** in `gdb_mi.py` — path to your `arm-none-eabi-gdb` binary
2. **`GDBSERVER_PORT`** in `gdb_mi.py` — 61234 (ST-LINK), 2331 (J-Link), 3333 (OpenOCD)
3. **`DEFAULT_ELF`** in `server.py` — your `.elf` file built with debug symbols

This works with any ARM Cortex-M project that produces an ELF with DWARF symbols and has a gdbserver accessible over TCP. Tested with ST-LINK v2/v3 via STM32CubeIDE.

---

## Caveats

- **IWDG/watchdog:** When GDB halts the core, the ST-LINK freezes the watchdog counter automatically — no spurious resets.
- **CubeIDE conflict:** Only one GDB at a time can connect. Disconnect CubeIDE's GDB first; the gdbserver stays alive.
- **No reconnection:** If the gdbserver crashes, call `disconnect()` then `connect()` again.
- **Release builds:** DWARF symbols are stripped in Release configuration. Use Debug builds.

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
