# Kütüphane — ürün brifi

Tarih: 2026-10-12. Durum: **onaylandı (D45).** Dayanak: `01-direction-decisions.md` D1–D44.
Çelişki olursa 01 geçerlidir; bu doküman kararları ürün diliyle bir araya getirir, yeni karar koymaz.

## 1. Tek cümle

Kütüphane, on-prem ve air-gapped kurumlarda **insanların ve LLM ajanlarının ortak kullandığı** bir bilgi
yönetimi platformudur; her cevap için **bilginin hangi sürümüne, kimin adına, hangi politikayla erişildiğini**
açıklayabilir.

## 2. Problem

Kurumlar yerel ajan çalıştırmaya başladı. Ajanlar kurum bilgisini okuyor, ama:

- **Kimin adına okuduğu bilinmiyor.** Ajan bir kullanıcı için çalışıyor; kullanıcının yetkisi düşünce ajanınki
  düşmüyor. MCP yetkilendirmesi de kullanıcı→ajan delegasyonunu kapsam dışı bırakıyor.
- **Sürüm kayıyor.** Doküman güncellenince dünkü cevabın dayandığı pasaj kayboluyor; denetimde "o gün ne
  biliyorduk" sorusu cevapsız kalıyor.
- **Ajan talimatları yönetişimsiz.** Skill, prompt, agent card dosyaları kopyalanarak yayılıyor; hangisinin
  hangi ajanda etkin olduğu bilinmiyor.
- **Air-gap'e bilgi elle ve imzasız giriyor.** USB ile taşınan güncellemenin kaynağı ve bütünlüğü kanıtlanmıyor.
- **Mevcut ürünler bu boşluğu kapatmıyor.** NotebookLM Enterprise bulut; Onyx ve benzerleri arama odaklı ve
  delegasyonu modellemiyor; Context7 tek kategori, tek sunum. *(Rakip ve MCP genellemeleri 2026-10 araştırmasına
  dayanır; satış/pazarlama dilinde kullanılmadan önce yeniden doğrulanmalı.)*

## 3. Kimin için

Regüle ya da air-gapped kurumların bilgi ve operasyon ekipleri (D1): hukuk, uyum, mühendislik, IT-ops; ve
**yerel ajan çalıştıran, GPU erişimi olan işletmeler** (D42).

| Aktör | Kütüphane'de ne yapar |
|---|---|
| **Okur** (insan) | Kitapları okur, soru sorar, atıflı cevap alır, eski cevabın kanıtını açar |
| **Ajan** (Claude Code, Codex, kurumun kendi ajanları) | MCP ile kitaplara erişir; bir kullanıcının devrettiği yetkiyle, sınırlı ve süreli |
| **Küratör** | Kitap ekler, sürüm yayınlar, import onaylar, runbook geri bildirimini izler |
| **Denetçi** (güvenlik, uyum) | "Kim, kimin adına, hangi sürüm, hangi politika, hangi model çağrısı" sorgusunu çalıştırır |
| **Yönetici** | Kurulum, kimlik bağlantısı, paket anahtarları; ileride master rolü |

## 4. Ayırt edici değer (kama)

1. **Sürüm atfı.** Her atıf `içerik@sürüm + profil + parça` taşır; eski cevap ve kanıtı yeniden gösterilebilir.
   Erişim hakkı ise sabitlenmez: açarken güncel yetki denetlenir (D26, D36).
2. **Modellenmiş delegasyon.** Kullanıcı→ajan devri birinci sınıf nesnedir; süreli, iptal edilebilir, devredenin
   güncel yetkisiyle kesişir; arama, doğrudan okuma, önbellek ve export aynı kapıdan geçer (D28).
3. **Açıklanabilir erişim.** Kütüphane'nin erişim kaydı ile LLMDAP'ın egress kaydı tek korelasyon kimliğiyle
   birleşir (D35).
4. **Kategoriye uygun sunum.** Aynı içerik insana okunur sayfa, ajana alıntılı parça olarak gider; ajan
   talimatları bütün olarak ve **ayrı bir etkinleştirme kapısından** sunulur (D25, D37).
5. **İmzalı offline akış.** Kurulumlar arası her bilgi akışı imzalı, sürüm zarflı pakettir; ağ ve fiziksel
   medya aynı paketi taşır; import atomiktir, eski paket yeniden oynatılamaz (D23, D29).

## 5. Ürün ailesi ve iş bölümü

