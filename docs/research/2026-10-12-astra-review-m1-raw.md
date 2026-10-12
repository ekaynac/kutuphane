**Genel görüş: katılıyorum ★.** M1 kapsamı D35 ve 04 §3’le uyumlu; fakat mevcut testler yönetişim iddiasını bütünüyle kanıtlamıyor. Basitleştirme, kontrol kapılarını azaltarak değil, servisleri ve soyutlamaları azaltarak yapılmalı. Dosya değiştirmedim.

## 1. Kabul testleri

[07 §4](../../docs/07-m1-definition.md:57) için öneriler aşağıda. Tırnak içleri somut geçme koşullarıdır.

| Test | Görüş, gerekçe ve risk | Önerilen geçme koşulu |
|---|---|---|
| AT-01 | **Eksik:** “tek bayt” kapsamı belirsiz; paket metaverisi sahte sürüm üretebilir. | “Dosya sırası/zaman damgası kimliği değiştirmez; içerik dosyasının baytı değişince içerik kimliği değişir. Yalnız katalog politikası değişince yalnız politika kimliği değişir.” |
| AT-02 | **Eksik:** farklı kimlik, farklı davranışı kanıtlamaz. | “Bütün profil tam metni; parçalı profil beklenen sınırları verir. Ayrıştırıcı sürümü değişince profil kimliği değişir; içerik kimliği sabit kalır.” |
| AT-03 | **Farklı öneriyorum:** aynı soru aynı parçaları gerektirmez; model değişkenliği yanlış başarısızlık üretir. | “Sabit içerik/profil ve aynı yetki bağlamında HTTP/MCP aynı kanıt kümesini döndürür; iki yüzeyin atıfları geçerli pasajlara çözülür.” |
| AT-04–05 | **Eksik:** sonuç teslimi ve yarış durumu yok; iptal sırasında sızıntı olabilir. | “Delegasyon veya U’nun hakkı kaldırıldığında bütün yollar engellenir; iptal öncesi başlayıp teslim öncesinde bekletilen istek de içerik teslim etmez. Aramada yetkisiz öğe, sayı ve özet görünmez.” |
| AT-06 | **Katılıyorum ★**, fakat kiplerin bağımsızlığı eksik. | “Sahip olunmayan kapsam/kip, sahte devreden, ikinci devir ve bitiş anı dâhil süresi dolmuş grant reddedilir; `read` otomatik `use` sağlamaz.” |
| AT-07 | **Eksik:** yalnız pasaj korunuyor; cevap gövdesi sızabilir. | “Eski cevap ve pasajlar model yeniden çağrılmadan gösterilir; güncel yetki yoksa cevap gövdesi ve kanıtları gösterilmez.” |
| AT-08 | **Eksik:** eşikler yazılmadan makinece kesin sonuç yok; atıf bulunması doğruluk değildir. | “Sürümlü soru–pasaj kümesinde çekimserlik ve kanıt isabeti M0’da onaylanan sayısal eşikleri karşılar; bütün atıflar çözülür.” |
| AT-09 | **Eksik:** korelasyon eşleşmesi eksiksizliği kanıtlamaz. | “Tek sorgu bütün retrieval/üretim çağrılarını, politika/grant sürümlerini ve kararları döndürür; eksik LLMDAP kaydı açıkça eksik olarak işaretlenir.” |
| AT-10 | **Eksik:** tek başarısız bağlantı dar kanıt. | “İzinli hedefler dışına doğrudan IP/DNS ve yerel model servisi denemeleri engellenir; üretim, embedding ve uzaktaki reranker çağrıları LLMDAP kayıtlarıyla eşleşir.” |
| AT-11 | **Eksik:** kimliksiz isteği reddetmek taklidi engellemez. | “API/MCP; süresi geçmiş, yanlış issuer/audience taşıyan ve değiştirilmiş token’ları reddeder; başlıkla principal veya adına çalışılan kullanıcı değiştirilemez.” |
| AT-12 | **Farklı öneriyorum:** “etkin olarak” etiketi kolay aşılır. | “Ayrı etkinleştirme grant’i olmadan K3 gövdesi hiçbir ajan yolundan verilmez; izinli teslim ayrı olay olarak kaydedilir.” |
| AT-13–14 | **Eksik:** anahtar yaşam döngüsü/onay yok; “hiçbir değişiklik” audit’i de yasaklıyor. | “Bilinmeyen/iptal edilmiş anahtar, bozuk imza ve eşit/eski sıra reddedilir; anahtar yenileme çalışır. Tarama, fark ve insan onayı olmadan yayın olmaz. Hata/eşzamanlı replay görünür kataloğu değiştirmez; ret kaydı korunur.” |
| AT-15 | **Katılıyorum ★**, fakat D13 eksik. | “Üç sonuç değeri, uygulayan, zaman, `tested_on` ve içerik sürümü saklanır; yeni sürüm eski geri bildirimi sahiplenmez.” |

## 2. Kararlarla çelişki

