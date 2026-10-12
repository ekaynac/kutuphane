"""Book policy (D24): the mandatory governance axes, validated before anything is stored.

E5 is two separate attributes (sensitivity, egress). E8 protection accepts only `standard` in M1 (D33).
E9 access modes belong to grants, not to the book, and arrive with the authorization slice (M1b).
"""
SENSITIVITY = ("normal", "restricted")
EGRESS = ("local_only", "cloud_ok")
PROTECTION_M1 = ("standard",)
POLICY_VERSION = 1


class PolicyError(ValueError):
    pass


def make_policy(*, sensitivity: str, egress: str, protection: str) -> dict:
    for name, value, allowed in (("sensitivity", sensitivity, SENSITIVITY), ("egress", egress, EGRESS),
                                 ("protection", protection, PROTECTION_M1)):
        if value not in allowed:
            raise PolicyError(f"{name} must be one of {', '.join(allowed)} (got {value!r})")
    if sensitivity == "restricted" and egress == "cloud_ok":
        raise PolicyError("restricted content cannot be cloud_ok")
    return {"v": POLICY_VERSION, "sensitivity": sensitivity, "egress": egress, "protection": protection}


def check_policy(doc) -> dict:
    """Re-validate a policy document at the shared write boundary (catalog.publish), not only in the CLI."""
    if not isinstance(doc, dict) or set(doc) != {"v", "sensitivity", "egress", "protection"} \
            or doc.get("v") != POLICY_VERSION:
        raise PolicyError("policy must be exactly {v, sensitivity, egress, protection} (D24: E5 and E8 mandatory)")
    return make_policy(sensitivity=doc["sensitivity"], egress=doc["egress"], protection=doc["protection"])
