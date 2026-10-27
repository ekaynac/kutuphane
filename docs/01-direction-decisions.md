# Kütüphane — yön kararları (karar kaydı)

> Ürünün adı **Kütüphane**dir (D20). Bu kayıtta 2026-10-07 öncesi çalışma adı "Kobra" geçen yerler,
> o anki adlandırmayla bırakıldı; Kobra artık Kütüphane'nin ajan/sohbet yüzüdür.

Canlı karar kaydı. Her karar tarihli; reddedilen seçenekler ve gerekçeleri korunur.
Kaynak: `docs/00-kickoff-brief.md` §5 soruları, operatörle 2026-10-07 oturumu.

## 0. Bağlam (2026-10-07 okuması)

InfraMedic içindeki Kobra bir NotebookLM değil; **cihaz grant'ıyla çalışan insan güdümlü bir ops konsolu**
(araçların çoğu SSH/REST/runbook, sözleşme portlarının ~%70'i filo/Saga'ya özgü). Yeni ürün için değerli olan
bilgi katmanı: içerik-SHA'lı sürüm/representation/placement/projection kataloğu, blue/green indeks nesilleri
(gen-N), kullanım anında yetki (`authorize_document`, `restricted` → bulut yok), seçili-setle sınırlı broker,
retrieval audit, korumalı PDF çıkarımı, promote akışı, `llmdapclient/rag.py`. Eksikler: notebook/çalışma alanı
nesnesi, geniş kaynak türleri, satır içi pasaj atfı, stüdyo çıktıları, streaming, dış API/MCP, filo RBAC'ından
bağımsız yetki modeli.

