# Etiketleme deneyi (D41–D44)

İnsan etiketli değerlendirme kümesi + Laya shadow. Her şey yerelde kalır; `data/` git'e girmez
(içerik kopyası, taslaklar, etiketler, erişim token'ı).

| Dosya | İş |
|---|---|
| `taxonomy.json` | Etiket kümesi: kategori K1–K8 + Uymuyor, hassasiyet, çıkış; soru–pasaj ilgisi |
| `select_corpus.py` | Salt-okunur kaynak repolardan katmanlı örnekleme + sır taraması; `data/manifest.json`, `data/docs.json`; ~%30 kör |
| `server.py` + `page.html` | Telefon dostu etiketleme sayfası (stdlib, token → cookie). Kör öğelerde taslak gösterilmez; Laya tahmini hiç sunulmaz. Etiketler `data/labels.jsonl` (ekleme; son kayıt geçerli) |
| `laya_shadow.py` | `laya-multilingual` (sabit revizyon) CPU'da zero-shot; `data/laya-shadow.jsonl` |

Taslaklar (`data/drafts/batch-*.json`) Claude tarafından üretilir: kategori, hassasiyet, çıkış, gerekçe,
0–1 soru + birebir pasaj. Gerçeklik referansı insan etiketidir (D30); taslak–insan uyumu ve çapalama etkisi
kör dilimde ölçülür.

Çalıştırma:

```sh
python3 -I select_corpus.py <aday-listesi.txt> data
python3 -I server.py --host <arayüz-ip> --port 8790   # erişim: http://<ip>:8790/?t=<data/token>
LAYA_THREADS=16 <venv>/bin/python -I laya_shadow.py
```
