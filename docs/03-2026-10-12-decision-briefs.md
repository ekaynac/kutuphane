# Kütüphane — karar brifleri (üçüncü beyin fırtınası)

Tarih: 2026-10-12. Durum: **kapandı.** Bu briflerin ★ önerileri Astra incelemesiyle revize edildi
(`04-2026-10-12-joint-proposals.md`); onaylanan kararlar `01-direction-decisions.md` D21–D40. Çelişki hâlinde
04 ve 01 geçerlidir. Kural: örnekler niyeti aktarır, overfit/overcommit yok (`02-…` §0).

## 0. Operatör girdileri — 2026-10-12

1. **OKF vizyonu benimsendi.** *"OKF is an open format for representing knowledge — metadata, context, and curated
   insight about your data and systems. People write it, agents generate it, organizations exchange it. Both humans
   and LLMs can consume it without special tools."* ve *"minimally opinionated … almost no rules, maximum adoption
   surface."*
2. **Minimally opinionated bir bilgi yönetim merkezi**: mevcut standartlar ve açık kaynak kütüphane/framework'ler
   değerlendirilerek; olabildiğince **open-source, on-prem ve air-gapped dostu**.
3. **Air-gapped ortamlara bilgi güncellemesi offline yollarla** (fiziksel cihaz vb.) yapılabilmeli.
4. **İki yeni ontolojik boyut:** *şifreleme* ve *erişen aktörün bilgiyi okuyup okuyamayacağı*. Örnek (niyet):
   ajanlar için **granted key** — *encrypted key* (yalnız erişim sahibi aktör **kullanır**, kendisi bile **asla
   okuyamaz**; hesap şifresi, API anahtarı) ve *encrypted information* (erişen okuyabilir).
5. **Jev bir model sınıfı olarak düşünülür.** Öncelik Laya; Jev API anahtarı mevcut. Jev ile testler ve shadow
   run'lar, sonra Laya dahil edilebilir ya da Jev ve Laya paralel shadow.
6. **Master platform**: InfraMedic master'dan bağımsız düşünüldü; ama teknik olarak InfraMedic master'ın yerine de
   kullanılabilecek **soyut bir master bilgi yönetimi ve merkeziyet framework'ü**.
7. Kararları beklenen başlıklar **ayrıntılandırılmalı** (bu doküman).

## 1. Yeni yön ilkeleri (öneri)

**İ1 — OKF-yerli, minimally opinionated çekirdek.** Kütüphane'nin taşınabilir birimi bir OKF concept'idir
(Markdown + YAML frontmatter, tek zorunlu alan `type`). Kütüphane OKF'nin *üstüne* kural koymaz; yönetişimi
(erişim, şifreleme, sürüm otoritesi, delegasyon, audit) **katalogda** tutar, dosyanın içinde değil. Sebep: OKF
erişim/hassasiyet alanı tanımlamıyor (v0.2) ve tüketicilerin bilinmeyen anahtarları korumasını şart koşuyor →
Kütüphane'ye özgü taşınabilir bilgiler tek bir isim alanlı frontmatter bloğunda (`kutuphane:`) gezer, otorite
yine katalogdur.

**İ2 — Önce benimse, sonra inşa et.** Her bileşen için önce açık kaynak bir aday (lisansı doğrulanmış) aranır;
yalnız kama (yönetişim, delegasyon, açıklanabilir erişim, sürüm atfı) kendimiz yazılır. §4'te tablo.

**İ3 — Hiçbir şey içeri erişmez; her şey imzalı dosya olarak taşınır.** InfraMedic master kanonunun en sağlam
değişmezi soyutlanarak Kütüphane'nin tamamına uygulanır: kurulumlar arası her bilgi akışı (güncelleme, geri
çağırma, öneri, import/export) **imzalı, sürüm zarflı bir pakettir** ve ağ ya da fiziksel medya ile aynı
biçimde taşınır. Alan kurulum, gelen her şeyi **kendi kapısından** geçirir.

