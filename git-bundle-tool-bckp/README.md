# git-bundle-tool-bckp

> **One command, verified backup of any git repository — as a single portable file.**

A small PowerShell tool that creates and verifies a [git bundle](https://git-scm.com/docs/git-bundle)
of the repository you're in, and drops it into a subfolder of your choice under
`<Desktop>\Projects Backup`. A bundle is a single file holding real git history — copy it to a USB
drive, OneDrive, or anywhere, and clone straight from it if you ever need to restore.

Handy as a plan-B when your git server is down, or before a risky operation.

---

## What it does

- Bundles **branches + tags + HEAD** — skips internal tooling refs (`refs/stash`, worktrees, etc.).
- **Verifies** the bundle right after creating it (`git bundle verify`), so you know it's restorable.
- Names the file `<yyyy-MM-dd_HHmm>-<repo>.bundle` — **date-prefixed**, so backups sort by date.
- Interactive **arrow-key menu** to pick — or create — the destination subfolder, so you can reuse
  the same layout across projects.

## Usage

Run in a PowerShell terminal, **inside any git repository**:

```powershell
& "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1"                 # arrow-key menu
& "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1" -OutDir "D:\X"  # fixed destination
```

Optional shortcut — add to your `$PROFILE`:

```powershell
function backup-repo { & "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1" @args }
```

Then just run `backup-repo` from any repo.

## Restore

```powershell
git clone "<path>\<stamp>-<repo>.bundle" restored-repo
```

## Notes

- Run it in a real terminal (not the PowerShell ISE — the menu reads keys directly).
- If the execution policy blocks it: `powershell -ExecutionPolicy Bypass -File "...\backup-repo.ps1"`.
- Windows PowerShell 5.1+ or PowerShell 7+.
