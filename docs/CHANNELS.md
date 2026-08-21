# 投稿チャネルと必要な設定

前提：**認証情報が無いチャネルは自動でスキップされる。**
入っていないものがあってもワークフローは緑のまま終わり、他のチャネルは投稿される。
Secrets を入れた翌日から、そのチャネルだけが動き出す。

## 稼働中

| チャネル | ワークフロー | 時刻(JST) | 素材 | 状態 |
|---|---|---|---|---|
| Instagram フィード（カルーセル） | `post.yml` | 20:00 | 画像4枚 | 稼働中 |
| Instagram ストーリーズ | `post.yml` | 20:00 | 9:16画像1枚 | 稼働中 |
| Threads | `post.yml` | 20:00 | 画像4枚 | 稼働中 |
| オウンドメディア記事 | `Owned-Media/media-write.yml` | 07:00 | — | トークン待ち |
| Threads（記事拡散） | `Owned-Media/media-promote.yml` | 12:00 | — | 稼働中 |

## 追加したチャネル

| チャネル | ワークフロー | 起動 | 素材 |
|---|---|---|---|
| Instagram リール | `reel-post.yml` | 手動（既定は投稿しない） | 縦動画 |
| YouTube ショート | `reel-post.yml` | 同上 | 縦動画 |
| TikTok | `reel-post.yml` | 同上 | 縦動画 |
| X | `x-post.yml` | 毎日20:00（空振り中） | 画像4枚 |

`reel-post.yml` は `publish=no` が既定。まず Artifacts で中身を確認し、
問題なければ `publish=yes` で実行する。慣れたら cron を足す。

## Secrets（リポジトリの Settings → Secrets and variables → Actions）

### すでに入っているもの
- `IG_TOKEN` — Instagram の長期トークン。リールもこれを使う
- `THREADS_TOKEN` — Threads の長期トークン
- `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` — R2 へ動画を置くため

### X（4つセットで1組。1つでも欠けるとスキップ）
1. https://developer.x.com でアプリを作る
2. User authentication settings を **Read and write** にする
3. Keys and tokens から取得

- `X_API_KEY` / `X_API_SECRET` — Consumer Keys
- `X_ACCESS_TOKEN` / `X_ACCESS_SECRET` — Access Token and Secret
  （**権限を Read and write に変えた後に作り直すこと。**前に発行したものは読み取り専用のまま）

無料枠は書き込み月500件。1日1件なら十分に収まる。

### YouTube ショート
1. Google Cloud で YouTube Data API v3 を有効化
2. OAuth クライアント（種類：デスクトップ）を作る
3. スコープ `https://www.googleapis.com/auth/youtube.upload` でリフレッシュトークンを取る

- `YT_CLIENT_ID` / `YT_CLIENT_SECRET` / `YT_REFRESH_TOKEN`
- 変数 `YT_PRIVACY`（任意）— `public` / `unlisted` / `private`。既定 `public`

最初は `YT_PRIVACY=unlisted` にして、動画を自分で見てから `public` に変えるのが安全。

### TikTok
1. https://developers.tiktok.com でアプリを作り、Content Posting API を追加
2. **URL プロパティに `media.camomile.co.jp` を登録して所有権確認をする**
   （TikTok が動画をURLから取りに来るため。未確認だと弾かれる）
3. スコープ `video.upload`（下書き）または `video.publish`（直接公開）

- `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` / `TIKTOK_REFRESH_TOKEN`
- 変数 `TIKTOK_MODE` — `inbox`（既定・下書き箱へ送る）/ `direct`（直接公開）

審査が通るまで直接公開は「自分だけ」に制限される。
まず `inbox` で運用し、審査通過後に `direct` へ切り替える。

## 変数（Settings → Variables → Actions）

- `TTS_CREDIT` — 既定 `VOICEVOX:ずんだもん`。
  VOICEVOX は商用利用できるが**クレジット表記が必須**。声を変えたらここも変える。
- `VOICEVOX_SPEAKER` — 話者ID。既定 `3`（ずんだもん ノーマル）
- `X_LINK` / `YT_PRIVACY` / `TIKTOK_MODE` / `TIKTOK_PRIVACY`

## 誘導先と計測

すべてのチャネルの本文に UTM 付きリンクが入る。

```
utm_source = instagram / threads / x / youtube / tiktok
utm_medium = social
utm_campaign = sns      （毎日の定型投稿）
utm_campaign = media    （記事の拡散：scripts/promote.py）
utm_content  = 曜日キー または 記事スラッグ
```

リンク先の `media.camomile.co.jp` は流入元を sessionStorage に保存し、
無料MEO診断フォームの hidden 項目として D1 の `leads` テーブルへ書き込む。
どの媒体の投稿が問い合わせにつながったかは管理画面の「流入元」列で追える。
