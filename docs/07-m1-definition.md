# Kütüphane — M1 tanımı: uçtan uca kanıt senaryosu

Tarih: 2026-10-12. Durum: **onaylandı (D45).** Dayanak: D35 ve `04-…` §3. M1'in amacı ürünün
kamasını (§4, `05-product-brief.md`) **tek bir senaryoda, makinece doğrulanabilir** biçimde kanıtlamak;
özellik genişliği değil.

## 1. Senaryo

Örnekler niyeti anlatır; testler rolleri kullanır, isimleri değil.

1. **Küratör** bir OKF/MD kitabı (ör. bir iç politika seti) ve bir metin-katmanlı PDF (ör. bir mevzuat metni)
   içe aktarır. Her biri içerik, profil ve politika sürüm kimliği alır.
2. Kitaplar iki profille sunulur: **bütün** (ajan talimatları ve kısa metinler) ve **parçalı** (hibrit arama +
   rerank).
3. **Okur U**, arayüzde soru sorar; cevap tıklanabilir, sürümlü atıflarla gelir. Kütüphanede dayanak yoksa
   cevap "kütüphanede yok" der.
4. U, **ajan A**'ya bir kitabı 8 saatliğine `read` kipinde devreder. A, Kütüphane MCP üzerinden aynı kitaba
   erişir ve aynı sürüme atıf verir.
5. Küratör PDF'in yeni sürümünü yükler. U'nun dünkü cevabındaki atıf hâlâ **eski sürümdeki doğru pasajı** açar.
6. Yönetici U'nun kitap üzerindeki hakkını kaldırır. A'nın bir sonraki isteği; arama, doğrudan okuma, atıf açma
   ve export yollarının hepsinde reddedilir.
7. **Denetçi**, dünkü cevap için tek sorguyla şunu görür: kim, kimin adına, hangi sürüm ve parça, hangi politika
   kararı, hangi LLMDAP model çağrısı.
8. Küratör kitabı imzalı paket olarak export eder; paket USB ile ikinci kuruluma taşınır ve import edilir.
   Kurcalanmış ya da eski paket reddedilir.
9. Bir runbook'u uygulayan okur "işe yaradı / yaramadı / değişti" geri bildirimi bırakır; kayıt sürüme bağlıdır.

## 2. Kapsam

**İçinde:** OKF/MD ve metin-katmanlı PDF ingest; üç sürüm kimliği (D26); bütün + parçalı profil; hibrit arama
+ tek reranker (bileşenler M0'dan); sürümlü atıf; insan arayüzü (okuyucu + soru-cevap + atıf görünümü); HTTP API;
Kütüphane MCP; tek seviyeli, süreli, iptal edilebilir kullanıcı→ajan delegasyonu (D28); K3 etkinleştirme kapısı
(D37); zorunlu ontoloji alanları (D24); birleşik denetim (D35); imzalı paket import/export (D29); basit runbook geri bildirimi (D13); LLMDAP
üzerinden model ve embedding egress'i, IdP kimliği (D18, D38).

**Dışında (M2+):** `envelope`/`sealed` koruma, OpenBao (D33); çok seviyeli delegasyon, OpenFGA servisi (D28);
master federasyonu ve recall (D27, D40); karar modeli entegrasyonu (D30, D34); DOCX/OCR; gelişmiş profil
yönetimi; stüdyo çıktıları ve sesli özet (D39).

## 3. Mimari çerçeve (M1)

- **Yığın:** tek Python uygulaması (D46); CLI, HTTP API ve MCP aynı fonksiyonları çağırır. Arayüz React + TS
  (D15). Postgres + pgvector + tam metin (D11, D16). Tek kutu docker compose: Core + LLMDAP + Postgres + IdP
  (D15, D38). InfraMedic'ten kod değil fikir taşınır (D46). Mikroservis, Redis, kuyruk, plugin altyapısı yok.
- **Tek yetki kapısı.** Her okuma yolu (arama, doğrudan okuma, atıf açma, export, MCP) aynı
  `authorize(principal, on_behalf_of, nesne, kip)` çağrısından geçer; **teslimden hemen önce yeniden denetlenir**.
  Karar, politika ve grant sürümüyle erişim kaydına yazılır. Arama yetkili küme ile **önceden süzülür**.
- **Önbellek yok** (D46). Hız gerekirse M2'de, yetki denetimiyle birlikte eklenir.
- **Ağ düzeni:** Core yalnız `core` ağında (Postgres + LLMDAP); model/embedding/reranker servisleri yalnız
  `models` ağında; LLMDAP iki ağda. Core'un dış ağa ve model servislerine doğrudan yolu yoktur.
- **Diskte şifreleme:** volume seviyesinde (E8 `standard`, D48); kurulum gereği olarak belgelenir ve kurulum
  denetim betiği doğrular.

**Temel nesneler:** M1a'da dört tablo — `book`, `content_version`, `profile_version`, `policy_version` (sürümler
değişmez). Sonraki dilimler: parça (M1d), ilişki + delegasyon + erişim kaydı (M1b), cevap kaydı (M1c/M1d),
paket (M1f), geri bildirim (M1f).

