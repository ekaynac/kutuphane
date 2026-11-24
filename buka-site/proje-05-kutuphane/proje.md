# Kütüphane — proje sayfası (proje.md)

Hazırlayan: Kütüphane ajanı (issue ekaynac/kutuphane#260). Kaynaklar repo-göreli yoldur; tümü `origin/main` @ `1efb12d` (2026-11-23) içindedir. Yayınlanacak her metin ve görsel ayrıca Enes onayından geçer.
Kütüphane sitede kendi proje sayfasıyla sunulur (Enes kararı 24.11: LLMDAP, Kütüphane ve nöbetçi-mcp üç ayrı proje); bu dosya o sayfanın malzemesidir. Proje numarası site ekibinindir; dosya adlarındaki "05" yalnız ilk istekten kalır.

```
baslik:          Kim yazdı, kim onayladı: ajanlar için denetlenebilir hafıza
                 (59 karakter)

tek_cumle:       İnsanların, ajanların ve uygulamaların aynı kopyadan okuduğu; her kaydın yazarını, onayını ve kullanım hakkını tutan bilgi kataloğu.
                 (132 karakter)
                 kaynak: README.md (ilk alıntı) · docs/23-vision-v1.md §1

sorun:           Ajan hafızası ürünleri hatırlar; ama bir notu kimin yazdığını, kimin kabul ettiğini ve bir modelin onu kullanıp kullanamayacağını kayda geçirmez.
                 Kütüphane bu kaydı tutar: yazan, yol kaydından gelir (ajan hiçbir zaman insan gibi kaydedilmez), onay insan eliyle verilir, hak model çağrısından önce denetlenir.
                 Proje, sahibinin kendi kodlama ajanlarının hafıza istekleriyle (#67–#81) şekillendi.
                 kaynak: README.md (giriş alıntısı, "Five principles") · SCOPE.md C1–C3 · docs/23-vision-v1.md "Basis" ve §4

ne_yaptik:       - Sürümlü kitap kataloğu: her dosya için lisans, köken ve "yapay zekâ girdisi olabilir mi" hakkı bir kstd.yaml bildiriminde durur.
                   kaynak: SCOPE.md K1, K7 · docs/guide/kstd.md
                 - Atıflı arama ve cevap: tam metin ve vektör araması; cevap [n] atıflarıyla gelir, kaynak pasaj tam sürümüyle açılır. Hakkı `ai_input: n` olan içerik hiçbir modele gitmez.
                   kaynak: SCOPE.md K2, C3 · README.md "MCP tools"
                 - Kalıcı ajan hafızası: ajan not önerir, not "bekliyor" başlar; durumunu yalnız yetkili bir insan değiştirir. Notlar değiştirilmez, geri çekilir.
                   kaynak: SCOPE.md K3, C2, C5 · docs/guide/concepts.md
                 - Telefonda parmak izi (passkey) ile onay: önerilen notları ve gelen paketleri görüp onaylayan/reddeden kürasyon sayfası. Passkey yalnız bu iş içindir, başka sisteme oturum vermez.
                   kaynak: SCOPE.md K4 · docs/guide/operations.md "On the phone (curator web, D72)"
                 - Ajanlar MCP ile, uygulamalar MCP veya HTTP ile bağlanır; imzalı paketle bilgi alınıp verilir; sunucu şirket içinde, internetsiz de çalışır.
                   kaynak: SCOPE.md K5, K8 · README.md (giriş paragrafı, "Who it is for")

nasil:           Python (3.11+), PostgreSQL 17 + pgvector 0.8, MCP (streamable HTTP; 2025-11-25 ve 2026-07-28), WebAuthn passkey, React arayüz; Docker Compose ile kurulur. Kod Apache-2.0.
                 Model sağlayıcısı ayarlanmamış bir kurulum hiç model çağırmaz (yalnız tam metin arama). Her model aşaması bir geçit (gateway) üzerinden ya da doğrudan OpenAI uyumlu bir uca gider; Spark'taki çağrılar LLMDAP'tan geçer. Cevap modeli her zaman dışarıdandır. LLMDAP köprüsü özel bir bileşendir, yalnız LLMDAP anlaşmasıyla verilir.
                 kaynak: SCOPE.md K2 (v1.1) · pyproject.toml (requires-python) · compose.yaml (pgvector/pgvector:0.8.0-pg17) · README.md "MCP tools" ve "Quick start" · web/package.json · docs/guide/changelog.md "A model stage can call a direct OpenAI-compatible provider (D88)" · LICENSE

kimler:          Enes Kaynakcı — proje sahibi; mimari ve kabul kararları · Geliştirme ve test: Buka'nın yapay zekâ ajanları;
                 her değişiklik bağımsız inceleme ve sahibin onayıyla.
                 kaynak: Enes (23.11, metin kendisinin)

durum:           aktif geliştirme; sürüm 0.1.0, "arayüzler değişebilir" (README.md "Status", pyproject.toml).
                 Herkese açık sürüm yok: GitHub'da 0 sürüm (release) ve 0 etiket (tag) var (gh api repos/ekaynac/kutuphane/releases, /tags, 2026-11-23).
                 Depo herkese açık, Apache-2.0 (gh api repos/ekaynac/kutuphane, 2026-11-23). Depodaki ilk commit: 2026-10-07 (git log --reverse). "İlk sürüm tarihi": yok, çünkü sürüm yok.
                 Kullanım: sahibin kendi ajanları için dahili olarak canlı bir kurulum çalışır (SCOPE.md "the live install"; ayrıntı repoda yok — "tek sunucu" bilgisi görev tanımından, sahibi doğrular).
                 Müşteri yok, dış pilot yok (görev tanımı; sahibi doğrular). Repodaki iki "pilot" belgesi (docs/18, docs/26) iç denemelerdir ve müşteri anlamına gelmez.

olgular:         1. "15 · MCP aracı, modelsiz kurulumda"
                    kaynak: tests/contract/tools.json (without_model_gateway: 15 araç). Bir cevap modeli bağlanınca ask_library ve 3 iş aracı eklenir: 19 (README.md "MCP tools" tablosu; scratch kurulumda tools/list 19 döndürdü).
                 2. "1.436 · otomatik test, her değişiklikte"
                    kaynak: `pytest --collect-only` @ 1efb12d: çekirdek 1.358 + kstd referans 78 = 1.436 toplanan test. CI (.github/workflows/ci.yml) iki takımı da her pull request ve main push'unda Postgres+pgvector üzerinde çalıştırır. (Sayı "toplanan test"tir, geçme sonucu burada iddia edilmez.)
                 3. "88 · yazılı proje kararı (D1–D88)"
                    kaynak: docs/01-direction-decisions.md (D1'den D88'e kesintisiz numaralı; bir kısmı sonradan dondurulmuş ya da kaldırılmıştır, SCOPE.md D7).

baglantilar:     - Açık repo (Apache-2.0): https://github.com/ekaynac/kutuphane
                 - Kapsam sözleşmesi: https://github.com/ekaynac/kutuphane/blob/main/SCOPE.md
                 - Kullanım kılavuzu: https://github.com/ekaynac/kutuphane/blob/main/docs/guide/index.md
                 (Hugging Face, yayın, demo: yok. Hepsi herkese açık: depo `public`, gh api repos/ekaynac/kutuphane -q .visibility → public.)

kurum_adlari:    Metinde kurum adı yok. Anılan adlar proje/ürün adıdır: LLMDAP (sahibin kendi projesi, docs/01-direction-decisions.md D3), nöbetçi-mcp (kardeş proje, SCOPE.md D4). Üçüncü taraf ürün ya da şirket adı kullanılmadı.
                 Ekran görüntülerinde de kurum adı yok; demo veri tümüyle kurgusal ("Demo Bilgi Birimi", "Demo Tedarikçi").

gorsel_fikri:    Bir kütüphane fişi (katalog kartı): bir pasajın üstünde üç küçük mühür, "yazan · onaylayan · hak". Kütüphane'de her kaydın bir sahibi, bir onaylayanı ve bir kullanım hakkı vardır.
```

## Not (site ekibi ve Enes için)

- Arayüz dili: ekran görüntülerindeki "Core web" arayüzü Türkçe, kürasyon (telefon) sayfası İngilizcedir. Kürasyon sayfası ürünün kendi diliyle gösterilmiştir.
- Model: cevap ekranındaki cevap gerçek bir modelden gelmez; örnek model (stub) ile üretildi. Altyazı da böyle der.
- Repo kimliğiyle çelişki yok: Kütüphane "RAG platformu ya da sohbet arayüzü" değildir (SCOPE.md "Bu repo değildir"); metinde arama ve cevap, katalog üzerindeki bir yetenek olarak anlatıldı.
- Küçük tutarsızlık (repo tarafı, siteyi etkilemez): README.md vizyon sürümünü 1.2 diye anar, docs/23-vision-v1.md başlığı 1.3'tür.
