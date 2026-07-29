<#
  backup-repo.ps1  --  Plan-B backup for any git repository (git bundle).
  Copyright (c) 2026 Hélder Costa

  Pick a repository (arrow-key menu) and it creates + VERIFIES a git bundle of it,
  saved into a subfolder of your choice under "<Desktop>\Projects Backup".
  Run it from ANYWHERE: the menu lists the current repo (if any), the git repos
  found under C:\GitHub, and a "Browse..." option for anything else.
  Bundle = branches + tags + HEAD; file name is date-prefixed so backups sort by date.

  Usage:
     & "<path>\backup-repo.ps1"                    # menus: repo + destination
     & "<path>\backup-repo.ps1" -RepoPath "C:\X"   # skip the repo menu
     & "<path>\backup-repo.ps1" -OutDir  "D:\Y"    # skip the destination menu

  Restore later:
     git clone "<path>\<stamp>-<repo>.bundle" restored-repo
#>
param([string]$OutDir, [string]$RepoPath)

$SCAN_BASE = 'C:\GitHub'   # folder scanned (2 levels deep) for repositories

# --- Arrow-key selector (Up/Down move, Enter selects, Esc cancels) -----------
function Select-Menu {
    param([string[]]$Items, [string]$Title, [string[]]$Details)
    if ($Items.Count -eq 0) { return -1 }
    $sel = 0
    Write-Host ""
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "  (Up/Down arrows | Enter to select | Esc to cancel)" -ForegroundColor DarkGray
    $top = [Console]::CursorTop
    try { [Console]::CursorVisible = $false } catch {}
    while ($true) {
        try { [Console]::SetCursorPosition(0, $top) } catch {}
        for ($i = 0; $i -lt $Items.Count; $i++) {
            $line = ("    " + $Items[$i]).PadRight(72)
            if ($i -eq $sel) { Write-Host $line -ForegroundColor Black -BackgroundColor Green }
            else             { Write-Host $line }
        }
        # Live hint: full path of the highlighted item (tail-truncated to fit the window).
        $hint = ""
        if ($Details -and $sel -lt $Details.Count -and $Details[$sel]) {
            $maxw = 100; try { $maxw = [Console]::WindowWidth - 6 } catch {}
            $d = [string]$Details[$sel]
            if ($d.Length -gt $maxw) { $d = "..." + $d.Substring($d.Length - $maxw + 3) }
            $hint = "  -> " + $d
        }
        $pad = 100; try { $pad = [Console]::WindowWidth - 1 } catch {}
        Write-Host $hint.PadRight($pad) -ForegroundColor DarkGray
        $k = [Console]::ReadKey($true)
        switch ($k.Key) {
            'UpArrow'   { $sel = ($sel - 1 + $Items.Count) % $Items.Count }
            'DownArrow' { $sel = ($sel + 1) % $Items.Count }
            'Enter'     { try { [Console]::CursorVisible = $true } catch {}; return $sel }
            'Escape'    { try { [Console]::CursorVisible = $true } catch {}; return -1 }
        }
    }
}

function Resolve-RepoRoot([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return $null }
    $r = git -C "$path" rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $r) { return $r } else { return $null }
}

