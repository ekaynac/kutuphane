"""The LLM proposer schema (docs/21). Run: python -m pytest experiments/labeling_v5/test_llm_propose.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_propose  # noqa: E402

ANSWER = {"origin": "human", "review": "unknown", "personal_data": "yes", "instruction": "no", "hostile": "no",
          "activation_risk": "n/a", "normative": "history", "acceptance": "rejected", "review_confidence": "low",
          "personal_data_confidence": "high", "activation_risk_confidence": "high", "normative_confidence": "medium"}


def reply(answer: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(answer)}}]}


def test_rejected_is_an_acceptance_choice_with_its_definition():
    """D68: `rejected` (never accepted) is a separate state; before v5.2 the schema refused it."""
    assert llm_propose.parse(reply(ANSWER))["acceptance"] == "rejected"
    assert "rejected" in llm_propose.SYSTEM.split('"acceptance": "', 1)[1].split('"', 1)[0].split("|")
    assert "never accepted" in llm_propose.SYSTEM


def test_an_unlisted_acceptance_is_a_schema_error():
    try:
        llm_propose.parse(reply({**ANSWER, "acceptance": "obsolete"}))
    except llm_propose.SchemaError as exc:
        assert "acceptance" in str(exc)
    else:
        raise AssertionError("an unlisted acceptance value must not pass")