| Parça | Sahip olduğu | Sahip olmadığı |
|---|---|---|
| **Kütüphane Core** | katalog, üç sürüm kimliği, şifreli saklama (Postgres), sunum profilleri, hibrit arama, yetki ve delegasyon, erişim kaydı, HTTP API, insan arayüzü | model çağrısı, kimlik doğrulama |
| **Kütüphane MCP** | harness'lara yüzey; Core API'nin ince, sürümlü istemcisi | kendi deposu, kendi politikası |
| **Master rolü** | aynı kod tabanında; katalog/politika yayını, kurulum kayıt defteri ("son bildirilen durum"), recall (D27) | kuruluma içeri erişim, yetki genişletme |
| **Kobra** | Core içindeki referans ajan/sohbet yüzü (D20) | — |
| **LLMDAP** | tüm model ve embedding egress'i, egress kaydı, model anahtarları (D3, D33) | bilgi deposu, retrieval (D16) |
| **Kurum IdP** | kimlik doğrulama (AD/LDAP ya da Keycloak); LLMDAP doğrulayıcıdır, Kütüphane yetkilendirir (D38) | yetkilendirme |

## 6. İlkeler

- **OKF-yerli, minimally opinionated.** Taşınabilir birim OKF concept'i; Kütüphane'ye özgü bilgiler
  `kutuphane:` frontmatter bloğunda; yönetişimin otoritesi katalog (D21).
- **Önce benimse, sonra inşa et.** Yalnız kama yazılır; çekirdekte AGPL yok; lisanslar seçimden önce
  doğrulanır (D22).
- **Hiçbir şey içeri erişmez** (D23). **Tek egress LLMDAP** (D3).
- **Dürüst ürün dili.** "Ajana sır verilmez", "asla öğrenemez" değil (D33); "eski cevabın kanıtı gösterilir",
  "cevap birebir yeniden üretilir" değil (D36); "şemada var" ürün vaadi değildir (D25).
- **Sadelik (D46).** Servis ve soyutlama sayısı asgari: tek Python uygulaması; sadeleştirme yönetişim
  kapılarından değil, parça sayısından yapılır.
- **Bileşenler değiştirilebilir ve sürümlü.** Ayrıştırıcı, parçalayıcı, gömücü, reranker küçük, sürümlü fonksiyon
  arayüzleri; kimlikleri provenance'a girer. Plugin altyapısı kurulmaz (D46).
- **Geliştirmeye ve ajana açık.** Her şey CLI + API + MCP ile sürülebilir; deterministik fixture'lar.

## 7. Kapsam dışı

- Cihaz/araç üzerinde eylem (D4). Runbook'lar doküman olarak yaşar, çalıştırılmaz (D13).
- Model barındırma ve model anahtarı yönetimi (LLMDAP'ın işi).
- Kendi kimlik sistemi (IdP'nin işi).
- Genel sohbet ürünü olmak; OpenWebUI/LibreChat ile yarışmak.
- M1'de: sesli özet ve stüdyo çıktıları (D39), `envelope`/`sealed` koruma (D33), master federasyonu (D27).

## 8. Başarı ölçütleri

- **M1:** `07-m1-definition.md` kabul testlerinin tamamı makinece geçer.
- **Arama kalitesi:** eşikler M0 ölçümünden sonra konur (D31); şimdiden sayı uydurulmaz.
- **Açıklanabilirlik:** her cevap için denetçi sorgusu tek çağrıda tam iz döner (AT-09).
- **Deney hattı:** karar modelleri insan etiketine karşı, kör dilimde ölçülür (D30, D43).

## 9. Riskler

| Risk | Etki | Karşılık |
|---|---|---|
| Upstream bağımlılık: LLMDAP #222 (embedding egress), #223 (kimlik) | M1 tamamlanmış sayılamaz (D18) | Bağımsız işler paralel; upstream işler önceliklendirilir |
| Ontoloji boşluğu: ilk korpusta taslakların ~%25'i hiçbir kategoriye oturmadı (plan, tasarım notu) | Kategori seti eksik olabilir | İnsan etiketleri gelince ontoloji gözden geçirilir (M0) |
| Kendi korpusumuz M1 kapsamını (K1–K3) zayıf temsil ediyor; ağırlık kayıt/kanıt | Arama ölçümü gerçek kullanımı yansıtmaz | Kamuya açık mevzuat seti eklenir (D41 b) |
| Tek etiketleyici | Etiket kapasitesi ve yanlılık | Kör dilim; gerekirse ikinci etiketleyici |
| Paylaşımlı DGX Spark | Ölçüm ve model işleri çakışır | Ağır işler öncesi operatöre sorulur; CPU kipi (D42) |
| Kapsam şişmesi ("LLM deney platformu") | M1 gecikir | Deney hattı ayrı; teslim kapsamını büyütmez (D39) |
