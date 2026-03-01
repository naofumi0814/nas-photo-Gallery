@echo off
chcp 65001 >nul 2>&1
setlocal

REM ============================================================
REM  PhotoArchive_RunHere.cmd
REM  このファイルを写真フォルダに置いてダブルクリックすると、
REM  そのフォルダを input_root としてギャラリーを生成します。
REM ============================================================

REM --- ★ ここを編集: ツール本体のフォルダパス ---
REM    photo_archive/ や .venv/ が置いてあるフォルダを指定してください
REM    末尾の \ は不要です
set "TOOL_HOME=C:\tools\photo-archive"

REM --- ★ ここを編集（任意）: .venv の Python パス ---
REM    .venv を使わない場合は python に変更してください
set "PYTHON=%TOOL_HOME%\.venv\Scripts\python.exe"

REM ============================================================
REM  以下は編集不要
REM ============================================================

echo ================================================
echo   Photo Archive — RunHere
echo ================================================
echo.

REM --- このcmdが置かれたフォルダ = 写真フォルダ = input_root ---
set "PHOTO_DIR=%~dp0"
REM 末尾の \ を除去
if "%PHOTO_DIR:~-1%"=="\" set "PHOTO_DIR=%PHOTO_DIR:~0,-1%"

echo 写真フォルダ: %PHOTO_DIR%
echo ツール本体:   %TOOL_HOME%
echo.

REM --- Python の存在確認 ---
if not exist "%PYTHON%" (
    echo [ERROR] Python が見つかりません: %PYTHON%
    echo   TOOL_HOME と PYTHON パスを確認してください。
    echo.
    pause
    exit /b 1
)

REM --- config.json の探索（優先順位: 写真フォルダ ＞ ツール本体フォルダ） ---
set "CONFIG="
if exist "%PHOTO_DIR%\config.json" (
    set "CONFIG=%PHOTO_DIR%\config.json"
    echo 設定ファイル: %PHOTO_DIR%\config.json （写真フォルダ内）
) else if exist "%TOOL_HOME%\config.json" (
    set "CONFIG=%TOOL_HOME%\config.json"
    echo 設定ファイル: %TOOL_HOME%\config.json （ツール本体フォルダ）
) else (
    echo [ERROR] config.json が見つかりません。
    echo   以下のいずれかの場所に config.json を作成してください:
    echo     1. %PHOTO_DIR%\config.json
    echo     2. %TOOL_HOME%\config.json
    echo   config.example.json をコピーして編集してください。
    echo.
    pause
    exit /b 1
)
echo.

REM --- ビルド実行 ---
REM   --input で写真フォルダを強制指定（config の input_root を上書き）
cd /d "%TOOL_HOME%"
"%PYTHON%" -m photo_archive build --config "%CONFIG%" --input "%PHOTO_DIR%" --open

if errorlevel 1 (
    echo.
    echo [ERROR] ビルドに失敗しました。ログを確認してください。
    echo.
    pause
    exit /b 1
)

echo.
echo ビルド完了！
echo.
pause
