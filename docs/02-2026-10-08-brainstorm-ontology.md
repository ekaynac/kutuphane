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

## 4. Araştırma yüzeyleri (2026-10-08, sürüyor)

- RAG'da güncel durum (hibrit, rerank, late chunking, GraphRAG ailesi, agentic RAG, değerlendirme).
- Bilgi yönetimi ürün manzarası ve "hiçbir ürünün birleştirmediği" özellik kümesi.
- "jev" benzeri karar tabanlı modeller: ne kastedildiği, platformda nasıl değerlendirilebileceği.

Bulgular bu dosyanın §5'ine eklenecek.
