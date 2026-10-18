#!/usr/bin/env python3
"""
Can OS · ABD piyasa detayı (yalnızca Python standart kütüphanesi).

Nasdaq'ın ücretsiz verisinden şunları üretir -> data/us_market.json:
  - endeks: S&P 500, Nasdaq-100, ≈Russell 2000 için genişlik (yükselen/düşen), işlem hacmi,
            hacim oranı (son 20 güne göre), en çok yükselen/düşen 10, en çok işlem gören 5,
            portföy hisselerinin günlük sıralaması
  - sektor: panodaki ABD sektör haritası evrenleri için piyasa değeri, günlük %, analist potansiyeli
  - hedef : analist hedef fiyatı ve al/tut/sat sayıları (günde bir kez, ABD kapanışından sonra)
  - sektor_adi: hisselerin Nasdaq sektör/endüstri bilgisi (pano etiketleri için)

Russell 2000 üye listesi ücretsiz yayımlanmadığı için yaklaşık olarak alınır:
ABD merkezli adi hisseler arasında piyasa değeri sırası 1001–3000 olanlar (≈R2000).
"""
import csv
import io
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
NY = ZoneInfo("America/New_York")
HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}
DATA = "data"
OUT = os.path.join(DATA, "us_market.json")
TGT = os.path.join(DATA, "us_targets.json")
VOLH = os.path.join(DATA, "us_volume_hist.json")
SP_CACHE = os.path.join(DATA, "sp500_list.json")


def get(url, timeout=25):
    with urlopen(Request(url, headers=HDR), timeout=timeout) as r:
        return r.read()


def fnum(x):
    if x in (None, "", "NA", "N/A"):
        return None
    try:
        return float(str(x).replace("$", "").replace(",", "").replace("%", "").replace("+", ""))
    except ValueError:
        return None


def key(sym):
    return re.sub(r"[^A-Z0-9]", "", sym.upper())


SUFFIX = re.compile(
    r"\b(common stock|ordinary shares|class [a-c]( common stock| ordinary shares)?|american depositary shares?|"
    r"depositary shares?|sponsored adr|adr|inc\.?|incorporated|corporation|corp\.?|company|co\.|plc|ltd\.?|limited|"
    r"n\.v\.|s\.a\.|ag|holdings?|group|\(the\)|the)\b",
    re.I,
)


def short_name(n, limit=18):
    s = SUFFIX.sub("", n or "")
    s = re.sub(r"[,.]+\s*$", "", re.sub(r"\s+", " ", s)).strip(" ,.-")
    s = s.replace("'", "’")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "."


