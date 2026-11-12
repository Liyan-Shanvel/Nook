# Publish the built installer as a GitHub Release, so installed Nook apps update themselves.
# Run after build.ps1:  powershell -NoProfile -ExecutionPolicy Bypass -File build\release.ps1 [-Notes "what changed"]
# Uses the GitHub login Git already has (Git Credential Manager). The token is never printed.
param([string]$Notes = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ver = (py -c "import version; print(version.VERSION)").Trim()
$repo = (py -c "import version; print(version.REPO)").Trim()
$tag = "v$ver"
$exe = "dist\Nook-Setup-$ver.exe"
if (-not (Test-Path $exe)) { throw "$exe not found - run build\build.ps1 first" }
if (git status --porcelain) { throw "uncommitted changes - commit and push first, so the release matches the code" }

# checksum next to the installer: the app refuses a download that does not match it
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$shaFile = "$exe.sha256"
[IO.File]::WriteAllText((Join-Path $root $shaFile), "$sha  Nook-Setup-$ver.exe`n")

# token from Git's own credential store (same login 'git push' uses)
$cred = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
$token = ($cred | Where-Object { $_ -like "password=*" }) -replace '^password=', ''
if (-not $token) { throw "no GitHub login found - run 'git push' once so Git signs in, then retry" }
$h = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "User-Agent" = "Nook-release" }

# tag must exist on GitHub (points at the pushed commit)
git tag -f $tag | Out-Null
git push origin $tag -f 2>&1 | Out-Null

$body = @{ tag_name = $tag; name = "Nook $ver"; body = $(if ($Notes) { $Notes } else { "Nook $ver" }); draft = $false; prerelease = $false } | ConvertTo-Json
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
}
Write-Host "Released $tag : $($rel.html_url)"
