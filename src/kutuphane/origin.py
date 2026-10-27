"""Origin from the write path (D70; docs/24 §5). The server computes it; a client can only ask for a lower value.

R2: an agent path (an `agent:` principal, a user acted for, or the MCP channel) is `model`. R4/R6: anything else (a
`user:` principal without `act`, over HTTP) is `unknown` in R1. R1 never stores `human`: a token is not a person's
act on exact bytes; `human` comes only from the later R3 passkey confirmation. `unknown` is handled as `model`.
"""
from .gate import Actor
from .kstd import ORIGINS

REFUSED = "origin-claim-refused"
STORED = ("model", "unknown")  # lowest first: the shown origin of a note is the lowest over its propose writes


def computed(actor: Actor) -> str:
    direct_user = actor.principal.startswith("user:") and actor.on_behalf_of is None and actor.channel == "http"
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
    """The shown origin of a note: the lowest of the stored origins of its propose writes (model < unknown)."""
    present = set(origins)
    return next((o for o in STORED if o in present), None)