## 2. Ontoloji güncellemesi — iki yeni eksen

`02-…` §2.1'deki E1–E7'ye eklenir:

| Eksen | Soru | Değerler (öneri) |
|---|---|---|
| **E8 Koruma** | İçerik nasıl şifreli tutulur? | `standard` — disk/DB seviyesinde şifreli, yetkili okumada Kütüphane çözer · `envelope` — içerik, alıcı (aktör/rol) anahtarlarına sarılmış bir DEK ile şifreli; yalnız yetkili alıcı bağlamında çözülür · `sealed` — içerik Kütüphane'nin okuma yüzeylerinde **hiç çözülmez**; yalnız bir *kullanım aracısı* içinde, kullanım anında çözülür |
| **E9 Erişim kipi** | Erişimi olan aktör ne yapabilir? | `discover` — varlığını ve meta veriyi görür · `read` — içeriği alır · `use` — içeriğin **kendi adına kullanılmasını** tetikler, içeriği **asla görmez** |

Operatörün iki örneği bu iki eksenin kesişimidir:
- *encrypted information* = `envelope` + `read`
- *encrypted key* = `sealed` + `use`

Diğer kombinasyonlar da anlamlı: `envelope` + `discover` (hassas bir raporun varlığı görünür, içeriği yalnız
yetkiliye), `standard` + `read` (sıradan kanon). `sealed` + `read` **geçersizdir** (sealed tanımı gereği okunamaz).

### 2.1 `use` kipinin dürüst sınırları

"Asla okuyamaz" iddiası ancak şu koşullarla doğrudur; bunlar ürün sözleşmesine yazılmalı:
1. **Kullanım aracısı ajanın dışında çalışır.** Ajan "şu anahtarla şu isteği yap" der; anahtarı aracı enjekte
   eder. (LLMDAP bridge bunu bugün model route'ları için zaten yapıyor: sağlayıcı anahtarını route başına enjekte
   ediyor, istemci anahtarı hiç tutmuyor.)
2. **Anahtar hedefe bağlıdır.** Her sealed anahtar izinli hedef(ler)e (host, yöntem, yol) bağlanır; aksi hâlde
   ajan isteği kendi sunucusuna yönlendirip anahtarı sızdırır.
3. **Yankı taraması.** Hedefin cevabı ajana dönmeden önce, kullanılan sırrın birebir değeri maskelenir
   (InfraMedic'in "leased-secret echo scanner" fikri: değer bilindiği için tahmin değil birebir eşleşme).
4. **Hedef sırrı görür.** `use` sırrı ajandan saklar, hedef sistemden değil. Kısa ömürlü/dinamik kimlik bilgisi
   (OpenBao dynamic secrets) bu riski daraltır.

## 3. Karar brifleri

Her brif: *nedir · neden önemli · seçenekler · öneri · kararın sonuçları.* ★ = öneri.

### B1 — Ontoloji eksenleri

**Nedir.** Bir bilgi öğesini sınıflandıran, birbirine dik boyutlar. Kategori (ürün türü) bunların kesişiminden
doğar; tek bir "tür" alanına çökertilmez.

**Neden önemli.** Kütüphane'nin Context7'den farkı "bilgi kategorilerine yaklaşımı"dır. Eksenler yanlış
çökertilirse (ör. "gizli" bir tür olursa) her yeni ihtiyaç yeni bir tür doğurur ve sistem şişer; dik eksenlerle
yeni ihtiyaç çoğu zaman mevcut değerlerin yeni bir kombinasyonudur.

**Eksenler (9):** E1 epistemik tür · E2 sunum biçimi · E3 köken/güven · E4 yaşam döngüsü · E5 erişim sınıfı
(hassasiyet, hedef kitle, egress) · E6 uygulanabilirlik · E7 tüketici · **E8 koruma** · **E9 erişim kipi**.

**OKF ile eşleme.** E1 ≈ OKF `type` (açık sözlük); E3 ≈ OKF v0.2 `generated` / `verified` / `sources`; E4 ≈
`status` / `stale_after`; E6 ≈ `resource` + `tags`. E5, E8, E9 OKF'de **yok** → katalogda (İ1).

**Seçenekler.** a) ★ 9 eksen; E1 değerleri açık sözlük (OKF gibi), diğerleri kapalı küçük kümeler.
b) Daha az eksen (E7 ve E6'yı kategoriye gömmek) — daha basit, ama "aynı içerik iki tüketiciye iki biçim" ilkesi
kaybolur. c) Değişiklik (yaz).

