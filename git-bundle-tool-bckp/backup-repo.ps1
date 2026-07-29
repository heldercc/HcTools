<#
  backup-repo.ps1  --  Plan-B backup for any git repository (git bundle).

  Creates and VERIFIES a git bundle of the CURRENT repository and saves it into a
  subfolder of your choice (arrow-key menu) under "<Desktop>\Projects Backup".
  The bundle carries branches + tags + HEAD (internal tooling refs are left out).
  File name is date-prefixed (<stamp>-<repo>.bundle) so backups sort by date.

  Usage (run in a PowerShell terminal, INSIDE any git repository):
     & "<path>\backup-repo.ps1"                  # arrow-key subfolder menu
     & "<path>\backup-repo.ps1" -OutDir "D:\X"   # fixed destination, no menu

  Restore later:
     git clone "<path>\<stamp>-<repo>.bundle" restored-repo
#>
param([string]$OutDir)

# --- Arrow-key selector (Up/Down move, Enter selects, Esc cancels) -----------
function Select-Menu {
    param([string[]]$Items, [string]$Title)
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
        $k = [Console]::ReadKey($true)
        switch ($k.Key) {
            'UpArrow'   { $sel = ($sel - 1 + $Items.Count) % $Items.Count }
            'DownArrow' { $sel = ($sel + 1) % $Items.Count }
            'Enter'     { try { [Console]::CursorVisible = $true } catch {}; return $sel }
            'Escape'    { try { [Console]::CursorVisible = $true } catch {}; return -1 }
        }
    }
}

# 1. Are we inside a git repository?
$inside = git rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -ne 0 -or $inside -ne 'true') {
    Write-Host "Not a git repository. Run this inside a repo." -ForegroundColor Red
    exit 1
}
$root  = git rev-parse --show-toplevel
$repo  = Split-Path -Leaf $root
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$file  = "$stamp-$repo.bundle"    # date PREFIX -> files sort chronologically by name

# 2. Pick the destination subfolder (menu), unless -OutDir is given
if (-not $OutDir) {
    $base = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Projects Backup'
    if (-not (Test-Path $base)) { New-Item -ItemType Directory -Force -Path $base | Out-Null }

    $subs      = @(Get-ChildItem $base -Directory | Select-Object -ExpandProperty Name | Sort-Object)
    $NEW_REPO  = "[+ new subfolder for this repo: $repo]"
    $NEW_OTHER = "[+ new subfolder (type a name)...]"
    $menu      = @($subs) + $NEW_REPO + $NEW_OTHER

    $pick = Select-Menu -Items $menu -Title "Where to store the backup of '$repo'?"
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

# 3. Create the bundle
Write-Host ""
Write-Host "Creating bundle of '$repo'  ->  $OutDir" -ForegroundColor Cyan
git bundle create "$out" --branches --tags HEAD
if ($LASTEXITCODE -ne 0) { Write-Host "Failed to create the bundle." -ForegroundColor Red; exit 1 }

# 4. Verify integrity (proves it is restorable)
Write-Host "Verifying..." -ForegroundColor Cyan
git bundle verify "$out"
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: bundle verification failed!" -ForegroundColor Red; exit 1 }

# 5. Summary
$size = "{0:N0} MB" -f ((Get-Item $out).Length / 1MB)
Write-Host ""
Write-Host "OK  ->  $out   ($size)" -ForegroundColor Green
Write-Host "Restore:  git clone `"$out`" restored-repo" -ForegroundColor DarkGray