# 1. Choose the SOURCE repository -----------------------------------------------
$root = $null
if ($RepoPath) {
    $root = Resolve-RepoRoot $RepoPath
    if (-not $root) { Write-Host "'$RepoPath' is not a git repository." -ForegroundColor Red; exit 1 }
} else {
    $script:repos = New-Object System.Collections.ArrayList
    $script:seen  = @{}
    function Add-Repo($label, $path) {
        $key = ([string]$path).ToLower()
        if (-not $script:seen.ContainsKey($key)) {
            $script:seen[$key] = $true
            [void]$script:repos.Add([pscustomobject]@{ Label = $label; Path = $path })
        }
    }
    # current folder, if it's inside a repo
    $cur = Resolve-RepoRoot (Get-Location).Path
    if ($cur) { Add-Repo "This repo:  $(Split-Path -Leaf $cur)" $cur }
    # scan the base folder (2 levels) for git repos
    if (Test-Path $SCAN_BASE) {
        foreach ($l1 in Get-ChildItem $SCAN_BASE -Directory -ErrorAction SilentlyContinue) {
            if (Test-Path (Join-Path $l1.FullName '.git')) { Add-Repo $l1.Name $l1.FullName }
            else {
                foreach ($l2 in Get-ChildItem $l1.FullName -Directory -ErrorAction SilentlyContinue) {
                    if (Test-Path (Join-Path $l2.FullName '.git')) { Add-Repo "$($l1.Name)\$($l2.Name)" $l2.FullName }
                }
            }
        }
    }
    $BROWSE = "[ Browse for another folder... ]"
    $menu = @($script:repos | ForEach-Object { $_.Label }) + $BROWSE
    $det  = @($script:repos | ForEach-Object { $_.Path }) + "(opens a Windows folder picker)"
    $pick = Select-Menu -Items $menu -Title "Which repository to back up?" -Details $det
    if ($pick -lt 0) { Write-Host "Cancelled." -ForegroundColor Yellow; exit 0 }
    if ($menu[$pick] -eq $BROWSE) {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Pick the git repository to back up"
        if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            Write-Host "Cancelled." -ForegroundColor Yellow; exit 0
        }
        $root = Resolve-RepoRoot $dlg.SelectedPath
        if (-not $root) { Write-Host "'$($dlg.SelectedPath)' is not a git repository." -ForegroundColor Red; exit 1 }
    } else {
        $root = $script:repos[$pick].Path
    }
}
$repo  = Split-Path -Leaf $root
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$file  = "$stamp-$repo.bundle"

# 2. Choose the DESTINATION subfolder -------------------------------------------
if (-not $OutDir) {
    $base = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Projects Backup'
    if (-not (Test-Path $base)) { New-Item -ItemType Directory -Force -Path $base | Out-Null }
    $subs      = @(Get-ChildItem $base -Directory | Select-Object -ExpandProperty Name | Sort-Object)
    $NEW_REPO  = "[+ new subfolder for this repo: $repo]"
    $NEW_OTHER = "[+ new subfolder (type a name)...]"
    $menu      = @($subs) + $NEW_REPO + $NEW_OTHER
    $det       = @($subs | ForEach-Object { Join-Path $base $_ }) + (Join-Path $base $repo) + "(you'll type a name under $base)"
    $pick = Select-Menu -Items $menu -Title "Where to store the backup of '$repo'?" -Details $det
    if ($pick -lt 0) { Write-Host "Cancelled." -ForegroundColor Yellow; exit 0 }
    $choice = $menu[$pick]
    if     ($choice -eq $NEW_REPO)  { $sub = $repo }
    elseif ($choice -eq $NEW_OTHER) { $sub = (Read-Host "New subfolder name") }
    else                            { $sub = $choice }
    if ([string]::IsNullOrWhiteSpace($sub)) { Write-Host "Empty name. Cancelled." -ForegroundColor Yellow; exit 0 }
    $OutDir = Join-Path $base $sub
}
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
$out = Join-Path $OutDir $file

# 3. Create + verify the bundle -------------------------------------------------
Write-Host ""
Write-Host "Creating bundle of '$repo'  ->  $OutDir" -ForegroundColor Cyan
git -C "$root" bundle create "$out" --branches --tags HEAD
if ($LASTEXITCODE -ne 0) { Write-Host "Failed to create the bundle." -ForegroundColor Red; exit 1 }
Write-Host "Verifying..." -ForegroundColor Cyan
git -C "$root" bundle verify "$out"
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: bundle verification failed!" -ForegroundColor Red; exit 1 }

# 4. Summary --------------------------------------------------------------------
$size = "{0:N0} MB" -f ((Get-Item $out).Length / 1MB)
Write-Host ""
Write-Host "OK  ->  $out   ($size)" -ForegroundColor Green
Write-Host "Restore:  git clone `"$out`" restored-repo" -ForegroundColor DarkGray