## 4. Kabul testleri

Hepsi otomatik (uçtan uca, compose üzerinde); fixture'lar deterministik ve repoda (PDF fixture'ı OKF metninden
üretilir). Bir test ancak tüm alt koşulları geçerse yeşildir. Sıkılaştırmalar Astra incelemesinden (D45).

| # | Test | Geçme koşulu |
|---|---|---|
| AT-01 | **Ingest ve sürüm kimlikleri** | OKF kitabı ve PDF içe aktarılır; her biri içerik, profil, politika kimliği alır. Dosya sırası ve zaman damgası kimliği değiştirmez; bir içerik dosyasının tek baytı değişince içerik kimliği değişir. Yalnız katalog politikası değişince yalnız politika kimliği değişir. |
| AT-02 | **İki profil** | Bütün profil tam metni, parçalı profil beklenen parça sınırlarını verir. Ayrıştırıcı ya da parçalayıcı sürümü değişince profil kimliği değişir, içerik kimliği sabit kalır. Atıflar profil kimliğini taşır. |
| AT-03 | **İnsan ve ajan aynı kitapta** | Sabit içerik/profil ve aynı yetki bağlamında HTTP (U) ve MCP (A, U adına) **aynı kanıt kümesini** döndürür; iki yüzeyin atıfları geçerli pasajlara çözülür. (Model cevabının birebir aynılığı ölçülmez.) |
| AT-04 | **İptal, bütün yollarda** | Delegasyon iptal edilince sonraki ilk istek arama, doğrudan okuma, atıf açma ve export yollarının hepsinde reddedilir. İptalden önce başlayıp teslim öncesinde bekletilen istek de içerik teslim etmez. Arama sonuçları, sayıları ve özetleri yetkisiz öğeyi sızdırmaz. |
| AT-05 | **Devredenin yetkisi düşer** | U'nun kitap hakkı kaldırılınca A'nın U'dan aldığı delegasyon, delegasyon nesnesi silinmeden etkisiz kalır; AT-04'teki yarış koşulu burada da geçerlidir. |
| AT-06 | **Delegasyon sınırları** | Sahip olunmayan kapsam ya da kip, sahte devreden, ikinci devir (derinlik > 1) ve bitiş anı dahil süresi dolmuş grant reddedilir. `read` otomatik `use` sağlamaz (kipler bağımsız, D24). |
| AT-07 | **Eski atıf** | Yeni sürüm sonrası eski cevap ve pasajları model yeniden çağrılmadan, eski sürümden birebir gösterilir. Güncel yetki yoksa ne cevap gövdesi ne kanıtları gösterilir. |
| AT-08 | **"Kütüphanede yok"** | Sürümlü soru–pasaj kümesinde çekimserlik ve kanıt isabeti, M0'da onaylanan sayısal eşikleri karşılar; bütün atıflar çözülür. (Eşikler M0 sonrası bu satıra yazılır.) |
| AT-09 | **Birleşik denetim** | Bir cevap kimliği için tek sorgu; principal, adına çalışılan kullanıcı, içerik/profil sürümü ve parçalar, politika ve grant sürümü, yetki kararları ve **bütün** retrieval/üretim çağrılarının LLMDAP kayıtlarını döner. Eksik LLMDAP kaydı açıkça "eksik" olarak işaretlenir. |
| AT-10 | **Tek egress** | Core'dan izinli hedefler (Postgres, LLMDAP) dışına doğrudan IP, DNS ve yerel model servisi denemeleri ağ seviyesinde başarısız olur. Üretim, embedding ve reranker çağrılarının tamamı LLMDAP kayıtlarıyla eşleşir. *(LLMDAP #222 kapısı)* |
| AT-11 | **Kimlik** | API ve MCP; kimliksiz, süresi geçmiş, yanlış issuer/audience taşıyan ve değiştirilmiş token'ları reddeder. Principal ya da adına çalışılan kullanıcı istek başlığıyla değiştirilemez. *(LLMDAP #223 kapısı)* |
| AT-12 | **K3 etkinleştirme kapısı** | Ayrı etkinleştirme grant'i olmadan bir ajan talimatının (K3) **gövdesi hiçbir ajan yolundan verilmez** (`read` dahil). İzinli teslim erişim kaydında ayrı olay olarak görünür. |
| AT-13 | **Paket taşıma ve anahtarlar** | Export edilen imzalı paket ikinci kuruluma import edilir; içerik kimlikleri iki kurulumda aynıdır. Güven kökü: ilk anahtar, yöneticinin bant dışı doğruladığı parmak iziyle sabitlenir. Anahtar yenileme çalışır; bilinmeyen ya da iptal edilmiş anahtarla imzalı paket reddedilir. |
| AT-14 | **İçe aktarma zinciri, kurcalama, replay, atomiklik** | Karantina → imza/özet doğrulama → tarama → fark → insan onayı zinciri atlanamaz; onaysız paket yayımlanmaz. Bozuk imza, tek baytı değişmiş paket ve eşit ya da eski sıra numaralı paket reddedilir. Hata ya da eşzamanlı replay görünür kataloğu değiştirmez; ret kaydı korunur. |
| AT-15 | **Runbook geri bildirimi** | Üç sonuç değeri (işe yaradı / yaramadı / değişti), uygulayan, zaman, `tested_on` ve içerik sürümü saklanır; yeni sürüm eski geri bildirimi sahiplenmez. |
| AT-16 | **Zorunlu alanlar** | E5 (hassasiyet, egress), E8 ve E9 olmadan kayıt ya da grant oluşturulamaz; M1'de E8 yalnız `standard` kabul edilir; delegasyonun `purpose` alanı kaydedilir (zorlayıcı değil, D28). |

