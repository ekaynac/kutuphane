# Kütüphane — ikinci beyin fırtınası: yeniden çerçeve, bilgi ontolojisi, iş bölümü

Tarih: 2026-10-08. Durum: **taslak, tartışma için**. Karar değil; kararlar `01-direction-decisions.md`'ye işlenir.
Operatörün 2026-10-08 notu üzerine yazıldı. Gerekirse D1–D20 yeniden değerlendirilir.

## 0. Beyin fırtınası kuralları (operatör, 2026-10-08)

1. **Örnekler niyeti aktarır.** Operatörün verdiği örneklere (ör. "kitaplar Redis'te gömülü dursun", "skill'ler
   gömülmeden sunulsun") overfit ve overcommit edilmez. Örnekten ihtiyaç çıkarılır, seçenekler sunulur, yalnız
   verilen karar kaydedilir.
2. Kıyas düzlemi **bilgi yönetimi teknolojileridir** (Context7, NotebookLM, kurumsal bilgi/arama, ajan bellek
   katmanları); sohbet kabukları (OpenWebUI, LibreChat) artık kıyas konusu değildir.
3. Reddedilen seçenekler gerekçesiyle kalır.

## 1. Yeniden çerçeve (operatörün tanımı)

Kütüphane; **bilgi yönetimi, bilgiye erişim, versiyonlama ve açıklanabilir erişim** platformudur. NotebookLM'in
on-prem / air-gapped, **LLM ajanlar ve insan aktörlerin ortak kullanımına** özelleştirilmiş hâli gibidir.
Context7 türü ürünlerden farkı **bilgi kategorilerine yaklaşımı**dır; kategoriler v1 için bu beyin fırtınasında
belirlenir. Ürün kataloğu ontoloji netleşince kurulur.

Kütüphane:
- ajanların rahatça etkileştiği **merkezi bir bilgi kümesi** gibi çalışır;
- bilginin **paylaşımını, delegasyonunu (entity: ajan / kullanıcı / rol), merkezi yönetimini** ve **yeni bilgi
  kümelerinin kaydını** yönetir;
- bir **master platform** üzerinden yönetilip yapılandırılır;
- **Kütüphane MCP**, master platformdan ayrık, modüler bir ürün olarak geliştirilir;
- bilgi **güvenli ve şifreli** saklanır;
- LLMDAP yüzeyleriyle iş bölümü, ayrık ürünler olarak kurgulanır.

## 2. Ontoloji — önce eksenler, sonra kategoriler

InfraMedic bilgi merkezi kanonunun en sağlam dersi: *birbirine dik kavramları asla tek bir "tür" alanında
çökertme.* Bu yüzden önce **eksenler**, sonra bu eksenlerin kesişiminden doğan **kategoriler (ürün türleri)**.

### 2.1 Eksenler (öneri)

| Eksen | Soru | Değer adayları |
|---|---|---|
| **E1 Epistemik tür** | Bu ne tür bir iddia? | *referans* (vendor doküman, standart, kitap) · *prosedür* (runbook, SOP) · *yargı* (öğrenilmiş örüntü, ders) · *gerekçe/politika* (neden, kural) · *ajan talimatı* (skill, prompt, agent card) · *kayıt/kanıt* (rapor, transkript, karar) · *model/karar artefaktı* (model, eval raporu) |
| **E2 Sunum biçimi** | Tüketiciye en iyi nasıl ulaşır? | *bütün* (bağlama sığar; skill gibi) · *parçalı+gömülü* (uzun metin; alıntılı retrieval) · *yapısal/sorgulanabilir* (şema, sözlük, tablo; exact lookup) · *çağrılabilir* (araç/MCP uç noktası) |
| **E3 Köken / güven** | Kim üretti, ne kadar güvenilir? | *dış-otoriter* (vendor, standart) · *iç-insan* · *ajan-önerisi* (kürasyon bekler) · *türetilmiş/öğrenilmiş* |
| **E4 Yaşam döngüsü** | Nasıl değişir? | *değişmez kayıt* · *sürümlü canlı doküman* · *taslak → kanon → süpersede → emekli* |
| **E5 Erişim sınıfı** | Kim görür, nereye çıkabilir? | hassasiyet (`restricted` / `normal`) · hedef kitle (entity: kullanıcı / ajan / rol) · egress (yalnız yerel / bulut-ok) |
| **E6 Uygulanabilirlik** | Nerede geçerli? | platform / sürüm / alan / `tested_on` |
| **E7 Tüketici** | Kim okuyacak? | insan · ajan · ikisi (sunum biçimi tüketiciye göre farklılaşabilir) |

E2 asıl ayırt edici eksen: **aynı içerik farklı tüketiciye farklı biçimde sunulabilir** (bir manuel insana
NotebookLM-vari sayfa, ajana bölüm alıntısı; bir skill insana okunur metin, ajana bütün dosya).

### 2.2 "Kitap" = katalog ürünü (öneri)

**Kitap**: kataloğun birimi; bir *artefakt kümesi* + bir *sunum profili* + bir *erişim politikası* + *sürüm*.
Sunum profili = ayrıştırıcı + parçalayıcı + gömücü + indeks türü + teslim biçimi; her biri **sürümlü, takılabilir
bileşen** (plugin ilkesi, D-kaydı §2). Profil kimliği provenance'a ve indeks parmak izine girer; aynı kitap iki
profille iki kez servis edilebilir.

Bu, operatörün "kitaplar gömülü hazır dursun, skill'ler gömülmeden gelsin" örneğinin genelleştirilmiş hâli:
**gömme bir kategori özelliği değil, profil seçimidir.** "Hazır tutma" (sıcak önbellek, Redis vb.) bir
uygulama seçeneğidir; karar ontolojiden sonra.

### 2.3 v1 kategori adayları (ürün türleri)

Aşağıdakiler eksenlerin "doğal" kesişimleri; v1'e hangilerinin gireceği operatör kararı.

| # | Kategori | E1 | Tipik E2 | Neden ayrı |
|---|---|---|---|---|
| K1 | **Referans eserler** (manuel, standart, vendor doküman, uzun PDF) | referans | parçalı+gömülü, alıntılı | NotebookLM çekirdeği; span atıf, hibrit arama |
| K2 | **Prosedürler / runbook'lar** | prosedür | yapısal (adımlar) + prosa | `tested_on`, sonuç defteri, imza ile arama; D13 |
| K3 | **Ajan talimatları** (skill, prompt, agent card, AGENTS.md) | ajan talimatı | bütün | gömme gereksiz; uyumluluk beyanı (harness, model); ajanların kendi "kullanım kılavuzu" |
| K4 | **Yapısal referanslar** (API şeması, değer sözlüğü, katalog, terimce) | referans | yapısal/sorgulanabilir | exact lookup; gömme yalnız keşif için |
| K5 | **Kayıtlar / kanıtlar** (rapor, transkript, karar kaydı) | kayıt | parçalı + zaman indeksi | değişmez, provenance, zaman; "ne zaman ne biliyorduk" |
| K6 | **Öğrenilmiş bilgi** (örüntü, SSS, ders, türetilmiş özet) | yargı | bütün/parçalı | yayından önce insan kürasyon kapısı; ajan önerir, insan yayınlar |
| K7 | **Model / karar artefaktları** (model, eval raporu, karar modeli) | model | yapısal + çağrılabilir | *v1 sonrası aday*; "jev" araştırması bekleniyor |

Öneri: **v1 = K1 + K2 + K3 (+ K4 hafif)**. K5 ve K6 ontolojide yer alır, v1'de yalnız şema düzeyinde.

### 2.4 Ajanlara sunum (Context7'den farkın somutu)

Context7 "kütüphane dokümanını sürümlü ve kısa biçimde ver" yapar; tek kategori, tek sunum. Kütüphane'nin iddiası:
- **kategoriye uygun sunum**: K3 bütün, K1 alıntılı, K4 sorgu, K2 adım;
- **entity-bazlı erişim ve delegasyon**: hangi ajan, kimin adına, hangi kitapları;
- **açıklanabilir erişim**: her okuma kayıtlı (kim, hangi sürüm, hangi profil, hangi parça), cevap yeniden üretilebilir;
- **sürüm sabitleme**: bir ajan oturumu kitapların belirli sürümlerine sabitlenir;
- **yeni bilgi kaydı**: ajanlar yeni küme önerir, kürasyon kapısından geçer.

## 3. İş bölümü — ayrık ürünler (öneri)

```
┌──────────────────────┐  yönetir/yapılandırır  ┌──────────────────────┐
│  Master platform     │ ─────────────────────▶ │  Kütüphane Core      │◀── insan UI (React)
│  (çoklu kurulum,     │                        │  katalog · sürüm ·   │
│   politika, katalog  │                        │  profil hattı ·      │◀── HTTP API (sürümlü)
│   yayını, tenant)    │                        │  retrieval ·         │
└──────────────────────┘                        │  erişim/delegasyon · │◀── Kütüphane MCP (ayrı ürün,
                                                │  erişim audit'i      │     ince istemci; harness'lar)
                                                └──────────┬───────────┘
                                                           │ model/embedding egress, kimlik
                                                ┌──────────▼───────────┐
                                                │  LLMDAP              │  OIDC/LDAP kimlik · bridge ·
                                                │                      │  imzalı egress audit · evidence
                                                └──────────────────────┘
```

| Ürün | Sahip olduğu | Sahip olmadığı |
|---|---|---|
| **Kütüphane Core** | katalog, sürümler, şifreli saklama (Postgres), sunum profilleri, retrieval indeksi, entity-bazlı erişim ve delegasyon, **erişim audit'i**, HTTP API, insan arayüzü | model çağrısı, kimlik doğrulama (LLMDAP'tan alır) |
| **Kütüphane MCP** | harness'lara yüzey; Core API'nin ince, sürümlü istemcisi; (seçenek) imzalı export paketini çevrimdışı okuma modu | kendi deposu, kendi politikası |
| **Master platform** | çoklu Core kurulumu yönetimi, politika ve katalog yayını, tenant/konfig | bilgi payload'ı |
| **LLMDAP** | kimlik otoritesi (OIDC/LDAP), tüm model+embedding egress'i, imzalı egress audit'i, evidence | bilgi deposu, retrieval (D16) |
| **Kobra** | Core içindeki referans ajan/sohbet yüzü | — |

