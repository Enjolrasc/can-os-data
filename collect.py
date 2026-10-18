"""Can OS · veri toplayıcı

Bu program, symbols.json dosyasındaki sembollerin fiyatlarını ücretsiz
kaynaklardan çeker ve data/ klasörüne yazar. GitHub Actions bunu belirli
saatlerde otomatik çalıştırır; yapay zekâ kullanmaz, token harcamaz.

Kaynaklar (sırayla denenir, ilk başarılı olan kullanılır):
  1. Yahoo Finance (ana kaynak; oturum çerezi ile)
  2. Nasdaq.com (ABD hisse ve ETF'leri için yedek)
  3. Stooq (ABD hisse ve ETF'leri için ikinci yedek)
  4. Avrupa Merkez Bankası / Frankfurter (döviz için yedek ve çapraz kontrol)

Çıktılar:
  data/latest.json          en son fiyatlar ve getiriler
  data/alerts.json          gece bekçisi: eşiği aşan hareketler
  data/history/GG-AA-YYYY   her günün son durumu (geçmiş birikir)

Yalnızca Python'un kendi kütüphanelerini kullanır; ek kurulum gerekmez.
"""

import csv
import io
import json
import os
import time
import threading
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
TR = timezone(timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_lock = threading.Lock()
_state = {"crumb": None, "yahoo_fail": 0, "stooq_fail": 0, "nasdaq_fail": 0}


def http_get(url, timeout=10, headers=None):
    h = dict(UA)
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with _opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def yahoo_login():
    """Yahoo artık oturum çerezi + 'crumb' anahtarı istiyor; bir kez alıp tüm isteklerde kullanırız."""
    try:
        try:
            http_get("https://fc.yahoo.com", timeout=10)
        except Exception:  # noqa: BLE001 — bu adres 404 döner ama çerezi yine de verir
            pass
        crumb = http_get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10).strip()
        if crumb and "<" not in crumb and len(crumb) < 40:
            _state["crumb"] = crumb
            return True
    except Exception as e:  # noqa: BLE001
        print(f"  Yahoo oturumu açılamadı: {e}", flush=True)
    return False


# ---------------------------------------------------------------- kaynaklar

def from_yahoo(sym):
    """Yahoo Finance: 1 yıllık günlük kapanışlar + anlık fiyat."""
    if _state["yahoo_fail"] >= 8:
        raise RuntimeError("yahoo: art arda hata, bu turda atlandı")
    q = urllib.parse.quote(sym)
    crumb = "&crumb=" + urllib.parse.quote(_state["crumb"]) if _state["crumb"] else ""
    last_err = None
    for attempt, host in enumerate(("query2", "query1", "query2")):
        try:
            raw = http_get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range=1y&interval=1d&includePrePost=false{crumb}")
            res = json.loads(raw)["chart"]["result"][0]
            meta = res["meta"]
            ts = res.get("timestamp") or []
            closes = res["indicators"]["quote"][0].get("close") or []
            rows = [(datetime.fromtimestamp(t, TR).date(), c) for t, c in zip(ts, closes) if c is not None]
            price = meta.get("regularMarketPrice")
            if price is None and rows:
                price = rows[-1][1]
            if price is None or not rows:
                raise ValueError("boş veri")
            mtime = meta.get("regularMarketTime")
            with _lock:
                _state["yahoo_fail"] = 0
            return {
                "rows": rows,
                "price": float(price),
                "time": datetime.fromtimestamp(mtime, TR) if mtime else None,
                "currency": meta.get("currency"),
                "source": "yahoo",
            }
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1) if "429" in str(e) else 0.3)
    with _lock:
        _state["yahoo_fail"] += 1
    raise RuntimeError(f"yahoo: {last_err}")


