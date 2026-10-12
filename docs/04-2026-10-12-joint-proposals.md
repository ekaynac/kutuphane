# Kütüphane — Claude + Astra ortak önerileri (B1–B11)

Tarih: 2026-10-12. Durum: **operatör tarafından bütünüyle onaylandı (2026-10-12) → `01-direction-decisions.md` D21–D40.**
Girdi: `03-2026-10-12-decision-briefs.md` (Claude önerileri ★) + Astra'nın bağımsız incelemesi
(`gpt-6-astra`, Codex CLI, medium reasoning, repo salt-okuma; ham metin `research/2026-10-12-astra-review-raw.md`).
Bu doküman iki görüşü birleştirir; ayrışma kalan yerde iki tarafın gerekçesi yazılıdır.

## 0. Ortak ana tez

Ürünün ayırt edici değeri: **bilginin hangi sürümüne, kimin adına, neden erişildiğini açıklayabilmek.** Öneriler
bunu güçlendiriyor; risk, M1'e federasyon + sır yönetimi + model deneylerinin birlikte yüklenmesi. Ortak öneri:
**M1'i tek uçtan uca kanıt senaryosuna indir, yönetişim iddiasını gevşetmeden.**

## 1. Başlık başlık ortak öneri

| # | Ortak öneri | Claude ilk önerisinden fark | Durum |
|---|---|---|---|
| B1 Ontoloji | 9 boyut korunur ama **9 kapalı katalog alanına dönüşmez**. Yönetişim için zorunlu olanlar (E5 erişim sınıfı, E8 koruma, E9 erişim kipi) zorlanır; diğerleri isteğe bağlı, açık sözlük (OKF ruhu). E3 *köken* ve *güven* ayrı nitelik; E5 *hassasiyet* ve *egress* ayrı nitelik. E2 sunum profilinde, E9 aktör–kaynak izin kümesinde yaşar. **`discover/read/use` doğrusal sıra değildir**: `read` sahibi otomatik `use` sahibi olmaz (ve tersi). | "Küçük kapalı kümeler" önerisi geri çekildi | uzlaşı |
| B2 Kategoriler | **K1–K3 ürün kapsamı.** K4 yalnız mevcut okuma altyapısıyla karşılanabildiği ölçüde. **K7 bağımsız deney hattı** (ürün vaadi değil). K5 ürün olarak ertelenir ama erişim/geri bildirim kayıtları zaten çekirdekte. Kategoriler ayrı motor değil, ortak çekirdeğin hazır profilleri. "Şemada destekliyoruz" ifadesi ürün vaadi olarak kullanılmaz. | K7 v1'den deney hattına; K4 daraltıldı | uzlaşı |
| B3 Kitap | Kitap = OKF bundle + yönetişim + sunum profili + sürüm; **ama üç ayrı sürüm kimliği**: *içerik* (bundle özeti), *profil* (aynı içerik yeni ayrıştırıcıyla farklı parçalara bölünür), *politika* (erişim, içerik değişmeden güncellenebilir). Atıf `içerik@sürüm + profil + parça` taşır; erişim kaydı politika ve grant sürümünü taşır. | Tek sürüm kimliği → üç | uzlaşı |
| B4 Master | Aynı kod tabanı, ayrı "master" rolü; M1'de yalnız paket sözleşmesi. Kurulum kayıtları "**son bildirilen durum**" olarak sunulur (offline kurulumun güncel durumu bilinemez). | — | uzlaşı |
| B5 Delegasyon | M1'de **tek seviyeli, süreli, iptal edilebilir** delegasyon. Delegasyon her kullanımda devredenin **güncel** yetkisiyle kesişir (devreden yetkisini kaybedince ajan da kaybeder). `purpose` alanı tek başına amacı zorlamaz (kayıt amaçlı). Yetki sınırı yalnız aramada değil: **doğrudan okuma, önbellek, export, sonuç teslimi** de aynı kontrolden geçer. Uygulama: yetki arayüzü OpenFGA biçiminde tasarlanır; M1'de servis sayısını azaltmak için **Postgres içi ilişki tabloları** ile başlanabilir, OpenFGA ölçüm sonrası (bkz. §2). | Derinlik M2'ye; OpenFGA kesin değil, adaptör | uzlaşı (Claude revizyonu) |
| B6 Paket | İmzalı zarf + çift yönlü taşıma doğru; eksikler eklenir: **güven kökü** (ilk anahtarın kuruluma nasıl güvenilir girdiği), **anahtar yenileme/iptal**, **yeniden oynatma koruması** (monoton paket sırası; eski paket/recall yeniden uygulanamaz), **atomik import**. İmza içeriğin doğruluğunu/güvenliğini kanıtlamaz (tarama + insan onayı ayrı kapı); şifreleme manifest/boyut sızıntısını kendiliğinden kapatmaz. | Güven kökü, replay, atomiklik eklendi | uzlaşı |
| B7 Karar modelleri | **Tek karar noktası + insan etiketli değerlendirme kümesi** (gerçeklik referansı insan, model değil). Laya öncelikli (operatör), Jev karşılaştırma sağlayıcısı. Ortak sözleşme + shadow doğru, ama **M1 koşulu değil**; ayrı deney hattı. Olasılıkların anlamı, çekimserlik (abstain) ve kalibrasyon görev bazında ölçülür. **Laya Jev etiketleriyle eğitilip Jev etiketleriyle ölçülmez** (öğretmene benzerliği ölçer, doğruluğu değil). | Paralel shadow M1'den deney hattına; insan etiketi şart | uzlaşı (operatörün Jev/Laya niyeti korunur, sıralama değişir) |
| B8 Retrieval | Mimari kabul (Postgres hibrit + tek reranker); **bileşen listesi küçük bir ölçümden sonra sabitlenir**: Türkçe kurum korpusu, dar yetki filtreleri, hedef donanım. Sürüm, ağırlık ve bağımlılık lisansları **doğrulanmalı** (AGPL-dışı ilke korunur). Araştırmadaki eşik ve "recall çözüldü" iddiaları garanti sayılmaz. | Bileşenler ölçüme bağlandı | uzlaşı |
| B9 M1 | **Tek uçtan uca kanıt senaryosu** (§3). | 10 maddeden daraltıldı | uzlaşı |
| B10 Onyx | Temel alınmaz; bu **mimari tercih** olarak kaydedilir ("fork kesin daha pahalı" hükmü olarak değil). Onyx CE/EE sınırları ve OKF araçlarının uygunluğu **doğrulanmalı**; "doğrudan kullanılır" yerine "aday". | Kesinlik yumuşatıldı | uzlaşı |
| B11 Sırlar | **M1'de model/Jev anahtarları yalnız LLMDAP'ta**; Kütüphane yalnız **referans, grant ve korelasyon kaydı** tutar. OpenBao, genel `sealed/use` ve kullanıcıya dönük `envelope/read` **M2**. Ön koşul: envelope içerikten türeyen metin, **vektör** ve önbelleklerin kim tarafından çözülebildiği tanımlanmadan gizlilik sözleşmesi tamam sayılmaz (gömme vektörü de gizli içeriktir). Hedef sınırlama + yankı maskeleme "ajan sırrı asla öğrenemez" garantisi için **yeterli değildir** → ürün dili "ajana sır verilmez" olur, "asla öğrenemez" değil. | envelope/read de M2; ürün dili düzeltildi | uzlaşı |
| Jev açık soru | **Gerçek Jev çağrıları #225 + güvenlik incelemesi gelene kadar bekler**; bu sürede sözleşme, fixture ve insan etiketli değerlendirme kümesi hazırlanır. "Experiment" etiketi D3'ün tek geçiş ilkesini karşılamaz; D18 benzer geçici bypass'ı zaten reddetti. Bekleme M1'i engellemez (shadow M1 dışında). | Claude iki seçeneği açık bırakmıştı | uzlaşı |

