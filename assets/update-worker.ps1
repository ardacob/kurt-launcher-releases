param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
$updatePlan = Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$installPath = [IO.Path]::GetFullPath($updatePlan.installation)
$stagePath = [IO.Path]::GetFullPath($updatePlan.stage)
$backupPath = Join-Path $installPath ('.kurt-rollback-' + [Guid]::NewGuid().ToString('N'))
$changed = [System.Collections.Generic.List[string]]::new()
$added = [System.Collections.Generic.List[string]]::new()
$oldExited = $false
try {
    if ($installPath -eq [IO.Path]::GetPathRoot($installPath)) { throw 'Root installation rejected' }
    $metadata = Get-Content -LiteralPath (Join-Path $stagePath 'verified.json') -Raw | ConvertFrom-Json
    $allowed = @('KurtLauncher.exe','src','assets','third-party','README.md','DOGRULAMA.txt','requirements.txt','build.ps1','KurtLauncher.spec','Baslat.cmd','_internal','tests','sign_release.py','GUNCELLEME-YAYINLAMA.md')
    foreach ($entry in $metadata.files.PSObject.Properties) {
        $rel = $entry.Name.Replace('/', '\')
        $top = $rel.Split('\')[0]
        if ($top -notin $allowed -or $rel.Split('\') -contains '..' -or [IO.Path]::IsPathRooted($rel) -or $rel.Contains(':')) { throw 'Unsafe update path' }
        $inputPath = [IO.Path]::GetFullPath((Join-Path $stagePath $rel))
        $targetPath = [IO.Path]::GetFullPath((Join-Path $installPath $rel))
        if (-not $inputPath.StartsWith($stagePath + '\',[StringComparison]::OrdinalIgnoreCase) -or -not $targetPath.StartsWith($installPath + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped update directory' }
        $hasher = [Security.Cryptography.SHA512]::Create()
        $hashStream = [IO.File]::OpenRead($inputPath)
        try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($hashStream)).Replace('-','').ToLowerInvariant() }
        finally { $hashStream.Dispose(); $hasher.Dispose() }
        if ($actualHash -ne $entry.Value.sha512) { throw 'Hash mismatch' }
        if ((Test-Path -LiteralPath $targetPath) -and ((Get-Item -LiteralPath $targetPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse target rejected' }
        # Refuse junction/symlink parents in the destination.
        $ancestor = Split-Path -Parent $targetPath
        while ($ancestor.Length -ge $installPath.Length) {
            if ((Test-Path -LiteralPath $ancestor) -and ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Reparse destination rejected' }
            $ancestor = Split-Path -Parent $ancestor
        }
    }
    $oldProcess = Get-Process -Id $updatePlan.pid -ErrorAction SilentlyContinue
    if ($oldProcess) {
        if (-not $oldProcess.WaitForExit(120000)) { throw 'Launcher did not close' }
    }
    $oldExited = $true
    New-Item -ItemType Directory -Path $backupPath | Out-Null
    foreach ($entry in $metadata.files.PSObject.Properties) {
        $rel = $entry.Name.Replace('/', '\')
        $targetPath = Join-Path $installPath $rel
        $inputPath = Join-Path $stagePath $rel
        if (Test-Path -LiteralPath $targetPath) {
            $savedPath = Join-Path $backupPath $rel
            New-Item -ItemType Directory -Path (Split-Path -Parent $savedPath) -Force | Out-Null
            Copy-Item -LiteralPath $targetPath -Destination $savedPath
            $changed.Add($rel)
        } else { $added.Add($rel) }
        New-Item -ItemType Directory -Path (Split-Path -Parent $targetPath) -Force | Out-Null
        Copy-Item -LiteralPath $inputPath -Destination $targetPath -Force
    }
    $env:KURT_DATA_DIR = $updatePlan.data
    $healthPath = $updatePlan.health
    $newProcess = Start-Process -FilePath (Join-Path $installPath 'KurtLauncher.exe') -ArgumentList @('--update-health', ('"' + $healthPath + '"')) -WindowStyle Hidden -PassThru
    for ($attempt=0; $attempt -lt 45; $attempt++) {
        if (Test-Path -LiteralPath $healthPath) { 'Update OK' | Set-Content -LiteralPath ($Plan + '.result'); exit 0 }
        if ($newProcess.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $newProcess.HasExited) { $newProcess.Kill(); $newProcess.WaitForExit() }
    throw 'New launcher failed its startup check'
} catch {
    $failureText = $_.Exception.Message
    foreach ($rel in $changed) {
        Copy-Item -LiteralPath (Join-Path $backupPath $rel) -Destination (Join-Path $installPath $rel) -Force
    }
    foreach ($rel in $added) {
        $addedPath = [IO.Path]::GetFullPath((Join-Path $installPath $rel))
        if ($addedPath.StartsWith($installPath + '\',[StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $addedPath -Force -ErrorAction SilentlyContinue }
    }
    ('Update failed; original restored: ' + $failureText) | Set-Content -LiteralPath ($Plan + '.result')
    if ($oldExited) { Start-Process -FilePath (Join-Path $installPath 'KurtLauncher.exe') -WindowStyle Hidden }
    exit 1
}
