**Ana görüşüm:** Ürünün ayrıştırıcı değeri, bilginin hangi sürümüne kimin adına ve neden erişildiğini açıklayabilmesi. Öneriler bunu güçlendiriyor; fakat M1’e federasyon, sır yönetimi ve model deneyleri birlikte yükleniyor.

Değerlendirmem verilen belgelere dayanıyor. Dış ürünlerin sürüm, lisans ve özellik iddiaları bağımsız doğrulanmış kabul edilmemeli.

**B1 — Ontoloji eksenleri**

**Görüş:** farklı öneriyorum: Dokuz boyut korunsun; dokuz kapalı katalog alanına dönüşmesin.  
**Gerekçe:** E3’te köken ve güven, E5’te hassasiyet ve egress ayrı nitelikler olmalı; kaynağın kimliği güvenilirliğini tek başına belirlemez. E2 sunum profilinde, E9 ise aktör–kaynak ilişkisindeki izin kümesinde yaşamalı.  
**Risk:** `discover/read/use` doğrusal bir yetki sırası değildir; `read` sahibi otomatik olarak `use` sahibi sayılmamalı.

**B2 — v1 kategorileri**

**Görüş:** farklı öneriyorum: K1–K3 ürün kapsamı; K4 yalnız mevcut okuma altyapısıyla karşılanabildiği ölçüde; K7 bağımsız deney hattı.  
**Gerekçe:** Kategoriler ayrı motorlar değil, ortak çekirdeğin hazır profilleri olsun. K5 kullanıcı ürünü ertelenebilir; fakat erişim ve geri bildirim kayıtları zaten çekirdekte gerekecek.  
**Risk:** “Şemada destekliyoruz” ifadesi, uygulanmamış davranış için ürün vaadine dönüşebilir.

**B3 — Kitap tanımı**

**Görüş:** eksik: İçerik, sunum profili ve politika için ayrı sürüm kimlikleri.  
**Gerekçe:** Bundle özeti içeriği sabitler; aynı içerik yeni ayrıştırıcıyla farklı parçalara dönüşebilir, erişim politikası da içerik değişmeden güncellenebilir. Atıf profil/parça kimliğini, erişim kaydı politika ve grant sürümünü de taşımalı.  
**Risk:** Eski cevabın kanıtlarını yeniden göstermek, modeli çalıştırıp birebir aynı cevabı üretmekle aynı taahhüt değildir.

**B4 — Master platform**

**Görüş:** katılıyorum ★  
**Gerekçe:** Aynı kod tabanı ve ayrı rol mantıklı; M1’de yalnız paket sözleşmesi yeterli. Kurulum kayıtları “son bildirilen durum” olarak sunulmalı.  
**Risk:** Offline kurulumun güncel durumu bilinemez; recall’ın uygulanması teslim ve yerel kabul zamanına bağlıdır.

**B5 — Delegasyon ve erişim**

**Görüş:** eksik: İptal, tutarlılık ve yetki daraltma sözleşmesi.  
**Gerekçe:** OpenFGA aday olarak kalsın; delegasyon, devredenin **güncel** yetkisiyle her kullanımda kesişsin. M1’de tek seviyeli, süreli, iptal edilebilir delegasyon yeterli; `purpose` alanı tek başına kullanım amacını zorlamaz.  
**Risk:** Arama ön filtresi yeterli değil; doğrudan okuma, önbellek, export ve sonuç teslimi de aynı yetki sınırına uymalı.

**B6 — Offline paketler**

**Görüş:** eksik: Güven kökü, anahtar yenileme ve eski paketi yeniden oynatma kuralları.  
**Gerekçe:** İmzalı zarf ve çift yönlü taşıma doğru. İlk anahtarın nasıl güvenilir sayıldığı, kayıp/iptal edilen anahtar ve eski recall/paketlerin sıralaması tanımlanmalı; import atomik olmalı.  
**Risk:** İmza içeriğin doğruluğunu veya güvenliğini kanıtlamaz; taşıma şifrelemesi başlık, manifest ve boyut sızıntılarını kendiliğinden kapatmaz.

**B7 — Karar modelleri**

**Görüş:** farklı öneriyorum: Önce tek karar noktası ve insan etiketli değerlendirme kümesi; Laya öncelikli, Jev karşılaştırması opsiyonel.  
**Gerekçe:** Ortak sözleşme ve shadow yaklaşımı doğru; eşzamanlı iki sağlayıcı M1 koşulu olmamalı. Olasılıkların anlamı, çekimserlik ve kalibrasyon görev bazında ölçülmeli.  
**Risk:** Jev etiketleriyle eğitilip Jev etiketleriyle değerlendirilen Laya, doğruluktan çok öğretmenine benzerliği ölçer.

**B8 — Retrieval yığını**

