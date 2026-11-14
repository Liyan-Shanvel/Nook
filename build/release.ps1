# Publish the built installer as a GitHub Release, so installed Deepcus apps update themselves.
# Run after build.ps1:  powershell -NoProfile -ExecutionPolicy Bypass -File build\release.ps1 [-Notes "what changed"]
# Uses the GitHub login Git already has (Git Credential Manager). The token is never printed.
param([string]$Notes = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ver = (py -c "import version; print(version.VERSION)").Trim()
$repo = (py -c "import version; print(version.REPO)").Trim()
$tag = "v$ver"
$exe = "dist\Deepcus-Setup-$ver.exe"
if (-not (Test-Path $exe)) { throw "$exe not found - run build\build.ps1 first" }
if (git status --porcelain) { throw "uncommitted changes - commit and push first, so the release matches the code" }

# checksum next to the installer: the app refuses a download that does not match it
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$shaFile = "$exe.sha256"
[IO.File]::WriteAllText((Join-Path $root $shaFile), "$sha  Deepcus-Setup-$ver.exe`n")

# token from Git's own credential store (same login 'git push' uses)
# fed from a file through cmd: Windows PowerShell's pipe into git mangles the first line
$q = Join-Path $env:TEMP "nook-cred-query.txt"
[IO.File]::WriteAllText($q, "protocol=https`nhost=github.com`n`n", (New-Object Text.UTF8Encoding $false))
$cred = cmd /c "git credential fill < `"$q`""
Remove-Item $q -ErrorAction SilentlyContinue
$token = ($cred | Where-Object { $_ -like "password=*" }) -replace '^password=', ''
if (-not $token) { throw "no GitHub login found - run 'git push' once so Git signs in, then retry" }
$h = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "User-Agent" = "Deepcus-release" }

# tag must exist on GitHub (points at the pushed commit)
# git prints progress on stderr; Windows PowerShell + "Stop" would treat that as a failure, so check the exit code instead
$ErrorActionPreference = "Continue"
git tag -f $tag 2>&1 | Out-Null
git push origin $tag -f 2>&1 | Out-Null
$pushed = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($pushed -ne 0) { throw "could not push tag $tag" }

$body = @{ tag_name = $tag; name = "Deepcus $ver"; body = $(if ($Notes) { $Notes } else { "Deepcus $ver" }); draft = $false; prerelease = $false } | ConvertTo-Json
try {
    $rel = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$repo/releases" -Headers $h -Body $body -ContentType "application/json"
} catch {
    throw "could not create release $tag (does it already exist? bump version.py): $($_.Exception.Message)"
}
$upload = $rel.upload_url -replace '\{.*\}$', ''
foreach ($f in @($exe, $shaFile)) {
    $name = Split-Path $f -Leaf
    $type = if ($name -like "*.exe") { "application/octet-stream" } else { "text/plain" }
    Invoke-RestMethod -Method Post -Uri "$upload`?name=$name" -Headers $h -InFile (Join-Path $root $f) -ContentType $type | Out-Null
    Write-Host "uploaded $name"
    $old = $name -replace '^Deepcus-Setup-', 'Nook-Setup-'   # apps older than 1.3.0 look for this name
    Invoke-RestMethod -Method Post -Uri "$upload`?name=$old" -Headers $h -InFile (Join-Path $root $f) -ContentType $type | Out-Null
    Write-Host "uploaded $old"
}
Write-Host "Released $tag : $($rel.html_url)"
