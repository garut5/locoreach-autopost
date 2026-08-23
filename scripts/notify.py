#!/usr/bin/env python3
"""定期実行が落ちたことを Google Chat のスペースへ知らせる。

自動投稿は誰も見ていない時間に走る。落ちても気づけないと、
記事だけ出て SNS が止まった状態が何日も続きうる。

NOTIFY_WEBHOOK が無いときは黙って何もしない（終了コード0）。
Secret を入れる前でもワークフローを壊さないため。
webhook の URL は認証情報そのものなので、絶対に出力しない。
"""
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    hook = os.environ.get("NOTIFY_WEBHOOK", "").strip()
    if not hook:
        print("NOTIFY_WEBHOOK が未設定のため通知しません")
        return 0

    name = os.environ.get("WF_NAME", "(不明なワークフロー)")
    url = os.environ.get("WF_URL", "")
    repo = os.environ.get("WF_REPO", "")

    text = (
        f"⚠️ 自動実行が失敗しました\n"
        f"ワークフロー: {name}\n"
        f"リポジトリ: {repo}\n"
        f"{url}"
    )
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        hook, data=body, headers={"Content-Type": "application/json; charset=UTF-8"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            print(f"通知しました（{res.status}）")
    except urllib.error.HTTPError as e:
        # 通知の失敗でジョブの結論を変えない。元の失敗のほうが重要
        print(f"通知に失敗しました: HTTP {e.code}", file=sys.stderr)
    except Exception as e:
        print(f"通知に失敗しました: {type(e).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
