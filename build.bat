@echo off

for %%P in (PyQt6 pyinstaller) do (
    pip show %%P >nul 2>&1
    if errorlevel 1 (
        echo Installing %%P...
        pip install %%P
        if errorlevel 1 (
            echo ERROR: Failed to install %%P. Aborting.
            exit /b 1
        )
    ) else (
        echo %%P already installed.
    )
)

echo Building...
pyinstaller TVSeriesTracker.spec --noconfirm

if errorlevel 1 (
    echo ERROR: Build failed.
    exit /b 1
)

echo Build complete: dist\TVSeriesTracker.exe
