#!/usr/bin/env python3
"""
Can OS · pano güncelleyici (token tasarrufu için).

GitHub toplayıcısının data/latest.json dosyasındaki ABD verilerini panonun
Main.dc.html dosyasına yazar. Claude'un bu sayıları tek tek elle düzenlemesine
gerek kalmaz; Claude yalnızca yorum metinlerini ve Fintables/Barchart/Investing
kısımlarını yapar.

Kullanım:
    python3 apply.py <Main.dc.html yolu> [--latest data/latest.json] [--dry]

Güncellenenler:
  - H  : portföydeki ABD satırları (SOFI, URNJ, SMR, PG, SCCO ...): p, v, pl, plp, d, sp son eleman
  - MK : S&P 500, NASDAQ, RUSSELL 2000 değer ve günlük % (en iyi/kötü hisseler hariç)
  - RDU: Fırsat Radarı ABD fiyatları (p)
  - ETF: 45 ülke ETF'i (fiyat, getiriler, 52h yüksek/düşük; büyüklük/F/K/temettü korunur)
  - USF: ABD tema ETF'leri (getiriler; tema içi 1Y sıralaması) ve usBench (VOO 1Y)
  - ETF_ASOF / USF_ASOF tarih metinleri
Sonunda kısa bir özet (JSON) yazar: tarih, güncellenen sayısı, eksikler, eşiği aşan hareketler.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AYLAR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']

# Endeks seviyesi vekil ETF'ten hesaplanıyorsa kullanılan oran (endeks / ETF).
# 16 Eki 2026 kapanışında panodaki Investing değerlerinden ayarlandı.
# Pazartesi taramasında Investing değeri alınırsa: oran = endeks / ETF fiyatı ile tazelenebilir.
KALIBRASYON = {'^GSPC': 7659.44 / 763.25, '^RUT': 2721.37 / 270.44}

MK_MAP = {'S&P 500': '^GSPC', 'NASDAQ': '^IXIC', 'RUSSELL 2000': '^RUT'}
MK_SUB = {
    'S&P 500': 'GitHub · SPY’den hesaplı · hisseler Nasdaq',
    'RUSSELL 2000': 'GitHub · IWM’den hesaplı · hisseler ≈R2000',
}


def split_top(s):
    """JS literal argüman listesini en üst seviyedeki virgüllerden böl (tırnak ve parantez duyarlı)."""
    out, cur, depth, q, esc = [], [], 0, None, False
    for ch in s:
        if q:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == q:
                q = None
            continue
        if ch in "'\"`":
            q = ch
            cur.append(ch)
        elif ch in '([{':
            depth += 1
            cur.append(ch)
        elif ch in ')]}':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if ''.join(cur).strip():
        out.append(''.join(cur).strip())
    return out


def f2(x):
    return f'{x:.2f}'


def num(tok):
    try:
        return float(tok)
    except ValueError:
        return None


def tr_num(x, dec=2):
    s = f'{x:,.{dec}f}'
    return s.replace(',', '#').replace('.', ',').replace('#', '.')


def js(v):
    """Python listesini panodaki JS biçiminde yaz (tek tırnaklı metin)."""
    if isinstance(v, list):
        return '[' + ', '.join(js(x) for x in v) + ']'
    if isinstance(v, str):
        return "'" + v.replace("'", '’') + "'"
    if isinstance(v, float):
        return f'{v:.2f}'
    if v is None:
        return 'null'
    return str(v)


def cut(n, k=14):
    return n if len(n) <= k else n[: k - 1].rstrip() + '.'


def us_market_date(iso):
    """Verinin ait olduğu ABD işlem günü (16:00 NY kapanışı öncesiyse bir önceki iş günü)."""
    t = datetime.fromisoformat(iso).astimezone(ZoneInfo('America/New_York'))
    d = t.date()
    if t.hour < 16 or t.weekday() >= 5:
        if t.weekday() < 5:
            d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    html_path = args[0]
    latest_path = 'data/latest.json'
    if '--latest' in args:
        latest_path = args[args.index('--latest') + 1]
    dry = '--dry' in args

    L = json.load(open(latest_path, encoding='utf-8'))
    V = L['veriler']
    flat = {}
    for g in ('abd_hisse', 'tema_etf', 'ulke_etf', 'endeks', 'emtia', 'doviz'):
        for k, v in V.get(g, {}).items():
            flat.setdefault(k, v)

    asof = us_market_date(L['guncelleme_iso'])
    asof_txt = f'{asof.day} {AYLAR[asof.month - 1]}'
    age_h = (datetime.now(ZoneInfo('Europe/Istanbul')) - datetime.fromisoformat(L['guncelleme_iso'])).total_seconds() / 3600

    U = None
    try:
        U = json.load(open('data/us_market.json', encoding='utf-8'))
        u_age = (datetime.now(ZoneInfo('Europe/Istanbul')) - datetime.fromisoformat(U['guncelleme_iso'])).total_seconds() / 3600
        if u_age > 30:
            U = None
    except Exception:
        U = None
    UH = (U or {}).get('hisse', {})
    for sym, x in UH.items():
        if sym not in flat and x.get('p'):
            flat[sym] = {'fiyat': x['p'], 'gun': x['d'] or 0.0, 'kaynak': 'nasdaq-screener'}
    MK_IDX = {'S&P 500': 'sp500', 'NASDAQ': 'ndx', 'RUSSELL 2000': 'r2k'}
    MKD_IDX = {2: 'sp500', 3: 'ndx', 4: 'r2k'}
    rep_u = {'mkd': [], 'sektor': 0, 'rdu_hedef': 0}

    src = open(html_path, encoding='utf-8').read()
    lines = src.split('\n')
    rep = {'h': [], 'mk': [], 'rdu': [], 'etf': 0, 'usf': 0, 'eksik': []}

    in_mk = False
    for i, line in enumerate(lines):
        s = line.strip()

        # ---- portföy ABD satırları
        m = re.match(r"^(\s*)h\('([A-Z.\-]+)', (.*)\)(,?)\s*$", line)
        if m and "'USD'" in line:
            ind, sym, rest, comma = m.groups()
            a = split_top(f"'{sym}', " + rest)
            if len(a) == 19 and sym in flat:
                x = flat[sym]
                q, c, p = float(a[5]), float(a[6]), float(x['fiyat'])
                v = q * p
                pl = v - q * c
                plp = pl / (q * c) * 100 if c else 0
                a[7], a[8], a[9], a[10], a[11] = f2(p), f2(v), f2(pl), (f2(plp) if c else '0'), f2(x['gun'])
                sp = a[18].strip()
                if sp not in ('[]', ''):
                    items = split_top(sp[1:-1])
                    items[-1] = f'{p:g}'
                    a[18] = '[' + ', '.join(items) + ']'
                lines[i] = f"{ind}h({', '.join(a)}){comma}"
                rep['h'].append(f"{sym} {p:g} ({x['gun']:+.2f}%)")
            elif sym not in flat:
                rep['eksik'].append(sym)
            continue

        # ---- piyasalar (ABD endeksleri)
        if s.startswith('const MK = ['):
            in_mk = True
        elif in_mk and s.startswith('];'):
            in_mk = False
        if in_mk:
            m = re.match(r"^(\s*)\{ l: '([^']+)', (.*)$", line)
            if m and m.group(2) in MK_MAP:
                lab, sym = m.group(2), MK_MAP[m.group(2)]
                x = flat.get(sym)
                if x:
                    lvl = x['fiyat'] * KALIBRASYON.get(sym, 1.0) if x['kaynak'].startswith('vekil') else x['fiyat']
                    line2 = re.sub(r"v: '[^']*'", f"v: '{tr_num(lvl)}'", line, count=1)
                    line2 = re.sub(r"d: -?[0-9.]+", f"d: {x['gun']:.2f}", line2, count=1)
                    if lab in MK_SUB:
                        line2 = re.sub(r"sub: '[^']*'", f"sub: '{MK_SUB[lab]}'", line2, count=1)
                    E = (U or {}).get('endeks', {}).get(MK_IDX[lab])
                    if E and E.get('top'):
                        up = [[a, cut(b), c] for a, b, c in E['top'][:3]]
                        dn = [[a, cut(b), c] for a, b, c in E['bot'][:3]]
                        line2 = re.sub(r"up: \[.*?\]\], dn: \[.*?\]\]", lambda _: f"up: {js(up)}, dn: {js(dn)}", line2, count=1)
                    lines[i] = line2
                    rep['mk'].append(f"{lab} {tr_num(lvl)} ({x['gun']:+.2f}%)")
                else:
                    rep['eksik'].append(sym)
            continue

        # ---- Fırsat Radarı ABD
        m = re.match(r"^\s*\{ s: '([A-Z.\-]+)', n: .*sec: .*p: ([0-9.]+), fv:", line)
        if m and ', r: ' in line:
            sym = m.group(1)
            if sym in flat:
                p = flat[sym]['fiyat']
                line2 = re.sub(r"p: [0-9.]+, fv:", f"p: {f2(p)}, fv:", line, count=1)
                u = UH.get(sym, {})
                if u.get('hedef'):
                    line2 = re.sub(r"tg: [0-9.]+,", f"tg: {f2(u['hedef'])},", line2, count=1)
                    if u.get('puan') is not None:
                        line2 = re.sub(r"r: [0-9.]+,", f"r: {u['puan']:.2f},", line2, count=1)
                    rep_u['rdu_hedef'] += 1
                lines[i] = line2
                rep['rdu'].append(sym)
            else:
                rep['eksik'].append(sym)
            continue

        # ---- ülke ETF satırları
        m = re.match(r"^(\s*)\['([A-Z]+)', '([^']+)', ([0-9.\-]+), (.*)\](,?)\s*$", line)
        if m and lines_context_is(lines, i, 'const ETF = ['):
            ind, sym = m.group(1), m.group(2)
            a = split_top(line.strip().rstrip(',')[1:-1])
            x = V.get('ulke_etf', {}).get(sym) or flat.get(sym)
            if x and len(a) == 15:
                vals = [x['fiyat'], x['gun'], x['hafta'], x['ay1'], x['ay3'], x['ay6'], x['ybb'], x['yil1'], x['zirve52'], x['dip52']]
                for j, val in enumerate(vals):
                    if val is not None:
                        a[2 + j] = f2(val)
                lines[i] = f"{ind}[{', '.join(a)}]{m.group(6)}"
                rep['etf'] += 1
            elif not x:
                rep['eksik'].append(sym)
            continue

        # ---- ABD tema ETF'leri
        m = re.match(r"^(\s*)\{ l: '([^']+)', v: '([^']+)', f: \[(.*)\],\s*$", line)
        if m and lines_context_is(lines, i, 'const USF = ['):
            ind, lab, verdict, body = m.groups()
            items = split_top(body)
            rows = []
            for it in items:
                a = split_top(it.strip()[1:-1])
                sym = a[0].strip("'")
                x = flat.get(sym)
                if x:
                    for j, key in zip(range(5, 11), ['gun', 'hafta', 'ay1', 'ay3', 'ay6', 'yil1']):
                        if x.get(key) is not None:
                            a[j] = f2(x[key])
                    rep['usf'] += 1
                else:
                    rep['eksik'].append(sym)
                rows.append(a)
            if lab == 'Altın':
                rows.sort(key=lambda a: -(num(a[4]) or 0))
            elif lab != 'Yüksek Temettü Verimi':
                rows.sort(key=lambda a: -(num(a[10]) if num(a[10]) is not None else -1e9))
            body2 = ', '.join('[' + ', '.join(a) + ']' for a in rows)
            lines[i] = f"{ind}{{ l: '{lab}', v: '{verdict}', f: [{body2}],"
            continue

    if U:
        # ---- MKD (ABD kayıtları: 3., 4., 5.)
        try:
            a = next(i for i, l in enumerate(lines) if l.strip().startswith('const MKD = ['))
            b = next(i for i in range(a, len(lines)) if lines[i].strip().startswith('];'))
            starts = [i for i in range(a, b) if lines[i].strip().startswith('{ n:')]
            for ei, li in enumerate(starts):
                nm = MKD_IDX.get(ei)
                E = U['endeks'].get(nm) if nm else None
                if not E or not E.get('n'):
                    continue
                ind = lines[li][:len(lines[li]) - len(lines[li].lstrip())]
                vr = E['vr'] if E.get('vr') is not None else (re.search(r"vr: ([0-9.]+)", lines[li]) or [None, 'null'])[1]
                lines[li] = f"{ind}{{ n: {E['n']}, up: {E['up']}, dn: {E['dn']}, vol: '{E['vol']}', vr: {vr},"
                end = starts[ei + 1] if ei + 1 < len(starts) else b
                for j in range(li + 1, end):
                    t = lines[j].lstrip()
                    ind2 = lines[j][:len(lines[j]) - len(t)]
                    for fld in ('top', 'bot', 'dv', 'mine'):
                        if t.startswith(fld + ':'):
                            lines[j] = f"{ind2}{fld}: {js(E[fld])},"
                rep_u['mkd'].append(f"{nm}: {E['up']}↑/{E['dn']}↓ hacim {E['vol']} ×{E.get('vr')}")
        except StopIteration:
            pass
        # ---- SEC_US sayıları (d, big, pot) — görüş metinleri Claude'da
        for i, l in enumerate(lines):
            m = re.match(r"^(\s*)const SEC_US = (\[.*\]);\s*$", l)
            if not m:
                continue
            arr = json.loads(m.group(2))
            known = {}
            for it in arr:
                for r in it.get('big', []) + it.get('pot', []):
                    known.setdefault(r[0], r[1])
            for it in arr:
                X = U.get('sektor', {}).get(it['l'])
                if not X:
                    continue
                if X.get('d') is not None:
                    it['d'] = X['d']
                if X.get('big'):
                    it['big'] = [[r[0], known.get(r[0], r[1]), r[2], r[3]] for r in X['big']]
                if X.get('pot'):
                    it['pot'] = [[r[0], known.get(r[0], r[1]), r[2], r[3]] for r in X['pot']]
                rep_u['sektor'] += 1
            lines[i] = f"{m.group(1)}const SEC_US = {json.dumps(arr, ensure_ascii=False)};"
            break

    out = '\n'.join(lines)
    out = re.sub(r"const ETF_ASOF = '[^']*';", f"const ETF_ASOF = '{asof_txt}';", out)
    out = re.sub(r"const USF_ASOF = '[^']*';", f"const USF_ASOF = '{asof_txt}';", out)
    voo = flat.get('VOO')
    if voo and voo.get('yil1') is not None:
        out = re.sub(r"const usBench = [0-9.\-]+;", f"const usBench = {voo['yil1']:.2f};", out)

    # ---- eşiği aşan hareketler (kısa liste)
    S = json.load(open('symbols.json', encoding='utf-8')) if __import__('os').path.exists('symbols.json') else {}
    esik = S.get('alarm_esikleri', {})
    buyuk = []
    for g, items in V.items():
        e = esik.get(g)
        if not e:
            continue
        for k, x in items.items():
            if x.get('gun') is not None and abs(x['gun']) >= e:
                buyuk.append(f"{x.get('ad', k)} {x['gun']:+.1f}%")

    if not dry:
        open(html_path, 'w', encoding='utf-8').write(out)

    print(json.dumps({
        'veri_zamani': L['guncelleme'],
        'veri_yasi_saat': round(age_h, 1),
        'abd_kapanis_tarihi': asof_txt,
        'portfoy': rep['h'],
        'endeksler': rep['mk'],
        'radar_abd': len(rep['rdu']),
        'radar_abd_hedef': rep_u['rdu_hedef'],
        'abd_piyasa_detayi': rep_u['mkd'] or 'us_market.json yok/eski — Barchart ile yap',
        'abd_sektor_guncellenen': rep_u['sektor'],
        'ulke_etf': rep['etf'],
        'tema_etf': rep['usf'],
        'eksik': sorted(set(rep['eksik'])),
        'toplayicida_basarisiz': L.get('basarisiz', []),
        'esik_asan': buyuk[:25],
        'yazildi': not dry,
    }, ensure_ascii=False, indent=1))


def lines_context_is(lines, i, header):
    """i. satırın hangi 'const X = [' bloğunun içinde olduğunu bul."""
    for j in range(i, max(i - 200, -1), -1):
        t = lines[j].strip()
        if t.startswith('const ') and t.endswith('= ['):
            return t == header
    return False


if __name__ == '__main__':
    main()
