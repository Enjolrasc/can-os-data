"""Tek seferlik erişim testi: hangi kaynaklar GitHub sunucusundan çalışıyor?"""
import json, urllib.request, urllib.parse, time, datetime
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}
def get(url, data=None, hdr=None, timeout=25):
    h = dict(H); h.update(hdr or {})
    req = urllib.request.Request(url, data=data, headers=h)
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
        return r.status, b, round(time.time() - t, 1)
out = {}
def test(name, url, data=None, hdr=None, keep=600):
    try:
        st, b, dt = get(url, data, hdr)
        out[name] = {"ok": True, "status": st, "bytes": len(b), "sn": dt, "ornek": b[:keep].decode("utf-8", "replace")}
    except Exception as e:
        out[name] = {"ok": False, "hata": str(e)[:300]}
nh = {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
test("nasdaq_screener", "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true", hdr=nh, keep=1500)
test("nasdaq_target", "https://api.nasdaq.com/api/analyst/MU/targetprice", hdr=nh, keep=1500)
test("nasdaq_ratings", "https://api.nasdaq.com/api/analyst/MU/ratings", hdr=nh, keep=800)
test("nasdaq_summary", "https://api.nasdaq.com/api/quote/MU/summary?assetclass=stocks", hdr=nh, keep=2500)
test("nasdaq_ndx_list", "https://api.nasdaq.com/api/quote/list-type/nasdaq100", hdr=nh, keep=800)
test("sp500_csv", "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv", keep=300)
test("iwm_holdings", "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund", keep=600)
d2 = datetime.date.today(); d1 = d2 - datetime.timedelta(days=7)
form = urllib.parse.urlencode({"fontip": "YAT", "sfontur": "", "fonkod": "KUT", "fongrup": "", "bastarih": d1.strftime("%d.%m.%Y"), "bittarih": d2.strftime("%d.%m.%Y"), "fonturkod": "", "fonunvantip": "", "strperiod": "1,1,1,1,1,1,1", "islemdurum": "1"}).encode()
th = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", "X-Requested-With": "XMLHttpRequest", "Origin": "https://www.tefas.gov.tr", "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx"}
test("tefas_history", "https://www.tefas.gov.tr/api/DB/BindHistoryInfo", data=form, hdr=th, keep=800)
test("tefas_main", "https://www.tefas.gov.tr/", keep=200)
test("fundturkey", "https://www.fundturkey.com.tr/api/DB/BindHistoryInfo", data=form, hdr=dict(th, Origin="https://www.fundturkey.com.tr", Referer="https://www.fundturkey.com.tr/TarihselVeriler.aspx"), keep=800)
json.dump(out, open("data/probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: (v["ok"], v.get("status"), v.get("bytes"), v.get("hata", "")[:120]) for k, v in out.items()}, ensure_ascii=False, indent=1))
