# M1 notları: dilimlerde verilen küçük teknik kararlar

Tarih: 2026-10-12. M1 dilimlerinde verilen küçük teknik kararlar (07 §5). Kod: `src/kutuphane/`.

# M1a: katalog ve sürüm kimlikleri

## Sürüm kimlikleri

- Kimlik = `önek_` + SHA-256(kanonik JSON `{"kind", "v": 1, "body"}`). Önekler: `ct_` içerik, `pf_` profil,
  `pl_` politika. Kanonik JSON: anahtarlar sıralı, boşluksuz, UTF-8.
- **İçerik gövdesi:** `(yol, dosya baytlarının SHA-256'sı)` çiftleri, yola göre sıralı. Yollar POSIX, NFC,
  göreli; `..`, mutlak yol ve sembolik bağlantı reddedilir. Gizli dosyalar (`.git` vb.) alınmaz. Zaman damgası ve
  dosya sırası kimliğe girmez.
- **Profil gövdesi:** profil adı + bileşen sürümleri (ör. `pypdf@6.20.0`, `kutuphane.source@1`). Bileşen sürümü
  değişince profil kimliği değişir, içerik kimliği değişmez.
- **Politika gövdesi:** E5 hassasiyet, E5 egress, E8 koruma (M1'de yalnız `standard`). Kısıtlı içerik
  `cloud_ok` olamaz (D46: InfraMedic'ten alınan fikir).

## Şema

D48'deki dört tabloya bir **`blob`** tablosu eklendi: dosya baytları içerik özetiyle tek kez saklanır; sürümler
manifest ile ona işaret eder. Değişmeyen dosya yeni sürümde tekrar saklanmaz ve eski sürümler okunabilir kalır
(AT-07'nin temeli). Sürüm satırları değişmez; `book` yalnız güncel içerik ve politikaya işaret eder.

## Paket manifesti ve sıra kapsamı (D47; uygulama M1f)

- Manifest: üretici kurulum ve anahtar parmak izi, kitap, içerik/profil/politika kimlikleri, dosya listesi
  (yol + özet), sıra numarası, recall listesi (M2).
- **Sıra numarası kapsamı: (imzalayan anahtar, kitap) başına monoton tam sayı.** Alan kurulum her çift için
  kabul ettiği en büyük sırayı tutar; eşit ya da küçük sıra reddedilir (AT-14). Kurulum başına tek sayaç
  reddedildi: bir kitabın bekleyen paketi başka kitabın paketini kilitlerdi.

# M1b: yetki çekirdeği

- **Üç tablo:** `grant_tuple` (OpenFGA biçiminde `object, relation, subject`; rol üyeliği de bir demet:
  `role:hukuk member user:ayse`; kitap hakkı `book:x read role:hukuk#member`), `delegation`, `access_event`.
  İptal yumuşak (`revoked_at`); erişim kaydı kararın dayandığı satırları (`grant_ids`, `delegation_id`) ve o
  anki politika kimliğini taşır.
- **Rol derinliği 1:** roller iç içe geçmez. Delegasyon yalnız kullanıcı → ajan; ajan devredemez.
- **Tek kapı:** `gate.deliver_file`; karar fetch öncesi ve teslimden hemen önce iki kez alınır. Arama (M1d) ve
  export (M1f) aynı kapıyı kullanacak.
- **K3 tanıma:** frontmatter `type` ∈ {skill, prompt, agent-card, agent-instructions} ya da dosya adı
  AGENTS.md / CLAUDE.md / SKILL.md. Ajan için `read` + `activate` gerekir; insan `read` ile referans okur.
- **Sınır:** kimlik doğrulama M1c'de; o zamana kadar CLI yönetim komutları ana makinedeki operatöre güvenir.

# Astra kod incelemesi #1 (PR #5–#7) sonrası

- **Tek anlık görüntü:** bir isteğin bütün kipleri, delegasyon, sahibin hakları ve yürürlükteki politika tek SQL
  ifadesiyle okunur (`authz.decide`). **Doğrusallaştırma noktası:** son karar ifadesi başlamadan commit edilmiş
  iptal uygulanır; sonrakiler uygulanmaz. Süre `clock_timestamp()` ile ölçülür (transaction içindeki donmuş
  `now()` değil). Erişim kaydı son kararın politikasını yazar.
- **Sınıflandırma normalleştirmesi:** frontmatter okunurken BOM ve CRLF/CR normalleştirilir; saklanan baytlar
  değişmez. Okuyucu sürümü 2'ye çıktı, dolayısıyla varsayılan profil kimliği değişti.
- **`publication` tablosu:** her yayın (içerik, profil, politika) üçlüsünü birlikte kaydeder; `book.current_profile`
  eklendi. Politika `catalog.publish` girişinde de doğrulanır (yalnız CLI'da değil).
- **`cat` komutu kaldırıldı:** her okuma tek kapıdan geçer; operatör istisnası yok.

# M1c: kimlik, egress, denetim kesiti

- **Kimlik (D50):** `identity.Verifier` JWKS dosyasıyla imza, `iss`, `aud`, `exp`, `iat`, `sub` doğrular;
  algoritma listesi RS256/ES256/EdDSA (`none` ve HMAC yok). Principal türü `kutuphane/principal_type` claim'inden
  (varsayılan `user`). **Delegasyon RFC 8693 `act` claim'i ile:** `sub` kullanıcı, `act.sub` ajan; iç içe `act`
  reddedilir. Token yetki vermez; ajan yine canlı delegasyon ister. Principal/nesne desenleri `\Z` ile biter
  (sondaki satır sonu kabul edilmez); e-posta biçimli adlar için `@` serbest.
- **Egress:** `llmdap.chat` → `POST /bridge/<route>/v1/chat/completions`; başlıklar (D52'den beri)
  `Authorization: Bearer <Core'un LLMDAP özne anahtarı>`, `x-llmdap-for-subject`, `x-llmdap-purpose`,
  `x-llmdap-correlation-id`. LLMDAP'ın döndürdüğü `x-llmdap-correlation-id-derived` `model_call` tablosuna yazılır;
  başarısız denemeler de kaydedilir. Yönlendirme izlenmez (sır başka adrese gitmesin); yalnız http(s).
- **Denetim:** LLMDAP'ta HTTP denetim sorgusu yok; `audit.explain` erişim kaydı + `model_call` + LLMDAP
  `llmdap-audit-export` JSONL'ını türetilmiş korelasyon kimliğiyle birleştirir. LLMDAP kaydı olmayan çağrı
  `llmdap_missing` olarak işaretlenir, rapor `complete: false` olur.
- **Henüz değil:** gerçek LLMDAP compose servisi ve ağ ayrımı (AT-10) Core bir servis olarak çalışmaya
  başlayınca (M1e) eklenir; AT-10/AT-11 #222/#223 gelmeden yeşile dönmez (D49). Embedding çağrıları #222 bekliyor.

# M1d (1. kısım): profiller, arama, atıf

- **Profiller:** `whole` (dosya başına tek parça, tam metin) ve `chunked` (başlıkta yeni parça; boş satırlarda
  bölünen bloklar ~1200 karaktere kadar birleşir; frontmatter parça metnine girmez). Parçalar yayınla aynı
  işlemde `chunk` tablosuna yazılır ve değişmez. Profil kimliği okuyucu, PDF, parçalayıcı sürümü ve FTS
  yapılandırmasını kapsar. CLI varsayılanı `chunked`.
- **Arama:** Postgres tam metin, `turkish` yapılandırması; sorgu kelimelerinin kökleri VEYA ile birleşir,
  `ts_rank_cd` sıralar. Önce yetkili kitaplarla süzülür (`authz.allowed_objects`); ajanlar için K3 parçaları
  yalnız `activate` varsa görünür. Sonuçtaki her kitap teslimden önce `gate.guard` ile yeniden karara bağlanır
  ve `search` olayı olarak kaydedilir.
- **Atıf:** `kitap@içerik/profil/yol#sıra`. `open_citation` o sürümün saklı parçasını güncel yetkiyle verir
  (`cite` olayı).
- **Kimlik düzeltmesi (güvenlik incelemesi):** `sub` artık normalleştirilmiyor; büyük harf ya da alfabe dışı
  karakter içeren özneler reddedilir, böylece iki farklı IdP öznesi tek bir principal üzerine düşmez. IdP
  eşleyicisi küçük harfli ad üretir.
- **Henüz değil:** vektör arama ve reranker (#222 + M0 ölçümü); cevap üretimi ve "kütüphanede yok" eşiği (M1d
  2. kısım; eşik M0'dan).

# Astra kod incelemesi #2 (PR #8–#10) sonrası

- **Arama tek doğrusallaştırma noktası:** ön-süzgeç ve son denetim, bütün kitaplar ve kipler için tek ifadeyle
  (`authz.allowed`). Sonuç kümesinden bir kitap arada yetkisini kaybettiyse arama güncel yetkiyle bir kez daha
  çalışır (iptal edilen kitap `k` kotasını tüketmez); ikinci değişiklikte istek `SearchChanged` ile reddedilir.
- **Denetim ayrıntısı:** `access_event.profile_id` ve `items` (teslim edilen atıf tutamaçları). Her model çağrısı
  kendi `call_id`'si ile gider (`<korelasyon>.<rastgele>`); tamamlanmış çağrı için LLMDAP'ta `llm.authz` +
  `llm.result`, reddedilen için `llm.authz` aranır. Durumlar: `complete`, `missing`, `not_sent`.
- **Egress politikası model çağrısında:** `llmdap.chat` artık `source_books` ister; rota sınıfı (`local`/`cloud`,
  operatör beyanı) `cloud` ise içeriği kullanılan her kitabın güncel politikası `cloud_ok` olmalı; bilinmeyen
  kitap da engellenir. Engellenen çağrı ağa çıkmadan `not_sent` olarak kaydedilir.
- **Sessiz kesme yok:** tek blok `MAX_CHUNK_CHARS` (4800) üstündeyse boşlukta bölünür; `whole` profili 500 bin
  karakteri aşan dosyayı açıkça reddeder.
- **Yalnız kanonik profiller:** `catalog.publish` `profiles.spec(name)` ile birebir eşleşmeyen profili reddeder;
  kimlik fiilî davranışı tanımlar.
- **LLMDAP hata kaydı:** durum ve türetilmiş korelasyon, bozuk ya da yarım gövdede de kaydedilir.
- **M1e notu:** ağ yüzeylerinde `Actor` yalnız doğrulanmış JWT'den kurulur; CLI'nın operatöre güvenen kurulumu
  taşınmaz.

# M1d (2. kısım): cevaplar

- **Akış:** ön-süzülmüş arama → numaralı pasajlar LLMDAP üzerinden modele (`source_books` ile, egress politikası
  denetlenir) → model `[n]` ile atıf yapar. Pasaj yoksa model hiç çağrılmaz. Model `KÜTÜPHANEDE_YOK` derse ya da
  geçerli hiçbir pasaja atıf yapmazsa cevap kabul edilmez: durum `not_in_library`, gövde saklanmaz.
- **Prompt enjeksiyonu:** sistem mesajı pasajlardaki talimatlara uyulmamasını söyler; bu bir azaltmadır, garanti
  değil. Asıl sınır yetki ve K3 kapısıdır (talimatlar ajana etkinleştirme izni olmadan gitmez).
- **`answer` tablosu:** soru, gövde, atıf yapılan ve modele verilen pasajlar (sürüm + profil + sıra), kaynak
  kitaplar, model. `reopen` modeli çağırmaz; gövde ve kanıt, bütün kaynak kitaplarda **güncel** okuma hakkı
  (ajan + K3 pasajında `activate`) tek ifadeyle doğrulanınca gösterilir; aksi hâlde hiçbiri gösterilmez. Cevabı
  yalnız soran principal ya da adına sorulan kullanıcı açabilir (paylaşım M1 dışında).
- **Eşik:** `MIN_SCORE = 0` geçicidir; AT-08 eşikleri M0 ölçümünden sonra yazılır.

# Astra kod incelemesi #3 (PR #11–#13) ve güvenlik incelemesi sonrası

- **Cevap teslimi de yeniden denetlenir:** model dönünce, modele verilen **bütün** kaynak kitaplar (ajan + K3
  pasajında `activate`) `gate.check_many` ile tek ifadede yeniden karara bağlanır; tutmazsa cevap ne döner ne
  saklanır. `reopen` aynı fonksiyonu kullanır.
- **Reopen bağlamı:** yalnız aynı principal + aynı "adına" bağlamı ya da cevabın yapıldığı kullanıcı açar; token'ın
  "X adına" iddiası tek başına yetmez.
- **Atıf:** tek bir geçersiz `[n]` bile cevabı reddeder (`not_in_library`). Anlamsal dayanak M0 değerlendirmesinde.
- **Parçalayıcı v2:** `_cap` davranış değişikliğiydi; profil kimliği artık farklı (eski parçalar korunur).
- **Migration 006:** eski satırlar `<korelasyon>.legacy-<id>` alır; aynı korelasyonda çok çağrı olan veride de
  yükseltme çalışır (testli).
- **Gönderim belirsizliği:** yalnız yerel egress reddi ve reddedilen bağlantı `not_sent` sayılır; gönderimden
  sonra kopan bağlantı `uncertain:*` hatasıyla kaydedilir ve denetimde `missing` (rapor `complete: false`).
- **Cevaptan denetim:** `audit.explain_answer(cevap_id)`; CLI `explain <id> --answer`.
- **M1e notu (arayüz):** cevap gövdesi model çıktısıdır; arayüz onu **düz metin** olarak gösterir, Markdown
  görseli/HTML yüklemez (pasaj metni dış URL'ye sızmasın).

# M1e (1. kısım): HTTP API, Kütüphane MCP, ağ düzeni

- **Tek ASGI uygulaması** (`server.py`, Starlette + MCP SDK): `/v1/search`, `/v1/citation`, `/v1/ask`,
  `/v1/answers/{id}`, `/v1/files/{book}/{content}/{path}`, `/mcp` (streamable HTTP, stateless). MCP araçları:
  `search_library`, `open_citation`, `ask_library`, `reopen_answer`, `read_document`. HTTP ve MCP aynı fonksiyonları
  çağırır.
- **Kimlik yalnız token'dan:** `Authorization: Bearer <jwt>`; MCP'de aynı doğrulayıcı (`TokenVerifier`
  uyarlaması). Başlıklar principal'ı ya da "adına" kullanıcıyı değiştiremez (testli). Her istek yeni korelasyon
  kimliği alır. MCP'nin DNS rebinding koruması açık; izinli host `KUTUPHANE_PUBLIC_URL`'den.
- **Hatalar:** 401 (`WWW-Authenticate: Bearer`), 403, 404, 400, 409 (arama sırasında yetki değişti), 502 (model);
  gövdede iç ayrıntı yok. Dosyalar `Content-Disposition: attachment` + `nosniff` ile döner.
- **Ağ (AT-10'un ağ yarısı):** Core yalnız `internal` `core` ağında (Postgres, ileride LLMDAP); kullanıcılar
  `edge` + `core` ağlarındaki nginx ters vekilden gelir. `deploy/egress_probe.py` Core konteyneri içinden
  doğrular: yalnız Postgres erişilebilir; internet, dış DNS ve makinedeki model servisleri erişilemez (2026-10-12'de
  geçti). LLMDAP bağlanınca izinli listeye eklenir; AT-10 #222 ile tamamlanır.
- **Henüz değil:** React arayüz (M1e 2. kısım), Core'un açılışta migration çalıştırması (şimdilik `kutuphane
  migrate`).

# M1e (2. kısım): arayüz

- **React + TS (D15), Vite**, `/ui` altında Core'dan servis edilir (Docker'da çok aşamalı derleme). Tek ekran:
  soru → atıflı cevap (`[n]` düğmeleri) → yan panelde sürümlü pasaj; "yalnız ara"; cevap kimliğiyle eski cevabı açma.
  Sistem fontları (air-gapped), açık/koyu tema.
- **Model çıktısı düz metin:** Markdown/HTML/görsel işlenmez; yalnız `[n]` düğmeye dönüşür. Bütün cevaplarda katı
  CSP (`default-src 'none'`, betik/stil/görsel/bağlantı yalnız aynı köken, `frame-ancestors 'none'`), `nosniff`,
  `no-referrer`, `X-Frame-Options: DENY`.
- **Giriş (M1):** IdP olmadığı için token yapıştırılır; sekmeye özel `sessionStorage`. Geliştirme token'ı
  `KUTUPHANE_DEV=1 kutuphane dev-keys deploy/dev` + `dev-token <sub> [--agent] [--act <ajan>]` (8 saat; yalnız
  `KUTUPHANE_DEV=1` iken çalışır). Kurum IdP'siyle OIDC PKCE girişi #223 + IdP bağlantısıyla gelir.
- **Şema koruması:** sunucu bekleyen migration varsa açılmaz (`kutuphane migrate` ister) — yerel denemede yakalanan
  gerçek bir 500 hatasının kalıcı çözümü.

# M1f (1. kısım): runbook geri bildirimi (AT-15)

- `runbook_feedback`: sonuç (`worked`/`failed`/`changed`), uygulayan principal (+ adına), `tested_on`, not,
  **tam içerik sürümü**. Yeni sürüm eskisinin geri bildirimini sahiplenmez; eski sürüm sorgusunda eskiler görünür.
- Kayıt ve okuma kitap üzerinde güncel `read` ister; kapıdan geçer (`feedback`, `read_feedback` olayları).
- Yüzeyler: `POST/GET /v1/feedback`, MCP `record_runbook_feedback`. Runbook çalıştırma yok (D4, D13).

# M1f (2. kısım): imzalı paketler (AT-13, AT-14; D51)

- **Biçim:** sıkıştırılmamış tar; `MANIFEST.json` (kanonik JSON: biçim, imzalayan, kitap, başlık, içerik kimliği,
  sıra, politika *önerisi*, dosyalar + özet + boyut), `MANIFEST.sig` (Ed25519, base64), `content/<yol>`. Açılırken
  diske hiçbir şey çıkarılmaz; bağlantı/aygıt/beklenmeyen üye reddedilir; boyutlar sınırlı.
- **Zincir:** `receive` = karantina + doğrulama (güvenilen ve iptal edilmemiş anahtar, imza, her dosya özeti,
  yeniden hesaplanan içerik kimliği, kabul edilenden yeni sıra) + tarama (K3 dosyaları, talimat benzeri metin —
  karar vermez, insana gösterir) + fark. Katalog değişmez. `approve` = insan onayı + **alıcının kendi politikası**
  (D23) + tek işlemde yayın; anahtar ve sıra satır kilidi altında yeniden denetlenir; sıra yalnız ileri gider.
  Hata olursa katalog değişmez, sebep kaydedilir. Reddedilen paketler (gerekçeyle) saklanır.
- **Anahtarlar:** `keygen` (Ed25519, 600), `trust <pub> --fingerprint <bant dışı doğrulanan>`, `untrust`.
  Yenileme: yeni anahtar güvenilir yapılır, eski iptal edilir; eski anahtarlı paket reddedilir.
- **Testler:** iki kurulum aynı test veritabanında iki şemayla (`install_b`); içerik kimliği iki kurulumda aynı;
  kurcalama (içerik, manifest, kanonik olmayan biçim), tekrar oynatma ve eski sıra, eşzamanlı onay yarışı, yarıda
  hata, insan reddi.

# Astra incelemesi #4 (PR #14–#21) ve düzeltmeler

Ham metin: `docs/research/2026-10-12-astra-review-m1-4-raw.md`. Altı bulgunun hepsi düzeltildi:

1. **Arayüzde önceki oturumun içeriği (yüksek):** çalışma alanı token'a anahtarlı ayrı bileşen; çıkış ya da başka
   kullanıcıyla giriş onu söker. Önceki cevap/pasaj/sonuç kalmaz, bekleyen isteklerin yanıtı düşecek yer bulamaz.
2. **Onay ile anahtar iptali yarışı (yüksek):** anahtar satırı `FOR SHARE` okunur. Sürmekte olan iptal önce
   biter ve onay reddedilir; ya da iptal onayın bitmesini bekler. İki bağlantılı test, kilit olmadan kırmızı.
3. **MCP hata gövdeleri (orta):** HTTP'nin hata eşlemesi (`_classify`) MCP araçlarına da sarıldı; beklenmeyen hata
   sunucuda kaydedilir, istemciye yalnız "internal error" gider.
4. **Ret kaydı bırakmayan paketler (orta):** manifest ayrıştırma (tek vekil karakter, aşırı iç içe JSON) ve alan
   türleri açıkça denetlenir → kayıtlı ret. Onayda yayın hatası (ör. profil sınırı) gerekçeyle kaydedilir; paket
   `verified` kalır, başka profille yeniden onaylanabilir.
5. **Boyut sınırı (orta):** CLI en çok sınır+1 bayt okur; sınırı aşan girdi saklanmaz, yalnız reddedilir.
6. **AT-10 probu (orta):** üç katman ayrı denetlenir: varsayılan rota yok, dış adlar çözülmüyor, yasak adreslere
   bağlantı yok; kurulumun gerçek model/ağ geçidi adresleri argüman olarak eklenir. Canlı: Core konteynerinde
   yeşil, host'ta beş ayrı kırmızı (prob boş geçmiyor).

Test boşlukları da kapandı: AT-03 artık gerçek `/mcp` `tools/call` ile (arama + pasaj açma, HTTP ile aynı);
AT-11 için dokuz bozuk-token durumu hem HTTP'de hem MCP'de (`initialize` ve `tools/call`) 401.

# M1d (2. kısım): hibrit arama, LLMDAP embedding ve özne anahtarı (D52)

- **LLMDAP bağlantısı:** `KUTUPHANE_LLMDAP_KEY` (Core'un `llmdap_sk_` anahtarı) yalnız `Authorization` başlığında
  gider; paylaşılan sır ve `x-llmdap-user` gönderilmez. `x-llmdap-for-subject` = adına çalışılan kullanıcı, yoksa
  çağıran. LLMDAP politikası: `p, svc-kutuphane, llm:invoke, llm/<rota>`.
- **Embedding:** `llmdap.embed` → `POST /bridge/<embed-rota>/v1/embeddings`; aynı `model_call` kaydı ve aynı egress
  denetimi (yerel kitap bulut embedding rotasına gitmez). `ingest` ve `approve-import` yeni sürümü indeksler;
  `kutuphane index <kitap>` eksikleri tamamlar. İndeksleme çağrılarının principal'ı `service:indexer`.
- **Arama:** tek SQL ifadesi: aynı ön-süzgeçten FTS sırası ve (sorgu vektörü varsa) kosinüs sırası, her biri 50
  aday, RRF (k=60). Vektör yoksa sıra yalnız FTS'tir (ölçümle doğrulandı: R@10 0.563 aynı). Sorgu vektörü
  alınamazsa arama tam metinle sürer; başarısız çağrı `model_call`'da kalır.
- **Sorgu metni:** arama sorgusu embedding rotasına kaynak kitapsız gider (kitap içeriği değil, kullanıcının
  yazdığı metin). Embedding rotası `cloud` ise sorgu kurum dışına çıkar; sorgu gizliliği isteniyorsa embedding
  rotası `local` olmalı (Spark profili zaten yerel).
- **Boyut:** bir modelin bütün vektörleri aynı genişlikte; farklı genişlik dönen model indekslenmez, sorgusu
  tam metne düşer (model değiştiyse yeni model adı).
- **Sınır:** RRF puanı her sonuçta > 0, bu yüzden "kütüphanede yok" artık puan eşiğiyle değil modelin
  `KÜTÜPHANEDE_YOK` cevabıyla gelir; AT-08 eşiği etiketlerle belirlenecek.
- **Reranker yok:** LLMDAP'ta rerank yüzeyi yok (LLMDAP#236). M0'a göre reranker R@1'i 0.34 → 0.41
  taşıyor; yüzey gelince aynı `_post` yolundan eklenir.
- **Testler:** sahte bridge gerçek sözleşmeyi taklit eder (özne anahtarı, başkasını adlandıran `x-llmdap-user` →
  401, embeddings yolu). Vektörle eşleşen ama okunamayan kitap görünmez; başka modelin vektörü yok sayılır; ajan
  `activate` olmadan talimat parçasını vektör yolundan da alamaz.

# Astra incelemesi #5 (PR #22–#24) ve düzeltmeler

Ham metin: `docs/research/2026-10-13-astra-review-m1-5-raw.md`. Yetki atlaması, SQL enjeksiyonu ya da anahtar
sızıntısı bulunmadı; düzeltilenler:

1. **Paket:** PostgreSQL'in tutamadığı değerler (NUL karakter, `bigint` dışı sıra) artık kayıtlı ret.
2. **LLMDAP etiketi:** principal en çok 128 karakter (LLMDAP `isChainLabel` sınırı); her principal geçerli
   `x-llmdap-for-subject`.
3. **Embedding cevabı:** indeksler tam `0..n-1`, vektörler sonlu, sıfır değil, tek genişlikte; bir modelin
   bütün vektörleri aynı genişlikte. Uymayan cevap saklanmaz; uymayan sorgu tam metne düşer.
4. **Ölçüm betiği:** önbellek girdiler, parametreler ve model revizyonu özetiyle anahtarlanır; parçalar güncel
   profille süzülür.
5. **Arayüz:** bitmiş oturumun geç gelen 401'i yeni oturumu kapatmaz.
6. **Belgeler:** sorgu metninin embedding rotasına gidişi, batch ortalaması süreler, bge-m3'ün `.bin` ağırlığı.

# Canlı LLMDAP sözleşme denetimi (AT-09, AT-11)

- `deploy/llmdap_contract.py`, gerçek bir LLMDAP gateway'ine karşı uçtan uca denetim yapar:
  - indeksleme, hibrit arama, cevap;
  - her çağrıda LLMDAP'ın türetilmiş kimliği;
  - birleşik denetimin LLMDAP zinciriyle `complete` olması;
  - başka özneyi adlandıran başlık, yanlış anahtar ve yalnız paylaşılan sır → 401.

  Kurulumda ve her LLMDAP yükseltmesinden sonra çalıştırılır.
- **2026-10-13 sonucu:** 9/9.
  - Gateway: LLMDAP `main` (0.26.0), stok `@llmdap/gateway`, yalnız bridge (`rag:false`, `memory:false`), subject-keys modu.
  - Upstream: yerel CPU bge-m3 + sabit sohbet ucu.
  - Bu deneme gateway'i Kütüphane oturumunun geçici alanında kaynaktan derleyerek yapıldı. Compose'a girmesi LLMDAP#237'yi (sade imaj) bekliyor.

# M1d (3. kısım): reranker (LLMDAP rerank yüzeyi, #236/#238)

- `retrieval.retrieve` HTTP, MCP, CLI ve cevaplar için tek giriş noktasıdır:
  1. sorgu vektörü (isteğe bağlı);
  2. ön-süzgeçli hibrit arama;
  3. reranker (isteğe bağlı) hibrit sonucun ilk 30'unu yeniden sıralar; puan, reranker'ın ilgililik puanı olur.
- Reranker yalnız aramanın zaten yetkilendirip kaydettiği pasajları yeniden sıralar. Havuzun tamamı çağıran adına
  okunmuş sayılır ve kaydedilir, çünkü metni reranker'a gider.
- Egress denetimi aynıdır: yerel kitabın pasajı bulut rerank rotasına gitmez.
- `llmdap.rerank` cevabı denetler:
  - her pasaj tam bir kez gelmeli;
  - indeks gerçek tamsayı olmalı;
  - puan sonlu olmalı.
- Denetimden geçmeyen ya da başarısız çağrıda hibrit sıra kalır; çağrı `model_call`'da kayıtlıdır.
- `llmdap.Routed`, embedding ve rerank rotaları için ortak tiptir (eski `Embedder`).
- **AT-08 için not:** reranker puanı (bge-reranker için 0–1) "kütüphanede yok" eşiğine RRF puanından daha uygun bir
  adaydır. Eşik etiketlerle belirlenir.

# Compose'ta gerçek LLMDAP (AT-10 canlı)

- `llmdap` servisi: `llmdap-bridge:0.28.0-llmdap1.18.0` (LLMDAP #237).
  - Salt okunur kök, bütün yetenekler kapalı, `no-new-privileges`.
  - İmzalı zincir `llmdap-audit` volume'unda.
  - Ayarlar `deploy/llmdap/` altında: rotalar, politika, anahtar hash'i ve env. Gizliler git'e girmez.
- **Ağlar artık her konuşma için ayrı:**

  | Ağ | Servisler |
  |---|---|
  | `db` | Postgres–Core |
  | `web` | ingress–Core |
  | `gateway` | Core–LLMDAP |
  | `models` | LLMDAP–model sunucuları |

  Hepsi `internal`. Canlı ölçüm:
  - Core yalnız Postgres ve LLMDAP'a ulaşır;
  - LLMDAP model sunucusuna ulaşır, ama internete ve Postgres'e ulaşamaz (adı bile çözülmez);
  - ingress Postgres'e, LLMDAP'a ve model sunucusuna ulaşamaz.
- `model-stub` (profil `dev-models`): yalnız standart kütüphane kullanan, belirlenimci sohbet, embedding ve rerank
  sunucusu. Ölçüm için kullanılmaz.
- `llmdap_contract.py` (rerank kontrolü eklendi) compose'taki gerçek LLMDAP'a karşı 11/11.

# Astra incelemesi #8 (PR #33–#42) ve düzeltmeler

Ham metin: `docs/research/2026-10-22-astra-review-m1-8-raw.md`. Dokuz bulgunun hepsi düzeltildi:

1. **MCP `ai_input`'u atlıyordu (yüksek):** MCP araçları ve `agent:` principal'ları model okuyucudur. `ai_input` izni olmayan pasajın metni dönmez (`text: null`, `withheld`), `read_document` reddedilir. Okuma yetkisi olmayan çağırana normal ret verilir; hak gerekçesi gösterilmez.
2. **Gölge koşucu eski etiketle buluta gönderebiliyordu (yüksek):** her barındırılan istekten hemen önce güncel etiket yeniden okunur.
3. **YAML'da yinelenen anahtar kısıtı eziyordu (orta):** yinelenen anahtar, merge anahtarı (`<<`) ve takma ad reddedilir; aşırı iç içe yapı `KstdError` olur.
4. **Güven, eylem sınırını uygulamıyordu (yüksek):** güven artık açık eylem listesi ve süre sonu ister (karar kuralı 4).
5. **Kabul edilmemiş ya da askıdaki öğe `permit` alabiliyordu (yüksek):** sıradan kullanım yalnız `accepted` öğede; `review` ve `history` görünümleri ayrı.
6. **Koşul ya da süre dışındaki kural talebi `permit` alıyordu (orta):** artık `escalate`.
7. **İzin sürüm bağlaması eksikti (orta):** öğe, politika sürümü ve sonraki ifadeler denetlenir.
8. **Yeniden açılan cevapta öğe bilgisi yoktu (orta):** bilgi ortak cevap fonksiyonlarında eklenir; CLI de alır.
9. **Lisans sözdizimi ve ayrıştırıcı hataları (düşük):** SPDX ifadesi gramerle denetlenir.

Karar kuralı vakaları 20'den 33'e çıktı; her kural için, kural kaldırılınca kırılan vaka var.

# Gerçek kullanım boşlukları G1, G3, G5 (docs/15 §3)

- **G1 biçimler:** `.txt`, `.json`, `.jsonl`/`.ndjson`, `.yaml`, `.toml`, `.sh`, `.py`, `.js`, `.ts`, `.xml`, `.csv`, `.mdc` düz metin olarak, `.html` yalnız görünen metniyle (betik, stil, şablon, yorum yok) aranır. JSONL'de her kayıt bir pasajdır; metin pasajları başladıkları satırı (`line`) taşır, arama ve atıf çıktısında görünür. Metin sayılmak için UTF-8 ve NUL'suz olmak gerekir. `kstd.yaml` üst veridir, dizinlenmez. `ai_use` kapıları biçimden bağımsızdır.
- **G3 dosya başına karantina:** çıkarılamayan dosya (metin katmanı olmayan, bozuk ya da şifreli PDF; UTF-8 olmayan ya da NUL içeren metin) saklanır ve listelenir ama dizinlenmez. `quarantine` tablosundaki kaydı (kitap, içerik sürümü, profil, yol, gerekçe) yayın sonucunda, `show` çıktısında ve CLI stderr'inde görünür; paket alımında `quarantined` bulgusu olur. Durum geçişi (D53): karantina bir (içerik sürümü, profil) çiftine aittir. Dosyayı düzelten sürüm (yeni bayt → yeni içerik kimliği) ya da onu okuyabilen okuyucu (yeni profil kimliği) dosyayı dizinler; eski sürümün karantinası güncel duruma taşınmaz. Güvenlik retleri kitap düzeyinde kalır: geçersiz `kstd.yaml`, sembolik bağ, yol ve boyut ihlali, PDF sayfa sınırı, UTF-8 olmayan ya da ön bilgisi geçersiz markdown (K3 sınıflandırması yapılamaz), kimlik bilgisine benzeyen dosya adı ya da metin (`secretscan.py`; önceden üründe gizli bilgi taraması yoktu).
- **G5 ajan dosyaları:** gizli yollar dışarıda kalır (`.git/`, `.env*`, nokta dosyaları). İzin listesi: `.claude/` (`agents`, `commands`, `rules`, `skills`, `hooks`, `CLAUDE.md`), `.cursor/rules/`, `.github/` (`copilot-instructions.md`, `instructions/`, `prompts/`, `agents/`, `chatmodes/`), `.agents/`, `.codex/`. Paketlerdeki yollar da aynı kurala uyar. K3 kuralı `agentfiles.py`'dedir: bu klasörlerdeki dosyalar, `SKILL.md` bulunan klasörün altındaki her dosya, adı talimat dosyası adıyla başlayan dosyalar (`AGENTS.md.hostile`), `.mdc` ve Copilot son ekleri, ön bilgi tipleri. Ajan `activate` olmadan bunları almaz (değişmedi). 011 göçü eski profillerde saklanan pasajları aynı kuralla işaretler.

# Astra incelemesi #9 (PR #46, #49, #51) ve düzeltmeler

Ham metin: `docs/research/2026-10-22-astra-review-9-raw.md`. On bulgunun hepsi düzeltildi; her biri için düzeltmeden önce kırılan bir test ya da vaka var:

1. **JSON anahtarlarındaki parola taranmıyordu (yüksek):** JSON ve JSONL'deki `"anahtar": "değer"` çiftleri kaçışları çözülerek (`"pass\u0077ord"`) taranır; yedek kalıplar tırnaklı anahtarı da kabul eder. `.codex/` gibi ajan klasörleri dahil.
2. **Koddaki güçlü parola literali kaçıyordu (yüksek):** tırnaklı literal hangi karakterleri içerirse içersin bütün olarak alınır, sonra kimlik bilgisi ataması değerlendirilir (`password = "aB3!very.secret-password"` yakalanır).
3. **HTML çıkarımı taramadan sonra sır üretebiliyordu (yüksek):** hem özgün metin hem de pasajlara kesilen çıkarılmış metin (varlıkları çözülmüş HTML, PDF metin katmanı) taranır. Çıkarım tek yerde (`source.extracted_text`); `profiles.py` aynı metni keser.
4. **Girdi kısıtı ikinci türetmede kayboluyordu (yüksek):** karar kuralı kayıtlı girdi grafiğinin tamamını geçişli olarak, döngüye karşı korumalı yürür; bilinmeyen ata `input-unknown` ile reddedilir.
5. **Girdinin kişisel veri ve işleme kısıtı uygulanmıyordu (yüksek):** soydaki her girdi için kişisel veri koşulu (güvenilmeyen düzenleyicinin `synthetic` beyanı `unknown` sayılır) denetlenir; türetilmiş öğe soyun en katı `export` ve `route` değerini miras alır.
6. **Kaynak ifadesi yokken silme torunları kaçırıyordu (yüksek):** gezinti istenen her kimlikle başlar, öğe yerelde olmasa da. Silinmiş olarak yalnız yerel öğeler raporlanır; dış teslimlerin yükümlülüğü (`unresolved`) korunur.
7. **Sıradan yapılandırma değerleri kitabı engelliyordu (orta):** anlamsal sabitler (`token: refresh_token`), yer tutucular (`${PASSWORD}`, `<your-key>`, `changeme`) ve URL'ler kimlik bilgisi sayılmaz; gerçek anahtarlar yakalanmaya devam eder. Dar ve denetlenebilir istisna: `ingest --accept-finding <yol>@sha256:<dosya özeti>:<kural>` (tekrarlanabilir). Yalnız o dosya içeriği ve o kural için geçerlidir; dosya değişirse geçersizdir; hiçbir bulguya uymayan istisna alımı reddeder. Kabul edilen bulgular yayın kaydına yazılır (`publication.accepted_findings`, 012 göçü) ve stderr'de görünür. Hata ve kayıtlarda eşleşen metin hiç yazılmaz: yalnız yol, satır ve kural.
8. **Boş `inputs` silme belirsizliğini gizliyordu (orta):** `inputs: []` alanın hiç olmamasıyla aynı sayılır; öğe `scope_unknown`'da kalır.
9. **JSONL kayıtları dize içindeki Unicode karakterde bölünüyordu (orta):** satırlar yalnız `\n`'de (normalize edilmiş `\r\n` dahil) biter, `splitlines()` kullanılmaz; atıf satır numaraları aynı kuralı sayar. Kesici sürümü 4 oldu (yeni profil kimliği).
10. **Negatif Content-Length model sunucusunun gövde sınırını aşıyordu (orta):** tek, geçerli, negatif olmayan ve sınırlı bir Content-Length gerekir; `Transfer-Encoding` (501) ve yinelenen uzunluk (400) reddedilir; soket okuma zaman aşımı 30 sn (408); en çok 8 eşzamanlı POST, fazlası hemen 503 alır. Kapsayıcı içinde atılabilir bir betikle denendi; `embedder` yeniden kuruldu ve sağlıklı.

Karar kuralı vakaları 38'den 45'e, silme vakaları 4'ten 6'ya çıktı.

# Astra incelemesi #10 (PR #55–#57) ve düzeltmeler

Ham metin: `docs/research/2026-10-23-astra-review-10-raw.md`. Dokuz bulgunun hepsi düzeltildi:

1. **Boş jeton kimlik doğrulamayı kapatıyordu (yüksek, etiketleme sayfası):** 16 karakterden kısa jeton başlangıçta reddedilir; boş çerez hiçbir zaman geçmez.
2. **Araç işareti model kanıtını eziyordu (orta):** model kanıtı önce değerlendirilir; `tool` yalnız adı belli bir kural tabanlı üreticiyle önerilir.
3. **Durum satırı alt dize eşleşmesi (orta):** `unstable`, `not approved` artık kabul önermez; değer kelime kelime ve olumsuzlukla okunur.
4. **Başka anahtarın geri çekmesi `accepted` öneriyordu (orta):** yalnız itiraz işareti olur; kaynağın kendi durumu korunur.
5. **Qwen önericisi başarısız öğeleri bir daha denemiyordu (orta):** yalnız tam ve geçerli öneri "bitti" sayılır; değerlendirme her öğenin son sonucunu kullanır.
6. **Bozuk model yanıtı tüm koşuyu düşürebiliyordu (orta):** yanıt zarfı ve beş alan tip olarak doğrulanır; şema hatası öğe başına kaydedilir.
7. **Sayfada çift tıklama öğe atlatıyordu (orta):** kaydetme ve gezinme sırasında düğmeler kilitlenir; eski yanıt imleci oynatmaz.
8. **`software_agent` sürümü sayı olarak kayboluyordu (orta):** ad ve sürüm dize olmalı (`version: "1.10"`); sayı ve mantıksal değer reddedilir.
9. **Alınan pakette `tool_made` doğrulanmıyordu (orta):** köken listeleri paketteki geçerli `kstd.yaml`'dan yeniden hesaplanır; fark varsa paket reddedilir.

# Astra incelemesi #11 (PR #61–#65) ve düzeltmeler

Ham metin: `docs/research/2026-10-26-astra-review-11-raw.md`. On bulgunun hepsi ele alındı; etiketleme sunucusunun testleri `experiments/labeling_v4/test_server.py`'de:

1. **Aynı makineden CSRF (orta, etiketleme sayfası):** `/api/label` yalnız `Content-Type: application/json` ve sunucunun kendi kaynağıyla (`Origin` = `http://<Host>`) kabul edilir; `text/plain` ve başka port ya da alan 403 alır.
2. **Gösterilmeyen alanlar kaydediliyordu (orta):** sunucu, seçilen tür, köken, talimat ve form kipinden (`basic`/`exception`/`all`) görünür alan kümesini sayfayla aynı kurallarla hesaplar. Her etiket `shown` içinde, `shown` izinli küme artı `kept` içinde, zorunlu alanlar `shown` içinde olmalı; değilse 400.
3. **Kabul edilen öneriler sahtelenebiliyordu (orta):** `accepted_proposals` istemciden alınmaz; değer, o öğe için gösterilen kural önerisine ya da Qwen önerisine eşitse sunucu alanı kabul sayar. Kayıt `proposal_version` taşır: `proposals.jsonl` ve `proposals_llm.jsonl` baytlarının sha256'sı.
4. **Ön ayar değişince girilen değer siliniyordu (orta):** değeri olan alan koşulu düşse de görünür kalır, `kept` olarak gönderilir; "Temizle" ile boşaltılabilir.
5. **Kör örnek aileler arasında sızıyordu (orta):** kör seçim aile başınadır (öğenin `group`'u, yoksa kaynak + `ref.path` klasörü); her katmanda öğelerin ~%30'u (sha256 sırasıyla, katmanın payına sığan aileler). Kayıt `blind` ve `family` taşır. Canlı veride 1.063 öğenin 319'u (%30,0; R 87/290, S 13/44, W 100/333, A 119/396), 264 ailenin 123'ü kör. Kayıtlı etiket yoktu; hiçbir etiket yeniden yazılmaz.
6. **Kör öğede `needs_split` varsayılanı (düşük):** kör öğede boş başlar, isteğe bağlı kalır; boş bırakılırsa kayıtta yoktur (`no` değil).
7. **Yeniden yüklemede çerezsiz oturum düşüyordu (orta):** `/` kimlik doğrulamasız, veri içermeyen statik sayfa kabuğudur; her `/api/` yolu çerez ya da `X-Label-Token` ister; `?t=` çerezi yine kurar. 401'de sayfa "Oturum yok: Telegram'daki bağlantıyı yeniden açın." yazar. Başsız Chromium'da çerezsiz yeniden yükleme denendi.
8. **Tek uzun pasaj gömme bütçesini aşıyordu (orta):** `EMBED_CHARS` (= 24.000 karakter) üstündeki pasajın yalnız başı gömülür; vektör `chunk_vector.truncated` ile işaretlenir (013 göçü). Pasaj metni ve tam metin araması değişmez.
9. **G21 yanlış teşhis (orta, `docs/18`):** saklanan cevapta atıflar kendi `n`'lerini taşır (4, 6, 7, 8). Tekrarlanabilen sorun gruplu referanstır: `[2,3,5,6]` okunmaz, 2, 3 ve 5 ne denetlenir ne listelenir. Atıf-kanıt çelişkisi saklanan cevapta yok (pasaj 6 `llama-3.1-8b` için avoid → pilot der); G21 buna göre düzeltildi.
10. **G19 karışık teşhis (düşük, `docs/18`):** soru 2 gömme yolu sağlıklıyken yeniden soruldu. İngilizcede rapor karma listede 7., yeniden sıralamadan sonra 10. sırada (kesim 8) → "kütüphanede yok"; Türkçede ilk sırada → doğru cevap. G19 bu izlerle, tek soru çifti olarak yeniden yazıldı.

# Astra incelemesi #12 (PR #92–#95) ve düzeltmeler

Ham metin: `docs/research/2026-10-27-astra-review-12-raw.md`. Sekiz bulgunun hepsi düzeltildi; her biri için düzeltmeden önce başarısız olan bir test var:

1. **Birleştirilen havuz yetkilendirilmiyordu (yüksek):** çeviriyle yapılan ikinci aramanın havuzu ilkiyle birleşince, tüm havuz arayanın o anki haklarıyla tek bir ifadede yeniden karara bağlanır (`search.authorize`). Bu, yeniden sıralayıcıdan, cevap modelinden ve teslimden öncedir. Hakkı düşen kitabın pasajı çıkar; kayıp `changed during search` diye günlüğe yazılır. Test: iki arama arasında hak A kitabından B kitabına geçer; A'nın hiçbir pasajı ne yeniden sıralayıcıya ne arayana ulaşır.
2. **Taşıyıcı çerez başka portlara sızıyordu (orta, etiketleme v5 ve v4):** çerez tamamen kaldırıldı; sunucu `Set-Cookie` göndermez. Tek kimlik bilgisi `X-Label-Token` başlığıdır. Sayfa `?t=`'yi sekmenin sessionStorage'ına alır. `/` kabuğu herkese açık; her `/api/` yolu başlık ister. CSRF köken denetimi kalır. Yalnız çerezle gelen istek 401 alır. Başsız Chromium'da çerezsiz açılış ve aynı sekmede yeniden yükleme denendi.
3. **Önerici dosya yolları vaka klasöründen çıkabiliyordu (orta, etiketleme v5):** tek denetim `propose.case_file`. Dosya, vaka klasörünün altında çözülür. Mutlak yol, `..`, klasör dışına çıkan sembolik bağ ve `copy: false` reddedilir; dosya okunmaz. `view()`, Qwen önericisi (`view()` üzerinden) ve sunucu bu denetimi kullanır. `select_human.py` ve `eval_auto.py` vaka dosyası okumaz. Test: hazırlanmış vaka; altın dosyanın baytları ne görünümde ne istemde.
4. **`current_only` zaman damgasını takvim gününe indiriyordu (orta):** `kstd.effective()` zamanı korur (`2026-10-27T23:59:00Z`). Yalnız tarih 00:00 UTC demektir ve tarih olarak yazılır. Test: aynı gün daha sonra başlayan `valid_from` şimdi geçerli değildir.
5. **014 göçü yanlış girdi hash'i verebiliyordu (orta):** `015` göçü `input_sha256`'yı gerçekten gömülen metinden yeniden hesaplar: `truncated` ise baştan, değilse tüm metinden. Belirsiz satırlar NULL olur ve hiç kopyalanmaz. Belirsiz satır, 014'ün aynı anahtarı verdiği, kesilmemiş uzun bir pasajla aynı başı taşıyan kesilmiş vektördür (onun kopyası olabilir). Test, test veritabanında: eski bütün vektör tüm metnin hash'ini alır; kopya NULL olur; aynı başlı üçüncü sürüm yeniden gömülür.
6. **Uzun soru sorgu önbelleğinde kalıyordu (orta):** 1.000 karakter sınırı gömme ve önbellek bakışından önce, her yolda (arama ve `ask`, HTTP/MCP/CLI) denetlenir. Önbelleğin 256 kayda ek olarak 4 MiB bayt bütçesi var. Testler: uzun soru hiçbir model çağrısı yapmaz ve önbelleğe girmez; bütçe aşılınca en eski kayıt çıkar, bütçeden büyük vektör saklanmaz.
7. **Atıf ayrıştırma kapalı başarısız olmuyordu (orta):** köşeli parantez içi için açık dil bilgisi: `n`, `n,m`, `n-m`, `n–m`. Rakam, boşluk, virgül ve tire taşıyan her köşeli parantez bir atıf grubudur; yalnız ISO tarih (`[2026-10-26]`) değildir. Bozuk grup (`[1-2-3]`) ya da aralık dışı uç (`[1-100000]`, 8 pasajda) cevabı reddeder, istisna atmaz. Uçlar aralık açılmadan önce denetlenir; çok uzun sayı sayıya hiç çevrilmez.
8. **Gövdedeki tarih yenilik sıralamasını yönlendirebiliyordu (orta):** tarih yalnız kaynağı belli üst veriden gelir. Sırayla: kstd `valid_from`, yoldaki tarih ya da ISO hafta, JSONL kaydının `classified_at` alanı. Metnin başka yerindeki tarih kullanılmaz. Yarından sonraki tarih yok sayılır. Test: gövdesinde `2099-12-31` olan pasaj öne geçmez.

# R1: ajan belleği (docs/24, #68–#73)

- **Notlar (A, #68):** dergi (journal), öğeleri ajan notları olan bir kitaptır. `propose_note` ve `link_notes` (MCP) ile `POST /v1/notes`, `POST /v1/notes/links` yazar; yazar `propose` kipi ister. Not `pending` başlar; Standing'i yalnız küratör, komut satırından (`kutuphane note standing`, `KUTUPHANE_CURATOR_DSN`) değiştirir. Ajanın `origin: human` iddiası reddedilir: not `model` olarak saklanır ve alındı `origin-claim-refused` taşır. 016 göçü ve `deploy/db-roles.sql`: sunucunun rolü (`kutuphane_app`) Standing yazamaz.
- **Okuma (B, #71):** `query_notes` ve `neighbours` model çağırmaz. `current` yalnız onaylı ve bağlamda geçerli nottur; `pending` not `open` kümesindedir. `collapse` yalnız `same_as` gruplarını birleştirir; çelişen (`contradicts`) notların ikisi de kalır. `open_citation` not referanslarını da açar.
- **Kod atıfları (C, #70):** `kutuphane repo add` bir dergiye çıplak ayna kaydeder (Kütüphane hiç `fetch` etmez). `verify_citations` ve `POST /v1/citations/verify` `verified`, `stale`, `missing` ya da gerekçeli `unverifiable` verir, kod metni döndürmez. Eski satırlara dayanan not yeni commit'te `current` değildir. 017 göçü; imaj git ≥ 2.45 ister.
- **SDK v2 ve işler (D, #72, #73):** `mcp>=2.3,<3`; MCP 2025-11-25 ve 2026-07-28 istemcilerine hizmet eder (`deploy/mcp_probe.py` ikisini de dener). `ask_library(background: true)` ve `POST /v1/ask` hemen `job_id` döndürür; `job_status`, `job_result`, `job_cancel`. 018 göçü.
- **Birleştirme:** dört dal tek dalda (`feat/r1-agent-memory`) birleşti; `FEATURES = (notes, coderepo, notesquery)`. B'nin yer tutucu `notes.py`/`coderepo.py`/016/017 dosyaları sahiplerinin sürümleriyle değişti. Sözleşme farkı: gerçek `coderepo` tek satırlık atıfı da `yol:2-2` biçiminde yazar ve yalnız `KUTUPHANE_REPO_ROOTS` içindeki depoyu okur; B'nin testi buna göre düzeltildi. Tam test takımı 552 geçti; geçici veritabanında uçtan uca deneme ve iki protokol sürümüyle probe geçti.

# Astra incelemesi #13 (R1 ajan belleği, PR #101) ve düzeltmeler

Ham metin: `docs/research/2026-10-27-astra-review-13-raw.md`. Dokuz bulgunun hepsi düzeltildi; her biri için düzeltmeden önce başarısız olan bir test var:

1. **Git graft'ları yayımlanmış commit sınırını aşıyordu (yüksek):** `info/grafts` soy ağacını yeniden yazar; `GIT_NO_REPLACE_OBJECTS` onu kapsamaz. `<izinli uç> <yetim commit>` satırı ulaşılamayan commit'i yayımlanmış gösteriyordu. Artık `check_git_dir` `info/grafts`'ı hem `repo add`'de hem her açılışta reddeder (`repo_invalid`). Kurulan ortam da `GIT_GRAFT_FILE=/dev/null` taşır, yani hiçbir graft uygulanmaz. Testler: `test_repositories_refused_at_add_and_at_open[grafts]` ve `test_grafts_cannot_publish_an_unreachable_commit` (graft'tan önce `commit_not_published`, sonra `repo_invalid`; denetim devre dışıyken bile ortam yüzünden yine `commit_not_published`).
2. **Öneri alındısı okuma hakkı düşünce de aday gösteriyordu (yüksek):** `gate.guard_many`'nin yeni `finish` kancası, aynı işlemde son karardan hemen sonra çalışır. Son karar artık her kitapta `read`'i de karara bağlar. Alındı bu karara göre kesilir: kitabı düşen aday çıkar; dergide `read` yoksa alındı en küçük biçimine iner (varlık ya da sayı bilgisi yok). Aday erişim kaydı da son karardan yazılır. Testler: `test_a_candidate_book_revoked_after_selection_is_not_in_the_receipt`, `test_journal_read_revoked_after_the_receipt_level_gives_the_minimal_receipt`.
3. **Çok atıflı notlar sorguyu düşürüyordu (yüksek):** `_citations` yalnız yükler. Hedefi olmayan kod atıfı doğrudan `not_checked` olur ve git süreci çalışmaz. Hedefli atıflar yalnız sayfanın değerlendirdiği notlarda doğrulanır: sırayla, sığmayan ilk nota kadar, `collapse`'ta kümeleriyle birlikte. Doğrulama da yalnız kod kuralı olmadan kümede olacak notlarda yapılır. `coderepo.Verifier` istek başına tek önbellek tutar ve en çok 200 atıflık toplu işlerle çalışır; `neighbours` ve `open_citation` da aynı yoldan geçer. `excluded` artık sayfanın geçtiği notları sayar; sayfalar boyunca toplamı bütün sonucu verir. Test: `test_many_cited_notes_never_fail_a_query`. Her biri 20 atıflı 11 emekli not artık hata vermez; hedefsiz sorgu hiç git çağırmaz. Hedefli sorguda doğrulanan atıflar sayfa artı bir notla sınırlıdır.
4. **`open_citation` bağlı kitapları yeniden denetlemiyordu (orta):** `open_note` artık `query_notes`'un kapılarını kullanır. Atıflar, bağ sayıları ve halef tüm okuma kümesinden gelir; son karar bu kümeyi karşılaştırır. Kitap düşerse `changed during query` kaydı yazılır ve bir kez yeniden çalışılır, sonra `SearchChanged` gelir. Notun kendi kitabı düşerse `revoked before delivery` döner. Test: `test_open_citation_reruns_when_a_linked_book_is_lost`. Kitap düşünce `links` boş, `successor` null olur.
5. **İptal, ekleme öncesinde kabul edilse de iş başarılı bitiyordu (orta):** `answers.ask` yeni bir `commit(answer_id)` kancası alır; kanca, cevabı ekleyen işlemin içinde çalışır. İş burada satırını `FOR UPDATE` ile kilitler, iptali, durumu ve kirayı denetler, sonra `succeeded`'ı yazar. Ekleme, denetim ve başarı güncellemesi tek işlemdir; önce işlenen iptal cevabı geri alır. Test: `test_a_cancel_that_lands_before_the_store_wins`.
6. **Süresi dolmuş işçi çalışıp cevap saklıyordu (orta):** `jobs.renew` kirayı yalnız `running` ve süresi dolmamışsa uzatır; biten kira hiç diriltilmez. `check` (model çağrısından ve saklamadan önce) çalışan, iptal edilmemiş ve süresi dolmamış bir kira ister (`clock_timestamp()`). Saklama, 5'teki kilitli denetimle süre dolumuna karşı da korunur; sonuç `failed: interrupted` olur. Testler: `test_an_expired_and_failed_job_stores_no_answer` ve `test_renewal_never_revives_an_expired_lease`.
7. **`since`, gizli kitaptaki bağ etkinliğini sızdırıyordu (orta):** `_changed` bir bağı yalnız iki ucu da şimdi okunabiliyorsa sayar (`src_book` ve `coalesce(dst_note_book, dst_book)` okuma kümesinde). Test: `test_since_ignores_links_from_unreadable_books`.
8. **`collapse` çelişen üyeleri sessizce düşürüyordu (orta):** `_kept`, bir `same_as` kümesinin istenen kümelerdeki (`sets`) üyeleri arasındaki tüm `contradicts` kenarlarına bakar. En yeni üye kalır; başka bir üyeye `contradicts` ile bağlı her üye de kalır. Çelişkisiz üyeler en yeniye katlanır. Test: `test_collapse_never_drops_a_contradicting_member`. A↔B çelişkisi varken ve C en yeniyken sonuç C, B, A olur.
9. **Mezar taşları bayt sınırını aşıyordu (orta):** `left` girdileri öğelerle birlikte sayfalanır: önce mezar taşları (not `seq` sırasıyla), sonra öğeler. Hepsi bütün zarfı sayan aynı bayt ve tahmin sınırı altındadır. `next_cursor` bir mezar taşından da devam eder (`[w, "left", seq]`), yani istemci `since` filigranını imleç null olana dek ilerletmez ve hiçbir kaldırma atlanmaz. `excluded` sayıları sayfadan sonra bilinir; zarfa üst sınırları ölçülerek konur. Test: `test_tombstones_are_paged_under_the_byte_limit`. 80 mezar taşı ve 6 öğe, 8192 baytlık sayfalarda, eksiksiz ve tekrarsız gelir.

`docs/24` §9.1, §9.4, §9.5, §10.2, §10.3, §11, §12.2 ve T32 buna göre güncellendi.

# R2: `derived_from` boyunca geri alma (docs/24 §20, #79)

- **Geri alma eylemi:** `kutuphane note rollback <ref> --curator user:… --reason "…"` yalnız komut satırındadır ve `KUTUPHANE_CURATOR_DSN` ister. Küratör kök notun kitabında `curate` tutmalıdır. Kök, küratör olayı alır: `approved` → `retired`, `pending` → `rejected` (D68: hiç kabul edilmedi); zaten dışarıdaki kök aynı değerle bir olay daha alır. Kendi `derived_from` zinciri köke ulaşan her not (başka dergide de) kendi sistem olayını alır: `retired`, `cause_seq` = kök olayı, gerekçe `derived from <kök>`. `derived_from` yalnız oluşturma bağıdır, bu yüzden başka bir ajan sonradan bağ ekleyerek not geri aldıramaz. Zaten `rejected` ya da `retired` olan türev not olay almaz; ondan türeyenler yine kapsamdadır.
- **Rapor:** eylem, kapsamdaki notları (önceki ve yeni Standing, yazanlar: `principal`, `on_behalf_of`, `client_id`), bu notları teslim eden erişim kayıtlarını (`query_notes`, `neighbours`, `open_citation`, öneri adayları; her öğe teslimdeki Standing ile), bunları kullanan cevapları ve dışa aktarımları (`export_*`, #74) yazar. Teslim, `{ref, standing_seq}` öğesi taşıyan izinli `access_event` satırıdır; yazma kayıtları (`propose`, `link`) teslim sayılmaz.
- **Kısıtlama türetmeyi izler:** 019 göçü `note_journal` görünümünü ekler. Her okuma ve her model çağrısı notun `search` ve `ai_input` değerlerini, `source_books` içindeki her derginin güncel değerleriyle VE'ler. Kaynak dergiye sonradan `journal restrict` uygulanırsa, başka dergideki türev notlar da hemen kısıtlanır. 019'dan sonra `deploy/db-roles.sql` yeniden uygulanmalıdır (görünüm için `SELECT`).
- Testler: `tests/test_rollback.py` (T39–T43).

# R2: sonuç geri bildirimi ve karar kayıtları (docs/24 §21, #74)

- **`record_outcome` / `POST /v1/outcomes`:** bir notun (`book@nt_…`) ya da bir pasajın (`book@ct_…/pf_…/yol#n`) tam sürümüne bir görevin (`task_ref`) sonucunu yazar: `passed`, `failed`, `reverted`, `reopened`. Kitapta `propose` ve `read` ister; `read` olmadan "var/yok" cevabı yalnız-öneren çağırana notun varlığını söylerdi. Köken yazma yolundan gelir (§5.2). Kayıtlar yalnız eklenir (`kutuphane_app` güncelleyemez, silemez); `idempotency_key` zorunludur, tekrar ilk alındıyı döner. Günlük yazma sınırına sayılır. 020 göçü.
- **Standing değişmez:** `query_notes`, `neighbours` ve `open_citation` sonuçları yalnız sayı olarak gösterir (`outcomes`); "current" kuralı onları okumaz.
- **Karar alanları:** `decision_proposal` notu `decision: {options, choice}` taşıyabilir; kanonik gövdeye yalnız verildiğinde girer, eski notların kimliği değişmez.
- **`train` hakkı:** dergi `train` belirtir (`journal create --train y|n`, varsayılan `n`; `journal restrict --no-train`); not `train` değeri bağımlılıklardan türer (§6.2 kuralı). Eski dergi ve notlar `train = false` alır.
- **`kutuphane decisions export <principal> --out FILE`:** okunabilir dergilerdeki karar notlarını JSONL yazar: bağlam, seçenekler, seçim, yazan, sonuç kayıtları, `ai_use`. Metin yalnız `ai_input` ve `train` ikisi de `y` iken vardır; yoksa yalnız referans ve SHA-256. Her kitap için `action = export_decisions` erişim kaydı, `items = [{ref, standing_seq}]`.

# Astra incelemesi #14 (PR #103/#104) ve düzeltmeler

Ham inceleme: `docs/research/2026-10-27-astra-review-14-raw.md`.

- **P1, dışa aktarma okuma geri alındıktan sonra referans tutuyordu:** `decisions export` atıfları ve bağları kayıtlar kurulurken alınan yetki görüntüsüne göre süzüyordu; son kapı yalnız dışa aktarılan dergileri yeniden karar veriyordu. Şimdi süzme `guard_many` `finish` kancasında, son okuma kararıyla yapılır. Test: `test_the_export_drops_references_whose_read_was_revoked_before_delivery`.
- **P1, kaynak kısıtlandıktan sonra eğitim metni çıkıyordu:** etkin `ai_input` ve `train` bir kez okunuyordu. Şimdi son karardan sonra `note_journal` yeniden okunur; hakkı düşen kayıt yalnız referans ve özetlere (SHA-256) indirilir. Test: `test_the_export_withholds_text_when_a_source_loses_train_before_delivery`.
- **P2, geri alma önceden onaylı kökü `rejected` yapıyordu:** `approved → retired → pending → rollback` köke `rejected` veriyordu (D68 ile çelişir). Şimdi bir kez onaylanmış kök `retired` olur; `rejected` yalnız hiç onaylanmamış kök içindir. Aynı kural `kutuphane note standing … rejected` için de geçerlidir: bir kez onaylanmış nota `rejected` reddedilir, ileti `retired` kullanılmasını söyler. Testler: `test_rollback_retires_a_reopened_root_that_was_approved_before`, `test_standing_refuses_rejected_for_a_note_that_was_ever_approved`.

# Astra incelemesi #15 (PR #108/#109) ve düzeltmeler

Ham inceleme: `docs/research/2026-10-27-astra-review-15-raw.md`. Her bulgu için önce `origin/main` üzerinde başarısız olan bir test yazıldı, sonra düzeltme yapıldı.

- **P1, ilgisiz bir değişiklik değişmemiş becerinin engelini düşürüyordu:** engel bir içerik sürümüne bağlıydı; beceri klasörü dışında bir dosya değişince yeni sürüm `SAFE` taramayla engelsiz yayımlanıyordu (önceki başarısız tarama ya da önceki araç sürümünün kısıtı eski sürümde kalıyordu). Şimdi `skillscan.store`, aynı girdi özetinin (input digest) temizlenmemiş her engelini yeni sürüme kopyalar (`carried_from`, göç `022_skill_block_carry.sql`); bu, taramanın yeniden kullanılmasından, yeniden çalışmasından ya da hiç çalışmamasından bağımsızdır. Tek bir `skill clear` bütün kopyaları kaldırır. Test: `test_an_unrelated_edit_keeps_the_block_of_unchanged_skill_bytes` (başarısız tarama, başka araç sürümü, araç yok).
- **P1, notlar engelli becerilerden türeyen içeriği veriyordu:** not teslimi yalnız `ai_input`'a bakıyordu. Şimdi SQL `note_skill_blocked(seq)` notun pasaj atıflarını ve `derived_from` bağımlılıklarını (geçişli) denetler. Mevcut `ai_input` davranışıyla tutarlı olarak metin gizlenir, not listede kalır: `query_notes`, `neighbours`, `open_citation` içindeki not ve `propose_note` adayları model okuyucularına `text: null` ve `withheld` verir; karar dışa aktarımı her okuyucu için metni, seçenekleri ve seçimi gizler. Test: `test_notes_withhold_text_derived_from_a_skill_blocked_later`.
- **P1, yetki ve engel ayrı sorgulardı:** son yetki kararı ile engel sorgusu arasında başka bir işlem okuyucunun hakkını geri alıp engeli temizleyebiliyordu. Şimdi `authz.decide(skills=…)` ve `authz.allowed(skills=…, notes=…)` hakları ve engelleri tek SQL deyiminde (tek anlık görüntü) okur; `gate.guard`, `gate.check_many`, `gate.guard_many`, `search` ve not okuma yolları bunu kullanır. `gate.blocked_skills` ve `refuse_blocked_skills` kaldırıldı. Testler: `test_the_final_decision_and_the_skill_block_are_one_snapshot`, `test_an_aggregate_delivery_reads_rights_and_skill_blocks_in_one_snapshot`.
- **P2, kurulum betiği derleme bağımlılıklarını özet denetimi dışında çalıştırıyordu:** `hatchling` sabitlenmemişti ve yalıtılmış derleme onu özetsiz indiriyordu. Şimdi `deploy/skillspector/build-requirements.txt` hatchling ve bağımlılıklarını sürüm ve sha256 ile sabitler; çalışma zamanı bağımlılıklarıyla birlikte `--require-hashes --no-build` ile (yalnız wheel) kurulur, proje `--no-build-isolation --no-deps` ile derlenir. `SKILLSPECTOR_WHEELS=<klasör>` ağsız kurulum sağlar. Python 3.14 artık desteklenmez (yara-python 4.5.4 için wheel yok). Gerçek kurulum özetli indirmeden sonra çevrimdışı denendi ve sözleşme testi geçti. Test: `test_the_installer_builds_without_unhashed_build_dependencies`.
- **P2, düşmanca JSON başarısız tarama yolundan kaçıyordu:** derin iç içe diziler `RecursionError`, `"\ud800"` ise `UnicodeEncodeError` veriyordu ve ingest duruyordu. Şimdi rapor bir dosyaya yazılır ve 8 MiB'den büyükse okunmaz; NaN/sonsuz reddedilir; yineleme olmadan derinlik (en çok 64), NUL ve tek başına vekil (surrogate) karakterler denetlenir; ayrıştırma, normalleştirme ve özet tek hata sınırındadır. Düşmanca rapor kayıtlı, engelleyen bir `failed` taramadır. Test: `test_a_hostile_report_is_a_recorded_blocking_failed_scan` (DEEP, SURROGATE, NUL, NAN, HUGE).
- **P2, kural 4 yetkisiz gevşetmeye üst yazma (supersession) ile izin veriyordu (eski):** `latest_per_issuer()` önceki kısıtı güven denetiminden önce atıyordu. Şimdi `handling_of` sıra ile okur: yetkisiz bir gevşetme aynı yayıncının kabul edilebilir kısıtının yerine geçmez. `kstd/tests/decision/cases.yaml` kural-4 grubuna dört vaka eklendi; ikisi eski değerlendiricide başarısız olur. `docs/11` taslak 0.3 kural 4 metni ve değişiklik notu güncellendi.

# Güvenlik incelemesi #16 (Astra yerine yerel inceleme; Codex kredisi bitti)

Ham inceleme: `docs/research/2026-10-27-review-16-raw.md`. Kapsam: küratör dilimi P (#115). İnceleyici yalnız okuyabildi ve hiçbir bulguyu yeniden üretemedi; burada her bulgu (2–6) için önce `_test` adlı geçici veritabanında başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Bulgu 1 (sayfa notun kimliğe giren bütün parçalarını göstermiyor) dilim Q'ya verildi. Testler `tests/test_curator_review16.py` içindedir.

- **Orta, kural onayı imzasız not emekliye ayırıyordu (bulgu 2):** onaylanan kuralın `supersedes` bağlı, aynı kapsamlı öncülleri `act = NULL` sistem olayıyla `retired` oluyordu; bunlar imzalanan bildirimde yoktu ve `verify-acts` onlara bakmıyordu. Şimdi seçenekler anında hesaplanır ve bildirime yazılır (`retires: [{ref, id, was}]`); imza sayfası bunları gösterir; eylem anında yeniden hesaplanan küme farklıysa 409 döner, aynıysa yalnız bunlar yazılır. `verify_acts` eylemin olaylarının neden olduğu sistem olaylarını `retires` ile karşılaştırır. Testler: `test_a_rule_approval_signs_the_retirements_it_causes`, `test_verify_acts_checks_the_system_events_of_an_act`.
- **Orta, web rolü imzasız sistem Standing değeri yazabiliyordu (bulgu 3):** `standing_event_web` ilkesinin sistem dalı değeri sınırlamıyordu. Şimdi yalnız `retired`; göç 026'daki `standing_event_retires_signed` tetikleyicisi hedefin nedenin eyleminin `retires` listesinde olmasını ve neden olayının aynı işlemde yazılmasını ister. `docs/25` §4.5 ve §4.6 güncellendi. Testler (`kutuphane_curator_web` rolüyle): `test_the_web_role_writes_no_unsigned_system_standing`, `test_web_system_events_are_only_the_supersession_of_its_approved_rule`.
- **Orta, geçiş anahtarı geri alınınca oturumlar sürüyordu (bulgu 4):** `curator_session.credential_id` (göç 026) girişin geçiş anahtarını tutar; `session()` geri alınmış anahtarın oturumunu reddeder; `revoke-passkey` oturumlarını bitirir; yeni komut `kutuphane curator end-sessions <user>`. Testler: `test_revoking_a_passkey_ends_its_sessions`, `test_a_session_of_a_revoked_passkey_is_refused`, `test_end_sessions_of_a_person`.
- **Düşük, kayıt oturumu kendi koduna bağlı değildi (bulgu 5):** `curator_session.enrollment` (yabancı anahtar; `login = 'enrollment'` için zorunlu) kaydı oturumun kendi koduna bağlar; `curator_enrollment.cancelled_at` ve `kutuphane curator cancel-enrollment` eklendi. Testler: `test_an_enrollment_session_registers_for_its_own_code`, `test_cancelling_an_enrollment_ends_its_session`.
- **Düşük, dağıtım yoklaması Docker kapsayıcıları görmeyince geçiyordu (bulgu 6):** `deploy/curator_probe.py` artık dönüş kodlarını ve kapsayıcıların varlığını (`docker inspect`) denetler, boş Funnel çıktısında başarısız olur ve Core'dan erişilemezliği yalnız DNS ya da bağlantı hatasında kabul eder. Testler: `test_the_probe_fails_when_docker_cannot_see_the_containers`, `test_the_probe_passes_a_good_deployment`.

# Güvenlik incelemesi #17 (yerel inceleme)

Ham inceleme: `docs/research/2026-10-27-review-17-raw.md`. Kapsam: küratör dilimleri R, D ve Q (#117). İnceleyici yalnız kodu okudu; burada her bulgu (1–7) için önce `_test` adlı geçici veritabanında, gerçek veritabanı rolleriyle (`kutuphane_decider`, `kutuphane_curator_web`) başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Göç: `029_curator_review17.sql`. Testler `tests/test_curator_review17.py` içindedir.

- **Orta–Yüksek, örneklemeyi veritabanı karar çalıştırıcısına karşı uygulamıyordu (bulgu 1):** çalıştırıcı rolü kullanımın `seq`, `at` ve `sampled` sütunlarını ve önerinin `seq`, `at` sütunlarını yazabiliyordu; çekiliş her denemede yeniydi (geri alıp yeniden denemek örneklemi düşürüyordu); zorunlu örneğe zararsız bir not seçebiliyordu. Şimdi rol yalnız sütun düzeyinde `INSERT` hakkı tutar (bu üç sütun yok) ve tetikleyiciler `seq` ile `at` değerini kendisi verir. Çekiliş, `(yetkilendirme, not)` için gizli bir anahtarla HMAC'tir (`delegation_sample_key`, yalnız sahip okur; hesap `SECURITY DEFINER` tetikleyicide), yani aynı not için hep aynıdır. Kullanım yalnız sınıfın en eski uygun notu için kabul edilir (`delegation_next`, atlama yok); öneri kullanımdan önce kaydedilmiş olmalıdır (`xmin`, kayıt noktası için `at`); yaratıcının `curate` hakkı ve çalıştırıcının yazarlığı tetikleyicide denetlenir; bir Standing olayından sonra öneri yazılamaz, bu yüzden geç bir öneri gölge kanıtı sayılmaz. Testler: `test_a_rollback_and_retry_gives_the_same_draw`, `test_a_cherry_picked_note_for_the_forced_sample_is_refused`, `test_the_runner_role_cannot_set_seq_at_or_sampled`, `test_a_fake_late_suggestion_is_no_shadow_evidence`, `test_a_use_needs_a_suggestion_committed_before_it`, `test_the_trigger_checks_the_creator_right_and_the_runner_authorship`.
- **Orta–Düşük, başka bir kişi canlı bir onayın yerine geçebiliyordu (bulgu 2):** R7'ye göre yalnız onaylayan geri çeker. Şimdi canlı bir onay varken başka bir kişi onaylayamaz: sayfa seçenek göstermez, eylem 403 döner ve `origin_confirmation_by_confirmer` tetikleyicisi satırı reddeder. Aynı baytları yeniden önererek açılan yeni istek de bir yol değildir. Testler: `test_another_person_cannot_replace_a_live_confirmation`, `test_a_new_request_is_no_path_to_take_over_a_live_confirmation`.
- **Düşük, onay sayfası okuma hakkı olmayan kişiye notun varlığını gösteriyordu (bulgu 3):** sayfa ve `confirm`/`withdraw` seçenekleri artık ayrıştırılan başvurunun kitabında doğrudan `read` hakkını aramadan önce denetler; her durum için tek ret (403, aynı ileti). Test: `test_a_person_without_read_gets_one_refusal_for_every_note_state`.
- **Düşük, karar çalıştırıcısı her model çağrısından önce metin kapısını yeniden denetlemiyordu (bulgu 4):** şimdi her nottan hemen önce not kapıdan yeniden okunur; kapıyı geçmeyen not gönderilmez (`closed_meanwhile`). Test: `test_the_text_gate_is_checked_again_before_each_model_call`.
- **Düşük (sıkılaştırma), çalıştırıcı rolü bütün not metinlerini okuyabiliyordu (bulgu 5):** rolün `note` üzerinde `SELECT` hakkı yok. Metni yalnız `decider_notes()` (`SECURITY DEFINER`) verir: `agent:kutuphane-decider` için doğrudan `read` verilmiş kitaplar ve canlı yetkilendirmelerin kitapları, `ai_input` ve beceri engeli kapısıyla. Test: `test_the_decider_role_reads_note_text_only_through_the_gate`.
- **Bilgi, `delegation_end` eylemine bağlı değildi (bulgu 6):** `act_action` (`end_delegation`) ve `(act, ended_by)` anahtarları eklendi. Test: `test_a_delegation_end_is_bound_to_its_end_delegation_act`.
- **Bilgi, küçük boşluklar (bulgu 7):** `KUTUPHANE_DELEGATION_MIN_SHADOW` en az 1 olan bir tam sayı olmalıdır; curator web başka bir değerle başlamaz (`test_a_bad_shadow_minimum_stops_curator_web_at_start`). Onay imza sayfası artık saklanan bildirimden `claim` ve `entered_by` gösterir (`test_confirm_e2e.py`). `spec_sha256` artık çalıştırıcının istem ve yanıt kodunun özetini (`runner_code`) içerir; bu kodda bir değişiklik yeni bir spektir (`test_a_change_to_the_prompt_code_changes_the_spec`).
- **Kalan sınır:** ele geçirilmiş bir çalıştırıcı önerilerin değerini ve zamanını hâlâ seçer, yani hangi notların uygun olacağını etkileyebilir; ama bir çekilişi kullanımdan önce göremez ve geri alamaz.

# Güvenlik incelemesi #18 (yerel inceleme)

Ham inceleme: `docs/research/2026-10-27-review-18-raw.md`. Kapsam: #118 (parçalayıcı 5), #122 ve #123 (MCP Skills, `handling.py`). İnceleyici yalnız kodu okudu; burada her bulgu (1–8) için önce `_test` adlı geçici veritabanında eski kodda başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Göç: `033_skill_frontmatter.sql`. Testler `tests/test_mcp_skills.py` ve `tests/test_search.py` içindedir.

- **Orta, not etiketleri okunamayan kitapları adlandırıyordu (bulgu 1):** `_meta.kutuphane/handling.books` bir notun bütün `source_books` kümesini politikasıyla veriyordu. Şimdi yalnız çağıranın son okuma kümesindeki kitaplar adlandırılır (`query_notes` ve `open_note` bu kümeyi `readable_out` ile verir); okunamayan kaynak kitaplar yalnız `unnamed_sources` sayısında görünür ve `sensitivity`/`egress` değerini yine sıkılaştırır. Test: `test_a_note_label_never_names_a_source_book_the_caller_cannot_read`.
- **Orta (erişilebilirlik), parçalayıcı düzenli ifadesi üstel geri izliyordu (bulgu 2):** `(?:\s*<!--.*?-->)+\s*` 40 bitişik yorumla bitmiyordu. Düzenli ifade kaldırıldı; yorumlar tek geçişte `str.find` ile bulunur (doğrusal). Test: `test_adjacent_comments_split_in_bounded_time` (1 saniyeden kısa; eski kod 30 saniyede bitmedi).
- **Düşük, içerik kimliği işlemden önce alınıyordu (bulgu 3):** `gate.guard` artık `content_of` alır; olaylar ve etiketler sunulan sürümün kimliğini taşır. Test: `test_events_and_labels_name_the_version_served`.
- **Düşük, `fetch` içindeki retler kaydedilmiyordu (bulgu 4):** `guard`, `fetch` içinden gelen `Denied` ve `NotFound` için her kip için gerekçeli bir ret olayı yazar ve hatayı yeniden yükseltir. Test: `test_refusals_inside_the_fetch_are_logged`.
- **Düşük (sıkılaştırma), gizli markdown yorumları pasajlara giriyordu (bulgu 5):** karar: kod çiti dışındaki her HTML yorumunun karakterleri boşlukla değiştirilir (satır sonları kalır, konumlar ve satır numaraları değişmez); yalnız yorumdan oluşan blok pasaj olmaz. G28 amacı korunur: dosyanın ilk içeriği olan, tek satırlık, en çok 500 karakterlik `<!-- source: … -->` yorumu bir alıntıdır, talimat değildir; kural pasajında kalır. Başka her yorum (`source:` olsa da) gizlenir. Testler: `test_markdown_comments_are_in_no_passage`, `test_only_a_short_leading_source_comment_stays`.
- **Düşük (bilgi), etkin ortam türleri olduğu gibi gidiyordu (bulgu 6):** `skill://` okumasında HTML, JavaScript, SVG ve XML `text/plain` (UTF-8 değilse `application/octet-stream`) olarak gider; baytlar ve özet değişmez. Test: `test_active_media_types_are_sent_as_plain_text`.
- **Düşük (DoS), her skills çağrısı bütün `SKILL.md` dosyalarını ayrıştırıyordu (bulgu 7):** doğrulanmış ön bilgi yayında `skill_frontmatter` tablosuna yazılır (göç 033'ten önceki bir sürüm ilk çağrıda bir kez dizinlenir); `get`/`read` yalnız istenen yolu tutan becerilere bakar. Test: `test_skills_calls_never_parse_a_skill_md`.
- **Düşük, `read_document` bütün beceri kuralını uygulamıyordu (bulgu 8):** beceri klasöründeki bir dosya artık en içteki becerisinin tamamını temsil eder: alt klasördeki engelli beceri reddeder ve model okuyucu için `ai_input` becerinin her dosyasında denetlenir. Testler: `test_read_document_applies_the_whole_skill_rule`, `test_read_document_checks_ai_input_for_the_whole_skill`.
- **Yeniden dizinleme etkisi:** ana veritabanındaki güncel kitapların markdown pasajları salt okunur karşılaştırıldı: 2.787 pasajdan hiçbiri değişmedi (inframedic-canon 585, radar-docs 2.199, ornek 3; yorumlu 13 dosyanın hepsi baştaki kaynak yorumudur). Bu yüzden parçalayıcı sürümü 5 kalır; yeniden yükleme gerekmez.

# Astra incelemesi #19 (PR #111–#129) ve düzeltmeler

Ham inceleme: `docs/research/2026-10-28-astra-review-19-raw.md`. Kapsam: `355b1c7..3a5a4c4` (geçiş anahtarları, eylemler, yetkilendirme, onay; MCP Skills; datascan; içe aktarma; G23 kayıt alıntıları). Dört bulgunun dördü de orta düzeydir. Her bulgu için önce `_test` adlı geçici veritabanında, dağıtımdaki rol haklarıyla, `origin/main` üzerinde başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Göçler: `038_function_search_path.sql`, `039_note_parts_at_creation.sql`. Testler `tests/test_astra_review19.py` içindedir.

- **Orta, #120'nin gölge kanıt koruması atlatılabiliyordu (bulgu 1):** `note_suggestion_check()` sabit bir `search_path` taşımıyordu ve `standing_event` ile `memory_seq` adlarını şemasız kullanıyordu. PostgreSQL, yolda adı geçmeyen geçici şemaya önce bakar; varsayılan TEMP hakkıyla karar çalıştırıcısı rolü boş bir geçici `standing_event` ve negatif sayı veren bir geçici `memory_seq` yaratıp bir insan kararından sonra yazılan öneriyi erken bir sıra numarasıyla "gölge kanıt" olarak kaydedebiliyordu. Düzeltme yalnız bu fonksiyonla sınırlı değildir: göç 016–037'deki 16 fonksiyon ve tetikleyici fonksiyonunun hepsi (uygulama, curator web ve karar rollerinin ulaştıkları) `SET search_path = pg_catalog, public, pg_temp` ile yeniden yazıldı ve her tablo, dizi, tür ve fonksiyon `public.` ile adlandırıldı. `pg_temp` yolda açıkça son sıradadır; adı geçmeseydi PostgreSQL tabloları yine önce orada arardı, bu yüzden yalnız `pg_catalog, public` yazmak yetmez. Ek savunma: üç rol betiği TEMP hakkını `PUBLIC`'ten ve kendi rolünden alır. Testler: `test_every_function_of_ours_pins_its_search_path` (katalog denetimi; eklenti fonksiyonları hariç), `test_no_login_role_makes_temporary_objects`, `test_a_temporary_shadow_cannot_fake_shadow_evidence` (TEMP hakkı geri verilse bile gölge tablo ve dizi işe yaramaz).
- **Orta, imzalı onay notun kanonik içeriği değişince geçerli kalıyordu (bulgu 2):** uygulama rolü `UPDATE`/`DELETE` tutmaz ama `INSERT` tutar; onaylanmış bir nota sonradan bir atıf ya da özgün oluşturma yazımına bağlı bir oluşturma bağlantısı ekleyebiliyordu. Kanonik özet değişiyor, gösterilen köken `human` kalıyordu; `verify-acts` bunu görmüyordu. Karar (seçenekler arasından): **önce önleme**. Atıflar ve oluşturma bağlantıları kanonik gövdenin, yani not kimliğinin parçasıdır (docs/24 §3, §6.3: "yalnız oluşturma bağlantıları kendi bağlantılardır"); bu yüzden onları notla aynı işleme bağlamak docs/24 ile tutarlıdır. Göç 039, `note.written_xact` sütununu (notu yazan üst düzey işlem kimliği, `xid8`; yazanın değil tetikleyicinin verdiği) ekler ve `note_citation` ile oluşturma `note_link` eklemelerini yalnız aynı işlemde (bir kayıt noktası içinden de) kabul eder; sonraki bağlantılar (`creation = false`) serbesttir. Ayrıca okumada savunma (039'dan önce yazılmış satırlar için): onay ve kabul, notun saklı parçaları imzalanan kimliği verdiği sürece geçerlidir. `origin.shown()` (dolayısıyla karar dışa aktarımı ve not okuyucular) uyuşmazlıkta `model` gösterir; telefonla imzalanmış bir onay (`standing_event.act`) `notes.effective_standing` içinde `pending` sayılır; `curator verify-acts` uyuşmazlığı `contents` sorunu olarak raporlar. Kanonik gövde hesabı `canonical.py` modülüne taşındı (`intact()` toplu denetim). Testler: `test_a_confirmed_note_gains_no_citation_or_creation_link_later`, `test_a_part_added_before_039_voids_the_confirmation_and_the_approval`, `test_parts_written_with_the_note_in_a_savepoint_are_accepted`.
- **Orta, `quoted_records` arama sonucunun ortak yetki kararını bozuyordu (bulgu 3):** getirme son yetki kararını verdikten sonra alıntı araması ayrı bir okuma kararı veriyordu; arada A'nın hakkı geri alınıp B'nin hakkı verilirse yanıt A'nın metnini ve B'nin kayıt tutamacını birlikte taşıyordu. Şimdi `quotes.quoted` isabetleri ve adlandırdığı kayıtları `search.authorize` ile TEK son deyimde yeniden karara bağlar (birleşik havuz, inceleme #12'deki gibi): kaybedilen bir kitabın pasajları ve ona giden işaretçiler düşer, kayıp günlüğe yazılır, adlandırılan her kayıt kitabı için bir `access_event` (eylem `quote`, öğeler = tutamaçlar) yazılır. `ask` aynı adımı model çağrısından önce kullanır (kendi kaynaklarını son kapısında günlüğe yazar). Testler: `test_search_never_hands_out_a_passage_with_a_record_not_readable_at_the_same_time`, `test_ask_never_sends_a_passage_with_a_record_not_readable_at_the_same_time` (eski kod modeli çağırıyor, sonra `Denied` veriyordu), `test_named_records_are_in_the_delivery_audit`.
- **Orta, paket onayı kişisel veri bulut kapısını atlıyordu (bulgu 4):** `check_personal_data()` yalnız `cmd_ingest` içinde çalışıyordu; `approve-import` sıradan bir müşteri e-postası olan paketi `cloud_ok` olarak yayımlayabiliyordu. Şimdi kapı ortak yayın noktasındadır (`catalog.publish`, herhangi bir yazmadan önce); her yayın yolu onu uygular ve `cmd_ingest` içindeki ayrı çağrı kaldırıldı. `receive` her açık bulguyu `personal_data` bulgusu olarak listeler (yol, dosya özeti, kural, satırlar; eşleşen metin asla). `approve-import --accept-finding '<yol>@sha256:<özet>:<kural>'` alır; her kabul paketin bir bulgusuyla eşleşmelidir. Ret, içe aktarmanın gerekçelerine yazılır ve onay yeniden denenebilir. Testler: `test_package_review_lists_the_personal_data_findings`, `test_a_cloud_approval_needs_the_acceptance_of_each_finding`, `test_a_local_approval_records_the_findings`.
- **Kalan sınır:** sahip rolü (KUTUPHANE_CURATOR_DSN) tetikleyicileri kapatabilir; bu yüzden okuma denetimleri ve `verify-acts` kalır. Bir `cloud_ok` kitabının paketi için `--deny-names` (ad listesi) onay aşamasında yoktur; paket alımı ad listesiyle taramaz.

# Astra incelemesi #20 (PR #130–#147) ve düzeltmeler

Ham inceleme: `docs/research/2026-10-29-astra-review-20-raw.md`. Kapsam: `0323569..origin/main` (#145 HTTP/MCP üzerinden paketler ve `license: unknown`; #146 pasaj haritası; #147 `/v1/health` ve yeniden başlatma; #130 göç 038/039; #135 curator web; #131 reranker rotası). Dört bulgunun dördü de orta düzeydir ve dördü de geçerlidir. Her bulgu için önce `_test` adlı geçici veritabanında `origin/main` üzerinde başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Göç: `044_passage_map_overlap.sql`. #147, #130, #135 ve #131 için bulgu yoktur.

- **Orta, `propose` hakkı alıcı kataloğun dosyalarını gösteriyordu (bulgu 1):** paket gönderen, `read` hakkı olmadan, `diff.removed` içinde alıcı kitabın paket dışında kalan dosya adlarını görüyordu; `diff.changed` ise içerik eşitliği için bir kâhindi. Şimdi `packages.status` (gönderim yanıtı ve durum okuması) `diff` alanını yalnız kitap üzerinde güncel bir `read` kararıyla verir; yoksa `null` olur. Test: `test_propose_without_read_gets_no_catalog_diff`.
- **Orta, lisans bildirimi okunamayan ataların yollarını söylüyordu (bulgu 2):** okunabilen bir nottan türeten çağıran, notun kaynak kitabını okuyamasa da `licence_notice.paths` içinde o kitabın `kitap/yol` adını alıyordu. Şimdi bildirim son yetki kararıyla süzülür: okunamayan kitaptaki yol adlandırılmaz, `unreadable` yalnız sayısını verir; dışa aktarma yasağı aynen kalır. Test: `test_the_notice_never_names_a_file_the_caller_cannot_read`.
- **Orta, sözcük örtüşmesi anlamı değişen pasajı ardıl yapıyordu (bulgu 3):** "enable" yerine "disable" yazılan bir pasaj sözcük çiftlerinin çoğunu tuttuğu için `overlap` eşleşmesi alıyor, `neighbours` eski notun kenarını çelişen pasaja bağlıyordu. Karar: içerik sürümü aynıysa (yalnız profil değişti, metin aynı, farklı kesildi) kural eskisi gibidir; içerik değiştiyse `overlap` için ardıl pasaj eski metnin tamamını tutmalıdır. Aksi halde atıf `stale` olur ve hiçbir şey düşmez. Göç 044 eski kuralla yazılmış içerik değişimli `overlap` satırlarını siler; `kutuphane reindex-map <kitap>` onları yeni kuralla yeniden yazar. Ana veritabanında salt okunur sayım: içerik değişimli 6 `overlap` satırının 6'sı yeni kuralla da `overlap` kalır. Testler: `test_a_changed_content_version_maps_by_overlap_only_when_the_old_text_is_whole`, `test_a_changed_word_in_a_new_content_version_leaves_the_citation_stale`.
- **Orta, yayınla yarış yanlış ardıl tutamacı üretiyordu (bulgu 4):** `resolve()` güncel sürümü (V2) okuduktan sonra `_stored()` canlı `book` satırıyla birleşiyordu; arada V3 yayımlanırsa V3'ün sıra numarası V2'nin kimlikleriyle birleşiyordu. Şimdi `_stored()` yalnız çağıranın okuduğu hedef sürümün satırlarını okur. Test: `test_resolve_reads_the_map_of_the_version_it_read_not_the_live_row`.

# Astra incelemesi #21 (PR #148–#174) ve düzeltmeler

Ham inceleme: `docs/research/2026-11-01-astra-review-21-raw.md`. Kapsam: `75dd9c7..origin/main` (#167, #169, #171, #172, #173, #174; ayrıca #148 ve #149). Üç bulgunun üçü de orta düzeydir ve üçü de geçerlidir. Her bulgu için önce `_test` adlı geçici veritabanında `origin/main` üzerinde başarısız olan bir test yazıldı, sonra düzeltme yapıldı. Göç: `048_passage_map_operators.sql`. #167, #169, #172, #173 ve #174 için bulgu yoktur.

- **Orta, göç 047 yükseltme sırasında yazılan geri bildirimi silebiliyordu (bulgu 1):** eski sunucu `runbook_feedback` tablosuna henüz kaydedilmemiş bir satır yazarken göç tabloyu boş görüyor, `DROP` kilidi için bekliyor ve satır kaydedildikten sonra tabloyu siliyordu. Şimdi 047, boşluk denetiminden önce tabloyu `ACCESS EXCLUSIVE` kipinde kilitler. Uygulanmış bir göç değişti; değişiklik yalnız henüz 047'yi uygulamamış veritabanlarını etkiler, uygulanmış olanlarda sonuç aynıdır. Test: `test_047_keeps_runbook_feedback_that_an_old_server_commits_during_the_upgrade`.
- **Orta, işleç değişen pasaj ardıl kalıyordu (bulgu 2, #149):** içerik değiştiğinde `overlap` için "eski metnin tamamı" denetimi büyük/küçük harfi ve işleçleri atıyordu; `retries >= 3` ile `retries <= 3` aynı sayılıyor, atıf `stale` yerine `moved` görünüyordu. Şimdi denetim sözcükleri, işleç ve noktalama dizilerini harf durumuyla birlikte karşılaştırır. Göç 048 eski kuralla yazılmış içerik değişimli `overlap` satırlarını siler; `kutuphane reindex-map <kitap>` onları yeniden yazar. Ana veritabanında salt okunur sayım: içerik değişimli 6 `overlap` satırının 6'sı yeni kuralla aynı yanıtı verir. Test: `test_a_changed_operator_or_case_in_a_new_content_version_is_not_an_overlap`.
- **Orta, onay kartı sınırlı kuralı "her yerde" diye gösteriyordu (bulgu 3, #171):** `scope` olmayan ama `applies_to` sınırı olan bir kural kartta "Applies everywhere (no scope)." diyordu; sınır yalnız kapalı Details içindeydi. Şimdi kart (kuyruk ve köken onayı) sınırı gösterir ("Applies to vcenter; version >=7,<8.") ve "everywhere" yalnız iki sınır da yoksa yazılır; `appliesTo` tek kopya olarak `core.js` içindedir. Test: `test_a_person_logs_in_with_a_passkey_and_batch_approves_a_same_as_group`.

# Astra incelemesi #22 (PR #179–#185) ve düzeltmeler

Ham inceleme: `docs/research/2026-11-02-astra-review-22-raw.md`. Kapsam: `ea9edb1..origin/main` (#179, #180, #182, #183, #184, #185). Beş bulgunun beşi de geçerlidir (iki yüksek, iki orta, bir düşük). Her bulgu için önce `_test` adlı geçici veritabanında `origin/main` üzerinde başarısız olan bir test yazıldı (`tests/test_astra_review22.py`, 13 test), sonra düzeltme yapıldı. Göç: `050_d73_history_only.sql`. #180 (göç 049, yalnız sıkılaştırma kuralı, D68, saat, küratör yarışı, cron), #182 (iki compose dosyası) ve #185'in köken okuması ile silinen işlevleri için bulgu yoktur.

- **Yüksek, kaldırılan karar verici rolü haklarını koruyordu (bulgu 1, #179):** `deploy/db-roles-decider.sql` silindi ama kurulu `kutuphane_decider` rolünün hakları geri alınmadı; rol öneri ve devredilmiş kullanım yazabiliyor, 025'in `SECURITY DEFINER` tetikleyicisi canlı bir devirde notu onaylıyordu. Şimdi göç 050, D73 tablolarına (`note_suggestion`, `curate_delegation`, `delegation_use`, `delegation_end`) her ekleme, değişiklik ve silmeyi reddeder, `decider_notes()` ile `delegation_next()` işlevlerini siler ve rol varsa tüm haklarını geri alır. Testler: `test_d73_tables_take_no_new_rows`, `test_decider_functions_are_dropped`.
- **Yüksek, dışa aktarım sırasında kısıtlanan kaynak sızabiliyordu (bulgu 2, #183/#184):** kısıtlı kaynak süzgeci yalnız iş adımında çalışıyordu; son karardan önce bir kaynak kitap (ya da günlüğün kendisi) `restricted` olursa notları dışarı çıkıyordu. Şimdi ortak `decisions.rights` son karar içinde kaynakları yeniden denetler, `journalexport._finish` günlüğün duyarlılığını da denetler; biri kısıtlıysa dışa aktarımın tamamı reddedilir (hiçbir şey verilmez, yeniden çalıştırılır). Karar dışa aktarımı da aynı kuralı alır. Testler: `test_journal_export_refused_when_a_source_becomes_restricted`, `test_journal_export_refused_when_the_journal_becomes_restricted`, `test_decision_export_refused_when_a_source_becomes_restricted`.
- **Orta, eski devir eylemleri doğrulanamıyordu (bulgu 3, #179):** `verify-acts`, saklı `delegate` ve `end_delegation` eylemleri için "no effect check" veriyordu. Şimdi iki salt okunur etki denetimi `passkey.EFFECTS` içindedir; `ACTIONS` onları yeniden sunmaz. Test: `test_historical_delegation_acts_have_effect_checks`.
- **Orta, denetim karakterli yol açılamayan pasaj üretiyordu (bulgu 4, #185):** sıkı tutamak ayrıştırıcısı sekme ve satır sonunu reddederken alım bu yolları kabul ediyordu. Şimdi `source.read_file` denetim karakterli yolu reddeder; kural tek kopya olarak `ids.CONTROL` içindedir (`notes`, `coderepo` onu kullanır). Ana veritabanında böyle bir yol varsa onun pasajları açılamaz; bu salt okunur sorgu ile bakılır: `SELECT count(*) FROM chunk WHERE path ~ '[[:cntrl:]]'`. Test: `test_control_character_path_is_refused`.
- **Düşük, eski model onayları "system" sayılıyordu (bulgu 5, #179):** `curator report` içinde `model:…` onayları `system` altına düşüyordu; sistem yalnız sıkılaştırır (R1). Şimdi `decided_by.delegations` geri geldi. Test: `test_report_keeps_delegated_approvals_apart`.