**Sonuçları.** Katalog şemasında 9 alan/ilişki; arayüzde filtre olarak görünür; MCP araçları E2'ye göre farklı
yanıt biçimi seçer.

### B2 — v1 kategorileri (ürün türleri)

**Nedir.** Kullanıcının ve ajanın "bu ne?" sorusuna verdiği adlar; eksenlerin doğal kesişimleri.

**Adaylar.**

| # | Kategori | Kesişim (özet) | v1? |
|---|---|---|---|
| K1 | Referans eserler (manuel, standart, uzun PDF) | referans · parçalı+gömülü · read | ★ |
| K2 | Prosedürler / runbook'lar | prosedür · yapısal adımlar · sonuç defteri | ★ |
| K3 | Ajan talimatları (skill, prompt, agent card, AGENTS.md) | ajan talimatı · bütün · harness uyumluluk beyanı | ★ |
| K4 | Yapısal referanslar (şema, sözlük, terimce) | referans · sorgulanabilir · exact lookup | ★ hafif |
| K5 | Kayıtlar / kanıtlar (rapor, karar, transkript) | kayıt · değişmez · zaman indeksli | şema |
| K6 | Öğrenilmiş bilgi (örüntü, ders, türetilmiş özet) | yargı · kürasyon kapısı | şema |
| K7 | Model / karar artefaktları (model kartı, eval raporu, karar defteri) | model · çağrılabilir | ★ shadow (B7) |
| **K8** | **Gizli malzeme** (granted key, kimlik bilgisi, gizli not) | E8 `envelope`/`sealed` · E9 `read`/`use` | **karar (B11)** |

**Not.** K8 bir "kategori" olarak görünür ama gücü eksenlerden gelir: herhangi bir K1 belgesi de `envelope`
olabilir. K8'i ayrı adlandırmanın sebebi arayüz ve yaşam döngüsü (rotasyon, iptal, son kullanma) farklılığıdır.

**Seçenekler.** a) ★ v1 = K1 + K2 + K3 + K4 (hafif) + K7 (shadow); K5/K6 şemada; K8 B11'e göre.
b) v1 = K1 + K2 + K3; geri kalan M2. c) başka.

### B3 — "Kitap" tanımı (katalog ürünü)

**Nedir.** Kataloğun yayımlanan, sürümlenen, paylaşılan birimi.

**Öneri tanım.** **Kitap = bir OKF bundle'ı (içerik) + bir yönetişim zarfı (katalog: erişim, koruma,
delegasyon) + bir veya daha fazla sunum profili + içerik adresli sürüm.**
- *Sunum profili* = ayrıştırıcı + parçalayıcı + gömücü + indeks + teslim biçimi; her biri sürümlü, takılabilir.
  Gömme bir **profil seçimidir**, kategori özelliği değil (bir skill kitabı gömülmeden "bütün" teslim edilir; bir
  manuel kitabı gömülü + alıntılı teslim edilir; aynı kitap iki profille servis edilebilir).
- *Sıcak tutma* (önbellek, ön-gömülmüş indeks) bir profil parametresidir; teknoloji (Redis vb.) ayrı karar.
- Sürüm = bundle içeriğinin içerik adresi (commit benzeri); her cevap `kitap@sürüm#concept§parça` atfı taşır.

**Neden OKF bundle.** OKF bundle'ı zaten "kendini tanımlayan bilgi kümesi"dir; kitabı onun üstüne kurmak
import/export'u bedavaya getirir ve ekosistemdeki üretici/doğrulayıcıları (okflint, OKF-Schema, okf-postgres,
OpenWiki) kullanılabilir kılar.

