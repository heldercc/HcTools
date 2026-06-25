#!/usr/bin/env python3
## @file server.py
# @brief MCP server exposing STM32 debug tools to Claude Code via stdio transport.
#
# @author  Hélder Costa <heldermoreiracosta@gmail.com>
# @date    2026-06-25
# @license MIT
# @copyright Copyright (c) 2026 Hélder Costa
#
"""
stm32-mcp — MCP server giving Claude live access to an STM32 debug session.

Transport : stdio (Claude Code spawns this process directly)
Debug backend: arm-none-eabi-gdb in MI mode → ST-LINK_gdbserver :61234

Workflow:
  1. Start a debug session in STM32CubeIDE (this launches ST-LINK_gdbserver -k)
  2. In CubeIDE click "Disconnect" (GDB disconnects; gdbserver stays alive due to -k)
  3. Claude calls connect() — optionally pass the .elf for symbolic debug
  4. Inspect variables, registers, memory; inject values; set breakpoints
  5. Claude calls disconnect() → CubeIDE can reconnect

Default ELF: Debug/SS-HUB-FW.elf (relative to project root, resolved at connect time).
"""
import asyncio
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

sys.path.insert(0, str(Path(__file__).parent))
from gdb_mi import GdbMiClient

_PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_ELF = str(_PROJECT_ROOT / "Debug" / "SS-HUB-FW.elf")

server = Server("stm32-debug")
_client: GdbMiClient | None = None  # active GDB session; None when disconnected


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ok(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=False)

def _err(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=f"ERROR: {text}")], isError=True)

def _raw(lines: list[str]) -> str:
    return "\n".join(lines)


# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

TOOLS = [
    Tool(
        name="connect",
        description=(
            "Start GDB, load ELF symbols, and connect to ST-LINK_gdbserver:61234. "
            "Must be called first. CubeIDE must have disconnected its GDB "
            "(click Disconnect in the debug toolbar — the gdbserver stays alive). "
            "elf_path defaults to Debug/SS-HUB-FW.elf."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "elf_path": {"type": "string", "description": "Absolute path to .elf file (optional)."}
            },
        },
    ),
    Tool(
        name="disconnect",
        description="Detach GDB cleanly so CubeIDE can reconnect.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="halt",
        description="Halt (pause) the target MCU. Required before reading variables or memory.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="resume",
        description="Resume target MCU execution.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="read_register",
        description=(
            "Read ARM Cortex-M registers. "
            "name = 'all' for all registers, or a specific name: 'pc', 'sp', 'lr', 'r0'..'r12', 'xpsr'."
        ),
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    ),
    Tool(
        name="read_variable",
        description=(
            "Read a C variable or expression by name using DWARF debug info from the ELF. "
            "Examples: 'g_pibra.srvac.state', 'g_hub_config.n_bloq', '*(uint32_t*)0x20000100'. "
            "Target must be halted."
        ),
        inputSchema={
            "type": "object",
            "properties": {"expr": {"type": "string"}},
            "required": ["expr"],
        },
    ),
    Tool(
        name="write_variable",
        description=(
            "Inject a value into a C variable at runtime without recompiling. "
            "Example: name='g_pibra.srvac.home_count', value='9'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["name", "value"],
        },
    ),
    Tool(
        name="read_memory",
        description="Read raw memory at a hex address. count = number of bytes (default 4).",
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Hex address, e.g. '0x20000000'"},
                "count": {"type": "integer", "default": 4},
            },
            "required": ["address"],
        },
    ),
    Tool(
        name="write_memory",
        description=(
            "Write bytes to a memory address (GPIO registers, variables by address, etc). "
            "hex_bytes = hex string, spaces OK: '01 00 00 00' or '01000000'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "hex_bytes": {"type": "string"},
            },
            "required": ["address", "hex_bytes"],
        },
    ),
    Tool(
        name="set_breakpoint",
        description=(
            "Set a breakpoint. location can be:\n"
            "  'App.cpp:234'          — file:line\n"
            "  'MQTT_Client_Connect'  — function name\n"
            "  '*0x08001234'          — raw address"
        ),
        inputSchema={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    ),
    Tool(
        name="remove_breakpoint",
        description="Remove a breakpoint by its number (shown in set_breakpoint output).",
        inputSchema={
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
        },
    ),
    Tool(
        name="backtrace",
        description="Get the current call stack (target must be halted).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="list_locals",
        description="List local variables and their values in the current stack frame (target must be halted).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="raw_gdb",
        description=(
            "Run any GDB console command and return its output. "
            "Use for operations not covered by other tools. "
            "Blocked: quit, detach, -gdb-exit (would kill the session)."
        ),
        inputSchema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    ),
]

