`main` / `26f90af` üzerinde **altı yeni bulgu** var. Dosya değiştirmedim; ağa veya veritabanına erişmedim. Testleri kaynaklarından değerlendirdim; aşağıdaki iki hata yolunu ayrıca bellek içinde doğruladım. `docs/08`’de kapatılmış bulguları tekrarlamıyorum.

1. **Yüksek — Kullanıcı değişince önceki kullanıcının içeriği gösteriliyor.**  
   Kanıt: [App.tsx:80](/home/mega/kobra/web/src/App.tsx:80). `signOut()` yalnız token ve kimliği temizliyor; `answer`, `hits`, `passage`, soru ve cevap kimliği korunuyor.  
   **Senaryo:** Ayşe gizli cevabı/pasajı açar → çıkar → aynı sekmede yetkisiz Mehmet giriş yapar → Ayşe’nin içeriği yeni yetki kontrolü olmadan yeniden görünür. Bekleyen eski istekler de sonradan state’i doldurabilir.  
   **Düzeltme:** Oturum değişiminde içerik state’ini sıfırlayın; eski oturumun isteklerini iptal edin veya sonuçlarını oturum nesliyle geçersiz kılın.

2. **Yüksek — Paket onayı, anahtar iptaliyle atomik değil.**  
   Kanıt: [packages.py:110](/home/mega/kobra/src/kutuphane/packages.py:110), [packages.py:206](/home/mega/kobra/src/kutuphane/packages.py:206). Onay import ve sıra satırlarını kilitliyor, fakat `trusted_key` yalnız düz `SELECT` ile okunuyor. `docs/08`’deki “anahtar … satır kilidi altında” ifadesi karşılanmıyor.  
   **Senaryo:** Onay anahtarı geçerli okur → ikinci bağlantı `untrust` işlemini tamamlar → ilk bağlantı iptal edilmiş anahtarlı paketi yayımlar.  
   **Düzeltme:** Onay işleminde güvenilen anahtar satırını `FOR SHARE` ile kilitleyip iptalle sıralayın. İki bağlantılı, kontrollü bekletme kullanan test ekleyin.

3. **Orta — MCP hata gövdeleri iç ayrıntıları sızdırıyor.**  
   Kanıt: [server.py:273](/home/mega/kobra/src/kutuphane/server.py:273). HTTP’nin `_error` eşlemesi MCP araçlarında yok. Kurulu SDK araç istisnasını `ToolError(...{e})` yapıyor, protokol katmanı da bu metni istemciye döndürüyor.  
   **Senaryo:** Doğrulanmış kullanıcı araç çağırır → bağlantı/SQL hatası oluşur → sunucu, veritabanı veya sorgu ayrıntıları hata metninde açığa çıkar. Bellek içi denemede yerleştirdiğim `INTERNAL_MARKER database host /internal/path` aynen taşındı.  
   **Düzeltme:** MCP araçlarına ortak, küçük bir hata sınırı ekleyin; beklenen hataları güvenli mesaja, bilinmeyenleri genel hataya çevirip ayrıntıyı yalnız sunucuda kaydedin.

4. **Orta — Bazı bozuk paketler ve onay hataları ret kaydı bırakmıyor.**  
   Kanıt: [packages.py:108](/home/mega/kobra/src/kutuphane/packages.py:108), [packages.py:177](/home/mega/kobra/src/kutuphane/packages.py:177), [packages.py:218](/home/mega/kobra/src/kutuphane/packages.py:218). Yalnız `PackageError` yakalanıyor.  
   **Senaryo:** Geçerli biçim alanı yanında JSON `"\ud800"` içeren manifest → kanonikleştirmede `UnicodeEncodeError` → kayıt oluşturulmadan çıkış. Bunu veritabanına dokunmadan doğruladım. Ayrıca doğrulanmış uzun metni `whole` profiliyle onaylamak, profil sınırında `ValueError` üretip import’u gerekçesiz `verified` bırakabilir.  
   **Düzeltme:** Manifest türlerini/sınırlarını açıkça doğrulayın; ayrıştırma hatalarını paket hatasına dönüştürün. Onay rollback’inden sonra beklenen yayın hatalarını da kalıcı kaydedin.

