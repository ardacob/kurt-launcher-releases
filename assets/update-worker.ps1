param([Parameter(Mandatory=$true)][string]$Plan)
$ErrorActionPreference = 'Stop'
$updatePlan = Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$installPath = [IO.Path]::GetFullPath($updatePlan.installation)
$stagePath = [IO.Path]::GetFullPath($updatePlan.stage)
$backupPath = Join-Path $installPath ('.kurt-rollback-' + [Guid]::NewGuid().ToString('N'))
$changed = [System.Collections.Generic.List[string]]::new()
$added = [System.Collections.Generic.List[string]]::new()
$oldExited = $false
$newProcess = $null
$oldExecutable = Join-Path $installPath 'KurtLauncher.exe'
if ($updatePlan.obsolete_executable) { $oldExecutable = [IO.Path]::GetFullPath($updatePlan.obsolete_executable) }
function Remove-OwnedDirectory([string]$Directory, [string]$Parent, [string]$Prefix) {
    $resolvedDirectory = [IO.Path]::GetFullPath($Directory)
    $resolvedParent = [IO.Path]::GetFullPath($Parent)
    if ((Split-Path -Parent $resolvedDirectory) -ne $resolvedParent -or -not (Split-Path -Leaf $resolvedDirectory).StartsWith($Prefix)) { throw 'Cleanup path rejected' }
    if ((Test-Path -LiteralPath $resolvedDirectory) -and -not ((Get-Item -LiteralPath $resolvedDirectory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Remove-Item -LiteralPath $resolvedDirectory -Recurse -Force
    }
}
function Get-KurtHash([string]$File) {
    $hasher = [Security.Cryptography.SHA512]::Create()
    $stream = [IO.File]::OpenRead($File)
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
}
try {
    if ($installPath -eq [IO.Path]::GetPathRoot($installPath)) { throw 'Root installation rejected' }
    $dataRoot = [IO.Path]::GetFullPath($updatePlan.data)
    $updatesRoot = [IO.Path]::GetFullPath((Join-Path $dataRoot 'updates'))
    $healthPath = [IO.Path]::GetFullPath($updatePlan.health)
    if ((Split-Path -Parent $healthPath) -ne $updatesRoot -or [IO.Path]::GetExtension($healthPath) -ne '.ok') { throw 'Health marker path rejected' }
    if (Test-Path -LiteralPath $healthPath) { Remove-Item -LiteralPath $healthPath -Force }
    $metadata = Get-Content -LiteralPath (Join-Path $stagePath 'verified.json') -Raw | ConvertFrom-Json
    if ($updatePlan.managed) {
        $expectedApp = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'KurtLauncher\app'))
        if ($installPath -ne $expectedApp -or $metadata.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Managed installation path rejected' }
    }
    if ($updatePlan.redirect_sha512) {
        if ((Get-KurtHash (Join-Path $installPath 'KurtLauncher.exe')) -ne $updatePlan.redirect_sha512) { throw 'Installed executable changed' }
    }
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
        for ($copyAttempt=0; $copyAttempt -lt 100; $copyAttempt++) {
            try { Copy-Item -LiteralPath $inputPath -Destination $targetPath -Force; break }
            catch { if ($copyAttempt -eq 99) { throw }; Start-Sleep -Milliseconds 100 }
        }
    }
    $env:KURT_DATA_DIR = $updatePlan.data
    $healthPath = $updatePlan.health
    $newProcess = Start-Process -FilePath (Join-Path $installPath 'KurtLauncher.exe') -ArgumentList @('--update-health', ('"' + $healthPath + '"')) -WindowStyle Hidden -PassThru
    for ($attempt=0; $attempt -lt 45; $attempt++) {
        if (Test-Path -LiteralPath $healthPath) {
            'Update OK' | Set-Content -LiteralPath ($Plan + '.result')
            # Cleanup is performed only after a successful startup. Failure here
            # must never roll back an already healthy application.
            try {
                if ($updatePlan.managed) {
                    $installedExe = Join-Path $installPath 'KurtLauncher.exe'
                    $installationState = @{format=1; product='KurtLauncher'; version=$metadata.version; sha512=(Get-KurtHash $installedExe)}
                    $statePath = Join-Path (Split-Path -Parent $installPath) 'installation.json'
                    [IO.File]::WriteAllText($statePath, ($installationState | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
                    if ($updatePlan.create_shortcut) {
                        $desktop = [Environment]::GetFolderPath('Desktop')
                        $shell = New-Object -ComObject WScript.Shell
                        $shortcut = $shell.CreateShortcut((Join-Path $desktop 'Kurt Launcher.lnk'))
                        $shortcut.TargetPath = $installedExe
                        $shortcut.WorkingDirectory = $installPath
                        $shortcut.IconLocation = $installedExe + ',0'
                        $shortcut.Save()
                    }
                }
                if ($updatePlan.obsolete_executable) {
                    $obsolete = [IO.Path]::GetFullPath($updatePlan.obsolete_executable)
                    $newExe = [IO.Path]::GetFullPath((Join-Path $installPath 'KurtLauncher.exe'))
                    $dataRoot = [IO.Path]::GetFullPath($updatePlan.data)
                    if ($obsolete -ne $newExe -and (Split-Path -Leaf $obsolete) -ieq 'KurtLauncher.exe' -and -not $obsolete.StartsWith($dataRoot + '\',[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $obsolete)) {
                        if ((Get-KurtHash $obsolete) -eq $updatePlan.obsolete_sha512) { Remove-Item -LiteralPath $obsolete -Force }
                    }
                }
                Remove-OwnedDirectory $backupPath $installPath '.kurt-rollback-'
                $updatesRoot = [IO.Path]::GetFullPath((Join-Path $updatePlan.data 'updates'))
                if ((Split-Path -Parent $stagePath) -eq $updatesRoot) { Remove-OwnedDirectory $stagePath $updatesRoot 'verified-' }
            } catch { ('Cleanup deferred: ' + $_.Exception.Message) | Add-Content -LiteralPath ($Plan + '.result') }
            exit 0
        }
        if ($newProcess.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $newProcess.HasExited) { & (Join-Path $env:SystemRoot 'System32\taskkill.exe') /PID $newProcess.Id /T /F | Out-Null; $newProcess.WaitForExit() }
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
    try {
        $failed = @{version=$metadata.version; message=$failureText}
        $failurePath = Join-Path $updatePlan.data 'updates\last-failure.json'
        [IO.File]::WriteAllText($failurePath, ($failed | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    } catch { }
    if ($oldExited -and (Test-Path -LiteralPath $oldExecutable)) { Start-Process -FilePath $oldExecutable -ArgumentList '--no-self-install' -WindowStyle Hidden }
    exit 1
}