**Seçenekler.** a) ★ yukarıdaki tanım. b) Kitap = koleksiyon (OKF'den bağımsız iç model, OKF yalnız export).
c) değişiklik.

**Sonuçları.** Non-markdown varlıklar (PDF, görsel) OKF'de tanımsız → kitabın içinde orijinal dosya bir
*representation* olarak saklanır, OKF concept'i `resource` ile ona işaret eder (InfraMedic katalog modeli:
version → representation).

### B4 — Master platform

**Nedir (operatör).** Soyut bir **master bilgi yönetimi ve merkeziyet framework'ü**; InfraMedic master'dan bağımsız,
ama onun yerine de kullanılabilecek.

**InfraMedic master kanonundan soyutlanan değişmezler** (`ekaynac/inframedic-master`, docs dalı, 2026-08-28):
1. **Master hiçbir kuruluma içeri erişmez**; kurulum dışa doğru (opt-in) gönderir, ya da paket elle taşınır.
2. Master'ın kuruluma verdiği her şey **imzalı bir artefakttır**; kurulum onu inceler, kendi kapısından geçirerek
   import eder. **Hiçbir dönen nesne kurulumda yetki genişletmez**, ayar/pin/indeks değiştirmez.
3. Tek istisna: **imzalı geri çağırma (recall)** — bir bilgi/model/öğe yayından kaldırılır; offline teslim
   edilebilir (dosya, fetch değil).
4. **Kurulum kayıt defteri**: master her kurulumun sürümünü ve sahip olduğu kitap sürümlerini tutar; uyuşmazlığı
   *raporlar*, üzerine yazmaz.
5. Air-gapped kurulumlar **ikinci sınıf değildir**; master'sız da tam çalışır.

**Kütüphane Master = bu değişmezlerle çalışan, Kütüphane Core kurulumlarının federasyon merkezi:** katalog yayını
(kitap sürümleri), politika şablonu yayını, kurulum kayıt defteri, opt-in toplama (kurulumlardan gelen imzalı
paketler), recall. InfraMedic master'ın ihtiyaçları (sürüme uygun bilgi üretimi, imzalı release bundle'ları,
kurulum kayıt defteri) bunun bir **uygulama profili** olur.

**Seçenekler.**
a) ★ Master = **aynı kod tabanında, "master" rolüyle çalışan bir Kütüphane Core**; federasyon ve kayıt defteri
   modülleri ek. v1'de rol tanımı ve paket sözleşmesi; çok-kurulumlu çalışma M2–M3.
b) Ayrı repo / ayrı ürün, ilk günden.
c) v1'de master yok; yalnız import/export.

**Sonuçları (a).** Core ↔ Master sözleşmesi = paket formatı (B6); InfraMedic master reposu ileride bu framework'ün
bir profili olarak yeniden değerlendirilir (InfraMedic'e şimdi dokunulmaz).

### B5 — Delegasyon ve erişim modeli

**Nedir.** Kim (entity: kullanıcı, ajan, rol/grup) hangi kitaba/öğeye hangi kipte (E9) erişir; ve bir kullanıcı
bu hakkı bir ajana nasıl devreder.

**Neden önemli.** Pazar araştırmasındaki kamanın 1. ve 2. maddesi; hiçbir ürün "kullanıcı→ajan delegasyonunu
modellenmiş nesne" olarak sunmuyor. MCP 2026-07-28 auth da delegasyonu kapsam dışı bırakıyor.

**Model (öneri).**
- **ReBAC** (ilişki tabanlı; Google Zanzibar ailesi): `user:ayse member group:hukuk`, `group:hukuk reader
  kitap:kvkk`, `agent:kobra-7 delegate_of user:ayse`…
- **Delegasyon nesnesi**: `grant(from=user, to=agent, scope=kitaplar/öğeler, mode≤kendi kipi, ttl, depth,
  purpose)`. Kural: **ajan hiçbir zaman devredenin sahip olmadığı bir hakkı alamaz**; zincir saklanır ve her
  okuma audit'inde görünür.
- **Retrieval'da pre-filter**: arama, yetkili öğe kümesiyle sınırlanmış sorguda çalışır (post-filter sızdırıyor).

**Seçenekler.**
a) ★ **OpenFGA** (Apache-2.0, CNCF) ayrı servis olarak; Kütüphane kendi delegasyon nesnesini onun üstünde modeller.
   Artı: olgun, ReBAC + koşullar, ListObjects ile pre-filter deseni belgeli. Eksi: bir servis daha.
