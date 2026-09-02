# locoreach-scheduler

決まった時刻に、このリポジトリのワークフローを `workflow_dispatch` で叩くだけの
Cloudflare Worker。

## なぜ要るのか

GitHub Actions の `schedule` が、実測で毎日4〜8時間遅れる。

| | 予定(JST) | 実際に発火した時刻 |
|---|---|---|
| 縦動画 | 18:00 | 8/31 01:04 / 9/1 23:09 |
| カルーセル | 20:00 | 8/31 03:08 / 9/2 00:32 |

公式ドキュメントにも「高負荷時は遅れる。落とされることもある」とある。
毎時00分を避けるところまでやったが、遅れは縮まなかった。
Cloudflare の Cron Triggers は自前で時刻を持つので、GitHub の混雑に
巻き込まれない。

## 動き

1. `media.camomile.co.jp/feed.xml` から今日の記事のスラッグを取る
   - 今日の記事が無ければ、投げずに通知して終わる
2. `posted.json` を見て、そのチャネルで投稿済みなら投げない
3. 未投稿なら `workflow_dispatch` を叩く
4. 投げられなければ Google Chat に知らせる

GitHub 側の `schedule` は残してある。あとから遅れて発火しても、
投稿側が `posted.json` を見て自分で止まるので二重投稿にはならない。

## 時刻（UTC）

| cron | JST | 投げるもの |
|---|---|---|
| `20 2 * * *` | 11:20 | corporate-post.yml |
| `15 9 * * *` | 18:15 | reel-post.yml |
| `40 11 * * *` | 20:40 | post.yml / media-promote.yml |

## Secret

Cloudflare の Workers → locoreach-scheduler → Settings → Variables and Secrets

| 名前 | 中身 |
|---|---|
| `GITHUB_TOKEN` | fine-grained PAT。garut5/locoreach-autopost に対して **Actions: Read and write** のみ |
| `NOTIFY_WEBHOOK` | Google Chat のスペース「診断依頼」等の Webhook URL（任意） |

トークンはソースにもログにも出さない。失敗時に出すのは状態コードだけ。

## 直したとき

```
cd worker && npx wrangler deploy
```
