/**
 * 決まった時刻に GitHub の workflow_dispatch を叩くだけの Worker。
 *
 * ## なぜ要るのか
 *
 * GitHub Actions の schedule が、実測で毎日4〜8時間遅れる。
 * 公式ドキュメントにも「高負荷時は遅れる。落とされることもある」と書いてある。
 * 毎時00分を避ける（分を散らす）ところまでやったが、遅れは縮まなかった。
 *
 *   縦動画      予定18:00 → 実際 8/31 01:04 / 9/1 23:09 JST
 *   カルーセル  予定20:00 → 実際 8/31 03:08 / 9/2 00:32 JST
 *
 * Cloudflare の Cron Triggers は自前で時刻を持つので、GitHub の混雑に
 * 巻き込まれない。ここから叩けば、指定した時刻に走る。
 *
 * ## 二重投稿について
 *
 * GitHub 側の schedule は残してある。遅れて発火しても、投稿側が
 * posted.json を見て「その記事はもう出した」と分かれば自分で止まる。
 * この Worker も投げる前に同じ posted.json を見るので、無駄打ちもしない。
 *
 * ## 秘密情報
 *
 * GITHUB_TOKEN は Worker の Secret に入れる。ここには書かない。
 * ログにも出さない（失敗時に出すのは状態コードだけ）。
 */

const REPO = "garut5/locoreach-autopost";
const FEED = "https://media.camomile.co.jp/feed.xml";
const POSTED =
  "https://raw.githubusercontent.com/garut5/locoreach-autopost/main/posted.json";
const UA = "locoreach-scheduler/1.0";

// cron（UTC）→ その時刻に投げるもの。
// key は posted.json のキー。null は記録を持たないので毎回投げる。
const JOBS = {
  // 11:20 JST 会社サイトの WP-Cron を起こす
  "20 2 * * *": [["corporate-post.yml", {}, null]],
  // 18:15 JST 縦動画
  "15 9 * * *": [[
    "reel-post.yml",
    { publish: "yes", targets: "all", format: "short", source: "article", narration: "voicevox" },
    "reel",
  ]],
  // 20:40 JST カルーセルと記事拡散
  "40 11 * * *": [
    ["post.yml", { dry_run: "0", source: "article" }, "carousel"],
    ["media-promote.yml", { dry_run: "no" }, "threads"],
  ],
};

/** JST の「今日」を YYYY-MM-DD で返す。 */
function todayJst() {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

/** RSS の先頭から、今日公開された記事のスラッグを返す。無ければ null。 */
async function todaySlug() {
  const res = await fetch(FEED, { headers: { "User-Agent": UA } });
  if (!res.ok) throw new Error(`feed ${res.status}`);
  const xml = await res.text();

  for (const m of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const link = /<link>([^<]*)<\/link>/.exec(m[1])?.[1]?.trim();
    const pub = /<pubDate>([^<]*)<\/pubDate>/.exec(m[1])?.[1]?.trim();
    if (!link || !pub) continue;
    const d = new Date(pub);
    if (isNaN(d)) continue;
    const day = new Date(d.getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10);
    // RSS は新しい順。先頭が今日でなければ、今日の記事は無い
    return day === todayJst() ? link.replace(/\/$/, "").split("/").pop() : null;
  }
  return null;
}

/** posted.json を読む。読めなければ空を返し、投稿側の判定に任せる。 */
async function posted() {
  try {
    const res = await fetch(POSTED, { headers: { "User-Agent": UA } });
    return res.ok ? await res.json() : {};
  } catch {
    return {};
  }
}

async function dispatch(env, workflow, inputs) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": UA,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );
  // 応答本文にはトークンは入らないが、念のため状態コードだけを扱う
  if (!res.ok) throw new Error(`${workflow} dispatch ${res.status}`);
}

/** 落ちたことを Google Chat に知らせる。未設定なら何もしない。 */
async function notify(env, text) {
  if (!env.NOTIFY_WEBHOOK) return;
  try {
    await fetch(env.NOTIFY_WEBHOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch {
    // 通知の失敗で本体の失敗を塗り替えない
  }
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const jobs = JOBS[event.cron];
      if (!jobs) return;

      let slug;
      try {
        slug = await todaySlug();
      } catch (e) {
        await notify(env, `[定期起動] RSS を読めませんでした: ${e.message}`);
        return;
      }
      if (!slug) {
        await notify(env, "[定期起動] 今日の記事がまだ出ていないため、投稿を投げませんでした。");
        return;
      }

      const done = await posted();
      const failed = [];
      for (const [workflow, inputs, key] of jobs) {
        if (key && (done[key] || []).includes(slug)) continue; // 投稿済み
        try {
          await dispatch(env, workflow, inputs);
        } catch (e) {
          failed.push(e.message);
        }
      }
      if (failed.length) {
        await notify(env, `[定期起動] 投げられませんでした: ${failed.join(" / ")}`);
      }
    })());
  },
};