b) **SpiceDB** (Apache-2.0) — benzer; Postgres backend'i var.
c) **Postgres içinde kendi ReBAC tablolarımız** — tek depo, en az parça; ama Zanzibar semantiğini yeniden yazmak.
d) v1'de yalnız rol tabanlı ACL; delegasyon M2.

**Sonuçları.** Kimlik doğrulama LLMDAP/IdP'de kalır (D14); yetkilendirme Kütüphane'de. Ajan kimliği standartları
(WIMSE, SPIFFE WIT-SVID, IETF agent-auth) izlenir; v1'de ajan = OIDC client + delegasyon nesnesi.

### B6 — Paket formatı ve offline taşıma

**Nedir.** Kurulumlar arası, master↔kurulum ve air-gap içine/dışına her bilgi akışının biçimi.

**Öneri.**
- **İçerik**: OKF v0.2 bundle (MIT). Non-markdown varlıklar `assets/` altında, concept'ler `resource` ile işaret eder.
- **Zarf** (OKF'nin üstünde, OKF'yi bozmadan): `MANIFEST` — üretici kurulum/sürüm, en düşük uyumlu tüketici
  sürümü, her dosyanın içerik özeti, kitap sürümleri, yönetişim önerileri (erişim *önerisi*; alan kurulum kendi
  politikasını uygular), recall listesi.
- **İmza**: Sigstore **cosign** offline anahtar modu ya da **minisign** (her ikisi açık kaynak); air-gap'te
  şeffaflık kaydı (Rekor) yok → anahtar tabanlı imza + pinlenmiş master anahtarı. OKF ekosisteminde imza
  katmanı henüz olgun değil ("trust card" fikri var) → kendi zarfımız, OKF'ye dokunmadan.
- **Taşıma**: aynı paket ağ ile ya da **fiziksel medya** (USB, tek yönlü veri diyotu) ile. Import akışı:
  *karantina → imza/özet doğrulama → sürüm uyumu → içerik taraması (talimat-benzeri span, zararlı içerik) →
  fark görünümü → insan onayı → yeni sürüm olarak yayın.* Import hiçbir zaman var olan sürümü üzerine yazmaz.
- **Şifreli içerik**: `envelope`/`sealed` öğeler paket içinde alıcı kurulumun açık anahtarına sarılı gider;
  paket ele geçse de okunmaz.

**Seçenekler.** a) ★ yukarıdaki (OKF + imzalı zarf, v1'de import + export). b) v1'de yalnız import, export M2.
c) kendi formatımız.

### B7 — Karar modelleri (Jev sınıfı)

**Nedir.** Muhakeme adımları *arasına* konan küçük, hızlı, şema-kısıtlı, kalibre olasılıklı karar modelleri.
Operatör: Jev bir model sınıfı; Laya öncelikli; Jev API anahtarı var; Jev ile shadow, sonra Laya, ya da paralel.

**Öneri.**
- **Karar noktası sözleşmesi** (sağlayıcıdan bağımsız): `soru_id, state (küçük dilim), tip (choice/score/noul),
  seçenekler` → `cevap, olasılık`. Jev ve Laya aynı sözleşmenin iki *sağlayıcısı*.
- **Karar defteri** (K7): her karar kaydı (soru, state özeti, sağlayıcı+sürüm, cevap, olasılık, gecikme,
  sonradan gelen gerçek sonuç). Golden set ve kalibrasyon raporu bu defterden üretilir.
