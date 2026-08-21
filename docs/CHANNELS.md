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
| オウンドメディア記事 | Claude の定期実行（Routine） | 07:03 | — | GitHub Actions を使わない |
| Threads（記事拡散） | `media-promote.yml` | 12:00 | 公開RSS | このリポジトリへ移設 |
| SNSトークンの自動更新 | `refresh-tokens.yml` | 月 10:00 | — | 同上。両リポジトリのSecretを更新 |

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

### 移設にともなって、このリポジトリに要るもの
`Owned-Media` 側にあった Secret を、こちらにも登録する。

- `THREADS_USER_ID`（任意。未設定なら `/me` から自動取得する）
- `GH_PAT` — Fine-grained PAT。**このリポジトリの Secrets: Read and write だけ**。
  Repository access は `locoreach-autopost` 1本、権限は Secrets のみ。
  コードの読み書き権限は与えないこと

## なぜ private の Actions を使わないのか

`Owned-Media` は private で、private リポジトリの Actions は
GitHub の無料枠（月2,000分）を消費する。2026年8月にこれを使い切り、
ジョブが起動前に弾かれる状態になった。

public リポジトリの Actions は無料・無制限なので、
定期実行はすべてこちらに置いている。`Owned-Media` 側の
`media-promote.yml` / `refresh-tokens.yml` / `ci.yml` は
schedule を止め、手動実行用に残してある。

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


---

# このリポジトリが public であることについて

`locoreach-autopost` は public、`Owned-Media` は private。
public リポジトリの Actions は無料・無制限なので、定期実行はすべてこちらに置いている。

## 何が見えて、何が見えないか

見える：投稿スクリプト、`content.json`（投稿本文）、ワークフローの定義。
どれも投稿すれば公開される内容か、その手順。

**見えない：Secrets の値。** GitHub の Secrets はリポジトリが public でも
暗号化されて保管され、Web でも API でも読み出せない。
ワークフローのログに出そうとしても `***` に伏せられる。

## 外部の人がワークフローを動かせないこと

秘密情報が漏れる典型は「外部の人が起動できるワークフローに秘密情報を渡している」場合。
このリポジトリの6本は **すべて `schedule` と `workflow_dispatch` だけ**で、
`pull_request` / `pull_request_target` / `issue_comment` を使っているものは1本もない。

- 誰でも fork して PR は出せるが、**PR ではワークフローが1本も起動しない**
- `workflow_dispatch` を叩けるのは、このリポジトリへの書き込み権限がある人だけ

新しいワークフローを足すときも、この2つ以外のトリガーを使わないこと。
とくに `pull_request_target` は、fork の PR に Secrets を渡してしまうので使わない。

## 入力をシェルに直接展開しないこと

`run:` の中に `${{ inputs.day }}` のように書くと、入力文字列がそのまま
シェルの一部として解釈される。`env:` で渡して `"$IN_DAY"` と参照する。
`reel-post.yml` では、さらに曜日が `mon`〜`sun` のいずれかであることを検査している。

## PAT を跨がせないこと

`GH_PAT` に `Owned-Media`（private）の権限を与えてはいけない。
public 側の Secret が漏れたときに、private 側を書き換えられる経路になる。
定期実行はすべてこちらに移したので、`Owned-Media` 側のトークンは
手動実行のときにしか使わない。

## 定期的に見ること

- Settings → Collaborators — 意図しない書き込み権限が増えていないか
- Settings → Secrets — 使っていない Secret が残っていないか
- 60日以上リポジトリに動きがないと、public リポジトリの schedule は
  GitHub 側で自動的に止まる。毎日 `posted.json` が更新されるので通常は起きない
