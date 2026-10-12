# Kütüphane — M1 tanımı: uçtan uca kanıt senaryosu

Tarih: 2026-10-12. Durum: **taslak, operatör onayı bekliyor.** Dayanak: D35 ve `04-…` §3. M1'in amacı ürünün
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
6. Yönetici U'nun kitap üzerindeki hakkını kaldırır. A'nın bir sonraki isteği; arama, doğrudan okuma, önbellek
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
(D37); birleşik denetim (D35); imzalı paket import/export (D29); basit runbook geri bildirimi (D13); LLMDAP
üzerinden model ve embedding egress'i, IdP kimliği (D18, D38).

**Dışında (M2+):** `envelope`/`sealed` koruma, OpenBao (D33); çok seviyeli delegasyon, OpenFGA servisi (D28);
master federasyonu ve recall (D27, D40); karar modeli entegrasyonu (D30, D34); DOCX/OCR; gelişmiş profil
yönetimi; stüdyo çıktıları ve sesli özet (D39).

## 3. Mimari çerçeve (M1)

- **Yığın:** Core Python (D6), arayüz React + TS (D15), Postgres + pgvector + tam metin (D11, D16), tek kutu
  docker compose: Core + LLMDAP + Postgres + IdP (D15, D38). InfraMedic'in katalog/nesil/yetki/audit kodu
  kopyalanıp ameliyat edilir (D6); InfraMedic'e dokunulmaz.
- **Tek yetki kapısı.** Her okuma yolu (arama, doğrudan okuma, atıf açma, önbellek, export, MCP) aynı
  `authorize(principal, on_behalf_of, nesne, kip)` çağrısından geçer; karar, politika ve grant sürümüyle
  erişim kaydına yazılır. Arama yetkili küme ile **önceden süzülür** (post-filter yok).
- **Önbellek:** yetki kararı önbellekten sunmadan önce yeniden alınır; önbellek anahtarı içerik + profil
  sürümünü taşır, yetkiyi değil.
- **Egress:** Core'un ağdan yalnız LLMDAP'a ve veritabanına çıkışı vardır; compose ağ politikası bunu zorlar.

**Temel nesneler (taslak):** `kitap` · `içerik_sürümü` (bundle özeti) · `profil_sürümü` · `politika_sürümü` ·
`parça` · `principal` (kullanıcı / ajan / rol) · `ilişki` (ReBAC demeti) · `delegasyon` (kimden, kime, kapsam,
kip, bitiş, iptal) · `erişim_kaydı` · `cevap_kaydı` (atıflar + korelasyon kimliği) · `paket` (manifest, imza,
sıra numarası) · `geri_bildirim`.

## 4. Kabul testleri

Hepsi otomatik (uçtan uca, compose üzerinde); fixture'lar deterministik ve repoda (PDF fixture'ı OKF metninden
üretilir). Bir test ancak tüm alt koşulları geçerse yeşildir.

| # | Test | Geçme koşulu |
|---|---|---|
| AT-01 | **Ingest ve sürüm kimlikleri** | OKF kitabı ve PDF içe aktarılır; her biri içerik, profil, politika kimliği alır. Aynı içerik tekrar yüklenince içerik kimliği değişmez; tek bayt değişince değişir. Politika değişikliği içerik kimliğini değiştirmez. |
| AT-02 | **İki profil** | Aynı içerik iki profille servis edilir; profil kimlikleri farklıdır; atıflar profil kimliğini taşır. |
| AT-03 | **İnsan ve ajan aynı kitapta** | Aynı soru arayüzden (U) ve MCP'den (A, U adına) sorulunca atıflar aynı içerik sürümüne ve parçalara işaret eder. |
| AT-04 | **İptal, bütün yollarda** | A'nın delegasyonu iptal edilince iptalden sonraki ilk istek; arama, doğrudan okuma, atıf açma, önbellek ve export yollarının hepsinde reddedilir. Arama sonuçları, sayıları ve özetleri yetkisiz öğeyi sızdırmaz. |
| AT-05 | **Devredenin yetkisi düşer** | U'nun kitap hakkı kaldırılınca A'nın U'dan aldığı delegasyon, delegasyon nesnesi silinmeden etkisiz kalır. |
| AT-06 | **Delegasyon sınırları** | A, U'nun sahip olmadığı kitaba ya da kipe (ör. U'da yalnız `discover` varken `read`) delegasyon alamaz; süresi dolan delegasyon reddedilir; delegasyon zinciri derinliği 1'i aşamaz. |
| AT-07 | **Eski atıf** | Yeni sürüm sonrası eski cevaptaki atıf eski sürümdeki doğru pasajı birebir açar; açılırken güncel yetki denetlenir (yetkisi düşen U açamaz). |
| AT-08 | **"Kütüphanede yok"** | Dayanağı olmayan sorulardan oluşan sabit kümede cevap "kütüphanede yok" döner ve uydurma atıf içermez; dayanağı olan kümede atıflı cevap döner. Eşikler M0 sonrası sayıyla yazılır. |
| AT-09 | **Birleşik denetim** | Bir cevap kimliği için tek sorgu; principal, adına çalışılan kullanıcı, içerik/profil sürümü ve parçalar, politika ve grant sürümü, yetki kararı ve LLMDAP egress kaydını (korelasyon kimliğiyle) döner. |
| AT-10 | **Tek egress** | Cevap üretimi ve embedding çağrılarının tamamı LLMDAP kaydında görünür; Core konteynerinden LLMDAP dışı bir model uç noktasına bağlantı denemesi ağ seviyesinde başarısız olur. *(LLMDAP #222 kapısı)* |
| AT-11 | **Kimlik** | Kimliği doğrulanmamış istek API'de ve MCP'de reddedilir; kimlik IdP'den gelir, LLMDAP doğrular, Kütüphane yetkilendirir. *(LLMDAP #223 kapısı)* |
| AT-12 | **K3 etkinleştirme kapısı** | Yalnız `read` hakkı olan ajana bir ajan talimatı (K3) **etkin talimat olarak** sunulmaz; etkinleştirme ayrı bir grant ister ve erişim kaydında ayrı olay olarak görünür. |
| AT-13 | **Paket taşıma** | Export edilen imzalı paket ikinci kuruluma import edilir; içerik kimlikleri iki kurulumda aynıdır. Güven kökü: ilk anahtar, yöneticinin bant dışı doğruladığı parmak iziyle sabitlenir. |
| AT-14 | **Kurcalama, replay, atomiklik** | Tek baytı değişmiş paket reddedilir; sıra numarası eski paket reddedilir; import yarıda hata verirse kurulumda hiçbir değişiklik kalmaz. |
| AT-15 | **Runbook geri bildirimi** | Geri bildirim runbook'un içerik sürümüne bağlı kaydedilir; yeni sürümde eski geri bildirim eski sürüme ait olarak görünür. |

## 5. M1 içinde verilecek kararlar

Bunlar M1'i bloklamaz; ilgili dilimde, kayda geçirilerek verilir.

- Üç sürüm kimliğinin kanonik özet şeması (M1a).
- Retrieval bileşenleri ve AT-08 eşikleri (M0 → M1b).
- ReBAC tablo şeması; OpenFGA arayüzüyle uyumlu adlandırma (M1c).
- Arayüzün M1 kapsamı: okuyucu, soru-cevap, atıf, denetim görünümü; ötesi M2 (M1d).
- Paket sıra numarasının kapsamı (kurulum başına mı, kitap başına mı) ve anahtar yenileme akışı (M1e).