İki audit akışı (Core'un *erişim* audit'i, LLMDAP'ın *egress* audit'i) **korelasyon kimliğiyle** birleşir;
"açıklanabilir erişim" ikisinin birleşik okumasıdır.

**Açık:** Master platform ayrı bir ürün mü, Core'un admin yüzü mü? `inframedic-master` ile ilişkisi?

## 4. Araştırma yüzeyleri (2026-10-08)

Üç yüzey, üç paralel web araştırması: ürün manzarası, RAG güncel durum, Jev/karar modelleri. Özetler §5'te;
tam raporlar ve kaynak listeleri `docs/research/2026-10-08-*.md`.

## 5. Araştırma bulguları

### 5.1 Bilgi yönetimi ürün manzarası

**Segmentler.** (i) Ajanlar için geliştirici dokümanı: Context7 (9k+ kütüphane, iki MCP aracı, git tag/branch
sürümleme, özel kaynak yalnız Pro/Enterprise, self-host yok), llms.txt (Mintlify/GitBook varsayılan), DeepWiki,
Ref.tools — hiçbirinde entity bazlı ACL, delegasyon, audit yok; hepsi SaaS. (ii) Kurumsal bilgi/arama: Glean
(müşteri-hosted), **Onyx** (MIT, self-host/air-gap, izin senkronu, sorgu audit'i, MCP — en yakın OSS rakip), M365
Copilot (bulut), **NotebookLM Enterprise → "Gemini Notebook Enterprise"** (bulut, residency, IAM, audit log,
Discovery Engine API; resmi MCP yok), Elastic Agent Builder, Vectara (on-prem/air-gap), RAGFlow/Dify/AnythingLLM
(self-host, zayıf ACL/audit), deepset/Cohere North (sovereign on-prem). (iii) Ajan bellek katmanları: Mem0,
Zep/Graphiti (bi-temporal graf), Letta (paylaşılan bellek blokları), Cognee (tam yerel), Honcho (insan ve ajan aynı
"peer" türü) — hiçbirinde delegasyon, imzalı provenance, açıklanabilir erişim yok. (iv) Paketleme: Agent Skills
(SKILL.md, açık standart 2025-12; imza/ACL yok), AGENTS.md (Linux Foundation AAIF), MCP resources/prompts (sürüm
semantiği yok), **Google OKF v0.1 (2026-06)**: Markdown + YAML frontmatter dizini; ACL/sürüm/provenance alanı yok →
**Kütüphane OKF import/export etmeli.** (v) Sürümleme/provenance: lakeFS "git for agent knowledge" (Enterprise'da
ABAC + audit), Dolt, W3C PROV, C2PA 2.4, Sigstore model signing. "Açıklanabilir erişim" yalnız niş ürünlerde
(TrustGraph, Sourcegraph, Provena). (vi) Erişim/kimlik: OpenFGA/SpiceDB RAG desenleri (pre-filter), MCP 2026-07-28
OAuth 2.1 sertleştirme (ajan kimliği/delegasyon/audit kapsam dışı), IETF ajan kimliği taslakları (WIMSE, SPIFFE
WIT-SVID, draft-klrc-aiagent-auth), AIP (Biscuit tabanlı yetki zinciri). Hiçbir ürün hepsini birden sunmuyor.

**Hiçbir ürünün birleştirmediği küme (kama):**
1. İnsan ve ajan **eşit birinci sınıf principal** + NotebookLM kalitesinde insan arayüzü.
2. **Delegasyon modellenmiş nesne**: kullanıcı→ajan grant'ı; kapsam, TTL, derinlik; zincir saklanır.
3. **İçerik adresli sürümleme + retrieval**: her cevap `doc@commit` atfı; ajan oturumu sürüme sabitlenir.
4. **Açıklanabilir erişim defteri**: kim/hangi ajan, kimin delegasyonuyla, hangi parça/sürüm, hangi sorguda, hangi
   politika kararıyla; W3C PROV olarak dışa aktarılabilir.
5. **İmzalı, taşınabilir bilgi paketleri** (OKF + Skills düzeni, Sigstore/C2PA tarzı manifest) — air-gap import/export.
6. **Air-gapped, at-rest şifreli kurulum + ayrık MCP ürünü.**
7. **Bi-temporal semantik** ("ajan X, D tarihinde ne biliyordu?").

**Riskler:** Google (OKF + Gemini Notebook Enterprise + Distributed Cloud → on-prem NotebookLM; en yüksek), Onyx
(sürüm+delegasyon eklemesi artımlı), lakeFS (retrieval/UI ekleyebilir), Microsoft (Entra Agent ID + Purview),
standart kayması (MCP auth, WIMSE/SPIFFE, A2A — delegasyon modeli bunları izlemeli), "docs over MCP" metalaşması →
**kama retrieval değil, yönetişim.**

### 5.2 RAG ve ajan bilgi erişiminde güncel durum

**Kanıtlanmış taban:** hibrit (BM25 + dense) + cross-encoder rerank. RRF tek başına bazı setlerde dense'i *düşürüyor*
→ füzyonu rerank ile yap, ölç. Postgres'te BM25 gerçek: ParadeDB `pg_search` (AGPL), VectorChord `vchord_bm25`,
TigerData `pg_textsearch` 1.0 (2026-03). pgvector 0.8 iteratif tarama ile ACL filtreli ANN recall çökmüyor.
VectorChord 1.1 MaxSim (ColBERT tarzı çok-vektör) mevcut. Ayrık vektör deposu eşiği: >50–100M vektör.
**Postgres + RLS yönetişimde kazanır.**

**Reranker:** bge-reranker-v2-m3 güvenli varsayılan; Qwen3-Reranker 0.6B/4B/8B (Apache-2.0, talimat-duyarlı) daha
güçlü. **Gömücü:** bge-m3 hâlâ en esnek (dense+sparse+multi-vector, Türkçe dahil); **Qwen3-Embedding 4B/8B**
(Apache-2.0) MMTEB +~10 puan, TR-TEB Türkçe 75–76 → paralel kolonla A/B. jina v4/v5 ticari lisanssız on-prem
**kullanılamaz**.

**Parçalama/ayrıştırma:** contextual retrieval (chunk'a 50–100 token LLM bağlam öneki) kalitede late chunking'i geçiyor
(72.4 vs 61.0 nDCG@10), maliyet vLLM prefix cache ile düşük; yapı-duyarlı parçalama ana akım. Ayrıştırıcı: **Docling**
varsayılan, MinerU formül/CJK, Marker hız, PyMuPDF4LLM yerel-metin PDF, unstructured Office/e-posta.
**Doküman türüne göre yönlendirme** → sunum profili fikrini doğrular; tabloları HTML sakla.

**Graf RAG:** GraphRAG 500 sayfa için $50–200 / 45 dk; GraphRAG-Bench'te basit QA'da vanilla RAG'ın altında. HippoRAG 2
en iyi ama araştırma kodu. Graphiti/Mem0 *ajan belleği* için. **v1: yalnız "Tip 1" graf** (varlık meta verisi filtre
olarak).

**Agentic RAG ve grep karşı-akımı:** Claude Code vektörsüz (grep/glob + ağaç); Context7 iki araç; PageIndex ağaç
gezinme. Karşı kanıt: "Context Rot" — 32k–128k arası çok-adımlı doğruluk düşer. **Sentez: ajanlar ikisini de ister**
— `search` (hibrit+rerank, ACL filtreli) **ve** `read_section` / `grep` / `tree` (ayrıştırılmış tam doküman) +
doküman başına llms.txt tarzı harita.

**Atıf:** karakter aralığı atfı üretimde (Anthropic Citations API; NotebookLM "kaynaklarda yok"). On-prem Qwen3 için:
numaralı chunk, cümle başına `[n]`, ardından NLI/reranker doğrulama geçişi (doğrulanmamış atıf yaygın).

**Güvenlik:** her chunk'ta sınıflandırma/ACL/provenance; **pre-filter** (RLS) — post-filter yakın-kopya sondasıyla
sızdırıyor; embedding inversion gerçek → vektörler gizli veri; indeks zehirlenmesine karşı insan onaylı ingest.

**Değerlendirme:** Ragas (offline) + DeepEval (CI) + TruLens (drift); indeks anlık görüntüsü, embedder/chunker sürümü,
prompt hash sürümlenir; yeniden gömme paralel tabloda A/B → cutover (InfraMedic gen-N ile aynı fikir).

**v1 önerileri (sıralı):** (1) Postgres-only: pgvector HNSW + BM25 eklentisi (spike) + reranker; (2) bge-m3 v1,
Qwen3-Embedding-4B paralel A/B; (3) Docling + yapı-duyarlı parçalama + bağlam öneki; (4) ajanlara çift yüzey;
(5) span atfı + doğrulama; (6) şemaya gömülü yönetişim; (7) ilk günden golden set + CI; (8) ertelenen: ColPali,
GraphRAG, Graphiti tarzı bellek.

### 5.3 Jev ve karar tabanlı modeller

**Jev nedir:** TypeSafe AI'ın "System One" modeli (duyuru 2026-10-08; erken erişim 2026-09-15). Otoregresif değil:
bir `state` (metin/JSON, 32k) + N tipli soru → paralel, tek geçişte, **şema dışına çıkamayan** tipli kararlar ve
**kalibre olasılıklar**. Üç ilkel: **Choice** (seçenek listesinden seç), **Score** (rubrik/sıralı), **Noul**
(evet/hayır olasılığı). Eğitim: RLCD (kalibre kararlar için RL; yayımlanmamış). İddialar: 70–500 ms, frontier LLM'lere
göre 40–200x hızlı; kendi eval'inde ~%67.8 vs GPT-5.6 %74.1 (referans etiketler frontier ortalaması, insan değil).
Zayıflıklar: *geçerli ama yanlış* değerde kendinden emin; aritmetik/tarih; olumsuzlama; çok-doküman uzlaştırma.
**Yalnız hosted API; açık ağırlık, self-host, VPC yok → air-gapped platformda Jev'in kendisi kullanılamaz.**

**Sınıf:** "muhakeme adımları *arasına* konan küçük, hızlı, şema-kısıtlı, kalibre sınıflandırıcı/skorlayıcı".
On-prem açık ağırlık karşılıkları: **Laya** (ModernBERT/mmBERT tabanlı, Apache-2.0, aynı choice/score/noul
ilkelleri, ~35 ms; ince ayar şart, mmBERT varyantı Türkçe kapsar), Kev (Qwen3.5 LoRA), ince ayarlı encoder'lar +
kalibrasyon (temperature scaling, MCGrad), guard modelleri (Qwen3Guard 0.6B/4B/8B — Türkçe dahil 119 dil, Llama Guard 4,
gpt-oss-safeguard), ödül/süreç modelleri (Skywork-Reward-V2, AgentPRM). Sıfır-atış kalitede Jev önde; etiketli karar
verisi biriktikçe fark kapanır.

**Kütüphane'de karar noktaları (her biri küçük bir state dilimi üstünde Choice/Score/Noul):**
1. sorgu yönlendirme — kategori / koleksiyon / sunum profili / "hibrit mi leksik mi";
2. ingest sınıflandırma — doküman türü, hassasiyet sınıfı, runbook/skill/referans, "bunun sürümü mü?";
3. ilgililik ve atıf doğrulama — "P pasajı C iddiasını destekliyor mu?";
4. erişim politikası risk skoru — "bu ajan bu görevde bu dokümanı okusun mu / dışa aktarsın mı?";
5. runbook sonuç tahmini — "sonraki adım başarılı olur mu / insan gerekir mi?";
6. ajan-okuma guardrail'i — getirilen içerikte prompt injection / politika taraması.

**Kütüphane ürünü olarak değerlendirme (fizibilite sırasıyla):** (1) soru tipi başına golden set + kalibrasyon raporu
(accuracy, macro-F1, Brier, ECE, reliability diyagramı; eşikler soru tipleri arasında taşınmaz) — rapor model kartının
yanında sürümlü doküman; (2) **shadow mode** — mevcut kural/LLM yoluyla paralel koşar, anlaşmazlıklar loglanır, insan
gözden geçirir, taban çizgiyi geçince terfi; (3) **karar defteri** — her karar (soru id, state hash, cevap, olasılık,
sonuç, maliyet, gecikme) bir kütüphane kaydı; ince ayar ve kalibrasyon drift'i için korpus; (4) **yörünge replay
harness'ı** — loglanmış ajan yörüngeleri karar modeli kapı noktalarına takılarak yeniden oynatılır; (5) **model
kayıt defteri** — karar modeli, eval raporu soy kütüğüyle, runbook gibi provenance'lı bir kütüphane öğesi (K7).

**Çıkarım:** K7 ("model / karar artefaktları") kategorisi ve **karar defteri** ontolojide yer almalı; v1'de karar
modelleri **shadow mode** ile girer (yetki vermez, yalnız ölçülür), kapı yetkisi insan kuralında kalır. Bu, operatörün
"LLM teknolojilerini test ettiğimiz platform" hedefinin somut ilk örneği olabilir.

## 6. Sentez — operatöre sorular (2026-10-08)

Araştırmanın yön kararlarına etkisi ve açık sorular sohbet kaydında; verilen kararlar `01-direction-decisions.md`'ye
D21+ olarak işlenecek. Başlıklar: ontoloji eksenleri ve v1 kategorileri; "kitap" tanımı ve sunum profili; ürün
ayrımı (Core / MCP / Master / LLMDAP / Kobra); OKF import/export; delegasyon modeli; karar defteri + shadow-mode;
retrieval yığını (D16 ayrıntısı); Jev sorularının cevapları.
