# Can OS · ajan portföyü kuralları

> Panodaki **13 // AJAN PORTFÖYÜ** bölümünü yöneten kurallar. Claude bu dosyayı gece görevinin D bölümünde okur. Kuralı değiştirmek için bu dosyayı düzenlemek yeterlidir.

## Amaç
Ajan, Can'ın örnek alacağı uzman bir analist gibi yatırım yapsın. riski ve fırsatları görsün, dengeli, sabırlı, sürekli al sat yapmayan ama fırsatları da kaçırmayan bir yatırımcı olsun. Can her işlemin mantığını panodan takip edip öğrenebilsin diye her alım/satım gerekçesiyle yazılır. Ajan sadece radardaki hisseleri değil, bağımsız şekilde bist ve abd borsalarına da yatirim yapabilir. Gerçek hesapla bağlantısı yoktur, emir verilmez. 

## Başlangıç
- Sermaye: **₺150.000**, başlangıç 19.10.2026.
- Komisyon ve vergi dahil. midas'ın komisyonu kullanılsın. güncel vergiler dahil edilsin. BIST’te tam lot, ABD’de kesirli hisse serbest.
- Kıyas: BIST 100 (başlangıç 11.626,87).

## Dağılım sınırları
| Kural | Sınır |
|---|---|
| Tek hisse | en fazla %20 |
| Tek sektör | en fazla %30 |
| ABD hisseleri toplamı | en fazla %30 |
| Altın / kıymetli maden | en fazla %15 |
| Faizsiz nakit (kira sertifikası fonu + serbest nakit) | en az %5 |

## Faizsiz nakit
Nakit asla faizli araçta veya para piyasası fonunda tutulmaz. Likidite: kira sertifikası (sukuk) katılım fonu — varsayılan **KTV** (Kuveyt Türk kısa vadeli kira sertifikaları katılım fonu) — ve katılım hesabında serbest nakit.

## Alınmayanlar
CCOLA, alkollü içecek şirketleri, kumar/bahis şirketleri, İsrail ortaklı şirketler. Bunlar panodaki takip listelerinde kalabilir; yalnızca ajan almaz.

## Hisse seçimi
- Kârlı (son 12 ay ana ortaklık net kârı pozitif).
- F/K: BIST’te ≤ 25, ABD’de ≤ 35.
- Net borç / FAVÖK ≤ 3 (bankalarda aranmaz).
- BIST’te son 4,5 ayda en az 4 aracı kurumun hedef fiyatı; ABD’de analist konsensüsü “al” tarafında.
- Temettü ödeyen ve sektör çeşitliliği sağlayanlar öncelikli. Can’ın ana portföyündeki yoğunlukları (ör. otomotiv) büyütmemeye dikkat edilir.
- Aday havuzu: panodaki Fırsat Radarı (RD/RDU), radarWatch/radarUSWatch ve sektör haritası.

## Alım-satım davranışı
1. Kaliteli hisse düştü diye satılmaz. Maliyetin %10 altına inerse ve nakit + limit uygunsa **ortalama düşürülür** (EKLE).
2. “Çöp” hisseden çıkılır: zarara geçti, yeni bilançoda belirgin bozulma, net borç/FAVÖK 3’ü aştı veya hikâye bozuldu (SAT).
3. Hedefe (aracı kurum ortalaması / analist konsensüsü) ulaşan ya da ağırlığı %20’yi aşan pozisyonda kısmi kâr alınır (AZALT).
4. Sakin işlem: **haftada en fazla 5 işlem** (temettü kayıtları hariç). Acele yok; şüphede bekle. 5 işlemin hepsini doldurması zorunlu değil. en fazla 5 olsun.
5. Temettü: net tutar nakde eklenir (TEMETTÜ kaydı), sonra kurallara göre yeniden yatırılır.
6. Satıştan gelen nakit en geç bir hafta içinde kurallara uyan bir adaya veya KTV’ye yatırılır.

## Kayıt
- Her işlem `AG_LOG` dizisine en üste yazılır: `{ when: 'gg.aa', act: 'AL|SAT|EKLE|AZALT|TEMETTÜ', sym, detail: 'adet × fiyat = tutar', why: 'tek cümle, veriye dayalı neden' }`.
- Her gece `AG_DAY` günlük özeti yazılır (3–5 cümle): değer ve günlük değişim → en çok etkileyen pozisyonlar → BIST 100’e göre durum → varsa işlem ve nedeni → yarın neyi izlediği.
- Yatırım tavsiyesi dili kullanılmaz; panodaki “yatırım tavsiyesi değildir” notu korunur.