## 2. Önceki kararlarda yeniden değerlendirme önerileri

1. **D9 dili:** "eski cevap yeniden üretilebilir" → "**eski cevap ve kanıtları (sabit sürümdeki atıflı pasajlar) yeniden
   gösterilebilir**". Modeli yeniden çalıştırıp birebir aynı cevabı üretmek ayrı ve daha zayıf bir taahhüttür.
2. **İçerik sürümü sabitlenir, erişim hakkı sabitlenmez:** eski bir cevap açılırken **güncel** yetki denetlenir
   (B3–B5 çelişkisinin çözümü).
3. **D4/D13 — üç ayrı sınır:** *doküman sunmak* · *talimatı etkinleştirmek* · *sırrı kullanarak işlem yapmak*.
   Önemli sonuç: K3 (skill, prompt, agent card) bir ajana sunulduğunda fiilen **talimat etkinleştirmedir**; bu,
   referans doküman sunmaktan farklı bir onay/politika kapısı ister.
4. **D14/D15 — kimlik rolleri:** IdP (kurum AD/LDAP ya da Keycloak) kimliği doğrular; LLMDAP egress'te bu kimliği
   **doğrulayıcı** olarak kullanır; Kütüphane yetkilendirir. Ek servisler (OpenFGA, OpenBao, Keycloak) offline
   kurulum, yedekleme ve **anahtar kurtarma** yükü getirir → M1'de servis sayısı en aza indirilir (B5, B11).
