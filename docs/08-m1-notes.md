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
