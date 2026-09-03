#!/usr/bin/env python3
# 銘柄カルテのデータ生成スクリプト
#
# やること
#   1) Stooqから各銘柄の月次株価（株式分割調整済みの終値）を取得
#   2) eps_input.json に手入力された実績EPSと組み合わせて
#      public/karte/data.js を書き出す
#
# 使い方（リポジトリのルートで）
#   python3 scripts/karte/generate_data.py
#
# 実データ運用に切り替えるには、eps_input.json の "sample" を false にし、
# 各銘柄の "eps" に本決算の実績EPSを10期分入れてから実行します。

import csv
import io
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
INPUT = pathlib.Path(__file__).parent / "eps_input.json"
OUT = ROOT / "public" / "karte" / "data.js"
MONTHS = 120

HEADER = (
    "// 銘柄カルテのデータファイル。scripts/karte/generate_data.py が再生成します。\n"
    "// sample:true の間は画面に「サンプルデータ」の注意書きが表示されます。\n"
)


def fetch_prices(code: str):
    url = f"https://stooq.com/q/d/l/?s={code}.jp&i=m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for row in rows:
        d = (row.get("Date") or "")[:7]
        c = row.get("Close")
        if len(d) == 7 and c:
            try:
                out.append({"d": d, "c": round(float(c))})
            except ValueError:
                pass
    return out[-MONTHS:]


def main():
    src = json.loads(INPUT.read_text(encoding="utf-8"))
    stocks = []
    for s in src["stocks"]:
        prices = fetch_prices(s["code"])
        if len(prices) < 100:
            raise SystemExit(
                f"{s['code']} の株価が{len(prices)}か月分しか取れませんでした。取得元を確認してください。"
            )
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
    OUT.write_text(
        HEADER + "window.KARTE_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"書き出しました: {OUT}")
    for s in stocks:
        print(f"  {s['code']} {s['name']}: 株価{len(s['prices'])}か月 / EPS{len(s['eps'])}期")


if __name__ == "__main__":
    main()
