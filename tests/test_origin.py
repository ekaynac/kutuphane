"""D70 in R1 (docs/24 §5): the server computes origin from the write path; R1 never stores `human`."""
import pytest

from kutuphane import origin
from kutuphane.gate import Actor

U, A = "user:ayse", "agent:kobra-7"


@pytest.mark.parametrize("actor", [Actor(A, channel="mcp"), Actor(A, channel="http"), Actor(A, U, channel="mcp"),
                                   Actor(A, U, channel="http"), Actor(U, channel="mcp")])
def test_agent_paths_store_model(actor):  # R2
    assert origin.compute(actor, None) == ("model", None)


def test_a_direct_user_write_over_http_is_unknown_never_human():  # R4/R6 (T3)
    actor = Actor(U, channel="http", client_id="kutuphane-ui")  # a UI client id is not a human act
    assert origin.compute(actor, None) == ("unknown", None)
    assert origin.compute(actor, "human") == ("unknown", origin.REFUSED)
    assert origin.compute(actor, "model") == ("model", None)  # a lower value is always allowed
    assert origin.compute(actor, "unknown") == ("unknown", None)


@pytest.mark.parametrize("requested", ["human", "assisted", "tool"])
def test_higher_claims_are_refused_with_a_notice(requested):  # T2
    assert origin.compute(Actor(A, channel="mcp"), requested) == ("model", origin.REFUSED)


def test_unknown_on_an_agent_path_stays_model():
    assert origin.compute(Actor(A, U, channel="mcp"), "unknown") == ("model", None)


def test_unknown_values_are_refused():
    with pytest.raises(ValueError):
        origin.compute(Actor(A, channel="mcp"), "person")


def test_the_shown_origin_is_the_lowest():
    assert origin.lowest(["unknown", "model"]) == "model"
    assert origin.lowest(["unknown"]) == "unknown"
    assert origin.lowest([]) is None