def screener():
    raw = json.loads(get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true", timeout=40))
    out = {}
    for r in raw["data"]["rows"]:
        sym = (r.get("symbol") or "").strip()
        if not sym:
            continue
        out[key(sym)] = {
            "s": sym.replace("/", "."),
            "ad": r.get("name") or "",
            "p": fnum(r.get("lastsale")),
            "d": fnum(r.get("pctchange")),
            "mc": fnum(r.get("marketCap")),
            "v": fnum(r.get("volume")),
            "ulke": r.get("country") or "",
            "sektor": r.get("sector") or "",
            "endustri": r.get("industry") or "",
        }
    return out


def ndx_list():
    raw = json.loads(get("https://api.nasdaq.com/api/quote/list-type/nasdaq100"))
    return [key(r["symbol"]) for r in raw["data"]["data"]["rows"]]


def sp500_list():
    try:
        c = json.load(open(SP_CACHE, encoding="utf-8"))
        if time.time() - c.get("t", 0) < 7 * 86400 and len(c.get("s", [])) > 450:
            return c["s"]
    except Exception:
        pass
    txt = get("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv").decode("utf-8")
    syms = [key(row["Symbol"]) for row in csv.DictReader(io.StringIO(txt))]
    json.dump({"t": time.time(), "s": syms}, open(SP_CACHE, "w"))
    return syms


BAD = re.compile(r"warrant|\bright|\bunits?\b|preferred|depositary|notes due|debenture|acquisition|\betf\b|\bfund\b|subordinated|%", re.I)


def r2k_approx(sc):
    pool = [k for k, x in sc.items() if x["ulke"] == "United States" and x["mc"] and x["p"] and not BAD.search(x["ad"])
            and "^" not in x["s"] and len(x["s"]) <= 5]
    pool.sort(key=lambda k: -sc[k]["mc"])
    return pool[1000:3000]


def money(x):
    if x >= 1e12:
        return "$" + f"{x / 1e12:.2f}".replace(".", ",") + " tn"
    if x >= 1e10:
        return f"${x / 1e9:.0f} mr"
    if x >= 1e9:
        return "$" + f"{x / 1e9:.1f}".replace(".", ",") + " mr"
    return "$" + f"{x / 1e9:.1f}".replace(".", ",") + " mr"


def breadth(name, members, sc, portfolio, volhist, day):
    rows = [(k, sc[k]) for k in members if k in sc and sc[k]["d"] is not None and sc[k]["p"]]
    up = sum(1 for _, x in rows if x["d"] > 0)
    dn = sum(1 for _, x in rows if x["d"] < 0)
    dollar = sum((x["p"] or 0) * (x["v"] or 0) for _, x in rows)
    srt = sorted(rows, key=lambda kx: -kx[1]["d"])
    rank = {k: i + 1 for i, (k, _) in enumerate(srt)}
    prev = [v[name] for d, v in sorted(volhist.items()) if d < day and v.get(name)][-20:]
    vr = round(dollar / (sum(prev) / len(prev)), 2) if len(prev) >= 5 else None
    dv = sorted(rows, key=lambda kx: -(kx[1]["p"] * (kx[1]["v"] or 0)))[:5]
    return {
        "n": len(rows), "up": up, "dn": dn, "vol_usd": dollar, "vol": money(dollar), "vr": vr,
        "top": [[x["s"], short_name(x["ad"]), round(x["d"], 2)] for _, x in srt[:10]],
        "bot": [[x["s"], short_name(x["ad"]), round(x["d"], 2)] for _, x in srt[::-1][:10]],
        "dv": [[x["s"], short_name(x["ad"]), round(x["d"], 2), money(x["p"] * x["v"])] for _, x in dv],
        "mine": [[sc[k]["s"], rank[k], round(sc[k]["d"], 2)] for k in (key(p) for p in portfolio) if k in rank],
    }


def fetch_target(sym):
    try:
        raw = json.loads(get(f"https://api.nasdaq.com/api/analyst/{sym}/targetprice", timeout=15))
        o = (raw.get("data") or {}).get("consensusOverview") or {}
        b, h, s = o.get("buy") or 0, o.get("hold") or 0, o.get("sell") or 0
        n = b + h + s
        return sym, {
            "hedef": o.get("priceTarget"), "dusuk": o.get("lowPriceTarget"), "yuksek": o.get("highPriceTarget"),
            "al": b, "tut": h, "sat": s, "n": n,
            # Barchart ölçeğine benzer 1–5 puan (5 = güçlü al): al=5, tut=3, sat=1 ağırlıklı ortalama
            "puan": round((5 * b + 3 * h + 1 * s) / n, 2) if n else None,
        }
    except Exception as e:
        return sym, {"hata": str(e)[:80]}


def main():
    S = json.load(open("symbols.json", encoding="utf-8"))
    now = datetime.now(timezone.utc)
    ny = now.astimezone(NY)
    day = ny.strftime("%Y-%m-%d") if ny.hour >= 16 else None  # kapanış sonrası günün tarihi
    sc = screener()
    print(f"screener: {len(sc)} hisse")
    try:
        sp = sp500_list()
    except Exception as e:
        print("S&P 500 listesi alınamadı:", e)
        sp = []
    try:
        ndx = ndx_list()
    except Exception as e:
        print("Nasdaq-100 listesi alınamadı:", e)
        ndx = []
    r2k = r2k_approx(sc)
    portfolio = S.get("portfoy_abd", [])

    try:
        volhist = json.load(open(VOLH, encoding="utf-8"))
    except Exception:
        volhist = {}
    ref_day = day or ny.strftime("%Y-%m-%d")
    idx = {
        "sp500": breadth("sp500", sp, sc, portfolio, volhist, ref_day),
        "ndx": breadth("ndx", ndx, sc, portfolio, volhist, ref_day),
        "r2k": breadth("r2k", r2k, sc, portfolio, volhist, ref_day),
    }
    if day and ny.weekday() < 5:
        volhist[day] = {k: v["vol_usd"] for k, v in idx.items()}
        volhist = dict(sorted(volhist.items())[-40:])
        json.dump(volhist, open(VOLH, "w"), indent=0)

    # ---- analist hedefleri: günde bir kez (ABD kapanışından sonra) veya dosya 20 saatten eskiyse
    try:
        tg = json.load(open(TGT, encoding="utf-8"))
    except Exception:
        tg = {"t": 0, "v": {}}
    sector_syms = sorted({s for v in S.get("abd_sektor", {}).values() for s in v})
    want = sorted(set(sp) | set(ndx) | {key(s) for s in sector_syms + portfolio + S.get("abd_hedef_ek", []) + list(S.get("abd_hisse", {}))})
    want_syms = [sc[k]["s"] for k in want if k in sc]
    if time.time() - tg.get("t", 0) > 20 * 3600 or os.environ.get("HEDEF_ZORLA"):
        t0 = time.time()
        res = {}
        with ThreadPoolExecutor(4) as ex:
            for sym, r in ex.map(fetch_target, want_syms):
                res[key(sym)] = r
        ok = sum(1 for r in res.values() if r.get("hedef"))
        print(f"analist hedefleri: {ok}/{len(want_syms)} ({time.time() - t0:.0f} sn)")
        if ok > len(want_syms) * 0.5:
            tg = {"t": time.time(), "zaman": now.astimezone(TR).strftime("%d.%m.%Y %H:%M"), "v": res}
            json.dump(tg, open(TGT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    T = tg.get("v", {})

    # ---- sektör haritası evrenleri
    names = S.get("abd_kisa_ad", {})
    sectors = {}
    for lab, syms in S.get("abd_sektor", {}).items():
        rows = []
        for s in syms:
            x = sc.get(key(s))
            if not x or not x["p"]:
                continue
            t = T.get(key(s), {})
            pot = (t["hedef"] / x["p"] - 1) * 100 if t.get("hedef") else None
            rows.append({"s": s, "ad": names.get(s) or short_name(x["ad"], 22), "mc": x["mc"] or 0, "d": x["d"], "pot": pot, "n": t.get("n")})
        dset = {key(s) for s in S.get("abd_sektor_d_semboller", {}).get(lab, syms)}
        drows = [r for r in rows if key(r["s"]) in dset and r["d"] is not None and r["mc"]]
        mcsum = sum(r["mc"] for r in drows)
        sectors[lab] = {
            "d": round(sum(r["d"] * r["mc"] for r in drows) / mcsum, 2) if mcsum else None,
            "big": [[r["s"], r["ad"], money(r["mc"]), round(r["d"], 2)] for r in sorted(rows, key=lambda r: -r["mc"])[:5] if r["d"] is not None],
            "pot": [[r["s"], r["ad"], round(r["pot"], 1), "hedef ort." + (f" · {r['n']} analist" if r["n"] else "") + (" · mikro" if r["mc"] < 1e9 else "")]
                    for r in sorted([r for r in rows if r["pot"] is not None], key=lambda r: -r["pot"])[:5]],
        }

    out = {
        "guncelleme": now.astimezone(TR).strftime("%d.%m.%Y %H:%M (TSİ)"),
        "guncelleme_iso": now.astimezone(TR).isoformat(timespec="seconds"),
        "kapanis_sonrasi": bool(day),
        "hedef_zamani": tg.get("zaman"),
        "endeks": idx,
        "sektor": sectors,
        "hisse": {sc[k]["s"]: {"p": sc[k]["p"], "d": sc[k]["d"], "mc": sc[k]["mc"], "ad": short_name(sc[k]["ad"], 22),
                              "sektor": sc[k]["sektor"], "endustri": sc[k]["endustri"], **({"hedef": T[k].get("hedef"), "puan": T[k].get("puan"), "analist": T[k].get("n")} if T.get(k, {}).get("hedef") else {})}
                  for k in want if k in sc},
        "not": "Russell 2000 üyeleri yaklaşık (ABD adi hisseler, piyasa değeri sırası 1001–3000).",
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: [v["n"], v["up"], v["dn"], v["vol"], v["vr"]] for k, v in idx.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
