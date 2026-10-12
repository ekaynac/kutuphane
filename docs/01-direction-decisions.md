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

## 8. Açık sorular

- Mevzuat (D41 b): mevzuat.gov.tr bu makineden erişilemiyor; aday kaynak HF `CtnkyaABC/turkish-law-corpus`
  (CC BY 4.0) + elle kontrollü `mtntasci/turkish-legal-rag` soruları. Metin-katmanlı PDF fixture'ı ayrıca gerekli.
