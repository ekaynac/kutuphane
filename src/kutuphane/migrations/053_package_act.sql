-- D85 (S3): a curator approves or rejects received packages with a passkey act (`package`). Curator web only stores
-- the signed statement; the owner-run publisher (`kutuphane imports publish-admitted`) applies it and names the act
-- in `publication.act`. The statement lists 1..50 items, each {import_id, book, manifest_sha256, content_id, decision,
-- policy (approve) | reason (reject)}.
ALTER TABLE curator_challenge DROP CONSTRAINT curator_challenge_action_check,
    ADD CONSTRAINT curator_challenge_action_check CHECK (action IN ('register', 'login', 'standing', 'confirm',
        'withdraw', 'delegate', 'end_delegation', 'package'));
ALTER TABLE curator_act DROP CONSTRAINT curator_act_action_check,
    ADD CONSTRAINT curator_act_action_check CHECK (action IN ('standing', 'confirm', 'withdraw', 'delegate',
        'end_delegation', 'package'));

-- A `package` statement is well formed or the challenge row is refused (the act row needs its challenge row).
CREATE FUNCTION package_statement_wellformed() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    items jsonb := NEW.payload -> 'items';
    i jsonb;
BEGIN
    IF NEW.action <> 'package' THEN
        RETURN NEW;
    END IF;
    IF jsonb_typeof(items) IS DISTINCT FROM 'array' OR jsonb_array_length(items) NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'a package statement has 1..50 items';
    END IF;
    IF (SELECT count(DISTINCT x -> 'import_id') FROM jsonb_array_elements(items) x) <> jsonb_array_length(items) THEN
        RAISE EXCEPTION 'a package statement names an import twice';
    END IF;
    FOR i IN SELECT * FROM jsonb_array_elements(items) LOOP
        IF jsonb_typeof(i) IS DISTINCT FROM 'object'
           OR jsonb_typeof(i -> 'import_id') IS DISTINCT FROM 'number'
           OR jsonb_typeof(i -> 'book') IS DISTINCT FROM 'string'
           OR (i ->> 'manifest_sha256') IS NULL OR (i ->> 'manifest_sha256') !~ '^[0-9a-f]{64}$'
           OR jsonb_typeof(i -> 'content_id') IS DISTINCT FROM 'string'
           OR (i ->> 'decision') IS NULL OR (i ->> 'decision') NOT IN ('approve', 'reject') THEN
            RAISE EXCEPTION 'a package item is not well formed';
        END IF;
        IF (i ->> 'decision') = 'approve' AND (
               jsonb_typeof(i -> 'policy') IS DISTINCT FROM 'object' OR i ? 'reason'
               OR (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(i -> 'policy') k)
                  IS DISTINCT FROM ARRAY['egress', 'protection', 'sensitivity', 'v']) THEN
            RAISE EXCEPTION 'an approve item has a policy {v, sensitivity, egress, protection} and no reason';
        END IF;
        IF (i ->> 'decision') = 'reject' AND (
               i ? 'policy' OR jsonb_typeof(i -> 'reason') IS DISTINCT FROM 'string'
               OR char_length(i ->> 'reason') NOT BETWEEN 1 AND 500) THEN
            RAISE EXCEPTION 'a reject item has a reason of 1..500 characters and no policy';
        END IF;
    END LOOP;
    RETURN NEW;
END $$;
CREATE TRIGGER package_statement_wellformed BEFORE INSERT ON curator_challenge
    FOR EACH ROW EXECUTE FUNCTION package_statement_wellformed();

-- A publication by passkey names its act, and only that act: `curator_passkey` and `act` go together.
ALTER TABLE publication ADD COLUMN act bigint REFERENCES curator_act(seq),
    ADD CONSTRAINT publication_act CHECK ((acceptance = 'curator_passkey') = (act IS NOT NULL));
CREATE UNIQUE INDEX publication_act_import ON publication (act, package_import) WHERE act IS NOT NULL;

-- ... and the row is exactly an approve item of that act's statement: this import, book and content, the signed
-- policy, the signer as `approved_by`, the channel `import`, and its passkey is not revoked (a lost phone).
CREATE FUNCTION publication_in_statement() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.curator_act a
          JOIN public.curator_challenge c ON c.id = a.challenge
          JOIN public.passkey k ON k.credential_id = a.credential_id AND k.revoked_at IS NULL
         CROSS JOIN jsonb_array_elements(c.payload -> 'items') i
          JOIN public.policy_version p ON p.id = NEW.policy_id
         WHERE a.seq = NEW.act AND a.action = 'package' AND a.principal = NEW.approved_by
           AND NEW.channel = 'import' AND (i ->> 'import_id')::bigint = NEW.package_import
           AND i ->> 'decision' = 'approve' AND i ->> 'book' = NEW.book AND i ->> 'content_id' = NEW.content_id
           AND i -> 'policy' = p.doc) THEN
        RAISE EXCEPTION 'publication is not an approve item of the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER publication_in_statement BEFORE INSERT ON publication
    FOR EACH ROW WHEN (NEW.act IS NOT NULL) EXECUTE FUNCTION publication_in_statement();