## 1. Kararlar — 2026-10-07

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D1 | Hedef kitle | **Regüle / air-gapped kurumların bilgi ve operasyon ekipleri** (hukuk, uyum, mühendislik, IT-ops). | Yalnız IT teknisyenleri (InfraMedic'in alanı, pazarı daraltır); genel ekipler (NotebookLM/OpenWebUI ile kafa kafaya, farksız). |
| D2 | Birincil nesne | **Kütüphane birincil**; notebook, kütüphaneden seçilmiş ve sürümleri sabitlenmiş bir görünüm. | Notebook başına sahiplenilen kaynaklar (NotebookLM modeli): yönetişim, sürüm ve yeniden kullanım kaybolur. |
| D3 | LLMDAP | **Zorunlu tek egress yolu**; solo kurulumda gömülü gelir. Upstream: `github.com/ekaynac/LLMDAP` (bize ait). | LLMDAP'sız mod / çoklu backend: yönetişim iddiası zayıflar, iki yol test edilir. |
| D4 | Kapsam | v1 **bilgi işi** (oku, sentezle, atıf ver); cihaz/araç eylemi yok. **Ancak core MCP sunucusu v1'de çıkar** — harness'lar Kobra'yı v1'den itibaren kullanabilmeli. | Baştan act: yetki/kilit/lease altyapısı InfraMedic'te, v1'i yutar. |
| D5 | Harness | **Çekirdek MCP + HTTP API ile açılır**, yanında ince bir referans ajan döngüsü. | Yalnız kendi döngümüz: harness-agnostic hedefiyle çelişir. |
| D6 | Kod/yığın | **Python.** InfraMedic'ten katalog, nesil, broker, authz, retrieval audit, uploads/extract, `rag.py` kopyalanıp ameliyat edilir (cihaz/grup kavramları → çalışma alanı/principal). **Arayüz baştan**, JS'li ve streaming'li. | Tümüyle sıfırdan: olgun ve test edilmiş katalog/nesil mantığını atmak. **Açık:** SQLite mi Postgres mi. |
| D7 | Çıktılar | Atıflı brifing, SSS, zaman çizelgesi, çelişki raporu **ve sesli özet** (TTS). | — (Spark GPU'su paylaşımlı; TTS modeli seçimi ve yükü ayrıca onaylanacak.) |
| D8 | InfraMedic ilişkisi | **InfraMedic ileride Kobra'yı kütüphane/servis olarak tüketir.** Sonuç: Kobra'nın sürümlü, kararlı bir sözleşmesi (API + MCP şeması) olmalı; sahibi Kobra. InfraMedic içindeki Kobra şimdilik değişmez. | Kardeş ürünler + yalnız export paketi (önerilmişti): operatör tek bilgi platformunu tercih etti. |
| D9 | İlk kilometre taşı | Karışık doküman klasörü içe aktarılır, sürümlenir, indekslenir; notebook'ta soru → tıklanabilir pasaj atıflı cevap; çağrı LLMDAP audit'inde görünür; doküman yeni sürümle değişir, eski cevap yeniden üretilebilir kalır. **Ek:** kütüphanede yalnız bilgi değil **runbook'lar** ve operasyonel olarak gelişen başka doküman türleri de olur. | — |
| D10 | Repo / lisans | Private repo `github.com/ekaynac/kobra`. Lisans: **tescilli, Mega Bilgisayar Tic. Ltd. Şti.** | Açık kaynak. |

## 2. Operatörün ek ilkeleri — 2026-10-07

- **LLM teknolojileri test platformu.** Kobra, ekibin LLM teknolojilerini denediği kapsamlı bir platform olur.
  Örnek: geliştirilmekte olan **Ketum** veri anonimleştiricisi Kobra'ya takılabilen bir bileşen olmalı.
  Sonuç: içe aktarma / redaksiyon / gömme / retrieval / üretim adımları **değiştirilebilir, sürümlü bileşenler**
  (plugin) olarak tasarlanır ve her bileşenin kimliği provenance'a ve indeks parmak izine girer.
- **Geliştirmeye açık, ajan dostu.** Kod tabanı bir ajanın rahat çalışacağı biçimde olur: net modül sınırları,
  CLI + API + MCP ile her şey sürülebilir, deterministik fixture'lar, hızlı test.
- **Enterprise ön yüz.** On-prem ve air-gapped kurumsal ortamlarda rahat kullanılan, user-friendly bir arayüz.
- **Runbook'lar birinci sınıf.** Atıf kadar operasyonel gelişim de önemli: runbook'ların kullanım/sonuç geri
  bildirimiyle evrilebileceği doküman türleri.

## 2b. LLMDAP upstream okuması — 2026-10-07 (`ekaynac/LLMDAP` @ b9d48eb)

TypeScript/Node 20; core `llmdap` 1.16.0, `@llmdap/gateway` 0.22.0 (0.x API, yakın zamanda kırıcı değişiklikler).
Güçlü yanlar: bridge (ollama/openai/anthropic şemaları, exact model pin, öncesi/sonrası audit), **governed
streaming artık var** (route başına `allowStreaming`), imzalı sorgulanabilir audit + evidence, Casbin politika,
LDAP dizin kimliği, tarball ile air-gapped kurulum, MCP `/mcp` + tek downstream proxy.

Kobra için boşluklar:
1. **RAG araması koleksiyon boyutunda O(n):** her sorguda tüm chunk'lar çözülür ve kaba kuvvet cosine; ANN,
   hibrit/BM25, rerank, meta filtre yok. Chunking sabit 1000/100 karakter.
2. **Paylaşılan korpus:** gateway `rag.index` aracı `recipients` açmıyor; ekip paylaşımı kütüphane seviyesinde
   rol anahtarı yönetimi ister.
3. **Embedding çağrıları bridge'den geçmiyor** → "tek egress" iddiası embedder için ayrıca kapatılmalı.
4. **Gateway çağıranı doğrulamıyor** (header + paylaşılan sır); OIDC yalnız kütüphanede. Kimlik doğrulama Kobra'nın işi.
5. **Redaksiyon/DLP kancası yok** → Ketum Kobra hattında ya da upstream bridge dönüşümü olarak girer.

## 3. Kararlar — 2026-10-07, ikinci tur

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D11 | Depolama | **Baştan Postgres.** | SQLite: çok kullanıcılı enterprise ve InfraMedic'in servis olarak tüketmesi (D8) için yetmez. |
| D12 | Ketum | **Şimdilik kapsam dışı.** Bileşen/plugin ilkesi (§2) yine de geçerli; Ketum hazır olunca takılır. | — |
| D13 | Runbook'lar v1 | **Doküman olarak**: sürümlü, `tested_on`, uygulayanın sonuç geri bildirimi (işe yaradı / yaramadı / değişti) ile evrilir. Çalıştırma yok. | Çalıştırılabilir adımlar (D4 ile çelişir). |
| D14 | Kimlik | **LLMDAP'ın OIDC/LDAP modu**; yerel admin yalnız ilk kurulum için. Stok gateway'de OIDC yok → upstream ask. | Kobra'nın kendi kullanıcı sistemi. |
| D15 | Kurulum / ön yüz | **docker compose tek kutu** (Kobra + LLMDAP + Postgres + embedder) + offline imaj paketi; ön yüz **React + TypeScript**. | — |
| D16 | Retrieval | **Kobra kendi indeksini tutar**: Postgres + pgvector + tam metin, hibrit arama + rerank, at-rest şifreli. Model ve embedding çağrıları LLMDAP bridge'inden. LLMDAP RAG'ı kullanılmaz. | LLMDAP RAG'ı + ölçeği upstream'e bırakmak (O(n) arama, rerank/hibrit yok). |
| D17 | Embedding egress | **Bridge'den geçer**; upstream ask açıldı. | Embedder'ı doğrudan çağırmak ("tek egress" iddiası bozulur). |

Upstream issue'lar (2026-10-07): `ekaynac/LLMDAP#222` (governed embeddings route),
`ekaynac/LLMDAP#223` (stok gateway'de env ile OIDC/JWT çağıran doğrulama).

## 4. Kararlar — 2026-10-07, üçüncü tur

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D18 | #222/#223 öncesi geçiş | **M1 bu iki upstream işi bekler**: embedding egress bridge'den, kimlik OIDC/LDAP ile gelmeden "tek egress" ve kimlik iddiaları milestone'da tamamlanmış sayılmaz. Bağımsız işler (katalog, ingest, indeks, arayüz) paralel ilerler. | Geçici doğrudan embedder + "unverified egress" etiketi (önerilmişti): operatör iddiaların baştan doğru olmasını tercih etti. |
| D19 | InfraMedic'in tüketimi | **HTTP + MCP servisi**; sürümlü sözleşme şeması bu repoda yaşar. Şimdilik yalnız sözleşme tasarlanır, InfraMedic'e dokunulmaz. | Python kütüphanesi olarak tüketim: süreç sınırı ve yetki sınırı bulanıklaşır. |
| D20 | Ad | **Ürünün adı Kütüphane.** Kobra, Kütüphane'nin içindeki ajan/sohbet yüzü olarak kalır. GitHub repo `ekaynac/kobra` → `ekaynac/kutuphane` olarak yeniden adlandırıldı (eski URL yönlendirir). | Kobra adının tamamen kalkması; Kütüphane'nin yalnız bir alt sistem adı olması. |

## 5. Kararlar — 2026-10-12 (ortak öneriler onaylandı)

Kaynak: `03-2026-10-12-decision-briefs.md` (Claude brifleri), Astra incelemesi
(`research/2026-10-12-astra-review-raw.md`), birleşik metin `04-2026-10-12-joint-proposals.md`. Operatör
2026-10-12'de ortak önerileri bütünüyle onayladı. Ayrıntı ve kabul testleri 04'tedir; burada karar özeti.

### 5.1 Yön ilkeleri

| # | Karar |
|---|---|
| D21 | **OKF-yerli, minimally opinionated çekirdek.** Taşınabilir birim OKF concept'i (tek zorunlu alan `type`); Kütüphane OKF'ye kural eklemez, yönetişim katalogda yaşar; taşınabilir ekler isim alanlı `kutuphane:` frontmatter bloğunda. |
| D22 | **Önce açık kaynağı benimse, sonra inşa et**; yalnız kama (sürüm atfı, delegasyon, açıklanabilir erişim, koruma) yazılır. Tescilli dağıtım nedeniyle **AGPL bileşen çekirdekte yok**; tüm lisanslar seçimden önce doğrulanır. |
| D23 | **Hiçbir şey kuruluma içeri erişmez; her bilgi akışı imzalı, sürüm zarflı paket**tir; ağ ve fiziksel medya (USB, veri diyotu) aynı paketi taşır; alan kurulum kendi kapısından geçirir. |

### 5.2 B1–B11

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D24 | Ontoloji (B1) | 9 boyut (E1–E9; E8 koruma `standard/envelope/sealed`, E9 erişim kipi `discover/read/use`). Yalnız **E5, E8, E9 zorunlu** ve zorlanır; diğerleri isteğe bağlı, açık sözlük. E3 köken ≠ güven, E5 hassasiyet ≠ egress. E9 doğrusal değil: `read` `use`'u kapsamaz. | 9 kapalı katalog alanı (OKF ruhuna aykırı, şişer). |
| D25 | Kategoriler (B2) | **M1 ürünü K1 referans + K2 runbook + K3 ajan talimatı.** K4 mevcut okuma altyapısı ölçüsünde. K7 karar modelleri **ayrı deney hattı**. K5/K6 ertelenir (kayıtlar çekirdekte zaten var). K8 gizli malzeme D33'e göre. Kategoriler ortak çekirdeğin profilleri; "şemada var" ürün vaadi değildir. | K4+K7'yi v1 ürün kapsamına almak. |
| D26 | Kitap (B3) | Kitap = OKF bundle + yönetişim zarfı + sunum profil(ler)i; **üç ayrı sürüm kimliği: içerik, profil, politika.** Atıf `içerik@sürüm + profil + parça`; erişim kaydı politika ve grant sürümünü taşır. Gömme profil seçimidir. Non-markdown varlık = representation, concept `resource` ile işaret eder. | Tek sürüm kimliği; OKF'den bağımsız iç model. |
| D27 | Master (B4) | Aynı kod tabanında **"master" rolü**; soyut master bilgi yönetimi/merkeziyet framework'ü, InfraMedic master'ın yerine de geçebilir. M1'de yalnız paket sözleşmesi. Kayıt defteri "son bildirilen durum" sunar. InfraMedic master değişmezleri (içeri erişim yok, yalnız imzalı artefakt, yetki genişletmez, offline recall) bağlayıcı. | Ayrı ürün ilk günden; v1'de master yok. |
| D28 | Delegasyon (B5) | M1: **tek seviyeli, süreli, iptal edilebilir** kullanıcı→ajan delegasyonu; her kullanımda devredenin **güncel** yetkisiyle kesişir; `purpose` kayıt amaçlı. Yetki sınırı arama, doğrudan okuma, önbellek, export ve sonuç tesliminde aynı. ReBAC arayüzü OpenFGA biçiminde; **M1 Postgres içi ilişki tabloları**, OpenFGA ölçüm sonrası. | Çok seviyeli delegasyon M1'de; yalnız rol ACL; M1'de OpenFGA servisi zorunlu. |
| D29 | Paket (B6) | OKF bundle + imzalı zarf (cosign offline / minisign — lisans doğrulanır). Zorunlu: **güven kökü** tanımı, anahtar yenileme/iptal, **replay koruması** (monoton sıra), **atomik import**; import akışı karantina → doğrulama → tarama → fark → insan onayı → yeni sürüm. İmza doğruluk/güvenlik kanıtı değildir. | Kendi format; yalnız import. |
| D30 | Karar modelleri (B7) | Ayrı **deney hattı**, M1 koşulu değil. Tek karar noktası (öneri: ingest sınıflandırma) + **insan etiketli** değerlendirme kümesi. Laya öncelikli, Jev karşılaştırma sağlayıcısı; ikisi aynı `systemone` sözleşmesi, LLMDAP üzerinden (#225). Laya Jev etiketleriyle eğitilip Jev etiketleriyle ölçülmez. Kalibrasyon, çekimserlik görev bazında ölçülür. | Paralel Jev+Laya shadow M1 şartı; model etiketini gerçeklik saymak. |
| D31 | Retrieval (B8) | Mimari: Postgres hibrit (vektör + BM25) + tek reranker. **Bileşenler küçük bir ölçümden sonra sabitlenir** (Türkçe kurum korpusu, dar yetki filtresi, hedef donanım). Adaylar: pgvector, pg_textsearch, Docling, bge-m3 / Qwen3-Embedding, bge-reranker / Qwen3-Reranker. | Bileşenleri ölçmeden sabitlemek; AGPL BM25 (ParadeDB, vchord_bm25). |
| D32 | Onyx (B10) | **Temel alınmaz** — mimari tercih (birincil nesne ve erişim sözleşmesi etrafında çekirdek). Onyx ve OKF ekosistem araçları "aday"; uygunluk doğrulanır. | Onyx CE fork'u; Onyx'i yan ürün olarak bağlamak. |
| D33 | Sırlar (B11) | **M1: model/Jev anahtarları yalnız LLMDAP'ta**; Kütüphane referans, grant ve korelasyon kaydı tutar. OpenBao, genel `sealed/use` ve `envelope/read` **M2**. Ön koşul: envelope içerikten türeyen metin, **vektör** ve önbelleklerin çözülebilirlik politikası. Ürün dili: "ajana sır verilmez" ("asla öğrenemez" değil). | Kütüphane'nin kendi enjeksiyon proxy'si; K8'in v1'de tam hâli. |
| D34 | Jev geçişi | Gerçek Jev çağrıları **#225 + güvenlik incelemesi** sonrası; o zamana kadar sözleşme, fixture, insan etiketli küme. LLMDAP dışı "experiment" yolu yok. | Etiketli LLMDAP dışı deney (D3/D18 ile çelişir). |

### 5.3 M1 (B9) ve önceki kararlarda düzeltmeler

| # | Karar |
|---|---|
| D35 | **M1 = tek uçtan uca kanıt senaryosu** (`04-…` §3): OKF/MD kitabı + metin PDF'i; bütün ve parçalı profil; insan (arayüz) + ajan (Kütüphane MCP); tek seviyeli delegasyon; sürümlü tıklanabilir atıf + "kütüphanede yok"; **birleşik audit** (erişim + LLMDAP egress, tek korelasyon); asgari imzalı import/export; basit runbook geri bildirimi; D18 kapıları (#222, #223). Kabul testleri 04 §3'te. **D9 bunun ile yer değiştirir.** Ertelenen: karar modeli shadow'u, DOCX/OCR çeşitliliği, gelişmiş profil yönetimi, çok seviyeli delegasyon, OpenBao/sealed/envelope, master federasyonu, stüdyo çıktıları. |
| D36 | **D9 dili düzeltildi:** "eski cevap yeniden üretilebilir" → "**eski cevap ve kanıtları (sabit sürümdeki atıflı pasajlar) yeniden gösterilebilir**". İçerik sürümü sabitlenir, **erişim hakkı sabitlenmez**: eski cevap açılırken güncel yetki denetlenir. |
| D37 | **D4/D13 netleşti — üç ayrı sınır:** doküman sunmak · talimatı etkinleştirmek · sırrı kullanarak işlem yapmak. K3 (skill, prompt, agent card) bir ajana sunulması talimat etkinleştirmedir → referans sunmaktan ayrı bir politika/onay kapısı. |
| D38 | **D14/D15 netleşti — kimlik rolleri:** IdP (kurum AD/LDAP ya da Keycloak — lisans doğrulanır) kimliği doğrular; LLMDAP egress'te bu kimliğin doğrulayıcısıdır; Kütüphane yetkilendirir. M1'de ek servis sayısı en aza indirilir (offline kurulum, yedekleme, anahtar kurtarma yükü). |
| D39 | **D7 netleşti:** sesli özet ve çoklu stüdyo çıktıları M1 dışında; "LLM deney platformu" hedefi ayrı deney hattında yürür, teslim kapsamını büyütmez. |
| D40 | **Recall semantiği** (B4–B6) M2 master işinden önce yazılır: teslim, uygulama zamanı, onay ve uygulanana kadarki durum. |

## 6. Kararlar — 2026-10-12 (ölçüm ve deney hattı)

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D41 | Ölçüm korpusu | **Karma korpus, retrieval ölçümü ve deney hattı ortak kullanır:** (a) kendi dokümanlarımız — Nöbetçi/InfraMedic repolarındaki markdown (runbook, mimari not, karar kaydı, ajan talimatı; TR/EN karışık; kaynak repolar salt-okunur, yalnız ölçüm ortamına kopya); (b) kamuya açık Türkçe mevzuat (FSEK md. 31; uzun saf Türkçe + metin-katmanlı PDF). Müşteri dokümanı kullanılmaz. Repoya yalnız manifest (yol + içerik özeti + kaynak commit) girer, içerik girmez. | Yalnız kamuya açık set (kurum gerçekliğini ölçmez); müşteri dokümanı (gizlilik riski). |
| D42 | Hedef donanım | **GPU'lu kurum varsayılır** (ürün yerel ajan çalıştıran işletmeler için). Ölçüm DGX Spark'ta iki kipte: GPU ve **GPU'suz (CPU)** — paylaşımlı unified memory'yi işgal etmemek ve hafif kurulum profilini görmek için. Ağır/uzun GPU işi öncesi operatöre sorulur. | Ayrı GPU'suz sunucu profili (hedef müşteride gereksiz). |
| D43 | İnsan etiketli küme | **Model taslak çıkarır, insan karar verir:** Claude kategori (K1–K8), hassasiyet ve egress etiketi ile soru→pasaj eşleşmesi taslaklar; **operatör** telefon dostu etiketleme sayfasında onaylar/düzeltir. Örneklerin **~%30'u kör** (taslak gösterilmeden) etiketlenir; model–insan uyumu ve taslağın çapalama etkisi bu dilimde ölçülür. Gerçeklik referansı insan etiketidir (D30). | Model etiketini gerçeklik saymak; tamamen elle etiketleme (emek). |
| D44 | Laya shadow (etiketleme) | Etiketleme katmanında **`laya-multilingual` zero-shot shadow** olarak çalışır: tahminleri etiketleyene **gösterilmez**, yalnız insan etiketine karşı ölçülür (doğruluk, kalibrasyon, çekimserlik; kör dilim ana ölçü). Çevrimdışı batch, yerel ağırlık (sürüm/özet kayıtlı), ağ çıkışı yok, D41 korpusu; bu bir **ölçümdür, ürün yolu değil** — Laya'nın ürün/shadow entegrasyonu D30 gereği LLMDAP #225 üzerinden. Model kartına göre taban modelde zero-shot zayıf beklenir (Türkçe MASSIVE 0.437); amaç etiketleme katmanında işe yarayıp yaramadığını ve ince ayar ihtiyacını görmek. | Laya tahminini etiketleyene öneri olarak göstermek (çapalama; ölçümü bozar). |

## 7. Kararlar — 2026-10-12 (ürün brifi, M1 ve sadelik)

Kaynak: `05`–`07` taslakları, Astra incelemesi (`research/2026-10-12-astra-review-m1-raw.md`), Claude + Astra
ortak önerileri. Operatör onayladı ve ek ilke koydu: **"kodun aşırı karmaşıklaştırılmaması çok önemli."**

| # | Konu | Karar | Reddedilen |
|---|---|---|---|
| D45 | Ürün brifi, yol haritası, M1 | `05`, `06`, `07` **onaylandı**; Astra incelemesiyle sıkılaştırılmış kabul testleri (AT-01…AT-16) geçerli. | — |
| D46 | **Sadelik ilkesi; D6 değişir** | Sadeleştirme **servis ve soyutlama sayısını azaltarak** yapılır, yönetişim kapılarını azaltarak değil. M1 **tek Python uygulaması**: CLI, API ve MCP aynı fonksiyonları çağırır; mikroservis, Redis, görev kuyruğu, ayrı audit servisi, dinamik plugin keşfi yok — bileşenler küçük, sürümlü fonksiyon arayüzleri. **M1'de önbellek yok.** InfraMedic'ten **kod taşınmaz, fikir taşınır** (içerik özetiyle kimlik, atıf tutamacı, kısıtlı → bulut yok); Core Postgres üstünde yeni ve küçük yazılır. | D6'daki "InfraMedic bilgi katmanını kopyala-ameliyat et" (~17 bin satır, SQLite, filo kavramları); BM25/reranker'ı sadelik için M1'den çıkarmak (D31'i bozar). |
| D47 | M1 dilim sırası | **M1a katalog → M1b yetki çekirdeği → M1c kimlik/egress/denetim kesiti → M1d arama ve atıf → M1e yüzeyler (API, MCP, arayüz) → M1f paket ve geri bildirim.** Paket manifesti ve sıra kapsamı M1a'da tanımlanır. Kimlik/egress #222/#223 gelene kadar fixture ile yürür; ilgili testler gerçek upstream olmadan yeşile dönmez. | Önce arama, sonra yetki (aramaya yetkiyi sonradan eklemek en pahalı yeniden çalışma). |
| D48 | M1a teknik çerçeve | Başlangıçta **dört tablo** (kitap, içerik/profil/politika sürümü; sürümler değişmez); diğer tablolar ihtiyaç duyan dilimde. Kimlikler: sürümlü kanonik kodlama + SHA-256. Bağımlılıklar hafif: markdown-it-py (MIT), pypdf (BSD-3), psycopg (LGPL-3, dinamik bağlama), PyYAML (MIT); Docling sonradan profil bileşeni. **Diskte şifreleme volume seviyesinde** (E8 `standard` tanımı), uygulama içi şifreleme kodu yok; kurulum gereği olarak belgelenir. | Uygulama içi sütun şifreleme (M1'de karmaşıklık); her şeyi tek JSONB torbasına koymak. |
| D49 | LLMDAP upstream işleri | #222 ve #223'ü **LLMDAP'ın kendi oturumu** geliştiriyor (operatör, 2026-10-12). Kütüphane M1c'yi taklit LLMDAP fixture'larıyla ilerletir; AT-10/AT-11 gerçek upstream gelmeden yeşile dönmez (D18). | Kütüphane oturumunun LLMDAP reposunda geliştirmesi. |
| D50 | M1c kimlik | **Core OIDC/JWT token'larını kendisi doğrular** (issuer, audience, süre, imza; JWKS). Geliştirme ve testte yerel üretilmiş anahtar; **Keycloak M1c'ye eklenmez** (D46). Kurum IdP bağlantısı #223 gelince test edilir. | M1c'de Keycloak servisi (offline kurulum ve bakım yükü). |
| D51 | Paket imzası (M1f) | **Ed25519 ayrık imza, kanonik manifest üzerinde** (`cryptography`, Apache-2.0/BSD); paket = sıkıştırılmamış tar (`MANIFEST.json`, `MANIFEST.sig`, `content/…`). Güven kökü: yönetici bant dışı doğruladığı parmak izini vermeden anahtar eklenemez. Sıra: (imzalayan anahtar, kitap) başına. minisign/cosign biçim uyumluluğu M2'de değerlendirilir (D46: M1'de en az parça). | M1'de minisign/cosign biçimini yeniden yazmak ya da araç bağımlılığı (air-gapped kurulum yükü). |
| D52 | LLMDAP bağlantısı (#226, #228 sonrası) | **Core LLMDAP'a kendi özne anahtarıyla bağlanır** (`GATEWAY_AUTH_MODE=subject-keys`, özne `svc-kutuphane`): kimlik başlıkla iddia edilmez, kanıtlanır; başlıkla başka özne adı LLMDAP'ta 401. Hizmet edilen kişi `x-llmdap-for-subject` etiketiyle LLMDAP zincirine yazılır; ajan dahil tam çağıran Core'un `model_call` kaydında, çağrı kimliğiyle birleşir (AT-09). **Embedding LLMDAP `surface: "embeddings"` rotasından** (openai şeması); vektörler `chunk_vector`'da model adıyla, M1'de ANN indeksi yok (yetkili kitaplarda tam tarama). **Hibrit = FTS + vektör, RRF** (M0: R@10 0.56 → 0.71). **Reranker LLMDAP'ta rerank yüzeyi gelene kadar yok** (D3: model yalnız LLMDAP'tan); upstream LLMDAP#236. Sade bridge imajı: LLMDAP#237. | Kullanıcı token'ını LLMDAP'a iletmek (LLMDAP'ın on-behalf-of'u henüz yok, #228 takip işi); reranker'ı Core içinde çalıştırmak (tek egress/denetim iddiasını deler). |
| D53 | Ontoloji kanonu (operatör, 2026-10-14) | **Bilgi fasetlerinin anlamlı davranışsal ayrımları olmalı:** her değer sistemin bir davranışını (kapı, sıralama, atıf yetkisi, arşiv, delegasyon, sunum) değiştirir; değiştirmeyen değer çıkarılır. **Faset durum değişimleri uygulamadan önce planlanır** (tetik, aktör, otomatik mi, denetim, geri alma). Ontoloji sistemin çekirdeğidir; uygulama sade kalır. Kategoriler insan türü değil, işlevseldir. Etiketleme v1 (K1–K8) durduruldu; v2 taslağı `docs/09-ontology-v2.md` (Claude, Astra, Mythos ortak beyin fırtınası), operatör onayı bekliyor; onaylanınca D24/D25 revize edilir. | Belge başına tek insan kategorisi (v1: yavaş, karma belgelerde bilgi kaybı, plan/tasarım/inceleme için sınıf yok). |
| D54 | Ontoloji v2 onayı (operatör, 2026-10-15) | **`docs/09-ontology-v2.md` v2.0 olarak onaylandı.** D24'ün E1 ekseni ve K1–K8 kategorileri yerini fasetlere bırakır: Role (`rule`/`evidence`/`none`), Agent instruction, Standing (`approved`/`pending`/`retired`), Time basis (`durable`/`window`, `as_of`=`window(t,t)`), Scope; E5 ikiye ayrılır: Sensitivity dışa aktarımı, Egress model rotasını yönetir (D25 bu anlamda revize). K1–K8 yalnız form ön ayarı. Birim blok (deterministik kural, profil sürümünde), bölüm türetilmiş görünüm. Kararlar: (1) karma hassasiyet belge düzeyinde, kör dilimde %10 üstü ise bölüm kapısı tasarlanır; (2) `curate` yalnız `user:`; (3) doğrudan grant'e `expires_at`, kaynağı emekliye ayrılan grant otomatik askıya alınır; (4) id sütunlu tablo satırı ayrı blok; (5) iş sırası: kural önericiyi ölç → etiketleme v2 → etiketle → annotation olayları. | v1 kategorileriyle devam. |
| D55 | Ana çıktı ve yön (operatör, 2026-10-20) | **Ana çıktı standardın kendisidir**: açık kaynak bir bilgi yönetimi standardı ve çerçevesi; Kütüphane onun referans uygulamasıdır. İki kapsam: kurumların on-prem kendi bilgisini yönetmesi, ve kurulumların insanlığın birikmiş bilgisini toplayan, süzen, sınıflayan ve aktaran soyut yönlendiriciler olması. Standart mevcut standartları birleştirir (OKF, PROV-O, SKOS, ODRL, nanopublication, VC/C2PA, MCP/A2A, Zanzibar) ve **uyumluluk düzeyleriyle** sunulur. **Kullanım hakları** (lisans, rıza, kişisel veri, yargı yetkisi, amaç sınırı) EU AI Act ve GDPR ile uyumlu eklenir; hangi düzeyde olacağı vizyon belgesinde ve beyin fırtınası 3'te kararlaştırılır. Sıra: NotebookLM zihin haritası → operatörün seçtiği makaleler → **vizyon belgesi** (`docs/10-vision.md`) → **beyin fırtınası 3** (Astra ve Mythos serbest: konuşulanların ötesine geçmeleri, araştırma yapmaları ve kör noktaları kapatmaları istenir) → etiketleme v4. **Etiketleme askıya alındı.** v2 fasetleri vizyon içinde bir profil olarak yeniden değerlendirilir. | Ürünü önce, standardı sonra yapmak; v2 etiketlemesine devam etmek. |
| D56 | Lisans ve taslak 0.2 kararları (operatör, 2026-10-20) | **D10 bir yanlış anlamaydı: standart ve Kütüphane (çerçeve) tamamen açık kaynaktır.** D10'un "tescilli" kısmı ve D22'nin "tescilli dağıtım nedeniyle" gerekçesi geçersiz. Öneri: kod Apache-2.0, şartname metni CC-BY-4.0; bilgi içeriğinin lisansını her yayıncı seçer (`rights.license`, `unknown` = izin yok); ifadeler ve manifestler için önerilen varsayılan CC0-1.0. **D54 (2) değişir:** delegasyonu yalnız insan verir; onay imzalı, kapsamlı ve süreli delegasyonla otomatik olabilir, onaylayan hiçbir zaman yazar değildir. Geçici ad `kstd`. Durum akışının en çok yaşı (L3) ayrıntılandırılacak; Kütüphane tamamen çevrimdışı çalışabilmelidir. Taslak: `docs/11-standard-draft.md` 0.2. | Tescilli referans uygulama; yalnız insan onayı. |
| D57 | Lisanslar ve durum yaşı (operatör, 2026-10-21) | **Bilgi paketlerinin lisans önerisi onaylandı:** içerik lisansını yayıncı seçer (`unknown` = izin yok); ifadeler ve manifestler için varsayılan CC0-1.0; makbuz ve denetim kayıtları paylaşılmaz. **Durum akışı en çok yaşı: seçenek c:** her güvenilen kaynak için ayrı sınır, varsayılan 30 gün; hava boşluklu kaynak için yönetici "hiçbir zaman" seçebilir, bu durumda her kullanımda "durum denetlenmedi" uyarısı görünür; süre aşılınca içerik yalnız kural yetkisini kaybeder, kanıt olarak kalır. Karar kuralının ilk uyumluluk vakaları `kstd/tests/decision/cases.yaml` (20 vaka). | Tek genel sınır; süre aşılınca içeriği gizlemek. |
| D58 | Kod lisansı ve ilk gün değeri (operatör, 2026-10-22) | **Kod Apache-2.0, şartname metni CC-BY-4.0** (`LICENSE`, `NOTICE`); D10 ve D22'nin tescilli kısımları kaldırıldı, AGPL yasağının gerekçesi artık lisans uyumu (Apache-2.0 ile birleşik dağıtım). **İlk gün değeri Kütüphane'nin kendisi:** `kstd.yaml` olan bir klasör içe aktarılınca cevaplar köken, geçerlilik ve lisansı gösterir; işleme kuralları Kütüphane ve LLMDAP tarafından ek iş olmadan uygulanır. Sıradaki iş: L0 doğrulayıcısı ve `kstd.yaml` içe aktarımı, sonra etiketleme v4 planı. | — |
| D59 | Görev yeniden çerçevelendi; etiketleme v4 kararları (operatör, 2026-10-22) | **Tek başına bir standart önermek çok büyük bir görev.** Önce mevcut durumu (W3C topluluk grupları, IETF, açık kaynak topluluklar, mevcut standartlar) bulup anlamak; bu topluluklara katılıp katkı vermek; kstd taslağı bir katkı ve test aracı olarak kalır, boşluk bulunan yerde öneri olur. Kütüphane bu çalışmanın referans uygulaması ve deney tezgâhıdır. İlk iş: manzara çalışması `docs/13-landscape.md` (grupların kapsamı, durumu, açık soruları, veri setleri ve test takımları, kstd ile örtüşme, katkı yolu). **Etiketleme v4:** 8 alan doğru; dosya başına bir etiket seti + "bölünmeli" işareti; küçük bir açık test seti eklenir; yerel LLM önerici `RadixArk/Qwen3.8-27B-NVFP4` (Spark'ta zaten vLLM ile servis ediliyor). Alanlar sayfa yapılmadan önce manzara çalışmasına göre yeniden denetlenir. | Standardı tek başına tamamlayıp sonra duyurmak. |
| D60 | Manzara çalışmasının alan değişiklikleri onaylandı; katkı ön koşulları (operatör, 2026-10-22) | `docs/13` §3.2'deki değişikliklerin hepsi onaylandı: origin `assisted` (+ `reviewed_by`, dışa aktarımda AI-generated işareti yok, AB YZ Yasası md. 50(4)); personal_data `synthetic` (yasal dayanak gerekmez, yalnız güvenilen ihraççıdan); `ai_use` üç durumlu (yok = belirtilmemiş; karar onu `n` sayar; dışa aktarımda `n` yazılmaz); yasal dayanak DPV kodu; `receipt` → `use_record`. Şirket W3C hesabıyla CLA'yı kabul etti. Repo herkese açık olacak. Katkıları operatör kendisi yapar; rehber `docs/14-contributions.md`. | Kendi terimlerimizi korumak. |
| D61 | Önce gerçek kullanım, sonra katkı (operatör, 2026-10-22) | Topluluklara katkı **beklemede**: önce Kütüphane operatörün gerçek iş projelerinde kullanılır, test edilir, gerçek kullanım durumları anlaşılır; katkı önerileri bu deneyime göre yeniden değerlendirilir (`docs/14`). Repo herkese açıldı (2026-10-22; geçmiş ve GitHub metinleri sır ve korpus için tarandı). Patent yok. Açıklama eşlemesi: `model` → `ai-autonomous`, `unknown` → anahtar yok (karar içinde `unknown` yine `model` sayılır). | Hemen katkı vermek. |
| D62 | Etiketleme v4 veri seti ve zararlı ajan örnekleri kabul (operatör, 2026-10-23) | `docs/16` §2'deki dört katman (R radar, W çalışma grupları/açık setler + nanopub, A ajan belgeleri, S sentetik; ~820 öğe) kabul edildi; küçük gruplar halinde, kullanım sırasında etiketlenir. Yayımlanmış zararlı ajan örnekleri (SkillSpector, Skill-Inject) ve kendi zararsız kopyalarımız kullanılır; canlı zararlı skill indirilmez. Program çıktısının kökeni açık: operatör `tool` yönünde, ayrık kategorilerden emin değil; yeni değer kesinlikle üretken YZ içermeyecek biçimde tanımlanmalı. Seçenekler ve kesin sınır `docs/17`. | — |
| D63 | Program çıktısının kökeni: `tool` (operatör, 2026-10-23) | `docs/17` seçenek B şimdilik kabul: tek değer `tool` = yazılım içeriği insanların yazdığı kurallarla (kod, şablon, sorgu, yapılandırma, kural seti) üretti ya da olayları kaydetti; hiçbir adımda öğrenilmiş model yok; `software_agent: {name, version}` zorunlu. İki eksenli seçenek D etiketleme v4 gruplarından sonra verilerle değerlendirilir. Üretken olmayan öğrenilmiş modeller (sınıflandırıcı, embedding, nöral OCR) `model` sayılır. Kural motorları için ayrıntı `docs/17` §8; karar açık. | Seçenek C (`programmatic` + `observed`): davranış farkı mevcut alanlardan okunabiliyor. |
| D64 | Kural motorlarının kökeni (operatör, 2026-10-26) | `docs/17` §8 kabul: eşik/karar tablosu, politika motoru ve çıkarım motoru (tür 1–3), tüm kuralları, eşikleri ve ağırlıkları insanlar yazdıysa `tool` (software_agent = motor + kural seti sürümü); herhangi bir parçası veriye uydurulmuşsa (tür 4) `model`; kural setini LLM yazdıysa `model`, adı belli bir kişi esastan incelediyse `assisted`. kstd üretim yolunu kaydeder; bir sistemin yasal olarak "YZ sistemi" olup olmadığına karar vermez. | YZ Yasası rehberine göre çıkarım motorlarını `model` saymak. |
| D65 | Özel etiketler ve etiketleme sayfası (operatör, 2026-10-26) | Özel etiketler (tags) arama ve düzen içindir; **bazıları erişimi de belirler**. Etiketleri insanlar ve ajanlar ekler; **ajanın etiketi insan onayı bekler**. Sözlük **yalnız kontrollü liste** (SKOS kavram şeması). Erişim etiketi yönetilen bir fasettir: kuralları (`docs/19` §5.2) karar vakalarıyla yazılmadan ve öğe düzeyi erişim (G10) olmadan kod yazılmaz. Etiketlemenin amacı ikisi birden: gerçek kitapları hazırlamak ve önericileri ölçmek (~%30 kör örnek). Belge türü ön ayarları (not, karar, prosedür, ajan talimatı, kayıt) yeterli. | Yalnız keşif etiketleri (Astra önerisi) — operatör erişim etiketi istedi. |
| D66 | Belge türü etiketi kaldırıldı (operatör, 2026-10-26) | Etiketleme formunda "belge türü" sorulmaz: D54 belge kategorilerini etiket olarak zaten kaldırmıştı ve tür hiçbir kararı değiştirmez (D53). Yerine isteğe bağlı tek soru: "Kural / karar mı?" (kabul, yetki, geçerlilik ve kapsam alanlarını açar). Formda 3 zorunlu soru kalır: köken, ajan talimatı mı, kişisel veri. | D65'teki tür ön ayarları. |
| D67 | Etiketleme v5: önce kürasyon (operatör, 2026-10-26) | v4 kuyruğu (1.063 öğe) kapandı; `docs/20` planı kabul: ~190 otomatik doğru cevaplı belge, 72 senaryo, 120 insan vakası. Öncelikli işlemler: **arama ve model cevabı**. İnsan vakalarında önce operatör karar verir, sonra öneriler gösterilir. İkinci okuyucu: **Astra** (insan-insan uyumu ölçülmez; sınır raporlanır). Eskiyen dış durum yalnız kural yetkisini düşürür; askıya alma ayrı politika ister. Lisansı belirsiz vakalar açık sette yalnız referans + hash + etiket olarak yer alır. | v4 kuyruğuna devam. |
| D68 | Reddedilen durum ve kurullar (operatör, 2026-10-26) | Kabul fasetine ayrı **`rejected`** durumu eklendi: `pending` → `rejected` (hiç kabul edilmedi; geçmiş görünümünde okunur, olağan kullanımda yok). `withdrawn` yalnız bir kez kabul edilmiş öğeler içindir. Bir kurul (Python Steering Council, IESG) kaynağın **karar vereni** olarak kaydedilir (`decided_by`); yerel kabul için yine adı belli bir kişi ya da yetkilendirilmiş ajan gerekir. | `withdrawn` + neden; kurulu yerel onaylayan saymak. |
| D69 | Konumlandırma: yönetişimli bilgi kataloğu + ajan belleği (operatör, 2026-10-27) | Kütüphane bir RAG platformu değildir: **veri kataloğu + ajan bellek katmanı**dır; kolay kullanım, yetki devri, RBAC ve MCP sunar. RAG platformları ve orkestratörler onu yönetişimli kaynak olarak kullanır. Vizyon 1.0: `docs/23`. İlk müşteri: ADC ve nöbetçi-mcp (#67–#81); yol haritası bu isteklerden çıkar. kstd iç sözleşmedir; dışa OKF / DataHub eşlemesiyle içe-dışa aktarılır. Minimal çekirdek kararı açık: karar verilene kadar yeni ifade türü ya da kategori eklenmez. | RAG platformu olmak; kstd'yi önce bağımsız standart olarak büyütmek. |
| D70 | Köken yazma yolundan hesaplanır (operatör, 2026-10-27) | `docs/22` §4 R1–R7 kabul: sunucu kökeni kimliği doğrulanmış yazma yolundan hesaplar; ajan yolu her zaman `model` verir. `human` ya da `assisted` yalnız kişinin kendi oturumunda, tam metni görüp, metnin özetine (digest) bağlı passkey onayıyla verilir; bir bayt değişirse yine `model`. Kompl bakımcısına öneri yapılmayacak. | Yazanın beyanına güvenmek; MCP form onayı. |

## 8. Açık sorular

- Mevzuat (D41 b): mevzuat.gov.tr bu makineden erişilemiyor; aday kaynak HF `CtnkyaABC/turkish-law-corpus`
  (CC BY 4.0) + elle kontrollü `mtntasci/turkish-legal-rag` soruları. Metin-katmanlı PDF fixture'ı ayrıca gerekli.
