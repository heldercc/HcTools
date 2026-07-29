# git-bundle-tool-bckp

> **One command, verified backup of any git repository — as a single portable file.**

A small PowerShell tool that creates and verifies a [git bundle](https://git-scm.com/docs/git-bundle)
of a git repository — **run it from anywhere and pick the repo** — and drops it into a subfolder of
your choice under `<Desktop>\Projects Backup`. A bundle is a single file holding real git history —
copy it to a USB drive, OneDrive, or anywhere, and clone straight from it if you ever need to restore.

Handy as a plan-B when your git server is down, or before a risky operation.

---

## What it does

- Bundles **branches + tags + HEAD** — skips internal tooling refs (`refs/stash`, worktrees, etc.).
- **Verifies** the bundle right after creating it (`git bundle verify`), so you know it's restorable.
- Names the file `<yyyy-MM-dd_HHmm>-<repo>.bundle` — **date-prefixed**, so backups sort by date.
- **Pick the repo from anywhere:** an arrow-key menu lists the current repo, the repos found under
  `C:\GitHub`, and a *Browse…* option (Windows folder picker) for anything else.
- Then an arrow-key menu to pick — or create — the **destination** subfolder, reused across projects.

## Usage

Run it from anywhere: you pick the **repo**, then the **destination**. (Inside a repo, that repo is the first menu option.)

### Easy — `run.bat` (one click)

Handles the execution policy for you — nothing to configure.

- **From a terminal (anywhere)** — you'll pick the repo from the menu:
  ```bat
  C:\GitHub\HcTools\git-bundle-tool-bckp\run.bat
  ```
- Or **copy `run.bat` into a repo folder and double-click it** — that repo shows up first in the menu. The window stays open so you can read the result.

### Manual — PowerShell

```powershell
& "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1"                     # repo + destination menus
& "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1" -RepoPath "C:\X"    # skip the repo menu
& "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1" -OutDir  "D:\Y"     # skip the destination menu
```

Optional shortcut — add to your `$PROFILE`, then just run `backup-repo` from any repo:

```powershell
function backup-repo { & "C:\GitHub\HcTools\git-bundle-tool-bckp\backup-repo.ps1" @args }
```

## Restore

```powershell
git clone "<path>\<stamp>-<repo>.bundle" restored-repo
```

## Notes

- Run it in a real terminal (not the PowerShell ISE — the menu reads keys directly).
- If the execution policy blocks it: `powershell -ExecutionPolicy Bypass -File "...\backup-repo.ps1"`.
- Windows PowerShell 5.1+ or PowerShell 7+.
