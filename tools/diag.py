import urllib.request, json, http.cookiejar
jar=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36","Accept":"application/json, text/plain, */*"}
def get(u,h=None):
    hh=dict(UA); hh.update(h or {})
    try: return op.open(urllib.request.Request(u,headers=hh),timeout=15).read().decode('utf-8','replace')
    except Exception as e: return 'ERR '+str(e)
N={"Origin":"https://www.nasdaq.com","Referer":"https://www.nasdaq.com/"}
r=get("https://api.nasdaq.com/api/quote/PG/info?assetclass=stocks",N)
try:
    d=json.loads(r)['data']; print('NASDAQ info primary',d.get('primaryData')); print('secondary',d.get('secondaryData')); print('status',d.get('marketStatus'))
except Exception as e: print('NASDAQ info',r[:300])
r=get("https://api.nasdaq.com/api/quote/PG/historical?assetclass=stocks&fromdate=2026-10-10&todate=2026-10-20&limit=10",N); print('NASDAQ hist',r[:400])
r=get("https://api.nasdaq.com/api/quote/COMP/info?assetclass=index",N); print('COMP',r[:400])
r=get("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=3&exchange=nyse",N); print('SCREENER',r[:500])
print('STOOQ',get("https://stooq.com/q/l/?s=pg.us,spy.us,^spx&f=sd2t2ohlcv&h&e=csv")[:300])
print('YAHOO',get("https://query2.finance.yahoo.com/v8/finance/chart/PG?range=5d&interval=1d")[:300])
print('CNBC',get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=PG|.SPX|.IXIC|.RUT&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")[:600])