- **Shadow mode**: karar modelleri v1'de **yetki vermez**; mevcut kural/LLM yolu kararı verir, modeller paralel
  koşar, anlaşmazlık loglanır. Terfi insan kararıyla.
- **Jev ile paralel Laya**: ★ ikisi aynı noktada paralel shadow (aynı soru, iki sağlayıcı) → doğrudan kıyas;
  Laya'nın ince ayarı Jev'in ve insanın etiketlediği defterle.
- **İlk karar noktaları (öneri)**: ingest sınıflandırma (kategori/E1, hassasiyet önerisi), sorgu yönlendirme
  (kitap/profil seçimi), atıf doğrulama ("P, C'yi destekliyor mu?").

**Kritik kısıtlar.**
- **Jev hosted API'dir → air-gapped kurulumda kullanılamaz.** Yalnız bağlantılı geliştirme/test ortamında ve
  yalnız `normal` hassasiyetli, egress'e izinli veriyle (E5). Air-gapped kurulumlar Laya ile çalışır.
- **D3 ile gerilim**: tüm model çağrıları LLMDAP'tan geçer; LLMDAP bridge bugün yalnız chat şemalarını
  (ollama/openai/anthropic) taşıyor, Jev'in `/v1/systemone` uç noktasını değil → LLMDAP'a **genel yönetişimli
  HTTP route** (ya da `systemone` şeması) upstream işi gerekir. O gelene kadar Jev testleri "LLMDAP dışı,
  etiketli deney" olarak mı koşsun, beklesin mi? → operatör kararı.
- **2026-10-12 operatör:** Jev ve benzerleri için LLMDAP issue'su açılsın; Laya da LLMDAP üzerinden kullanılsın;
  bu katmana security review yapılsın → **`ekaynac/LLMDAP#225`** (governed `systemone` şeması; Laya'nın
  `laya-serve`'ü Jev ile aynı `POST /v1/systemone` sözleşmesini sunduğu için tek şema ikisini kapsar; hosted/local
  egress sınıfı, şema dışı cevabı reddetme, yerel ağırlık digest'i, shadow çift korelasyonu, zorunlu güvenlik
  incelemesi).
- **Jev API anahtarı sohbete yazılmamalı.** LLMDAP'ın route anahtarı olarak (`apiKeyEnv`) ya da ortam
  değişkeninde tutulur. (Bu, K8 "sealed + use" fikrinin ilk gerçek örneği.)

**Seçenekler.** a) ★ yukarıdaki; Jev+Laya paralel shadow, LLMDAP upstream işi açılır, beklerken Jev yalnız
etiketli deney. b) Önce yalnız Jev, Laya sonra. c) Karar modelleri M2.

### B8 — Retrieval yığını (lisans süzgeciyle)

| Bileşen | Aday | Lisans | Not |
|---|---|---|---|
| Depo | PostgreSQL | PostgreSQL | D11 |
| Vektör | pgvector 0.8 | PostgreSQL | ACL filtreli iteratif tarama |
| BM25 | ★ **pg_textsearch 1.0** (TigerData) | **PostgreSQL** | ParadeDB `pg_search` AGPL; VectorChord/`vchord_bm25` AGPL (+ELv2) → tescilli dağıtımda **risk** |
| Ayrıştırma | Docling | MIT | MinerU (AGPL!) formül için — lisans kontrolü gerek; PyMuPDF AGPL → **dikkat** |
| Gömücü | bge-m3 | MIT | Qwen3-Embedding-4B (Apache-2.0) paralel A/B |
| Reranker | bge-reranker-v2-m3 / Qwen3-Reranker | Apache-2.0 | |
| Değerlendirme | Ragas, DeepEval | Apache-2.0 | |

**Lisans ilkesi (öneri):** Kütüphane tescilli dağıtılacağı için **AGPL bileşenler çekirdekte kullanılmaz**;
gerekiyorsa ayrı süreç/opsiyonel eklenti olarak ve hukuki kontrolden sonra.

