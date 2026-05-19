$packages = @("PyQt6", "pyinstaller")

foreach ($pkg in $packages) {
    pip show $pkg *>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing $pkg..."
        pip install $pkg
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install $pkg. Aborting."
            exit 1
        }
    } else {
        Write-Host "$pkg already installed."
    }
}

Write-Host "Building..."
pyinstaller TVSeriesTracker.spec --noconfirm

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete: dist\TVSeriesTracker.exe"
} else {
    Write-Error "Build failed."
    exit 1
}
