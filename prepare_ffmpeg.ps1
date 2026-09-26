$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Vendor = Join-Path $Root 'vendor\ffmpeg'
$Bin = Join-Path $Vendor 'bin'
$Zip = Join-Path $Vendor 'ffmpeg-9.0.2-essentials_build.zip'
$Extract = Join-Path $Vendor '_extract'
$Url = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
$ExpectedSha256 = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'

New-Item -ItemType Directory -Force -Path $Vendor | Out-Null
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

$Ffmpeg = Join-Path $Bin 'ffmpeg.exe'
$Ffprobe = Join-Path $Bin 'ffprobe.exe'
if ((Test-Path $Ffmpeg) -and (Test-Path $Ffprobe)) {
    Write-Host 'Bundled FFmpeg already prepared.' -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $Zip)) {
    Write-Host 'Downloading FFmpeg 9.0.2 Essentials...' -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
}

$ActualSha256 = (Get-FileHash -Path $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
    throw "FFmpeg archive SHA-256 mismatch. Expected $ExpectedSha256, got $ActualSha256"
}
Write-Host 'FFmpeg SHA-256 verified.' -ForegroundColor Green

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Extract | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Extract -Force

$FoundFfmpeg = Get-ChildItem -Path $Extract -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
$FoundFfprobe = Get-ChildItem -Path $Extract -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1
if (-not $FoundFfmpeg -or -not $FoundFfprobe) {
    throw 'ffmpeg.exe or ffprobe.exe was not found in the verified archive.'
}

Copy-Item $FoundFfmpeg.FullName $Ffmpeg -Force
Copy-Item $FoundFfprobe.FullName $Ffprobe -Force
Remove-Item $Extract -Recurse -Force

Write-Host 'FFmpeg prepared in vendor\ffmpeg\bin.' -ForegroundColor Green