5. **D7 — sesli özet ve çoklu stüdyo çıktıları M1 dışında** açıkça konumlanır; "LLM deney platformu" hedefi
   teslim kapsamını büyütmez (deney hattı ayrı).
6. **B4–B6 — recall semantiği:** recall, yerel egemenlik ve çevrimdışı çalışma birlikte açık *teslim* ve
   *uygulama* semantiği ister (recall ne zaman, kimin onayıyla uygulanır; uygulanana kadar ne olur).

## 3. Ortak M1 — tek uçtan uca kanıt senaryosu

**Kapsam:**
1. Bir OKF/MD kitabı ve bir metin-katmanlı PDF içe aktarılır → içerik / profil / politika sürüm kimlikleri.
2. İki sunum profili: *bütün* ve *parçalı* (hibrit arama + rerank).
3. İnsan (arayüz) ve ajan (Kütüphane MCP) aynı kitaba erişir.
4. Tek seviyeli, süreli, iptal edilebilir kullanıcı→ajan delegasyonu.
5. Sürümlü, tıklanabilir atıf; "kütüphanede yok" dürüstlüğü.
6. **Birleşik audit**: Kütüphane erişim kaydı + LLMDAP egress kaydı tek işlem (korelasyon) üzerinden okunur.
7. Asgari imzalı paket import/export (güven kökü, replay koruması, atomik import dahil).
8. Runbook geri bildirimi basit kayıt olarak.
9. D18 kapıları korunur: kimlik (#223) ve embedding egress (#222) LLMDAP üzerinden.

**Ertelenen (M2+):** karar modeli shadow'u (deney hattında ayrıca ilerler), DOCX/OCR çeşitliliği, gelişmiş profil
yönetimi, çok seviyeli delegasyon, OpenBao + genel sealed/use + envelope/read, master federasyonu, stüdyo çıktıları.

**Kabul testleri (makinece doğrulanabilir):**
- Yetkisi iptal edilen ajan, iptalden sonraki ilk istekte okuyamıyor (arama, doğrudan okuma, önbellek, export dahil).
- Devredenin yetkisi geri alınınca, ona bağlı ajan delegasyonu da etkisiz.
- Yeni sürüm sonrası eski atıf doğru sürümdeki doğru pasaja açılıyor; açılırken güncel yetki denetleniyor.
- Offline paket bir kurulumdan diğerine taşınıyor; kurcalanmış ya da eski (replay) paket reddediliyor; import ya
  tamamen uygulanıyor ya hiç.
- Bir cevap için "kim, kimin adına, hangi sürüm/parça, hangi politika kararı, hangi model çağrısı" tek sorguda
  açıklanabiliyor (erişim + egress birleşik).

## 4. Deney hattı (M1'e paralel, M1 koşulu değil)

- Karar noktası sözleşmesi (`systemone` şekli), fixture'lar, **insan etiketli** değerlendirme kümesi.
- İlk karar noktası (öneri): ingest sınıflandırma.
- Laya yerel; Jev #225 + güvenlik incelemesi sonrası; ikisi aynı LLMDAP yönetişiminde, insan etiketlerine karşı ölçülür.
