**PR #24 için düzeltme gerekiyor.** Doğrudan yetki atlaması veya anahtar sızıntısı bulmadım; vektör doğrulaması, LLMDAP etiket uyumu ve ölçüm güvenilirliğinde sorunlar var. Dosya değiştirmedim; ağ/veritabanı kullanmadım. Testleri çalıştırmadım; kodlarını inceledim ve dört sınır durumunu yalnız bellekte doğruladım. LLMDAP okumaları `git show origin/main:…` ile yapıldı.

**1. Güvenlik**

- **Orta — PR #22’nin kayıtlı ret düzeltmesi eksik.** [`packages.py:112`](/home/mega/kobra/src/kutuphane/packages.py:112) alan türlerini denetliyor; PostgreSQL’in kabul etmediği değerleri denetlemiyor. Kanonik manifestte `issuer="bad\u0000issuer"` → tür kontrolünü geçer → 127’de sorgu parametresi hatası → `PackageError` olmadığı için kayıtlı ret oluşmaz. Geçerli imzalı pakette `sequence=2**63` de 201’de `bigint` sınırına çarpar. Bellekte doğrulayıcının ikisini kabul ettiğini doğruladım. **Düzeltme:** metinlerde NUL, sıra için `1..2**63-1` kontrolü; bu durumları ret testlerine ekleme.

- **Orta — geçerli Core principal’ı LLMDAP’ta reddediliyor.** [`llmdap.py:122`](/home/mega/kobra/src/kutuphane/llmdap.py:122) principal’ı doğrudan etikete koyuyor. [`authz.py:15`](/home/mega/kobra/src/kutuphane/authz.py:15) `user:` + 124 karakteri kabul ediyor: toplam 129. LLMDAP `src/adapters/audit/chain.ts:44` etiketi en çok 128 karakter kabul ediyor; `bridge/attribution.ts` ihlalde 400 üretiyor. Sonuç: embedding FTS’e düşer, cevap üretimi 502 olur. **Düzeltme:** sınırlı, çakışmasız etiket eşlemesi veya uyumlu principal sınırı; sahte bridge’e aynı gramer. ASCII olmayan principal, mevcut HTTP/MCP kimlik doğrulamasında zaten reddediliyor; buradan yeni Unicode açığı çıkmıyor.

Vektör yolunda okunamayan kitap, etkinleştirilmemiş K3, eski içerik ve başka profil için **bulgu yok**: [`search.py:55`](/home/mega/kobra/src/kutuphane/search.py:55) filtresi iki sıralamada da uygulanıyor. Sıra ve puanlar filtrelenmiş adaylardan hesaplanıyor. SQL enjeksiyonu için de **bulgu yok**: f-string yalnız sabit SQL parçasını ekliyor; vektör dahil değerler parametreli.

İndeksleme `source_books=[book]` gönderiyor; doğru rota sınıflandırması altında `local_only` kitap buluta çıkamıyor. Sorgu ise [`vectors.py:48`](/home/mega/kobra/src/kutuphane/vectors.py:48) üzerinden boş kaynak listesiyle buluta gidebilir. Bu, kitap içeriğinin otomatik aktarılması değildir; fakat kullanıcı yerel belgeden metin yapıştırırsa kitap politikası onu korumaz. Sorgu gizliliği de bekleniyorsa yerel embedding rotası gerekir.

Bearer yalnız başlıkta; `model_call` ve normal hata yollarında anahtar yok, yönlendirmeler izlenmiyor. Bu yollarda sızıntı **bulgusu yok**.

**2. Doğruluk**

