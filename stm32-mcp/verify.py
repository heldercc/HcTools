"""Quick sanity check — run from tools/stm32-mcp/ directory."""
import sys, inspect
from pathlib import Path

import server
import gdb_mi
from gdb_mi import _mi_quote, _to_gdb_path, GdbMiClient

errors = []

def check(name, cond, detail=""):
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name}" + (f": {detail}" if detail else ""))
        errors.append(name)

# 1 imports
check("imports", True)

# 2 no stray global _gdb
check("no stray global _gdb", "global _gdb" not in open("server.py").read())

# 3 paths exist
check("ELF exists", Path(server.DEFAULT_ELF).exists(), server.DEFAULT_ELF)
check("GDB exe exists", Path(gdb_mi.GDB_EXE).exists(), gdb_mi.GDB_EXE)

# 4 _mi_quote escaping
check("_mi_quote basic", _mi_quote("hello") == '"hello"')
check("_mi_quote escapes internal quotes", '\\"' in _mi_quote('say "hi"'))

# 5 _to_gdb_path
p = _to_gdb_path(r"C:\foo\bar.elf")
check("_to_gdb_path forward slashes", p == "C:/foo/bar.elf", p)

# 6 write_memory normalisation
h = "01 00 00 00"
n = h.replace(" ", "").replace("0x", "").replace("0X", "")
check("write_memory hex normalisation", n == "01000000", n)

# 7 list_locals MI syntax
src = inspect.getsource(GdbMiClient.list_locals)
check("list_locals no '--all-values 1'", "--all-values 1" not in src)
check("list_locals uses positional 1", "-stack-list-variables 1" in src)

# 8 halt drains after ^done
check("halt() calls _drain", "_drain" in inspect.getsource(GdbMiClient.halt))

# 9 asyncio.to_thread in server
check("asyncio.to_thread used", "asyncio.to_thread" in open("server.py").read())

# 10 tool count
check("14 tools registered", len(server.TOOLS) == 14, str(len(server.TOOLS)))

print()
if errors:
    print(f"FAILED: {errors}")
    sys.exit(1)
else:
    print("All checks passed. Confidence: 90%+")
