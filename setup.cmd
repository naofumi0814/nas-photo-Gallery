@echo off
chcp 65001 >nul 2>&1
setlocal

REM ============================================================
REM  Photo Archive — 初回セットアップ
REM  このファイルをダブルクリックすると:
REM    1. Python 仮想環境（.venv）を作成
REM    2. Pillow をインストール
REM    3. PhotoArchive_RunHere.cmd を生成
REM  生成された cmd を写真フォルダに置いてダブルクリックするだけで
REM  ギャラリーが生成されます。
REM ============================================================

echo ================================================
echo   Photo Archive — セットアップ
echo ================================================
echo.

REM --- このスクリプトの場所 = ツール本体フォルダ ---
set "TOOL_HOME=%~dp0"
if "%TOOL_HOME:~-1%"=="\" set "TOOL_HOME=%TOOL_HOME:~0,-1%"

echo ツール本体: %TOOL_HOME%
echo.

REM --- Python の確認 ---
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python が見つかりません。
    echo   Python 3.9 以上をインストールしてください。
    echo   https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/3] Python 仮想環境を作成中…
if not exist "%TOOL_HOME%\.venv" (
    python -m venv "%TOOL_HOME%\.venv"
    if errorlevel 1 (
        echo [ERROR] 仮想環境の作成に失敗しました。
        pause
        exit /b 1
    )
    echo   .venv を作成しました。
) else (
    echo   .venv は既に存在します。スキップ。
)
echo.

echo [2/3] Pillow をインストール中…
"%TOOL_HOME%\.venv\Scripts\pip.exe" install --quiet Pillow
if errorlevel 1 (
    echo [ERROR] Pillow のインストールに失敗しました。
    pause
    exit /b 1
)
echo   Pillow インストール完了。
echo.

echo [3/3] PhotoArchive_RunHere.cmd を生成中…

REM --- RunHere.cmd を生成（TOOL_HOME を埋め込み）---
set "OUT_CMD=%TOOL_HOME%\PhotoArchive_RunHere.cmd"

(
echo @echo off
echo chcp 65001 ^>nul 2^>^&1
echo setlocal
echo.
echo REM ============================================================
echo REM  PhotoArchive_RunHere.cmd
echo REM  このファイルを写真フォルダに置いてダブルクリックしてください。
echo REM  そのフォルダ内の写真を自動でスキャンしてギャラリーを生成します。
echo REM  ※ 初回は config.json 不要です。出力先は _gallery/ に自動設定されます。
echo REM ============================================================
echo.
echo REM --- ツール本体のパス（setup.cmd が自動設定済み）---
echo set "TOOL_HOME=%TOOL_HOME%"
echo.
echo REM --- 以下は編集不要 ---
echo.
echo set "PHOTO_DIR=%%~dp0"
echo if "%%PHOTO_DIR:~-1%%"=="\" set "PHOTO_DIR=%%PHOTO_DIR:~0,-1%%"
echo.
echo echo ================================================
echo echo   Photo Archive
echo echo ================================================
echo echo.
echo echo 写真フォルダ: %%PHOTO_DIR%%
echo echo.
echo.
echo REM --- Python を探す ---
echo set "PYTHON=%%TOOL_HOME%%\.venv\Scripts\python.exe"
echo if not exist "%%PYTHON%%" (
echo     where python ^>nul 2^>^&1
echo     if errorlevel 1 (
echo         echo [ERROR] Python が見つかりません。
echo         echo   %%TOOL_HOME%%\setup.cmd を先に実行してください。
echo         pause
echo         exit /b 1
echo     ^)
echo     set "PYTHON=python"
echo ^)
echo.
echo REM --- config.json を探す（写真フォルダ優先、無くてもOK）---
echo set "CONFIG_OPT="
echo if exist "%%PHOTO_DIR%%\config.json" (
echo     set "CONFIG_OPT=--config "%%PHOTO_DIR%%\config.json""
echo     echo 設定: %%PHOTO_DIR%%\config.json
echo ^) else if exist "%%TOOL_HOME%%\config.json" (
echo     set "CONFIG_OPT=--config "%%TOOL_HOME%%\config.json""
echo     echo 設定: %%TOOL_HOME%%\config.json
echo ^) else (
echo     echo 設定: デフォルト（出力先: %%PHOTO_DIR%%\_gallery\）
echo ^)
echo echo.
echo.
echo REM --- ビルド実行 ---
echo cd /d "%%TOOL_HOME%%"
echo "%%PYTHON%%" -m photo_archive build %%CONFIG_OPT%% --input "%%PHOTO_DIR%%" --open
echo.
echo if errorlevel 1 (
echo     echo.
echo     echo [ERROR] ビルドに失敗しました。
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo.
echo echo ビルド完了！
echo pause
) > "%OUT_CMD%"

echo   %OUT_CMD%
echo   を生成しました。
echo.
echo ================================================
echo   セットアップ完了！
echo ================================================
echo.
echo 使い方:
echo   1. %OUT_CMD%
echo      を写真が入ったフォルダにコピーしてください。
echo   2. コピーした cmd をダブルクリックしてください。
echo   3. ギャラリーが _gallery/ フォルダに生成されます。
echo.
echo ※ 出力先を変えたい場合は config.json を作成して
echo   output_root を指定してください。
echo.
pause
