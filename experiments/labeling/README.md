# Etiketleme deneyi (D41–D44)

İnsan etiketli değerlendirme kümesi + Laya shadow. Her şey yerelde kalır; `data/` git'e girmez
(içerik kopyası, taslaklar, etiketler, erişim token'ı).

| Dosya | İş |
|---|---|
| `taxonomy.json` | Etiket kümesi: kategori K1–K8 + Uymuyor, hassasiyet, çıkış; soru–pasaj ilgisi |
| `select_corpus.py` | Salt-okunur kaynak repolardan katmanlı örnekleme + sır taraması; `data/manifest.json`, `data/docs.json`; ~%30 kör |
| `server.py` + `page.html` | Telefon dostu etiketleme sayfası (stdlib, token → cookie; metinler ASD-STE100 İngilizce, "Guide" paneli seçenekleri, farklarını ve örnekleri gösterir). Kör öğelerde taslak etiket kaydedilmeden gösterilmez, kayıttan sonra gösterilir; Laya tahmini hiç sunulmaz. "Restricted" seçilince çıkış "local only" olur (ürün kuralı). Etiketler `data/labels.jsonl` (ekleme; son kayıt geçerli) |
| `laya_shadow.py` | `laya-multilingual` (sabit revizyon) CPU'da zero-shot; `data/laya-shadow.jsonl` |
| `v2.py` + `page_v2.html` (`/v2`) | Ontoloji v2 etiketlemesi (docs/09 §5, D54): belge başlıklara göre bölümler halinde (bloklar `experiments/ontology/propose.py` kuralıyla); belge düzeyinde hassasiyet, egress ve kök ön ayar; bölüm başına ön ayar istisnası, "restricted" işareti, ayrıntılı inceleme işareti. Kör belgede öneri yok. Kayıt `data/labels_v2.jsonl`: bölümlerin blok hash'leriyle (metni değişmeyen blok etiketini korur). Restricted + bulut reddedilir. |

Taslaklar (`data/drafts/batch-*.json`) Claude tarafından üretilir: kategori, hassasiyet, çıkış, gerekçe,
0–1 soru + birebir pasaj. Gerçeklik referansı insan etiketidir (D30); taslak–insan uyumu ve çapalama etkisi
kör dilimde ölçülür.

Çalıştırma:

```sh
python3 -I select_corpus.py <aday-listesi.txt> data
python3 -I server.py --host <tailnet-ip> --port 8790   # erişim: http://<ip>:8790/?t=<data/token>
# Düz HTTP: yalnız loopback ya da tailnet (WireGuard şifreli) kabul edilir; başka arayüz için --allow-any-interface.
# Kopya, sonradan değişmiş ya da sır taramasına takılan kaynaklar sunulmaz (fail-closed).
LAYA_THREADS=16 <venv>/bin/python -I laya_shadow.py
```
