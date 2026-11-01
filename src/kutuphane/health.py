"""`GET /v1/health` (#141): is each dependency up now? One boolean per dependency, `null` for one the deployment does
not configure. The answer never names a route, a model or an address: a caller learns only what works.

The model checks are real governed calls with fixed, book-free inputs (purpose `health`), so each one is in
`model_call` like any other call. `llmdap` is true when the bridge answered at least one of them (any HTTP status).
"""
from . import llmdap, retrieval
from .gate import Actor

PURPOSE = "health"
DEPENDENCIES = ("db", "llmdap", "embedding", "rerank", "chat")


def _probe(call) -> bool | None:
    if call is None:
        return None
    try:
        call()
    except llmdap.EgressError:
        return False
    return True


def check(conn, actor: Actor, bridge: llmdap.Bridge | None, model: str | None,
          stages: retrieval.Stages) -> dict:
    """The dependency map and `ok` (every configured dependency is up). `conn` is open, so `db` is true."""
    embedder, reranker = stages.embedder, stages.reranker
    out = {
        "db": conn.execute("SELECT true").fetchone()[0],
        "embedding": _probe(None if embedder is None else lambda: llmdap.embed(
            conn, embedder, actor, [PURPOSE], source_books=[], purpose=PURPOSE)),
        "rerank": _probe(None if reranker is None else lambda: llmdap.rerank(
            conn, reranker, actor, PURPOSE, [PURPOSE, "ok"], source_books=[], purpose=PURPOSE)),
        "chat": _probe(None if bridge is None or not model else lambda: llmdap.chat(
            conn, bridge, actor, model=model, messages=[{"role": "user", "content": "ok"}], source_books=[],
            purpose=PURPOSE, options={"max_tokens": 1})),
    }
    probed = [name for name in ("embedding", "rerank", "chat") if out[name] is not None]
    out["llmdap"] = None if not probed else conn.execute(
        "SELECT EXISTS (SELECT 1 FROM model_call WHERE correlation_id = %s AND http_status IS NOT NULL)",
        (actor.correlation_id,)).fetchone()[0]
    result = {name: out[name] for name in DEPENDENCIES}
    return {"ok": all(v is not False for v in result.values()), **result}
