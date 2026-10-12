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
- **Egress:** `llmdap.chat` → `POST /bridge/<route>/v1/chat/completions`; başlıklar `x-llmdap-auth` (paylaşılan
  sır; #223 ile OIDC'ye geçecek), `x-llmdap-user`, `x-llmdap-for-subject`, `x-llmdap-purpose`,
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