def from_nasdaq(sym):
    """Nasdaq.com yedeği: ABD hisse ve ETF'leri için 1 yıllık kapanışlar."""
    if any(ch in sym for ch in "=^.") or _state["nasdaq_fail"] >= 8:
        raise RuntimeError("nasdaq: atlandı")
    end = datetime.now(TR).date()
    start = end - timedelta(days=375)
    hdr = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
    last_err = None
    for cls in ("etf", "stocks"):
        try:
            raw = http_get(f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={cls}&fromdate={start}&todate={end}&limit=400", headers=hdr)
            rows_raw = ((json.loads(raw).get("data") or {}).get("tradesTable") or {}).get("rows") or []
            rows = []
            for r in rows_raw:
                try:
                    rows.append((datetime.strptime(r["date"], "%m/%d/%Y").date(), float(str(r["close"]).replace("$", "").replace(",", ""))))
                except (KeyError, ValueError):
                    continue
            if rows:
                rows.sort()
                with _lock:
                    _state["nasdaq_fail"] = 0
                return {"rows": rows, "price": rows[-1][1], "time": None, "currency": "USD", "source": "nasdaq"}
        except Exception as e:  # noqa: BLE001
            last_err = e
    with _lock:
        _state["nasdaq_fail"] += 1
    raise RuntimeError(f"nasdaq: {last_err or 'boş veri'}")


def from_stooq(sym):
    """Stooq yedeği: yalnızca ABD hisse/ETF'leri (ör. SPY -> spy.us)."""
    if any(ch in sym for ch in "=^.") or _state["stooq_fail"] >= 5:
        raise RuntimeError("stooq: atlandı")
    end = datetime.now(TR).date()
    start = end - timedelta(days=380)
    try:
        text = http_get(f"https://stooq.com/q/d/l/?s={sym.lower()}.us&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d", timeout=8)
    except Exception as e:  # noqa: BLE001
        with _lock:
            _state["stooq_fail"] += 1
        raise RuntimeError(f"stooq: {e}")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append((datetime.strptime(r["Date"], "%Y-%m-%d").date(), float(r["Close"])))
        except (KeyError, ValueError):
            continue
    if not rows:
        raise RuntimeError("stooq: boş veri")
    return {"rows": rows, "price": rows[-1][1], "time": None, "currency": "USD", "source": "stooq"}


ECB_PAIRS = {"USDTRY=X": ("USD", "TRY"), "EURTRY=X": ("EUR", "TRY"), "GBPTRY=X": ("GBP", "TRY"),
             "CHFTRY=X": ("CHF", "TRY"), "JPYTRY=X": ("JPY", "TRY"), "EURUSD=X": ("EUR", "USD")}


def from_ecb(sym):
    """Avrupa Merkez Bankası (Frankfurter): dövizde günlük kurlar, 1 yıllık geçmiş."""
    if sym not in ECB_PAIRS:
        raise RuntimeError("ecb: desteklenmeyen sembol")
    base, quote = ECB_PAIRS[sym]
    end = datetime.now(TR).date()
    start = end - timedelta(days=375)
    rates = json.loads(http_get(f"https://api.frankfurter.app/{start}..{end}?from={base}&to={quote}"))["rates"]
    rows = sorted((datetime.strptime(dt, "%Y-%m-%d").date(), v[quote]) for dt, v in rates.items() if quote in v)
    if not rows:
        raise RuntimeError("ecb: boş veri")
    return {"rows": rows, "price": rows[-1][1], "time": None, "currency": quote, "source": "ecb"}



NASDAQ_INDEX = {"^GSPC": "SPX", "^IXIC": "COMP", "^NDX": "NDX", "^RUT": "RUT", "^DJI": "INDU", "^VIX": "VIX"}
NASDAQ_COMMODITY = {"GC=F": "GC:CMX", "SI=F": "SI:CMX", "PL=F": "PL:NMX", "PA=F": "PA:NMX", "BZ=F": "BZ:NMX",
                    "CL=F": "CL:NMX", "HO=F": "HO:NMX", "NG=F": "NG:NMX", "HG=F": "HG:CMX", "ALI=F": "ALI:CMX",
                    "ZW=F": "ZW:CBT", "ZC=F": "ZC:CBT", "ZS=F": "ZS:CBT", "KC=F": "KC:NYB", "CC=F": "CC:NYB",
                    "SB=F": "SB:NYB", "CT=F": "CT:NYB", "TTF=F": "TFM:IEU"}
# Doğrudan fiyat bulunamazsa, aynı varlığı izleyen ETF'in getirileri "vekil" olarak kullanılır (fiyat seviyesi değil, % değişim).
PROXY_ETF = {"^GSPC": "SPY", "^IXIC": "QQQ", "^NDX": "QQQ", "^RUT": "IWM", "^DJI": "DIA", "^VIX": "VIXY",
             "GC=F": "GLD", "SI=F": "SLV", "PL=F": "PPLT", "PA=F": "PALL", "BZ=F": "BNO", "CL=F": "USO",
             "NG=F": "UNG", "HG=F": "CPER", "ZW=F": "WEAT", "ZC=F": "CORN", "ZS=F": "SOYB", "SB=F": "CANE"}


def _nasdaq_hist(code, cls):
    end = datetime.now(TR).date()
    start = end - timedelta(days=375)
    hdr = {"Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
    raw = http_get(f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(code)}/historical?assetclass={cls}&fromdate={start}&todate={end}&limit=400", headers=hdr)
    rows_raw = ((json.loads(raw).get("data") or {}).get("tradesTable") or {}).get("rows") or []
    rows = []
    for r in rows_raw:
        try:
            rows.append((datetime.strptime(r["date"], "%m/%d/%Y").date(), float(str(r.get("close") or r.get("value")).replace("$", "").replace(",", ""))))
        except (KeyError, ValueError, TypeError):
            continue
    rows.sort()
    return rows


def from_nasdaq_special(sym):
    """Nasdaq.com: endeksler ve vadeli emtialar."""
    if sym in NASDAQ_INDEX:
        code, cls = NASDAQ_INDEX[sym], "index"
    elif sym in NASDAQ_COMMODITY:
        code, cls = NASDAQ_COMMODITY[sym], "commodities"
    else:
        raise RuntimeError("nasdaq: desteklenmeyen sembol")
    rows = _nasdaq_hist(code, cls)
    if not rows:
        raise RuntimeError("nasdaq: boş veri")
    return {"rows": rows, "price": rows[-1][1], "time": None, "currency": "USD", "source": "nasdaq"}


def from_proxy(sym):
    if sym not in PROXY_ETF:
        raise RuntimeError("vekil: desteklenmeyen sembol")
    d = from_nasdaq(PROXY_ETF[sym])
    d["source"] = "vekil:" + PROXY_ETF[sym]
    return d


def from_dxy(sym):
    """Dolar endeksi (DXY), ICE formülüyle ECB kurlarından hesaplanır."""
    if sym != "DX-Y.NYB":
        raise RuntimeError("dxy: desteklenmeyen sembol")
    end = datetime.now(TR).date()
    start = end - timedelta(days=375)
    rates = json.loads(http_get(f"https://api.frankfurter.app/{start}..{end}?from=USD&to=EUR,JPY,GBP,CAD,SEK,CHF"))["rates"]
    rows = []
    for dt, r in rates.items():
        try:
            v = (50.14348112 * (1 / r["EUR"]) ** -0.576 * r["JPY"] ** 0.136 * (1 / r["GBP"]) ** -0.119
                 * r["CAD"] ** 0.091 * r["SEK"] ** 0.042 * r["CHF"] ** 0.036)
            rows.append((datetime.strptime(dt, "%Y-%m-%d").date(), v))
        except (KeyError, ZeroDivisionError):
            continue
    rows.sort()
    if not rows:
        raise RuntimeError("dxy: boş veri")
    return {"rows": rows, "price": rows[-1][1], "time": None, "currency": None, "source": "ecb-hesap"}


def fetch(sym):
    errors = []
    for fn in (from_yahoo, from_nasdaq_special, from_nasdaq, from_stooq, from_ecb, from_dxy, from_proxy):
        try:
            return fn(sym)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "atlandı" not in msg and "desteklenmeyen" not in msg:
                errors.append(msg[:90])
    raise RuntimeError(" | ".join(errors) or "kaynak yok")


# ---------------------------------------------------------------- hesaplar

def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100, 2)


def metrics(d):
    rows, price = d["rows"], d["price"]
    today = (d["time"] or datetime.now(TR)).date()
    if d["time"] is None and len(rows) > 1:
        # Anlık fiyat yok: fiyat = son kapanış; getiriler bir önceki kapanışa göre hesaplanır.
        hist = rows[:-1]
    else:
        # Son satır bugünün (henüz kapanmamış) mumu ise önceki kapanışı ondan bir önceki satır verir.
        hist = rows[:-1] if rows and rows[-1][0] >= today and len(rows) > 1 else rows
    closes = [c for _, c in hist]

    def back(n):
        return closes[-n] if len(closes) >= n else None

    prev_year = [c for dt, c in hist if dt.year < today.year]
    hi = max([c for _, c in rows] + [price])
    lo = min([c for _, c in rows] + [price])
    return {
        "fiyat": round(price, 6),
        "gun": pct(price, back(1)),
        "hafta": pct(price, back(5)),
        "ay1": pct(price, back(21)),
        "ay3": pct(price, back(63)),
        "ay6": pct(price, back(126)),
        "ybb": pct(price, prev_year[-1] if prev_year else None),
        "yil1": pct(price, closes[0] if len(closes) >= 240 else None),
        "zirve52": round(hi, 6),
        "dip52": round(lo, 6),
        "zirveye": pct(price, hi),
        "para": d["currency"],
        "zaman": (d["time"] or datetime.now(TR)).strftime("%d.%m.%Y %H:%M"),
        "kaynak": d["source"],
    }


def fx_cross_check(fx):
    """Döviz kurlarını Avrupa Merkez Bankası verisiyle karşılaştırır (günde bir yayımlanır)."""
    out = {}
    try:
        ecb = json.loads(http_get("https://api.frankfurter.app/latest?from=USD&to=TRY,EUR,GBP,CHF,JPY"))["rates"]
        usdtry = ecb.get("TRY")
        refs = {
            "USDTRY=X": usdtry,
            "EURTRY=X": usdtry / ecb["EUR"] if usdtry and ecb.get("EUR") else None,
            "GBPTRY=X": usdtry / ecb["GBP"] if usdtry and ecb.get("GBP") else None,
            "CHFTRY=X": usdtry / ecb["CHF"] if usdtry and ecb.get("CHF") else None,
            "EURUSD=X": 1 / ecb["EUR"] if ecb.get("EUR") else None,
        }
        for sym, ref in refs.items():
            mine = fx.get(sym, {}).get("fiyat")
            if ref and mine:
                diff = pct(mine, ref)
                out[sym] = {"ecb": round(ref, 4), "fark_yuzde": diff, "uyari": abs(diff) > 1.5}
    except Exception as e:  # noqa: BLE001
        out["hata"] = str(e)
    return out


# ---------------------------------------------------------------- ana akış

def main():
    cfg = json.load(open(os.path.join(ROOT, "symbols.json"), encoding="utf-8"))
    thresholds = cfg.get("alarm_esikleri", {})
    now = datetime.now(TR)
    data, failed, by_source = {}, {}, {}

    jobs = []
    for group, items in cfg.items():
        if group.startswith("_") or group == "alarm_esikleri":
            continue
        names = items if isinstance(items, dict) else {s: s for s in items}
        data[group] = {}
        for sym, name in names.items():
            if not sym.startswith("_"):
                jobs.append((group, sym, name))

    def work(job):
        group, sym, name = job
        try:
            m = metrics(fetch(sym))
            m["ad"] = name
            return group, sym, m, None
        except Exception as e:  # noqa: BLE001
            return group, sym, None, str(e)[:200]

    # 3 paralel istek: hızlı ama kaynakları yormayacak kadar.
    print('Yahoo oturumu: ' + ('açık' if yahoo_login() else 'yok (yedek kaynaklar kullanılacak)'), flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for group, sym, m, err in pool.map(work, jobs):
            if m:
                data[group][sym] = m
                by_source[m["kaynak"]] = by_source.get(m["kaynak"], 0) + 1
            else:
                failed[sym] = err

    latest = {
        "guncelleme": now.strftime("%d.%m.%Y %H:%M") + " (TSİ)",
        "guncelleme_iso": now.isoformat(timespec="seconds"),
        "kaynaklar": by_source,
        "basarisiz": failed,
        "doviz_capraz_kontrol": fx_cross_check(data.get("doviz", {})),
        "veriler": data,
    }
    os.makedirs(os.path.join(DATA, "history"), exist_ok=True)
    ok_count = sum(len(v) for v in data.values())
    if ok_count < 0.3 * len(jobs):
        # Kaynaklar büyük ölçüde cevap vermediyse elimizdeki son iyi veriyi bozmayalım.
        print(f"UYARI: yalnızca {ok_count}/{len(jobs)} sembol alınabildi; latest.json güncellenmedi.", flush=True)
        for s_, e_ in list(failed.items())[:40]:
            print(f"  ! {s_}: {e_}")
        return
    with open(os.path.join(DATA, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "history", now.strftime("%Y-%m-%d") + ".json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, separators=(",", ":"))

    # Gece bekçisi: eşiği aşan günlük hareketleri kaydet (aynı gün aynı sembol için tek kayıt, en günceli).
    alerts_path = os.path.join(DATA, "alerts.json")
    try:
        alerts = json.load(open(alerts_path, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        alerts = []
    day = now.strftime("%Y-%m-%d")
    for group, items in data.items():
        limit = thresholds.get(group)
        if not limit:
            continue
        for sym, m in items.items():
            if m.get("gun") is not None and abs(m["gun"]) >= limit:
                alerts = [a for a in alerts if not (a["sembol"] == sym and a["gun_tarihi"] == day)]
                alerts.append({
                    "gun_tarihi": day, "zaman": now.strftime("%d.%m.%Y %H:%M"), "grup": group,
                    "sembol": sym, "ad": m["ad"], "degisim": m["gun"], "fiyat": m["fiyat"], "esik": limit,
                })
    cutoff = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    alerts = [a for a in alerts if a["gun_tarihi"] >= cutoff]
    with open(alerts_path, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in data.values())
    print(f"{now:%d.%m.%Y %H:%M} · {total} sembol alındı · kaynaklar: {by_source} · başarısız: {len(failed)}")
    for s, e in failed.items():
        print(f"  ! {s}: {e}")


if __name__ == "__main__":
    main()