_BLOCKED_GDB_CMDS = {"quit", "detach", "-gdb-exit", "disconnect"}


# ------------------------------------------------------------------
# Tool dispatch
# ------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    global _client

    # connect / disconnect don't require an existing session
    if name == "connect":
        if _client and _client.is_running:
            await asyncio.to_thread(_client.stop)
        elf = arguments.get("elf_path") or DEFAULT_ELF
        _client = GdbMiClient()
        try:
            await asyncio.to_thread(_client.start)
            r = await asyncio.to_thread(_client.connect, elf)
        except Exception as e:
            return _err(str(e))
        if not r["ok"]:
            return _err(f"GDB connect failed:\n{_raw(r['raw'])}")
        return _ok(f"Connected to ST-LINK_gdbserver:61234\nELF: {elf}\n{_raw(r['raw'])}")

    if name == "disconnect":
        if _client:
            await asyncio.to_thread(_client.stop)
            _client = None
        return _ok("GDB disconnected. CubeIDE can now reconnect.")

    # all other tools require an active session
    if _client is None or not _client.is_running:
        return _err("No active GDB session. Call connect() first.")
    g = _client

    if name == "halt":
        r = await asyncio.to_thread(g.halt)
        return _ok("Target halted.") if r["ok"] else _err(_raw(r["raw"]))

    if name == "resume":
        r = await asyncio.to_thread(g.resume)
        return _ok("Target running.") if r["ok"] else _err(_raw(r["raw"]))

    if name == "read_register":
        reg = arguments["name"]
        if reg == "all":
            r = await asyncio.to_thread(g.read_registers)
        else:
            r = await asyncio.to_thread(g.console, f"info register {reg}")
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "read_variable":
        r = await asyncio.to_thread(g.read_variable, arguments["expr"])
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "write_variable":
        # C assignment expression: GDB evaluates "name = value" and sets the variable
        expr = f"{arguments['name']} = {arguments['value']}"
        r = await asyncio.to_thread(g.read_variable, expr)
        if r["ok"]:
            return _ok(f"Set: {arguments['name']} = {arguments['value']}")
        return _err(_raw(r["raw"]))

    if name == "read_memory":
        r = await asyncio.to_thread(g.read_memory, arguments["address"], arguments.get("count", 4))
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "write_memory":
        r = await asyncio.to_thread(g.write_memory, arguments["address"], arguments["hex_bytes"])
        return _ok("Written.") if r["ok"] else _err(_raw(r["raw"]))

    if name == "set_breakpoint":
        r = await asyncio.to_thread(g.set_breakpoint, arguments["location"])
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "remove_breakpoint":
        r = await asyncio.to_thread(g.remove_breakpoint, arguments["number"])
        return _ok(f"Breakpoint {arguments['number']} removed.") if r["ok"] else _err(_raw(r["raw"]))

    if name == "backtrace":
        r = await asyncio.to_thread(g.backtrace)
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "list_locals":
        r = await asyncio.to_thread(g.list_locals)
        return _ok(_raw(r["raw"])) if r["ok"] else _err(_raw(r["raw"]))

    if name == "raw_gdb":
        cmd = arguments["command"].strip()
        if any(cmd.startswith(b) for b in _BLOCKED_GDB_CMDS):
            return _err(f"Command '{cmd}' is blocked to protect the session.")
        r = await asyncio.to_thread(g.console, cmd)
        return _ok(_raw(r["raw"]))

    return _err(f"Unknown tool: {name}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

if __name__ == "__main__":
    asyncio.run(main())
