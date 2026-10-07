# Kobra — yön kararları (karar kaydı)

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

## 4. Açık sorular

1. InfraMedic'in Kobra'yı tüketmesi: ne zaman ve hangi yüzeyden (Python kütüphanesi mi, HTTP/MCP servisi mi)?
2. #222/#223 gelene kadar geçiş: embedder doğrudan mı (audit'te "unverified egress" etiketiyle), yoksa milestone bunlara mı bekler?
