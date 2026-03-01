@echo off
chcp 65001 >nul 2>&1
setlocal

REM ============================================================
REM  PhotoArchive_RunHere.cmd
REM  このファイルを写真フォルダに置いてダブルクリックすると、
REM  そのフォルダを input_root としてギャラリーを生成します。
REM  config.json が無くても動きます（出力先: _gallery/ フォルダ）。
REM
REM  ※ setup.cmd を先に実行すると、TOOL_HOME が自動設定された
REM     このファイルが生成されます。
REM ============================================================

REM --- ★ ここを編集: ツール本体のフォルダパス ---
REM    setup.cmd で生成した場合は自動設定済みです
set "TOOL_HOME=C:\tools\photo-archive"

REM ============================================================
REM  以下は編集不要
REM ============================================================

set "PHOTO_DIR=%~dp0"
if "%PHOTO_DIR:~-1%"=="\" set "PHOTO_DIR=%PHOTO_DIR:~0,-1%"

echo ================================================
echo   Photo Archive
echo ================================================
echo.
echo 写真フォルダ: %PHOTO_DIR%
echo.

REM --- Python を探す（.venv 優先 → システム Python） ---
set "PYTHON=%TOOL_HOME%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python が見つかりません。
        echo   %TOOL_HOME%\setup.cmd を先に実行してください。
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

REM --- config.json を探す（写真フォルダ優先、無くてもOK） ---
set "CONFIG_OPT="
if exist "%PHOTO_DIR%\config.json" (
    set "CONFIG_OPT=--config "%PHOTO_DIR%\config.json""
    echo 設定: %PHOTO_DIR%\config.json
) else if exist "%TOOL_HOME%\config.json" (
    set "CONFIG_OPT=--config "%TOOL_HOME%\config.json""
    echo 設定: %TOOL_HOME%\config.json
) else (
    echo 設定: デフォルト（出力先: %PHOTO_DIR%\_gallery\）
)
echo.

REM --- ビルド実行 ---
cd /d "%TOOL_HOME%"
"%PYTHON%" -m photo_archive build %CONFIG_OPT% --input "%PHOTO_DIR%" --open

if errorlevel 1 (
    echo.
    echo [ERROR] ビルドに失敗しました。
    pause
    exit /b 1
)

echo.
echo ビルド完了！
pause
