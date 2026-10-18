"""Can OS · veri toplayıcı

Bu program, symbols.json dosyasındaki sembollerin fiyatlarını ücretsiz
kaynaklardan çeker ve data/ klasörüne yazar. GitHub Actions bunu belirli
saatlerde otomatik çalıştırır; yapay zekâ kullanmaz, token harcamaz.

Kaynaklar (sırayla denenir):
  1. Yahoo Finance (ana kaynak)
  2. Stooq (Yahoo cevap vermezse ABD hisse ve ETF'leri için yedek)
  3. Frankfurter / Avrupa Merkez Bankası (döviz kurları için çapraz kontrol)

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
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
TR = timezone(timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def http_get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- kaynaklar

def from_yahoo(sym):
    """Yahoo Finance: 1 yıllık günlük kapanışlar + anlık fiyat."""
    q = urllib.parse.quote(sym)
    last_err = None
    for host in ("query1", "query2"):
        try:
            raw = http_get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range=1y&interval=1d&includePrePost=false")
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
            return {
                "rows": rows,
                "price": float(price),
                "time": datetime.fromtimestamp(mtime, TR) if mtime else None,
                "currency": meta.get("currency"),
                "source": "yahoo",
            }
        except Exception as e:  # noqa: BLE001 — bir sonraki sunucuyu dene
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"yahoo: {last_err}")


def from_stooq(sym):
    """Stooq yedeği: yalnızca ABD hisse/ETF'leri (ör. SPY -> spy.us)."""
    if any(ch in sym for ch in "=^."):
        raise RuntimeError("stooq: desteklenmeyen sembol")
    end = datetime.now(TR).date()
    start = end - timedelta(days=380)
    url = f"https://stooq.com/q/d/l/?s={sym.lower()}.us&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
    text = http_get(url)
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append((datetime.strptime(r["Date"], "%Y-%m-%d").date(), float(r["Close"])))
        except (KeyError, ValueError):
            continue
    if not rows:
        raise RuntimeError("stooq: boş veri")
    return {"rows": rows, "price": rows[-1][1], "time": None, "currency": "USD", "source": "stooq"}


def fetch(sym):
    errors = []
    for fn in (from_yahoo, from_stooq):
        try:
            return fn(sym)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    raise RuntimeError(" | ".join(errors))


# ---------------------------------------------------------------- hesaplar

def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100, 2)


def metrics(d):
    rows, price = d["rows"], d["price"]
    today = (d["time"] or datetime.now(TR)).date()
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

    # 6 paralel istek: hızlı ama kaynakları yormayacak kadar.
    with ThreadPoolExecutor(max_workers=6) as pool:
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