- **Orta — embedding doğrulaması yanlış eşlemeyi ve arama hatasını engellemiyor.** [`llmdap.py:161`](/home/mega/kobra/src/kutuphane/llmdap.py:161) yalnız sıralama, adet ve parti içi boyut eşitliğine bakıyor. İki girdiye iki `index=0` yanıtı kabul ediliyor; yanlış vektör kalıcı parçaya bağlanabilir. `NaN` ve boş vektör de geçiyor. Ayrıca [`010_vector.sql:14`](/home/mega/kobra/src/kutuphane/migrations/010_vector.sql:14) boyutsuz: aynı modelin eski 1024 ve yeni 768 boyutlu vektörleri saklanabilir. Sonraki kosinüs sorgusu hata verir; [`vectors.py:49`](/home/mega/kobra/src/kutuphane/vectors.py:49) yalnız embedding çağrısındaki `EgressError`’ı yakaladığından FTS’e düşmez. **Düzeltme:** indekslerin tam `0..n-1` kümesi olduğunu, sonlu/sıfır olmayan vektörleri ve model boyutunu doğrula; uyumsuz sorguyu SQL’den önce FTS’e düşür.

- **Orta — M0 önbelleği yanlış sonuç ve revizyon bildirebilir.** [`eval_models.py:140`](/home/mega/kobra/experiments/retrieval/eval_models.py:140), 169 ve 179’da anahtar yalnız model adı/cihaz. Aynı çıktı dizininde soru sırası, korpus, şablon veya `--rerank-every` değişirse eski diziler yeni sorularla puanlanıyor. Yeni indirilen revizyon, eski vektörlerin revizyonuymuş gibi raporlanabilir. **Düzeltme:** girdi, parametre ve sabit model revizyonu özetlerini önbellekte saklayıp uyuşmazlıkta yeniden hesapla.

- **Orta — M0 başka profillerin parçalarını karıştırıyor.** [`eval_models.py:68`](/home/mega/kobra/experiments/retrieval/eval_models.py:68), 75’te `current_profile` filtresi yok. Aynı içerik önce `whole`, sonra `chunked` yayımlanırsa dense korpus ikisini içerir; `(path, ordinal)` haritası çakışır, ürünün FTS sonucuna yanlış metin atanabilir. **Düzeltme:** güncel profil filtresi ve profil içeren parça anahtarı.

- **Düşük — eski oturumun 401’i yeni oturumu kapatabilir.** [`App.tsx:89`](/home/mega/kobra/web/src/App.tsx:89): A’nın bekleyen isteği → çıkış → B girişi → A’nın gecikmiş 401’i, üst bileşenin `onSignOut()` işlevini çağırır. İçerik sızıntısı kapanmış; yan etki kalmış. **Düzeltme:** çıkışı isteğin token’ı hâlâ etkinse uygula.

Yarım indekslemede yayın ve önceki tamamlanmış partiler kalır; `index` eksikleri tamamlayabilir. Tamamlanana kadar sıralama kısmi vektör kapsamasından etkilenir. `reopen` sabit kaynakları ve güncel yetkiyi kullandığından yeni tutarsızlık **bulgusu yok**.

RRF’nin pozitif puanı ilgililik eşiği değildir: alakasız sorgu da pasaj bulabilir; geçerli `[1]` tek başına anlamsal dayanak sağlamaz. Bu sınır `docs/08`’de açık olduğundan yeniden bulgu saymıyorum; AT-08 kapanmış değildir.

**3. Kabul testleri**

AT-04’ün FTS iptal yarışları, vektörün yetkisiz kitap/K3 testleri mevcut; vektörlü iptal yarışı, eski sürüm/profil ve puan değişmezliği ayrıca kanıtlanmıyor. AT-09 birleştirme ve eksik kayıt; AT-11 bozuk token, Bearer ve atıf başlığı için Core testleri var.

Sahte bridge kimlik bağlamayı ve embedding yolunu temsil ediyor; ancak etiket gramerini ve tam rota kabulünü uygulamıyor. AT-10/11’in canlı LLMDAP kısmı kanıtlanmış değil; belgeler bunu doğru açık bırakıyor.

**4. Sadelik**

Ortak `_post`, tek SQL ve tam vektör taraması D46’ya uygun. Yeni servis gerekmez; küçük doğrulamalar yeterli.

Model betiği `trust_remote_code=True` kullanmıyor, `np.load` pickle açmıyor. Ancak `.bin` indirmesine izin veriliyor; safetensors zorunluluğu ve sabit revizyon tekrarlanabilirliği güçlendirir. Ayrıca “sorgu başına” embedding süreleri batch=16 ortalamasıdır; tek istek gecikmesi olarak sunulmamalı.