# Resolve pip and python commands
$pip = $null
$py  = $null

if (Get-Command pip -ErrorAction SilentlyContinue)    { $pip = "pip" }
elseif (Get-Command pip3 -ErrorAction SilentlyContinue) { $pip = "pip3" }

if (Get-Command py -ErrorAction SilentlyContinue)         { $py = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue){ $py = "python3" }

if (-not $pip -and -not $py) {
    Write-Error "Python is not installed or not in PATH. Download it from https://www.python.org/downloads/ and make sure to check 'Add Python to PATH' during installation."
    exit 1
}

# Prefer py -m pip over bare pip for reliability
if ($py) { $pip = "$py -m pip" }

$packages = @("PyQt6", "pyinstaller")

foreach ($pkg in $packages) {
    Invoke-Expression "$pip show $pkg" *>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing $pkg..."
        Invoke-Expression "$pip install $pkg"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install $pkg. Aborting."
            exit 1
        }
    } else {
        Write-Host "$pkg already installed."
    }
}

Write-Host "Building..."
Invoke-Expression "$py -m PyInstaller TVSeriesTracker.spec --noconfirm"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete: dist\TVSeriesTracker.exe"
} else {
    Write-Error "Build failed."
    exit 1
}