5. **Orta — Paket boyut sınırı bellek ve karantina depolamasını sınırlamıyor.**  
   Kanıt: [cli.py:145](/home/mega/kobra/src/kutuphane/cli.py:145), [packages.py:178](/home/mega/kobra/src/kutuphane/packages.py:178). CLI önce dosyanın tamamını `read_bytes()` ile okuyor; fazla büyük bulunduğunda da ham paketin tamamı ret satırına yazılıyor.  
   **Senaryo:** Operatör çok büyük bir paketi `receive` eder → sınır kontrolünden önce bellek tükenebilir; kontrol geçilirse reddedilen veri veritabanını doldurabilir.  
   **Düzeltme:** En fazla limit+1 bayt okuyun; aşırı büyük girdiler için sınırlı metadata/ret kaydı tutun.

6. **Orta — AT-10 probu DNS izolasyonunu kanıtlamıyor.**  
   Kanıt: [egress_probe.py:16](/home/mega/kobra/deploy/egress_probe.py:16). `create_connection()` DNS çözümlemesiyle TCP bağlantısını tek sonuca indiriyor.  
   **Senaryo:** Dış DNS çözülür, ardından TCP bağlantısı engellenir → prob bunu tamamen engellenmiş sayıp yeşil döner. Sabit host adresleri de gerçek model hedeflerinin erişilemezliğini kanıtlamaz.  
   **Düzeltme:** DNS çözümlemesini ayrı sınayın; gerçek ağ geçidi/model hedeflerini yapılandırmadan alın. Bu bulgu canlı ağda kaçış doğrulaması değil, mevcut kanıtın eksikliğidir.

Kabul testlerine ilişkin değerlendirmem:

| Test | İddia kanıtlanıyor mu? |
|---|---|
| **AT-03** | Kısmen. [test_server.py:118](/home/mega/kobra/tests/test_server.py:118) MCP auth context’ini elle kuruyor; yalnız atıf listelerini karşılaştırıyor. Gerçek `/mcp` araç çağrısı ve iki yüzeyden pasaj çözümleme eksik. |
| **AT-10, ağ** | Hayır; bulgu 6 nedeniyle “ağ yarısı yeşil” fazla güçlü. |
| **AT-11, Core** | JWT birim testleri güçlü. HTTP/MCP uçlarında bütün bozuk-token matrisi yok; MCP testi yalnız kimliksiz/geçerli `initialize` deniyor. |
| **AT-13** | Taşıma, parmak izi, yenileme ve önceden iptal edilmiş anahtar kapsanıyor; onay sırasındaki iptal yarışı kapsanmıyor. |
| **AT-14** | Kurcalama, replay ve rollback için anlamlı testler var; bulgu 4’teki hatalar ve bulgu 2’deki yarış eksik. |
| **AT-15** | Sürüme bağlılık ve iptal rollback’i kanıtlanıyor; başarılı `failed` kaydı, zaman ve adına bağlamı assertion’ları eksik. |
| **AT-16** | Paylaşılan politika/grant sınırındaki doğrulamalar ve `purpose` kaydı için yeterli çekirdek kanıt var. |

HTTP kimlik atlatma; MCP kimlik/araç yetkisi ve stateless oturum düzeni; düz metin render/CSP, attachment teslimi, StaticFiles ve MCP DNS-rebinding ayarında **yeni bulgu yok**. Manifest dışı dosya, içerik-hash bağı, traversal/symlink reddi ve replay mantığında da bulgu yok. Sıra boşlukları monotonluk sözleşmesine uygun; göndericinin politika önerisi alıcının açık politikasını ezmiyor.

Dev token üretimi ortam bayrağıyla kapalı; üretimde kabulü seçilen JWKS belirliyor. Mevcut Docker kopyalama adımlarında somut sır sızıntısı bulmadım. Normalizasyon 4’te yeni doğruluk bulgusu yok; 80 karakterlik ölçüm yalnız retrieval göstergesi, AT-08 kanıtı değil.

D46 açısından yapı sade ve uygun. Bulgular yeni servis/framework gerektirmiyor; küçük hata sınırları, doğru kilit ve oturum temizliği yeterli.