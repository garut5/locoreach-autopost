#!/usr/bin/env python3
"""定期実行が落ちたことを Google Chat のスペースへ知らせる。

自動投稿は誰も見ていない時間に走る。落ちても気づけないと、
記事だけ出て SNS が止まった状態が何日も続きうる。

NOTIFY_WEBHOOK が無いときは黙って何もしない（終了コード0）。
Secret を入れる前でもワークフローを壊さないため。
webhook の URL は認証情報そのものなので、絶対に出力しない。

--strict を付けると、届かなかったときに終了コード1で落ちる。
通常の失敗通知では使わない（通知の失敗で本体の失敗を塗り替えたくない）。
「通知経路が生きているか」を確かめる用。ステップの成否そのものが
判定になるので、標準出力を読まなくても結果が分かる。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def post(hook: str, text: str) -> tuple[bool, str]:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        hook, data=body, headers={"Content-Type": "application/json; charset=UTF-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return 200 <= res.status < 300, f"HTTP {res.status}"
    except urllib.error.HTTPError as e:
        # 例外の本文には URL が入りうるので、状態コードだけ返す
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="届かなかったら終了コード1で落ちる（経路の確認用）")
    ap.add_argument("--test", action="store_true",
                    help="失敗通知ではなく、疎通確認のメッセージを送る")
    args = ap.parse_args()

    hook = os.environ.get("NOTIFY_WEBHOOK", "").strip()
    if not hook:
        print("NOTIFY_WEBHOOK が未設定のため通知しません")
        return 1 if args.strict else 0

    name = os.environ.get("WF_NAME", "(不明なワークフロー)")
    url = os.environ.get("WF_URL", "")
    repo = os.environ.get("WF_REPO", "")

    if args.test:
        text = (
            "✅ 通知テスト\n"
            "このメッセージが見えていれば、自動実行が落ちたときの通知は届きます。\n"
            f"リポジトリ: {repo}\n{url}"
        )
    else:
        text = (
            f"⚠️ 自動実行が失敗しました\n"
            f"ワークフロー: {name}\n"
            f"リポジトリ: {repo}\n"
            f"{url}"
        )

    ok, detail = post(hook, text)
    if ok:
        print(f"通知しました（{detail}）")
        return 0

    print(f"通知に失敗しました: {detail}", file=sys.stderr)
    # 通常の失敗通知では、通知の失敗でジョブの結論を変えない。
    # 元の失敗のほうが重要で、そちらを見てほしい
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