**Seçenekler.** a) ★ tablo + AGPL-dışı ilkesi. b) değişiklik.

### B9 — M1 kapsamı

**Öneri M1 ("Kütüphane tek kutuda, OKF-yerli, açıklanabilir"):**
1. Bir OKF bundle'ı ve karışık dokümanlar (PDF/DOCX/MD) içe aktarılır → kitap + sürüm.
2. Sunum profilleri: *bütün* (K3 skill) ve *parçalı+gömülü* (K1) — hibrit arama + rerank.
3. İnsan arayüzü: kitap seç, soru sor, **tıklanabilir span atıflı** cevap (`kitap@sürüm`), "kütüphanede yok" dürüstlüğü.
4. **Kütüphane MCP** (ayrı paket): `search`, `read_section`, `tree`, `grep`, `list_books` + delegasyonlu erişim.
5. ReBAC + **kullanıcı→ajan delegasyonu** (B5) ve **açıklanabilir erişim defteri** (her okuma: kim, kimin adına,
   hangi sürüm/parça, hangi karar).
6. Runbook (K2) sonuç geri bildirimi.
7. Doküman yeni sürümle değişir; eski cevap yeniden üretilebilir kalır.
8. **İmzalı paket export/import** (USB senaryosu dahil, karantina + insan onayı).
9. Karar defteri + bir karar noktasında Jev/Laya shadow.
10. Tüm model/embedding çağrıları LLMDAP'tan (D17, D18: #222/#223 beklenir).

**Seçenekler.** a) ★ 1–10. b) 1–7 (M1), 8–10 M2. c) değişiklik.

### B10 — (yeni) Benimse mi, inşa et mi: Onyx örneği

**Bağlam.** Onyx (ex-Danswer) self-host, air-gap, MCP; CE MIT. Ancak RBAC, SSO, grup senkronu, sorgu geçmişi
(audit) gibi özellikler **Enterprise** başlığında; çekirdek modeli sohbet + konnektör + indeks; sürümleme yok.

**Seçenekler.**
a) ★ **Onyx'i temel almayız**: kamamız (sürüm atfı, delegasyon, açıklanabilir erişim, sealed/envelope) tam olarak
   Onyx'in EE'de tuttuğu ya da hiç sahip olmadığı yerde; fork'u yönetişime bükmek, temiz bir çekirdekten pahalı.
   Konnektör ve UI desenlerinden **ilham** alınır; OKF ekosistemi araçları (okflint, OKF-Schema, okf-postgres)
   ve tablo §4'teki bileşenler **doğrudan kullanılır**.
b) Onyx CE'yi fork'layıp üstüne yönetişim katmanı.
c) Onyx'i yan ürün olarak (arama arayüzü) Kütüphane'ye bağlamak.

### B11 — (yeni) K8 gizli malzeme ve `use` aracısı nerede yaşar?

**Bağlam.** `sealed + use` için bir kullanım aracısı gerekir (§2.1). D4 "v1'de eylem yok" diyor; `use` bir eylem
türüdür.

**Seçenekler.**
a) ★ **Depo Kütüphane'de (OpenBao, MPL-2.0, KV + transit), kullanım LLMDAP'ta**: LLMDAP zaten route başına
   anahtar enjekte ediyor → upstream iş: *"sealed credential, destination-bound, governed HTTP route"*. Kütüphane
   grant'ı ve audit'i tutar; ajan hiçbir yerde sırrı görmez. v1'de K8 = `envelope + read` (encrypted
   information) **ve** model/Jev anahtarları için `sealed + use` (zaten LLMDAP'ın işi); genel amaçlı sealed
   anahtarlar M2.
b) Kütüphane kendi enjeksiyon proxy'sini yazar (LLMDAP'tan bağımsız).
c) K8 tamamen M2.

## 4. Benimse/inşa et tablosu (İ2)

