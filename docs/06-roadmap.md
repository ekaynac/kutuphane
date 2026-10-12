# Kütüphane — yol haritası

Tarih: 2026-10-12. Durum: **onaylandı (D45).** Takvim yok; takvim M0 ölçümünden ve ilk M1
diliminden sonra konur. Her aşamanın çıkışı **makinece doğrulanabilir** bir ölçüttür.

## Genel görünüm

```
M0 Ölçüm ─────────────┐ (sürüyor, M1'e paralel)
                      ▼ bileşen kararı, ontoloji gözden geçirmesi
M1 Uçtan uca kanıt ── M1a → M1b → M1c → M1d → M1e → M1f ──▶ kabul testleri AT-01…AT-16
                      ▲ kapı: LLMDAP #222, #223
M2 Koruma + federasyon başlangıcı (envelope/sealed, recall, master rolü, karar modeli ürünleşmesi)
M3 Federasyon + tüketiciler (çok kurulumlu master, InfraMedic tüketimi, stüdyo çıktıları)
```

## M0 — Ölçüm (sürüyor)

| İş | Çıktı | Durum |
|---|---|---|
| İnsan etiketli küme (D43) | kategori/hassasiyet/çıkış etiketleri; soru–pasaj ilgisi | sayfa açık; etiketleme operatörde |
| Kamuya açık mevzuat seti (D41 b) | `CtnkyaABC/turkish-law-corpus` (CC BY 4.0) alt kümesi + elle kontrollü 290 soru | aday seçildi |
| Retrieval ölçümü (D31) | gömücü/reranker/BM25 karşılaştırması; GPU ve CPU kipi (D42) | etiketlerden sonra |
| Laya shadow (D44) | insan etiketine karşı doğruluk, kalibrasyon; ince ayar kararı | ilk koşu: zero-shot dejenere |
| Ontoloji gözden geçirmesi | "Uymuyor" etiketlerinden kategori önerisi | etiketlerden sonra |

**Çıkış:** retrieval bileşenleri sabitlenir (yeni D-kaydı); ontoloji revizyonu karara bağlanır.

## M1 — Uçtan uca kanıt senaryosu (D35)

Ayrıntı ve kabul testleri: `07-m1-definition.md`. Dilimler sırayla (D47: yetki ve upstream kesiti aramadan önce); her dilim kendi testlerini yeşile çevirir.

| Dilim | İçerik | Yeşile dönen testler |
|---|---|---|
| **M1a Katalog** | repo düzeni, dört tablo, OKF/MD + metin PDF ingest, üç sürüm kimliği, paket manifesti ve sıra kapsamının tanımı, CLI | AT-01 |
| **M1b Yetki çekirdeği** | ReBAC ve delegasyon tabloları, tek yetki kapısı (teslim öncesi yeniden denetim), K3 etkinleştirme kapısı, zorunlu ontoloji alanları, erişim kaydı | AT-04, AT-05, AT-06, AT-12, AT-16 |
| **M1c Kimlik, egress, denetim kesiti** | IdP token doğrulama, LLMDAP istemcisi, compose ağ düzeni, birleşik denetim sorgusu (#222/#223 gelene kadar fixture) | AT-09, AT-10, AT-11 |
| **M1d Arama ve atıf** | bütün + parçalı profil, hibrit arama + rerank (M0 seçimi), sürümlü atıf, "kütüphanede yok" | AT-02, AT-07, AT-08 |
| **M1e Yüzeyler** | HTTP API, Kütüphane MCP, okuyucu arayüzü | AT-03 |
| **M1f Paket ve geri bildirim** | imzalı export/import, güven kökü, anahtar yenileme/iptal, replay koruması, karantina→onay zinciri, atomik import; runbook geri bildirimi | AT-13, AT-14, AT-15 |

**Kapı (D18):** AT-10 (tek egress) ve AT-11 (kimlik) LLMDAP #222 ve #223 gelmeden yeşile dönemez; M1 bu iki
test geçmeden tamamlanmış sayılmaz. Diğer dilimler beklemeden ilerler.

## M2 — Koruma ve federasyonun başlangıcı

- `envelope/read` ve `sealed/use` (D33); OpenBao değerlendirmesi; envelope içerikten türeyen vektör ve
  önbelleklerin çözülebilirlik politikası (ön koşul).
- Çok seviyeli delegasyon; OpenFGA ölçümü (D28).
- **Recall semantiği** yazılır ve uygulanır (D40); master rolü: katalog/politika yayını, kurulum kayıt defteri.
- Karar modeli ürün entegrasyonu: LLMDAP #225 + güvenlik incelemesi sonrası; M0 sonuçlarına göre (D30, D34).
- DOCX/OCR çeşitliliği, gelişmiş profil yönetimi; K4–K6'nın ürünleşmesi (M0 ontoloji bulgusuna göre).

## M3 — Federasyon ve tüketiciler

- Çok kurulumlu master; opt-in toplama; fiziksel medya akışlarının işletim kılavuzları.
- InfraMedic'in Kütüphane'yi HTTP + MCP ile tüketmesi (D8, D19); InfraMedic master'ın bu framework'ün bir
  profili olarak yeniden değerlendirilmesi (D27).
- Stüdyo çıktıları ve sesli özet (D7, D39).
