#!/usr/bin/env python3
# 銘柄カルテのデータ生成スクリプト
#
# やること
#   1) Yahoo!ファイナンスから各銘柄の月次株価（株式分割調整済みの終値）を取得
#   2) eps_input.json に手入力された実績EPSと組み合わせて
#      public/karte/data.js を書き出す
#
# 使い方（リポジトリのルートで）
#   python3 scripts/karte/generate_data.py
#
# 実データ運用に切り替えるには、eps_input.json の "sample" を false にし、
# 各銘柄の "eps" に本決算の実績EPSを10期分入れてから実行します。
#
# 株価の取得元について
#   もともとStooqのCSV（https://stooq.com/q/d/l/）を使っていましたが、
#   2026年9月時点でアクセス制限（Exceeded the daily site hits limit）がかかり
#   使えなくなったため、Yahoo!ファイナンスの時系列ページに切り替えています。
#   使うのは「調整後終値」で、株式分割はさかのぼって調整済みです。
#   Yahoo!ファイナンスも短時間に何十回も叩くと一時的に500を返します。
#   取得できた月次株価は price_cache.json に貯めておき、取得に失敗したときは
#   キャッシュを使って処理を続けます（キャッシュはリポジトリには含めません）。

import datetime
import html
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
INPUT = pathlib.Path(__file__).parent / "eps_input.json"
OUT = ROOT / "public" / "karte" / "data.js"
CACHE = pathlib.Path(__file__).parent / "price_cache.json"
MONTHS = 120
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

HEADER = (
    "// 銘柄カルテのデータファイル。scripts/karte/generate_data.py が再生成します。\n"
    "// sample:true の間は画面に「サンプルデータ」の注意書きが表示されます。\n"
)


def _today() -> str:
    # 未来日付を渡すとYahoo側が500を返すので、今日の日付を上限にする
    return datetime.date.today().strftime("%Y%m%d")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _fetch_retry(url: str, tries: int = 3) -> str:
    for i in range(tries):
        try:
            return _fetch(url)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))
    raise RuntimeError("unreachable")


def _cells(row: str):
    row = row[row.find("<t"):] if "<t" in row else row
    out = []
    for part in re.split(r"</t[dh]>", row):
        text = html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
        if text:
            out.append(text)
    return out


def _load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def fetch_prices(code: str, pages: int = 12):
    """Yahoo!ファイナンスの月次時系列から調整後終値を取る。{'d':'YYYY-MM','c':終値} の配列。"""
    found = {}
    for page in range(1, pages + 1):
        body = _fetch_retry(
            f"https://finance.yahoo.co.jp/quote/{code}.T/history"
            f"?from=20140101&to={_today()}&timeFrame=m&page={page}"
        )
        table = body[body.find("<tbody>"):body.find("</tbody>")]
        got = 0
        for row in table.split("<tr ")[1:]:
            c = _cells(row)
            if not c or not re.fullmatch(r"\d{4}/\d{1,2}", c[0]):
                continue
            nums = [x.replace(",", "") for x in c[1:]]
            if len(nums) < 6:  # 始値 高値 安値 終値 出来高 調整後終値
                continue
            try:
                adjusted = float(nums[5])
            except ValueError:
                continue
            y, m = c[0].split("/")
            found[f"{y}-{int(m):02d}"] = round(adjusted)
            got += 1
        if got == 0:
            break
        time.sleep(0.8)
    return [{"d": d, "c": found[d]} for d in sorted(found)][-MONTHS:]


def main():
    src = json.loads(INPUT.read_text(encoding="utf-8"))
    cache = _load_cache()
    stocks = []
    for s in src["stocks"]:
        code = s["code"]
        try:
            prices = fetch_prices(code)
            cache[code] = {p["d"]: p["c"] for p in prices}
        except Exception as e:
            if code not in cache:
                raise SystemExit(f"{code} の株価を取得できず、キャッシュもありません: {e}")
            print(f"注意: {code} の株価取得に失敗したためキャッシュを使います（{e}）")
            months = cache[code]
            prices = [{"d": d, "c": months[d]} for d in sorted(months)][-MONTHS:]
        if len(prices) < 36:
            raise SystemExit(
                f"{s['code']} の株価が{len(prices)}か月分しか取れませんでした。取得元を確認してください。"
            )
        if len(prices) < MONTHS:
            # 上場が10年以内の銘柄（霞ヶ関キャピタルなど）はここに入る
            print(f"注意: {s['code']} {s['name']} の株価は{len(prices)}か月分（上場来）です")
        eps = s.get("eps", [])
        if len(eps) < 10:
            print(f"注意: {s['code']} {s['name']} のEPSが{len(eps)}期分しかありません")
        stocks.append(
            {
                "code": s["code"],
                "name": s["name"],
                "market": s["market"],
                "fyMonth": s["fyMonth"],
                "prices": prices,
                "eps": eps,
            }
        )

    data = {
        "sample": bool(src.get("sample", True)),
        "updated": src.get("updated", ""),
        "source": src.get("source", ""),
        "stocks": stocks,
    }
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.write_text(
        HEADER + "window.KARTE_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"書き出しました: {OUT}")
    for s in stocks:
        print(f"  {s['code']} {s['name']}: 株価{len(s['prices'])}か月 / EPS{len(s['eps'])}期")


if __name__ == "__main__":
    main()
