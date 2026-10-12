# Retrieval ölçümü (M0, D31, D41 b)

Ürünün **kendi arama yolu** (yetki ön-süzgeci, sıralama, atıf) kamuya açık, elle kontrol edilmiş Türkçe hukuk
sorularıyla ölçülür. Veri ve sonuçlar git'e girmez; yalnız betikler.

- **Veri:** `mtntasci/turkish-legal-rag` @ `32263dd4ae7b0ea750f9e5e16643c14c2baa557f` (CC BY 4.0): 25 kanun,
  5.757 madde (`statute_full`), 266 aktif soru. Metinler mevzuat.gov.tr kaynaklı (FSEK md. 31).
- **Korpus:** `build_corpus.py` → kanun başına bir markdown, madde başına `## Madde N` (parçalayıcı maddede keser).
- **Ölçüm:** `eval_search.py` ayrı bir veritabanında (`kutuphane_eval`) yayınlar ve her soruyu `search.search` ile
  sorar. İsabet = altın maddenin gövdesinden (``Madde N-`` sonrası) 80 karakterlik pencere sonucun içinde.
  "answerable" = altın pencere korpusta birebir bulunan sorular (151/266; kalanlar veri setindeki metin
  farklılıkları).

## Sonuçlar — 2026-10-12, Postgres FTS (`turkish`), CPU, model yok

| Sıralama | answerable R@1 | R@5 | R@10 | MRR@10 | tümü R@10 |
|---|---|---|---|---|---|
| `ts_rank_cd` normalizasyon 0 (önceki) | 0.046 | 0.139 | 0.245 | 0.091 | 0.139 |
| normalizasyon 1 | 0.093 | 0.225 | 0.311 | 0.146 | 0.177 |
| normalizasyon 2 | 0.093 | 0.265 | 0.344 | 0.169 | 0.195 |
| **normalizasyon 4 (seçildi)** | 0.192 | 0.417 | **0.563** | 0.286 | 0.320 |
| normalizasyon 5 (4\|1) | 0.225 | 0.450 | 0.536 | 0.316 | 0.305 |
| normalizasyon 8 | 0.086 | 0.252 | 0.338 | 0.157 | 0.192 |

4 ile 5 arasındaki fark 151 soruda gürültü düzeyinde; tek bayrak (4) seçildi. Sorgu başına ~19 ms.

**Yorum:** sözcük tabanlı arama tek başına zayıf (en iyi R@10 0.56). Vektör arama + reranker (D31) gerekçesi
sayısal; ölçümü GPU/CPU izni ve LLMDAP #222 sonrası bu düzenekle yapılır. İç doküman korpusu insan etiketleriyle
ayrıca ölçülür (D41 a, D43).

```sh
python -I build_corpus.py <statute_chunks.csv> <corpus_dir>
KUTUPHANE_DSN=<eval-db> python -I eval_search.py <corpus_dir> <qa_benchmark_gold.csv> --k 10
```