## 5. M1 içinde verilecek kararlar

Bunlar M1'i bloklamaz; ilgili dilimde, kayda geçirilerek verilir.

- Üç sürüm kimliğinin kanonik özet şeması; paket manifesti ve sıra numarası kapsamı (M1a).
- ReBAC tablo şeması; OpenFGA arayüzüyle uyumlu adlandırma (M1b).
- LLMDAP istemci sözleşmesi ve fixture'ları (M1c).
- Retrieval bileşenleri ve AT-08 eşikleri (M0 → M1d).
- Arayüzün M1 kapsamı: okuyucu, soru-cevap, atıf, denetim görünümü; ötesi M2 (M1e).
- Anahtar yenileme akışının ayrıntısı (M1f).

## 6. Durum — 2026-10-12

Kod `main`'de (PR #5–#19), 162 otomatik test yeşil. "Core tarafı" = Kütüphane'nin kendi payı tamam; kalan kısım
dış bağımlılığa bağlı.

| # | Durum | Kanıt / kalan |
|---|---|---|
| AT-01 | yeşil | `test_ingest.py` (kimlikler, tek bayt, zaman damgası, politika, PDF) |
| AT-02 | yeşil | `test_search.py` (tam parça sınırları, PDF sayfa/ofset, bileşen sürümü → yeni profil) |
| AT-03 | yeşil | `test_server.py` (HTTP kullanıcı ve gerçek `/mcp` üzerinden ajan: aynı kanıt kümesi, aynı pasajlar) |
| AT-04 | yeşil | dosya, arama, atıf, cevap, yeniden açma yolları; iki oturumlu iptal yarışları. Paket export'u yönetici işlemidir (ajan yolu değil). |
| AT-05 | yeşil | `test_authz.py`, `test_search.py`, `test_answers.py` |
| AT-06 | yeşil | kapsam/kip, sahte devreden, derinlik, bitiş anı, `read`≠`use` |
| AT-07 | yeşil | eski cevap + kanıt modeli çağırmadan, güncel yetkiyle; delegasyon iptali |
| AT-08 | **mekanizma yeşil, eşik açık** | "kütüphanede yok", geçersiz atıf reddi; sayısal eşik M0 ölçümünü bekliyor |
| AT-09 | **Core yeşil** | erişim + `model_call` + LLMDAP export birleşimi, cevap kimliğinden; gerçek LLMDAP kaydı #222/#223 sonrası |
| AT-10 | **ağ yarısı yeşil; Core yeşil** | `deploy/egress_probe.py`: varsayılan rota yok, dış ad çözülmüyor, yalnız Postgres'e bağlanır. Embedding de LLMDAP'tan (#226, D52), her çağrı `model_call`'da. Canlı eşleşme gerçek LLMDAP compose'a girince; reranker rerank yüzeyini bekliyor |
| AT-11 | **Core yeşil; LLMDAP sözleşmesi uygulandı** | dokuz bozuk-token durumu HTTP ve MCP'de 401; başlıkla kimlik değiştirilemez. Core LLMDAP'a özne anahtarıyla bağlanır (#228, D52); canlı test gerçek LLMDAP compose'a girince |
| AT-12 | yeşil | K3 `activate` kapısı, harf/CRLF varyantları, atıf yapılmamış K3 kaynakları |
| AT-13 | yeşil | `test_packages.py` (iki kurulum, güven kökü, anahtar yenileme/iptal, onay sırasında iptal) |
| AT-14 | yeşil | kurcalama, tekrar oynatma, eşzamanlı onay yarışı, yarıda hata, bozuk manifest ve büyük girdi ret kaydı |
| AT-15 | yeşil | `test_feedback.py` (sürüme bağlı geri bildirim) |
| AT-16 | yeşil | zorunlu E5/E8/E9, `purpose` kaydı, `publish` sınırında doğrulama |

**M1'i kapatmak için kalan:** gerçek LLMDAP'ın compose'a eklenmesi (yalnız bridge'li sade bir gateway imajı
gerekiyor; LLMDAP#237) ve AT-10/AT-11'in canlı denenmesi; LLMDAP rerank yüzeyi (#236) → reranker; iç doküman etiketleri
→ kesin model seçimi ve AT-08 eşikleri. Hibrit arama (bge-m3 önerisi, M0) Kütüphane tarafında hazır (D52).