**Görüş:** farklı öneriyorum: Mimariyi kabul edelim, bileşen listesini ölçüm sonrası sabitleyelim.  
**Gerekçe:** Postgres üzerinde hibrit arama ve tek reranker yeterli başlangıç. Türkçe kurum korpusu, dar yetki filtreleri ve hedef donanımla küçük bir karşılaştırma yapılmalı; tam sürümlerin, model ağırlıklarının ve bağımlılıkların lisansları **doğrulanmalı**.  
**Risk:** Araştırmadaki “iteratif taramayla recall sorunu çözülür” ve sabit vektör sayısı eşikleri garanti kabul edilmemeli.

**B9 — M1 kapsamı**

**Görüş:** farklı öneriyorum: Tek uçtan uca kanıt senaryosu.  
**Gerekçe:** Bir OKF/MD kitabı ve metin PDF’si; bütün/parçalı sunum; insan ve ajan erişimi; tek seviyeli delegasyon; atıf, sürüm ve birleşik audit; asgari imzalı import/export yeterli. Runbook geri bildirimi basit kayıt olsun; shadow, DOCX/OCR çeşitliliği ve gelişmiş profil yönetimi ertelensin.  
**Risk:** D18’deki kimlik ve embedding kapıları korunmalı; kapsam küçültmek yönetişim iddiasını gevşetmemeli.

**B10 — Onyx’i temel almak**

**Görüş:** katılıyorum ★  
**Gerekçe:** Kütüphane’nin birincil nesnesi ve erişim sözleşmesi etrafında çekirdek kurmak daha tutarlı. Ancak “fork kesin daha pahalı” hükmü yerine bunu mimari tercih olarak kaydedelim.  
**Risk:** Onyx’in CE/EE sınırları ve OKF araçlarının uygunluğu **doğrulanmalı**; “doğrudan kullanılır” henüz fazla kesin.

**B11 — Gizli malzeme**

**Görüş:** farklı öneriyorum: M1’de model anahtarları LLMDAP’ta; Kütüphane yalnız referans, grant ve korelasyon kaydı tutsun.  
**Gerekçe:** OpenBao entegrasyonu, genel `sealed/use` ve kullanıcıya dönük `envelope/read` M2’ye taşınsın. Özellikle envelope içeriğinden üretilen metin, vektör ve önbelleklerin kim tarafından çözülebildiği belirlenmeden gizlilik sözleşmesi tamamlanmış olmaz.  
**Risk:** Hedef sınırlama ve birebir yankı maskeleme, “ajan sırrı asla öğrenemez” garantisi için yeterli değildir.

**Açık soru — LLMDAP#225 beklenirken Jev**

**Görüş:** farklı öneriyorum: Gerçek Jev çağrıları beklesin; sözleşme, fixture ve değerlendirme hazırlıkları ilerlesin.  
**Gerekçe:** “Experiment” etiketi D3’ün tek geçiş yolu ilkesini karşılamaz; D18 benzer geçici bypass’ı zaten reddetmiş. #225 ve güvenlik incelemesinden sonra Jev ile Laya aynı yönetişim altında ölçülsün.  
**Risk:** Geçici yol kalıcı ikinci entegrasyona dönüşebilir; bekleme ise M1’i engellememeli, çünkü shadow M1’den çıkarılabilir.

## Genel değerlendirme

- **B1–B3:** Kapalı ontoloji ile minimally opinionated hedefi gerilimli; zorunlu yönetişim kurallarıyla isteğe bağlı sınıflandırmayı ayırın.
- **B3–B5:** İçerik sürümünü sabitlemek eski erişim hakkını sabitlememeli; eski cevabı açarken güncel yetki denetlenmeli.
- **B4–B6:** Recall, yerel egemenlik ve çevrimdışı çalışma birlikte açık teslim/uygulama semantiği istiyor.
- **D9:** “Yeniden üretilebilir cevap” ifadesini, saklanan cevap ve kanıtların yeniden gösterilmesiyle sınırlandırın.
- **D4/D13:** Doküman sunmak, talimatı etkinleştirmek ve sırrı kullanarak işlem yapmak ayrı sınırlar olsun.
- **D14/D15:** Kimlik sağlayıcısı ile LLMDAP’ın doğrulayıcı rolünü netleştirin; ek servislerle offline kurulum, yedekleme ve anahtar kurtarmayı yeniden değerlendirin.
- **D7:** Sesli özet ve çoklu çıktı türlerini M1 dışında açıkça konumlandırın; deney platformu hedefi teslim kapsamını büyütmesin.
- **M1 kabulü:** Yetkisi iptal edilen ajan okuyamıyor; eski atıf doğru kaynağa açılıyor; offline paket taşınıyor; erişim ve egress aynı işlem üzerinden açıklanabiliyor.