| İhtiyaç | Benimse (aday) | Lisans | İnşa (kama) |
|---|---|---|---|
| Taşınabilir bilgi formatı | OKF v0.2 + okflint / OKF-Schema | MIT | `kutuphane:` frontmatter bloğu, imzalı zarf |
| Depo, vektör, BM25 | Postgres + pgvector + pg_textsearch | PostgreSQL | sürüm/representation/projection kataloğu (InfraMedic'ten ameliyatla) |
| Ayrıştırma | Docling | MIT | profil yönlendirici |
| Gömme/rerank | bge-m3, Qwen3-Embedding, bge-reranker | MIT/Apache | — |
| Kimlik (IdP) | Keycloak (öneri) / kurum LDAP-AD | Apache-2.0 | — |
| Egress, model kimliği, egress audit | LLMDAP | bize ait | upstream işler |
| Yetki/delegasyon | OpenFGA | Apache-2.0 | delegasyon nesnesi, açıklanabilir erişim defteri |
| Sır deposu | OpenBao | MPL-2.0 | grant + audit |
| İmza | cosign (offline) / minisign | Apache-2.0 / ISC | zarf formatı, recall |
| MCP | MCP Python SDK | MIT | Kütüphane MCP araç seti |
| Eval | Ragas, DeepEval | Apache-2.0 | golden set yönetimi, karar defteri |
| Karar modeli | Laya (Apache-2.0), Jev (API) | — | karar noktası sözleşmesi |
| Arayüz | React + TS | MIT | NotebookLM-vari okuyucu, atıf görünümü |

## 5. Önceki kararlara etkisi

- **D2, D16** güçlendi (kitap = OKF bundle + katalog; kendi hibrit indeks).
- **D3** (LLMDAP zorunlu egress) Jev için upstream iş doğurur (B7).
- **D4** (v1'de eylem yok): K8 `use` kipi bir eylem; öneri (B11-a) eylemi LLMDAP'ın mevcut route enjeksiyonuyla
  sınırlar, D4'ün ruhunu korur.
- **D8/D19** (InfraMedic tüketir): Master framework (B4) InfraMedic master'ın yerine geçebilir → sözleşme ailesi
  genişler; InfraMedic'e şimdi dokunulmaz.
- **D14** (kimlik LLMDAP OIDC/LDAP): air-gapped kurulumda IdP olarak Keycloak önerisi eklenir.

## 6. Kaynaklar (2026-10-12)

- OKF: https://okf.md/ · https://okf.md/spec/ · https://okf.md/ecosystem-map/ (v0.2) ·
  normatif metin: GoogleCloudPlatform/open-knowledge-format `SPEC.md`
- OKF "minimally opinionated" yorumları: https://themenonlab.blog/blog/google-okf-open-knowledge-format-karpathy-llm-wiki-standard ·
  https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing
- OKF güven katmanı (imza OKF'nin dışında): https://pub.towardsai.net/from-self-updating-okf-wiki-to-production-trust-system-b014dbd12149 ·
  https://www.skills.sh/saschb2b/skills/trust-card
- Onyx: https://github.com/onyx-dot-app/onyx
- pg_textsearch (PostgreSQL lisansı, v1.0): https://www.postgresql.org/about/news/pg_textsearch-v10-3264 ·
  https://thenewstack.io/better-relevance-for-ai-apps-with-bm25-algorithm-in-postgresql/
- VectorChord / vchord_bm25 lisansı (AGPL, ELv2): https://ext.pigsty.io/e/vchord_bm25/ ·
  https://raw.githubusercontent.com/supervc-stack/VectorChord/main/README.md
- OpenBao 2.7 (transit, control groups): https://openbao.org/community/release-notes/2-7-0/ ·
  https://openssf.org/blog/2026/08/06/announcing-openbao-v2-6/
- InfraMedic master sözleşmesi: `ekaynac/inframedic-master`, dal `docs/inframedic-facing-contract`, README §3, §5, §6, §10
- Önceki araştırmalar: `docs/research/2026-10-08-*.md`
