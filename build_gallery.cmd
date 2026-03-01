@echo off
chcp 65001 >nul 2>&1
setlocal

echo ================================================
echo   Photo Archive Builder
echo ================================================
echo.

REM --- Determine script directory ---
set "SCRIPT_DIR=%~dp0"

REM --- Check for config.json ---
set "CONFIG=%SCRIPT_DIR%config.json"
if not exist "%CONFIG%" (
    echo [ERROR] config.json が見つかりません: %CONFIG%
    echo   config.example.json をコピーして config.json を作成してください。
    echo.
    pause
    exit /b 1
)

REM --- Check for Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python が見つかりません。Python 3.9 以上をインストールしてください。
    pause
    exit /b 1
)

echo 設定ファイル: %CONFIG%
echo.

REM --- Run the builder ---
python -m photo_archive build --config "%CONFIG%" --open

if errorlevel 1 (
    echo.
    echo [ERROR] ビルドに失敗しました。logs/errors.log を確認してください。
    echo.
    pause
    exit /b 1
)

echo.
echo ビルド完了！
echo.
pause
