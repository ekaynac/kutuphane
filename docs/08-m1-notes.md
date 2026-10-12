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
