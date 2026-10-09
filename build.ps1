# Build SuperTerm.exe — ONE portable file, nothing to install.
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = $PSScriptRoot

function Run($what, $block) {
    & $block
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

$version = (Select-String -Path app.py -Pattern '^APP_VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building SuperTerm $version (single exe)"

Run "icon" { python make_icon.py }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
Run "PyInstaller" {
    python -m PyInstaller --noconfirm --clean --windowed --onefile `
        --name SuperTerm `
        --icon "$root\assets\icon.ico" `
        --add-data "$root\assets;assets" `
        --hidden-import serial.tools.list_ports_windows `
        --exclude-module tkinter `
        --exclude-module pytest `
        --distpath "$root\dist" --workpath "$root\build_tmp" --specpath "$root\build_tmp" `
        "$root\app.py"
}
Remove-Item -Recurse -Force "$root\build_tmp" -ErrorAction SilentlyContinue
Write-Host "Done: $root\dist\SuperTerm.exe"