- **Farklı öneriyorum — [07:75](../../docs/07-m1-definition.md:75):** K3’ü “etkin talimat olarak” sunmama, D37/04 §2.3’ten daha dar. **Risk:** referans etiketiyle etkinleştirme kapısını aşmak.
- **Eksik — [07:76](../../docs/07-m1-definition.md:76), §5:** D29’un karantina→doğrulama→tarama→fark→insan onayı zinciri ve anahtar iptali kabul kapsamına taşınmamış. **Risk:** imzayı güvenlik onayı saymak.
- **Eksik — [07 §2–4](../../docs/07-m1-definition.md:28):** D24’ün zorunlu E5/E8/E9 alanları, D28’in kayıt amaçlı `purpose` alanı ve D16’nın at-rest şifrelemesi testlenmiyor. **Risk:** bütün AT’ler yeşilken bağlayıcı kararların karşılanmaması.
- **Eksik — [07:50](../../docs/07-m1-definition.md:50):** “Compose ağ politikası” somut topoloji değil. `internal` dış bağlantıyı keser; aynı ağdaki servisleri birbirinden ayırmaz. **Risk:** yanlış izolasyon güvencesi. [Docker belgesi](https://docs.docker.com/reference/cli/docker/network/create/)
- **Eksik — 05–07:3:** onay durumu kullanıcı bilgisinin gerisinde. [05 §2](../../docs/05-product-brief.md:12)’deki rakip/MCP genellemeleri ayrıca **doğrulanmalı**; karar değil. **Risk:** taslağı veya varsayımı kesin ürün gerçeği saymak.

## 3. Aşırı karmaşıklık riski

**Farklı öneriyorum:** M1’de tek Python uygulaması; CLI/API/MCP aynı uygulama servislerini çağırsın. Dinamik plugin keşfi yerine küçük, sürümlü fonksiyon arayüzleri kullanılsın. Redis, görev kuyruğu, ayrı audit servisi ve genel iş akışı motoru eklenmesin. Önbellek ertelenebilir; varsa yetki kontrolü zorunlu kalır.

**Katılıyorum ★:** OpenFGA/OpenBao/master’ın ertelenmesi doğru. InfraMedic’ten yalnız gerekli modülleri taşıyın; filo soyutlamalarını taşımayın. Gerekçe işletim yükü; risk gereksiz uyarlama katmanlarıdır. Bunlar yönetişimi gevşetmez. BM25/reranker’ı M1’den çıkarmak ise D31’i değiştirir.

## 4. M1a için en basit mimari

**Farklı öneriyorum:** `src/kutuphane/{catalog,ingest,authz,audit,api,cli}.py`, `web/`, `migrations/`, `tests/fixtures/`, `compose.yaml`; başlangıçta mikroservis yok.

**Dört tablo:** `book`, `content_version`, `profile_version`, `policy_version`. Sürümler değişmez; kitap güncel sürümlere işaret eder. Bundle `bytea`, manifest/ayarlar JSONB; yabancı anahtarlar açık olsun. Parça tablosu M1b’de; ilişki/delegasyon tabloları yetki diliminde eklenir. **Risk:** tablo sayısını azaltmak uğruna her şeyi tek JSONB torbasına çevirmek.

**Kimlikler:** sürümlü kanonik kodlama + SHA-256:

- İçerik: sıralanmış dosya yolları ve bayt özetleri; taşıma metaverisi/yönetişim zarfı hariç.
- Profil: ayrıştırıcı/parçalayıcı/gömücü/reranker sürümleri, ağırlık özetleri ve ayarlar.
- Politika: kanonik politika belgesi; grant sürümü ayrıca kaydedilir.

**Ingest:** doğrula→kaynak baytlarını koru→çıkar→tek transaction ile yayınla. PDF, concept’in `resource` ile işaret ettiği representation olsun; çıkarılmış pasajları profil sürümüne bağlayın. Ağsız, süre/bellek sınırlı ayrıştırma kullanın.

Adaylar: [markdown-it-py: MIT](https://github.com/executablebooks/markdown-it-py/blob/master/LICENSE), [pypdf: BSD-3-Clause](https://github.com/py-pdf/pypdf/blob/main/LICENSE). Sabitlenecek sürümler, geçişli bağımlılıklar ve Türkçe çıkarım kalitesi **doğrulanmalı**; AGPL kabul edilmemeli.

## 5. Dilimleme

**Farklı öneriyorum:** M1a→M1c’nin yetki çekirdeği→M1d’nin kimlik/egress/audit kesiti→M1b→M1d’nin arayüzü→M1e.

Gerekçe: en pahalı yeniden çalışma, aramaya sonradan yetki eklemek ve upstream uyumsuzluğunu geç keşfetmektir. Paket manifesti/sıra kapsamı M1a’da tanımlansın; uygulaması M1e’de kalabilir. **Risk:** erken entegrasyon beklemeye dönüşmesin; fixture çalışması sürsün, fakat #222/#223 gerçek doğrulanmadan kabul yeşile dönmesin.