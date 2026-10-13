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
sayısal; model ölçümü aşağıda. İç doküman korpusu insan etiketleriyle
ayrıca ölçülür (D41 a, D43).

## Sonuçlar — 2026-10-13, modeller, GPU ve CPU çapraz (`eval_models.py`)

Aynı 151 cevaplanabilir soru; ilk aşamada FTS ve vektör listeleri (50'şer), hibrit = RRF (k=60), reranker hibritin
ilk 30 adayını sıralar. GPU fp16, CPU fp32. Revizyonlar: bge-m3 `5617a9f`, Qwen3-Embedding-0.6B `97b0c61`,
bge-reranker-v2-m3 `953dc6f`, Qwen3-Reranker-0.6B-seq-cls `6a5829f` (ağırlıklar yerel, ölçüm çevrimdışı).

| Yöntem (GPU) | R@1 | R@5 | R@10 | MRR@10 | sorgu başına |
|---|---|---|---|---|---|
| FTS (ürün, normalizasyon 4) | 0.192 | 0.417 | 0.563 | 0.286 | ~19 ms |
| bge-m3 vektör | 0.344 | 0.550 | 0.636 | 0.441 | 2 ms (+ 150 parça/sn indeksleme) |
| Qwen3-Embedding-0.6B vektör | 0.291 | 0.483 | 0.550 | 0.370 | 9 ms (25 parça/sn) |
| hibrit FTS + bge-m3 | 0.338 | 0.583 | **0.709** | 0.437 | — |
| **hibrit + bge-reranker-v2-m3** | **0.411** | **0.609** | **0.709** | **0.505** | 404 ms |
| hibrit + Qwen3-Reranker-0.6B | 0.232 | 0.556 | 0.656 | 0.362 | 2.3 sn |

**Çapraz test (CPU ↔ GPU, bge-m3):** belge vektörlerinin kosinüsü en az 0.9997; ilk-10 vektör sonuçları %99.5 aynı.
Reranker puan farkı en çok 0.0023 (bge) / 0.011 (Qwen3), 1140 ortak çift. **Kalite cihazdan bağımsız.**

**Hız (CPU, 12 iş parçacığı, `nice`, makine yükü ~26/20 çekirdek — kötü durum):** bge-m3 3 parça/sn (GPU'nun 1/49'u),
sorgu 72 ms; bge-reranker sorgu başına 27.7 sn (30 aday, GPU'nun 1/69'u). CPU'da reranker yalnız her 7. soruda
ölçüldü (38 soru; kalite GPU'dan). GPU da paylaşımlıydı (başka eğitim + vLLM): GPU süreleri de kötü durum.

**Yorum ve öneri (D31):** bileşenler **bge-m3 + hibrit (RRF) + bge-reranker-v2-m3**. Doğru maddenin ilk sırada
gelmesi FTS'e göre 2.1 kat (0.19 → 0.41). Qwen3 modelleri bu korpusta hem geride hem yavaş (Qwen3-Reranker şablonsuz
çalıştırıldığında anlamsızdı, R@1 0.06; şablonla 0.23). GPU'suz kurulumda reranker için aday sayısı düşürülmeli ya da
reranker kapatılmalı; hibrit tek başına R@10 0.71 verir. Kesin seçimden önce: hedef donanımda yüksüz CPU ölçümü (D42)
ve iç doküman etiketleri (D43).

```sh
python -I build_corpus.py <statute_chunks.csv> <corpus_dir>
KUTUPHANE_DSN=<eval-db> python -I eval_search.py <corpus_dir> <qa_benchmark_gold.csv> --k 10
HF_HOME=<cache> HF_HUB_OFFLINE=1 KUTUPHANE_DSN=<eval-db> python -I eval_models.py run <qa.csv> <out> --device cuda
CUDA_VISIBLE_DEVICES= ... python -I eval_models.py run <qa.csv> <out> --device cpu --rerank-every 7 --embedders bge-m3
python -I eval_models.py compare <out> cuda cpu
```

Model ölçümü ayrı bir ortam ister (`torch`, `sentence-transformers`, `numpy`); ürünün bağımlılığı değildir.
