"""Personal-data and fleet-data findings (G35, docs/26 §6) for `kstd-init` and ingest.

A finding is a labelling question, not a credential leak: it never refuses a book by itself. `kstd-init` proposes
`personal_data: unknown` for a file with a finding (never `no`), ingest records the findings in the publication,
and both list them for the operator (catalog.py, cli.py). Only a book policy that sends passages to cloud models
(`egress: cloud_ok`) refuses an open finding; the operator accepts a reviewed one with `--accept-finding`, as for
a credential finding (source.AcceptedFinding).

The rules, tuned for a low false-positive rate:
- `private-ipv4`: RFC 1918 (10/8, 172.16/12, 192.168/16) and shared address space (100.64/10, for example a
  tailnet). Not a finding: a version (after `v`, `version`, `release`, `==` …), a dotted number with more than four
  parts (an OID), the base address of these blocks (`10.0.0.0/8` in a firewall rule), loopback, link-local,
  the RFC 5737 documentation ranges and public addresses;
- `private-ipv6`: unique local addresses (fc00::/7) except the block bases; not loopback, link-local or the RFC 3849
  documentation prefix;
- `email`: an address, except RFC 2606/6761 reserved names (`example.com`, `*.example`, `*.test`, `*.invalid`,
  `*.localhost`), no-reply service addresses, an ssh remote (`git@github.com:org/repo`, `ssh://git@host/`) and a
  file name (`icon@2x.png`);
- `phone`: an international number (`+` and 8–15 digits, not grouped in threes like an amount), a `tel:` URI, or a
  number after a phone word (`tel`, `phone`, `telefon`, `gsm`, `mobile`, `cep`, `fax` …);
- `listed-name`: a name of a deny-list file (customers, sites), case-insensitive, whole words (load_names).

A finding gives the line and the rule only, never the matched text: the text is the personal data.
"""
import ipaddress
import re
from pathlib import Path

from .secretscan import Finding

PRIVATE_IPV4, PRIVATE_IPV6, EMAIL, PHONE, LISTED_NAME = (
    "private-ipv4", "private-ipv6", "email", "phone", "listed-name")
RULES = frozenset({PRIVATE_IPV4, PRIVATE_IPV6, EMAIL, PHONE, LISTED_NAME})
MIN_NAME_CHARS = 3

_V4_NETS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))
_V6_NET = ipaddress.ip_network("fc00::/7")
_BASES = frozenset({*(n.network_address for n in _V4_NETS), ipaddress.ip_address("fc00::"),
                    ipaddress.ip_address("fd00::")})
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")
_VERSION_BEFORE = re.compile(r"(?i)(?:\bv|\bver|\bversion|\brelease|\bbuild|\brev|==)\s*[:=]?\s*\Z")
_IPV6 = re.compile(r"(?i)(?<![\w:.])f[cd][0-9a-f]{2}(?::[0-9a-f]{0,4}){1,7}(?![\w:])")
_EMAIL = re.compile(r"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@"
                    r"((?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24})(?![\w-]|\.\w)")
_RESERVED = ("example.com", "example.net", "example.org")
_RESERVED_TLDS = ("example", "test", "invalid", "localhost")
_NO_REPLY = re.compile(r"(?i)\A(?:no-?reply|do-?not-?reply|mailer-daemon)\Z")
_FILE_TLDS = frozenset({"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "pdf", "js", "ts", "py", "md", "json",
                        "yaml", "yml", "css", "html", "txt", "zip"})
_INTERNATIONAL = re.compile(r"(?<![\w+.])\+[1-9]\d{0,2}(?:[ .-]?\(?\d{1,4}\)?){1,6}(?!\w|[.,]\d)")
_PHONE_WORD = re.compile(r"(?i)\b(?:tel|tél|phone|telephone|telefon|telefonu|gsm|mobile?|mobil|cep|fax|faks)\b"
                         r"(?:[^\S\n]*(?:no|nr|number|numarası|numarasi)\b)?\.?[^\S\n]*[:=]?[^\S\n]*"
                         r"(?P<n>\(?\+?\d[\d ()./-]{5,}\d)(?!\w|[.,]\d)")


def load_names(path: Path) -> re.Pattern:
    """The deny-list file: one name per line (a customer, a site); `#` starts a comment line. Whitespace inside a
    name matches any whitespace. Raises ValueError for a file with no names or a name shorter than 3 characters."""
    names = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        name = " ".join(line.split())
        if not name or name.startswith("#"):
            continue
        if len(name) < MIN_NAME_CHARS:
            raise ValueError(f"{path}: line {n}: a name needs at least {MIN_NAME_CHARS} characters")
        names.append(name)
    if not names:
        raise ValueError(f"{path}: no names")
    alternatives = "|".join(r"\s+".join(map(re.escape, name.split())) for name in sorted(set(names), key=len,
                                                                                            reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def _private_ipv4(text: str, m: re.Match) -> bool:
    if any(len(o) > 1 and o.startswith("0") for o in m.group().split(".")):
        return False
    if _VERSION_BEFORE.search(text, max(0, m.start() - 12), m.start()):
        return False
    try:
        address = ipaddress.IPv4Address(m.group())
    except ValueError:
        return False
    return address not in _BASES and any(address in net for net in _V4_NETS)


def _private_ipv6(m: re.Match) -> bool:
    try:
        address = ipaddress.IPv6Address(m.group())
    except ValueError:
        return False
    return address not in _BASES and address in _V6_NET


def _email(text: str, m: re.Match) -> bool:
    local, domain = m.group().split("@", 1)
    domain = domain.casefold()
    if domain in _RESERVED or domain.endswith(tuple("." + d for d in _RESERVED)) \
            or domain.rsplit(".", 1)[-1] in _RESERVED_TLDS or domain.rsplit(".", 1)[-1] in _FILE_TLDS:
        return False
    if _NO_REPLY.match(local) or "noreply" in domain or "no-reply" in domain:
        return False
    return not (text.startswith(":", m.end()) or text.endswith("://", 0, m.start()))


def _digits(number: str) -> str:
    return re.sub(r"\D", "", number)


def _international(m: re.Match) -> bool:
    digits, groups = _digits(m.group()), re.findall(r"\d+", m.group())
    amount = len(groups) > 2 and all(len(g) == 3 for g in groups[1:])  # +10 000 000: an amount, not a number
    return 8 <= len(digits) <= 15 and not amount


def findings(text: str, names: re.Pattern | None = None) -> list[Finding]:
    """Every personal-data or fleet-data match in the text, one per line and rule (never the matched text)."""
    hits = [(PRIVATE_IPV4, m.start()) for m in _IPV4.finditer(text) if _private_ipv4(text, m)]
    hits += [(PRIVATE_IPV6, m.start()) for m in _IPV6.finditer(text) if _private_ipv6(m)]
    hits += [(EMAIL, m.start()) for m in _EMAIL.finditer(text) if _email(text, m)]
    hits += [(PHONE, m.start()) for m in _INTERNATIONAL.finditer(text) if _international(m)]
    hits += [(PHONE, m.start("n")) for m in _PHONE_WORD.finditer(text) if 7 <= len(_digits(m["n"])) <= 15]
    if names is not None:
        hits += [(LISTED_NAME, m.start()) for m in names.finditer(text)]
    return sorted({Finding(text.count("\n", 0, at) + 1, rule) for rule, at in hits})
