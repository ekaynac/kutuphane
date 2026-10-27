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
