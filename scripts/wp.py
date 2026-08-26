#!/usr/bin/env python3
"""camomile.co.jp（WordPress）へ投稿するための最小のクライアント。

    from wp import WordPress
    wp = WordPress()                       # 環境変数から資格情報を読む
    wp.create_post(title=..., content=..., status="publish")

## エンドポイントについて

`/wp-json/` は Xserver の WAF が 403 で弾く（返ってくるのは XSERVER の
エラーページで、WordPress まで届いていない）。WordPress にはもう一つ
公式の入口 `?rest_route=` があり、こちらは通る。中身は同じ REST API。

**書き込みは認証必須のまま**で、未認証の POST は 401 で拒否される。
つまり口を開けているのではなく、通る形を選んでいるだけ。

## 資格情報

  WP_BASE_URL       既定 https://camomile.co.jp
  WP_USER           WordPress のユーザー名
  WP_APP_PASSWORD   アプリケーションパスワード（通常のログイン用ではない）

アプリケーションパスワードは WordPress 5.6 以降の標準機能で、
管理画面のログインパスワードとは別物。投稿だけに使え、
管理画面にはログインできず、いつでも個別に失効させられる。
**値はログにも例外にも出さない。**
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

UA = "locoreach-autopost/1.0"


class WordPressError(RuntimeError):
    pass


class WordPress:
    def __init__(self) -> None:
        self.base = os.environ.get("WP_BASE_URL", "https://camomile.co.jp").rstrip("/")
        user = os.environ.get("WP_USER", "").strip()
        # アプリケーションパスワードは画面上 4文字ずつ空白区切りで表示される。
        # そのまま貼られても通るように空白を落とす
        app = os.environ.get("WP_APP_PASSWORD", "").replace(" ", "").strip()
        if not user or not app:
            raise WordPressError("WP_USER と WP_APP_PASSWORD が要ります")
        token = base64.b64encode(f"{user}:{app}".encode()).decode()
        self._auth = f"Basic {token}"

    def _call(self, route: str, data: dict | None = None, method: str = "GET",
              params: dict | None = None) -> dict:
        # rest_route は「経路」だけを入れる値。ここに ?slug=... まで詰めると
        # 経路名の一部として符号化され、存在しない経路として 404 になる。
        # 追加の条件は、rest_route と並ぶ普通のクエリとして渡すこと。
        query = {"rest_route": route}
        query.update(params or {})
        url = f"{self.base}/?" + urllib.parse.urlencode(query)
        body = json.dumps(data).encode() if data is not None else None
        headers = {"User-Agent": UA, "Authorization": self._auth}
        if body:
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as res:
                return json.loads(res.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            # 本文に資格情報は入らないが、長いHTMLが返ることがあるので切り詰める
            detail = e.read().decode("utf-8", "replace")[:300]
            raise WordPressError(f"HTTP {e.code}: {detail}") from None

    def whoami(self) -> dict:
        """資格情報が通るかの確認。投稿はしない。"""
        return self._call("/wp/v2/users/me")

    def can_edit(self) -> int:
        """投稿を作らずに、資格情報と権限だけを確かめる。

        context=edit は edit_posts 権限がないと 401/403 になる。
        つまり「読めた」ことが「書ける」ことの証明になる。
        whoami() と違って /wp/v2/users を使わないので、
        Wordfence のユーザー名秘匿が有効でも通る。
        """
        r = self._call("/wp/v2/posts", params={"context": "edit", "per_page": 1})
        return len(r)

    def find_by_slug(self, slug: str) -> list[dict]:
        """同じスラッグの投稿を探す。二重投稿を防ぐため。

        status を指定しているのは、下書き・予約投稿も見つけたいから。
        publish だけ見ていると、予約済みの分にもう一度投げてしまう。
        """
        return self._call("/wp/v2/posts", params={
            "slug": slug,
            "status": "publish,future,draft,pending,private",
        })

    def create_post(self, *, title: str, content: str, slug: str = "",
                    status: str = "publish", date: str = "",
                    categories: list[int] | None = None,
                    excerpt: str = "") -> dict:
        payload: dict = {"title": title, "content": content, "status": status}
        if slug:
            payload["slug"] = slug
        if excerpt:
            payload["excerpt"] = excerpt
        if categories:
            payload["categories"] = categories
        if date:
            # status=future の予約投稿はサイトの時刻で解釈される
            payload["date"] = date
        return self._call("/wp/v2/posts", payload, method="POST")

    def categories(self) -> list[dict]:
        return self._call("/wp/v2/categories", params={"per_page": 100})
