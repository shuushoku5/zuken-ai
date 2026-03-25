#!/usr/bin/env python3
"""
機械図面 自動添削AI - CLIプロトタイプ (Phase 1)

使い方:
    python review_cli.py drawing.png
    python review_cli.py drawing.jpg --output result.json
    python review_cli.py drawing.png --format text
    python review_cli.py drawing.png --model claude-sonnet-4-20250514

必要:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("エラー: anthropic パッケージが必要です")
    print("  pip install anthropic")
    sys.exit(1)

from system_prompt import build_system_prompt


# --- 設定 ---
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def load_image_as_base64(image_path: str) -> tuple[str, str]:
    """画像ファイルを読み込み、base64文字列とmedia_typeを返す"""
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"ファイルが見つかりません: {image_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            f"未対応の画像形式: {suffix}\n"
            f"対応形式: {', '.join(SUPPORTED_FORMATS)}"
        )

    media_type = MEDIA_TYPES[suffix]

    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # ファイルサイズチェック（Claude APIの制限: 約20MB）
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > 20:
        raise ValueError(f"ファイルサイズが大きすぎます: {file_size_mb:.1f}MB (上限20MB)")

    return image_data, media_type


def review_drawing(
    image_path: str,
    model: str = DEFAULT_MODEL,
    knowledge_base_path: str = None,
    user_context: str = None,
) -> dict:
    """図面画像をClaude APIに送信し、検図結果を取得する"""

    # APIキーの確認
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY が設定されていません\n"
            "  export ANTHROPIC_API_KEY='sk-ant-...'"
        )

    # 知識ベースパスの解決
    if knowledge_base_path is None:
        script_dir = Path(__file__).parent
        knowledge_base_path = str(script_dir / "knowledge_base.json")

    # システムプロンプト生成
    system_prompt = build_system_prompt(knowledge_base_path)

    # 画像読み込み
    image_data, media_type = load_image_as_base64(image_path)

    # ユーザーメッセージ組み立て
    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            },
        },
        {
            "type": "text",
            "text": build_user_message(image_path, user_context),
        },
    ]

    # API呼び出し
    client = anthropic.Anthropic(api_key=api_key)

    print(f"検図中... (model: {model})", file=sys.stderr)
    start_time = time.time()

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    elapsed = time.time() - start_time
    print(f"完了 ({elapsed:.1f}秒)", file=sys.stderr)

    # レスポンス解析
    raw_text = response.content[0].text

    # JSON部分を抽出（```json ... ``` で囲まれている場合に対応）
    result = extract_json(raw_text)

    # メタ情報を追加
    result["_meta"] = {
        "image_path": str(image_path),
        "model": model,
        "elapsed_seconds": round(elapsed, 1),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    return result


def build_user_message(image_path: str, user_context: str = None) -> str:
    """ユーザーメッセージを組み立てる"""
    msg = (
        "この機械図面を検図してください。\n"
        "製図原則・加工常識・検図実務の観点から不備を指摘し、"
        "指定されたJSONフォーマットで出力してください。\n\n"
        f"ファイル名: {Path(image_path).name}\n"
    )

    if user_context:
        msg += f"\n追加情報: {user_context}\n"

    msg += (
        "\n注意:\n"
        "- 画像から読み取れる情報のみで判断してください\n"
        "- 読み取れない部分は confidence: low として報告してください\n"
        "- JSONのみを出力してください（説明文は不要です）\n"
    )

    return msg


def extract_json(text: str) -> dict:
    """テキストからJSON部分を抽出する"""
    # まず全体がJSONかどうか試す
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ``` で囲まれたブロックを探す
    import re

    json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # { ... } を探す
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    # JSON解析失敗時はraw textとして返す
    return {
        "drawing_summary": "（JSON解析失敗）",
        "findings": [],
        "summary": {"overall_assessment": "JSON解析に失敗しました。生テキスト出力を確認してください。"},
        "_raw_response": text,
    }


def format_as_text(result: dict) -> str:
    """検図結果を人間が読みやすいテキスト形式に変換する"""
    lines = []
    lines.append("=" * 60)
    lines.append("機械図面 添削結果")
    lines.append("=" * 60)

    # 概要
    if "drawing_summary" in result:
        lines.append(f"\n【図面概要】{result['drawing_summary']}")

    # メタ情報
    meta = result.get("_meta", {})
    if meta:
        lines.append(f"  ファイル: {meta.get('image_path', '不明')}")
        lines.append(f"  モデル: {meta.get('model', '不明')}")
        lines.append(f"  処理時間: {meta.get('elapsed_seconds', '?')}秒")

    # サマリー
    summary = result.get("summary", {})
    if summary:
        lines.append(f"\n【総評】{summary.get('overall_assessment', '')}")
        e = summary.get("error_count", 0)
        w = summary.get("warning_count", 0)
        s = summary.get("suggestion_count", 0)
        lines.append(f"  🔴 error: {e}件  🟡 warning: {w}件  🔵 suggestion: {s}件")

    # 指摘一覧
    findings = result.get("findings", [])
    if findings:
        lines.append(f"\n{'─' * 60}")
        lines.append(f"指摘一覧 ({len(findings)}件)")
        lines.append(f"{'─' * 60}")

        severity_icons = {"error": "🔴", "warning": "🟡", "suggestion": "🔵"}

        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "?")
            icon = severity_icons.get(sev, "⚪")
            confidence = f.get("confidence", "")
            conf_str = f" [{confidence}]" if confidence else ""

            lines.append(f"\n{icon} [{f.get('finding_id', f'F-{i:03d}')}] {f.get('title', '(無題)')}{conf_str}")
            lines.append(f"  重要度: {sev}")

            if f.get("location"):
                lines.append(f"  箇所:   {f['location']}")
            if f.get("problem"):
                lines.append(f"  問題:   {f['problem']}")
            if f.get("impact"):
                lines.append(f"  影響:   {f['impact']}")
            if f.get("fix"):
                lines.append(f"  修正案: {f['fix']}")
            if f.get("reference_rule_ids"):
                lines.append(f"  根拠:   {', '.join(f['reference_rule_ids'])}")
    else:
        lines.append("\n指摘なし ✅")

    lines.append(f"\n{'=' * 60}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="機械図面 自動添削AI - CLIプロトタイプ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python review_cli.py drawing.png
  python review_cli.py drawing.jpg --output result.json
  python review_cli.py drawing.png --format text
  python review_cli.py drawing.png --context "材質はA5052、試作品"
        """,
    )
    parser.add_argument("image", help="図面画像ファイルのパス (.png/.jpg/.jpeg/.gif/.webp)")
    parser.add_argument("--output", "-o", help="結果の出力先ファイル（省略時は標準出力）")
    parser.add_argument(
        "--format",
        "-f",
        choices=["json", "text"],
        default="text",
        help="出力形式 (default: text)",
    )
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help=f"使用モデル (default: {DEFAULT_MODEL})")
    parser.add_argument("--context", "-c", help="追加コンテキスト（例: 材質、用途など）")
    parser.add_argument("--knowledge-base", "-k", help="知識ベースJSONのパス")

    args = parser.parse_args()

    try:
        # 検図実行
        result = review_drawing(
            image_path=args.image,
            model=args.model,
            knowledge_base_path=args.knowledge_base,
            user_context=args.context,
        )

        # 出力
        if args.format == "json":
            output_text = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            output_text = format_as_text(result)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_text)
            print(f"結果を保存しました: {args.output}", file=sys.stderr)
        else:
            print(output_text)

    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"API エラー: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"予期しないエラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
