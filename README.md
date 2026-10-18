# Can OS · veri deposu

Bu depo, **Can OS · Finans Ajanı** panosunun fiyat verilerini toplar.
Yapay zekâ kullanmaz, token harcamaz; GitHub'ın kendi sunucularında, bilgisayar kapalıyken de çalışır.

## Nasıl çalışıyor?

1. **`symbols.json`** — izlenen semboller listesi (döviz, emtia, endeks, ABD hisseleri, ülke ve tema ETF'leri) ve gece bekçisinin alarm eşikleri.
2. **`collect.py`** — fiyatları ücretsiz kaynaklardan çeken program (Yahoo Finance; yedek olarak Stooq; dövizde Avrupa Merkez Bankası ile çapraz kontrol).
3. **`.github/workflows/collect.yml`** — zamanlayıcı:
   - hafta içi 10:00–23:30 (TSİ) arası her 30 dakikada bir,
   - geceleri 00:00–08:00 arası 2 saatte bir (gece bekçisi).

## Çıktılar (`data/` klasörü)

| Dosya | İçerik |
|---|---|
| `latest.json` | En son fiyatlar; günlük, haftalık, 1/3/6 aylık, yılbaşından beri ve 1 yıllık getiriler; 52 haftalık zirve/dip |
| `alerts.json` | Gece bekçisi: eşiği aşan hareketler (son 7 gün) |
| `history/YYYY-AA-GG.json` | Her günün son durumu — geçmiş burada birikir |

Claude, akşam güncellemesinde ve sabah brifinginde bu dosyaları okuyup panoya yorum yazar.

## Elle çalıştırma

GitHub'da üstteki **Actions** sekmesi → **Fiyat topla** → **Run workflow**.
