# Build Deepcus: icon -> Deepcus.exe (PyInstaller) -> dist\Deepcus-Setup-<version>.exe (Inno Setup).
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
Write-Host "Building Deepcus $ver"
# an old build's read-only folder makes PyInstaller fail with "Access is denied"
# and Windows sometimes will not let the old folder itself be removed. So move it aside first, then clear old ones.
Get-Process FocusOS, Deepcus -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$root\dist\*" } | Stop-Process -Force
if (Test-Path dist\Deepcus) {
    attrib -r "dist\Deepcus\*" /s /d | Out-Null
    Rename-Item dist\Deepcus ("Deepcus.old-" + (Get-Date -Format "HHmmss"))
}
New-Item -ItemType Directory -Force dist | Out-Null
# Keep dist clean: older installers move to dist\old (GitHub Releases keeps every version anyway).
New-Item -ItemType Directory -Force dist\old | Out-Null
Get-ChildItem dist -File | Where-Object { $_.Name -match '-Setup-' -and $_.Name -notlike "Deepcus-Setup-$ver.exe*" } |
    Move-Item -Destination dist\old -Force
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
Get-ChildItem dist\Deepcus-Setup-*.exe | Select-Object Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}}
