@echo off
chcp 65001 >nul

echo ===================================================
echo   機械図面 自動添削AI - 起動中...
echo ===================================================
echo.

REM APIキーが設定されているか確認
if "%ANTHROPIC_API_KEY%"=="" (
    echo [警告] ANTHROPIC_API_KEY が設定されていません。
    echo.
    echo 設定方法:
    echo   1. 下の行の「ここにAPIキーを貼る」を書き換えてください
    echo   2. またはコマンドプロンプトで set ANTHROPIC_API_KEY=sk-ant-...
    echo.
    REM ↓ APIキーをここに直接書いてもOK（他人に共有する場合は消すこと）
    REM set ANTHROPIC_API_KEY=sk-ant-ここにAPIキーを貼る
)

REM 必要なパッケージ確認
python -c "import flask; import anthropic" 2>nul
if %errorlevel% neq 0 (
    echo [セットアップ] 必要なパッケージをインストールします...
    pip install flask anthropic
    echo.
)

REM ブラウザを開く
start "" "http://localhost:5000"

REM サーバー起動
echo サーバーを起動します...
echo ブラウザが開かない場合は http://localhost:5000 にアクセスしてください
echo 終了: Ctrl+C
echo.
python app.py

pause
