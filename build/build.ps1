# Build Nook: icon -> Nook.exe (PyInstaller) -> dist\Nook-Setup-<version>.exe (Inno Setup).
# Run from anywhere: powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Apps\FocusOS\build\build.ps1"
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
py -m pytest -q tests
if ($LASTEXITCODE -ne 0) { throw "tests failed - not building" }
py build\make_icon.py
# one version for everything: version.py -> exe file info + installer
$ver = (py -c "import version; print(version.VERSION)").Trim()
if ($ver -notmatch '^\d+\.\d+\.\d+$') { throw "bad version in version.py: $ver" }
$v4 = ($ver.Split('.') + '0') -join ', '
$vi = [IO.File]::ReadAllText("$root\build\version.txt")
$vi = $vi -replace 'filevers=\([^)]*\)', "filevers=($v4)" -replace 'prodvers=\([^)]*\)', "prodvers=($v4)"
$vi = $vi -replace "('FileVersion', ')[^']*'", "`${1}$ver'" -replace "('ProductVersion', ')[^']*'", "`${1}$ver'"
[IO.File]::WriteAllText("$root\build\version.txt", $vi, (New-Object Text.UTF8Encoding $false))
Write-Host "Building Nook $ver"
# an old build's read-only folder makes PyInstaller fail with "Access is denied"
# and Windows sometimes will not let the old folder itself be removed. So move it aside first, then clear old ones.
Get-Process FocusOS, Nook -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$root\dist\*" } | Stop-Process -Force
if (Test-Path dist\Nook) {
    attrib -r "dist\Nook\*" /s /d | Out-Null
    Rename-Item dist\Nook ("Nook.old-" + (Get-Date -Format "HHmmss"))
}
New-Item -ItemType Directory -Force dist | Out-Null
Get-ChildItem dist -Directory -Filter "*.old-*" | ForEach-Object {
    attrib -r "$($_.FullName)\*" /s /d | Out-Null
    Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
py -m PyInstaller build\focusos.spec --noconfirm --workpath .build-tmp --distpath dist
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup not found: winget install JRSoftware.InnoSetup --scope user" }
& $iscc /Q "/DAppVersion=$ver" build\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Get-ChildItem dist\Nook-Setup-*.exe | Select-Object Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}}
