#!/usr/bin/env python3
"""
機械図面 自動添削AI - Web UI (Phase 2)

使い方:
    python app.py
    → ブラウザで http://localhost:5000 を開く

必要:
    pip install flask anthropic
    set ANTHROPIC_API_KEY=sk-ant-...   (コマンドプロンプト)
    $env:ANTHROPIC_API_KEY = "sk-ant-..."  (PowerShell)
"""

import json
import os
import sys
import time
import uuid
import base64
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory

try:
    import anthropic
except ImportError:
    print("エラー: 必要なパッケージをインストールしてください")
    print("  pip install flask anthropic")
    sys.exit(1)

from system_prompt import build_system_prompt
from review_cli import extract_json

# --- Flask アプリ ---
app = Flask(__name__, template_folder="templates", static_folder="static")

# 設定
UPLOAD_FOLDER = Path("uploads")
RESULTS_FOLDER = Path("results")
UPLOAD_FOLDER.mkdir(exist_ok=True)
RESULTS_FOLDER.mkdir(exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# 知識ベース読み込み（起動時に1回）
SCRIPT_DIR = Path(__file__).parent
SYSTEM_PROMPT = build_system_prompt(str(SCRIPT_DIR / "knowledge_base.json"))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    """メインページ"""
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return render_template("index.html", api_key_set=api_key_set)


@app.route("/review", methods=["POST"])
def review():
    """図面添削API"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY が設定されていません"}), 500

    if "file" not in request.files:
        return jsonify({"error": "ファイルが選択されていません"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "ファイルが選択されていません"}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "error": f"未対応の形式です。対応: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    file_data = file.read()
    if len(file_data) > MAX_FILE_SIZE:
        return jsonify({"error": "ファイルサイズが大きすぎます（上限20MB）"}), 400

    context = request.form.get("context", "").strip()

    ext = file.filename.rsplit(".", 1)[1].lower()
    media_type = MEDIA_TYPES[ext]
    image_b64 = base64.standard_b64encode(file_data).decode("utf-8")

    # ファイル保存
    file_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    save_name = f"{file_id}.{ext}"
    save_path = UPLOAD_FOLDER / save_name
    with open(save_path, "wb") as f:
        f.write(file_data)

    # ユーザーメッセージ
    user_text = (
        "この機械図面を検図してください。\n"
        "製図原則・加工常識・検図実務の観点から不備を指摘し、"
        "指定されたJSONフォーマットで出力してください。\n\n"
        f"ファイル名: {file.filename}\n"
    )
    if context:
        user_text += f"\n追加情報: {context}\n"
    user_text += (
        "\n注意:\n"
        "- 画像から読み取れる情報のみで判断してください\n"
        "- 読み取れない部分は confidence: low として報告してください\n"
        "- JSONのみを出力してください（説明文は不要です）\n"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        start_time = time.time()

        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }],
        )

        elapsed = time.time() - start_time
        raw_text = response.content[0].text
        result = extract_json(raw_text)

        result["_meta"] = {
            "file_id": file_id,
            "filename": file.filename,
            "image_url": f"/uploads/{save_name}",
            "model": DEFAULT_MODEL,
            "elapsed_seconds": round(elapsed, 1),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_estimate_jpy": round(
                (response.usage.input_tokens * 3 / 1_000_000
                 + response.usage.output_tokens * 15 / 1_000_000) * 150, 1
            ),
            "timestamp": datetime.now().isoformat(),
            "context": context,
        }

        result_path = RESULTS_FOLDER / f"{file_id}.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return jsonify(result)

    except anthropic.APIError as e:
        return jsonify({"error": f"Claude API エラー: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"予期しないエラー: {str(e)}"}), 500


@app.route("/history")
def history():
    """過去の添削履歴一覧"""
    results = []
    for p in sorted(RESULTS_FOLDER.glob("*.json"), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("_meta", {})
            summary = data.get("summary", {})
            results.append({
                "file_id": meta.get("file_id", p.stem),
                "filename": meta.get("filename", "不明"),
                "image_url": meta.get("image_url", ""),
                "timestamp": meta.get("timestamp", ""),
                "error_count": summary.get("error_count", 0),
                "warning_count": summary.get("warning_count", 0),
                "suggestion_count": summary.get("suggestion_count", 0),
                "overall": summary.get("overall_assessment", ""),
            })
        except Exception:
            continue
    return jsonify(results)


@app.route("/result/<file_id>")
def get_result(file_id):
    """過去の添削結果取得"""
    result_path = RESULTS_FOLDER / f"{file_id}.json"
    if not result_path.exists():
        return jsonify({"error": "結果が見つかりません"}), 404
    with open(result_path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("=" * 50)
        print("  ANTHROPIC_API_KEY が未設定です")
        print()
        print("  PowerShell:")
        print('    $env:ANTHROPIC_API_KEY = "sk-ant-..."')
        print()
        print("  コマンドプロンプト:")
        print("    set ANTHROPIC_API_KEY=sk-ant-...")
        print("=" * 50)
        print()

    print("=" * 50)
    print("  機械図面 自動添削AI")
    print("  http://localhost:5000 をブラウザで開いてください")
    print("  終了: Ctrl+C")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
