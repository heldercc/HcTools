## @file test_live.py
# @brief Integration test — runs against real hardware with ST-LINK_gdbserver active.
#
# @author  Hélder Costa <heldermoreiracosta@gmail.com>
# @date    2026-06-25
# @license MIT
# @copyright Copyright (c) 2026 Hélder Costa
#
"""Live connection test — runs against the actual ST-LINK_gdbserver."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from gdb_mi import GdbMiClient

ELF = str(Path(__file__).parent.parent.parent / "Debug" / "SS-HUB-FW.elf")

print("=== stm32-mcp live test ===")
print(f"ELF: {ELF}")

g = GdbMiClient()
g.start()
print("[1] GDB started")

r = g.connect(ELF)
print(f"[2] connect: ok={r['ok']}")
for line in r["raw"]:
    print(f"    {line}")

if not r["ok"]:
    print("ABORT: could not connect to ST-LINK_gdbserver:61234")
    g.stop()
    sys.exit(1)

print()
print("[3] halt target...")
r = g.halt()
print(f"    ok={r['ok']}")
for line in r["raw"]:
    print(f"    {line}")

print()
print("[4] read PC register...")
r = g.console("info register pc")
for line in r["raw"]:
    print(f"    {line}")

print()
print("[5] read PIBRA struct fields...")
for expr in [
    "PIBRA.bloqueadores[0].state",
    "PIBRA.bloqueadores[0].absolutePos",
    "PIBRA.bloqueadores[0].speed",
    "PIBRA.desviadores[0].state",
    "PIBRA.desviadores[0].speed",
    "PIBRA.desviadores[0].absolutePos",
]:
    r = g.read_variable(expr)
    val = next((l for l in r["raw"] if "^done" in l or "^error" in l), str(r["raw"]))
    ok = "OK" if "^done" in val else "FAIL"
    print(f"    [{ok}] {expr} => {val}")

print()
print("[6] resume target...")
r = g.resume()
print(f"    ok={r['ok']}")

print()
print("[7] disconnect GDB")
g.stop()
print("Done.")
