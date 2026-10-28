-- #136: what each model stage of the answer's retrieval did ({embedding, translation, rerank}, each ok, failed or
-- skipped), so a reopened answer shows whether it was built on a degraded search. Answers stored before this
-- migration have none (NULL).
ALTER TABLE answer ADD COLUMN retrieval jsonb;
