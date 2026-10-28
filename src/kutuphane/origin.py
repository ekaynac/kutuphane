"""Origin from the write path (D70; docs/24 §5) and the shown origin (docs/25 §7.6). The server computes it; a client
can only ask for a lower value.

R2: an agent path (an `agent:` principal, a user acted for, or the MCP channel) is `model`. R4/R6: anything else (a
`user:` principal without `act`, over HTTP or the CLI import of docs/24 §23) is `unknown` in R1. R1 never stores
`human`: a token is not a person's act on exact bytes; `human` comes only from the R3 passkey confirmation
(`origin_confirmation`, migration 024), and R7 withdrawal removes it. `unknown` is handled as `model`. A
confirmation counts only while the note's stored parts give the id that the person signed (canonical.py, Astra
review #19); else the shown origin is `model`.
"""
from . import canonical
from .gate import Actor
from .kstd import ORIGINS

REFUSED = "origin-claim-refused"
STORED = ("model", "unknown")  # lowest first: the write-path origin of a note is the lowest over its propose writes
CONFIRMABLE = ("human", "assisted")  # a refused claim of these opens an R3 request (024 `confirmable`)


def computed(actor: Actor) -> str:
    direct_user = actor.principal.startswith("user:") and actor.on_behalf_of is None \
        and actor.channel in ("http", "cli")
    return "unknown" if direct_user else "model"


def compute(actor: Actor, requested: str | None) -> tuple[str, str | None]:
    """(stored origin, notice). A requested `model` is always allowed (a lower value); `unknown` on an agent path
    stays `model`; a requested human, assisted or tool is refused with a notice and the computed value is stored."""
    if requested is not None and requested not in ORIGINS:
        raise ValueError(f"origin must be one of {', '.join(ORIGINS)}")
    value = computed(actor)
    if requested in (None, value, "unknown"):
        return value, None
    if requested == "model":
        return "model", None
    return value, REFUSED


def lowest(origins) -> str | None:
    """The write-path origin of a note: the lowest of the stored origins of its propose writes (model < unknown)."""
    present = set(origins)
    return next((o for o in STORED if o in present), None)


_SHOWN = """
SELECT s.seq,
       (SELECT CASE WHEN bool_or(wr.origin = 'model') THEN 'model' ELSE 'unknown' END FROM write_record wr
         WHERE wr.note_seq = s.seq AND wr.action = 'propose' AND (%(w)s::bigint IS NULL OR wr.seq <= %(w)s)),
       c.claim, c.entered_by, c.confirmed_by,
       EXISTS (SELECT 1 FROM origin_withdrawal x
                WHERE x.confirmation = c.seq AND (%(w)s::bigint IS NULL OR x.seq <= %(w)s))
  FROM unnest(%(seqs)s::bigint[]) s(seq)
  LEFT JOIN LATERAL (SELECT oc.seq, oc.claim, oc.entered_by, oc.confirmed_by FROM origin_confirmation oc
                      WHERE oc.note_seq = s.seq AND (%(w)s::bigint IS NULL OR oc.seq <= %(w)s)
                      ORDER BY oc.seq DESC LIMIT 1) c ON true
"""


def shown(conn, seqs, w: int | None) -> dict:
    """{seq: (origin, entered_by, confirmed_by)} at the watermark `w` (None: now), docs/25 §7.6. The latest
    confirmation with seq <= w counts unless a withdrawal with seq <= w removed it; then, and with no confirmation,
    the write-path value (entered_by and confirmed_by None). A withdrawal never brings back an older confirmation.
    A live confirmation of a note whose stored parts no longer give the signed id shows `model` (D70)."""
    seqs = sorted(set(seqs))
    if not seqs:
        return {}
    rows = conn.execute(_SHOWN, {"seqs": seqs, "w": w}).fetchall()
    whole = canonical.intact(conn, [r[0] for r in rows if r[2] and not r[5]])
    out = {}
    for seq, written, claim, entered_by, confirmed_by, withdrawn in rows:
        if claim and not withdrawn:
            out[seq] = (claim, entered_by, confirmed_by) if seq in whole else ("model", None, None)
        else:
            out[seq] = (written, None, None)
    return out


def details(origin: str, entered_by: str | None, confirmed_by: str | None) -> dict:
    """The kstd origin details of a shown origin (docs/11 §5.2): `assisted` + `reviewed_by` (the confirmer);
    `human` + `entered_by` and `confirmed_by`. Nothing for the write-path values."""
    if confirmed_by is None:
        return {}
    if origin == "assisted":
        return {"reviewed_by": confirmed_by}
    return {"entered_by": entered_by, "confirmed_by": confirmed_by}
