# HcTools

> Open-source tools for embedded systems development.  
> by **Hélder Costa** — [heldermoreiracosta@gmail.com](mailto:heldermoreiracosta@gmail.com)

These tools were born out of real projects and extracted here because nothing quite like them existed. They are minimal, focused, and do one thing well.

---

## Tools

### [stm32-mcp](./stm32-mcp/) — Live STM32 debug bridge for Claude Code

> **Give Claude Code live, read/write access to a running STM32 firmware — no printf, no recompile.**

An MCP (Model Context Protocol) server that connects [Claude Code](https://claude.ai/code) to a live STM32 debug session via `arm-none-eabi-gdb` in MI mode.

While the firmware runs on the MCU, Claude can:
- Read any C variable or struct by name (via DWARF debug symbols)
- Inspect state machines and buffers in real time
- Inject values without recompiling
- Set breakpoints and capture call stacks
- Read/write raw memory (GPIO registers, peripheral state, etc.)

```
Claude Code → MCP (stdio) → GDB/MI → ST-LINK gdbserver → STM32
```

Works with ST-LINK, J-Link, OpenOCD — any probe that exposes a gdbserver over TCP. Any ARM Cortex-M project with a Debug-build ELF.

→ **[Full documentation and setup guide](./stm32-mcp/README.md)**

---

### [git-bundle-tool-bckp](./git-bundle-tool-bckp/) — One-command verified repo backup

> **Back up any git repository to a single verified file — a plan-B for when the server is down.**

A PowerShell tool that creates and verifies a `git bundle` of the current repo (branches + tags + HEAD) and files it under `Desktop\Projects Backup` (date-prefixed names, so they sort by date), with an interactive arrow-key menu to pick the destination. A bundle is portable, restorable git history in a single file — clone straight from it.

→ **[Documentation](./git-bundle-tool-bckp/README.md)**

---

## License

MIT — use freely, attribution appreciated.
