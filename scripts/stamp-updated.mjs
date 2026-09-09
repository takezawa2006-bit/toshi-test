/**
 * デプロイのたびに、ポータルのフッターの最終更新日をその日の日付に書き換える。
 *
 * 日本時間で数え、「最終更新　2026年9月9日（水）」の形にする。
 * 作品カードの「2026年9月」などの時期表示には触れない。
 */
import { readFile, writeFile } from "node:fs/promises";

const TARGET = new URL("../public/portal/index.html", import.meta.url);
const MARK = /(<p id="last-updated">)[\s\S]*?(<\/p>)/;

const jst = new Date(Date.now() + 9 * 60 * 60 * 1000);
const year = jst.getUTCFullYear();
const month = jst.getUTCMonth() + 1;
const date = jst.getUTCDate();
const week = "日月火水木金土"[jst.getUTCDay()];
const text = `最終更新　${year}年${month}月${date}日（${week}）`;

const html = await readFile(TARGET, "utf8");
if (!MARK.test(html)) {
  console.error("最終更新の差し込み先が見つかりませんでした。フッターを確認してください。");
  process.exit(1);
}

await writeFile(TARGET, html.replace(MARK, `$1${text}$2`));
console.log("フッターの最終更新日を書き換えました:", text);
