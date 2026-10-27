"""G35 (docs/26 §6): personal-data and fleet-data findings. They propose `personal_data: unknown` and are listed for
the operator; they are a labelling question, so they never refuse a local book. Every text here is invented."""
import pytest

from kutuphane import datascan
from kutuphane.datascan import Finding


def rules(text, names=None):
    return [(f.line, f.rule) for f in datascan.findings(text, names)]


@pytest.mark.parametrize("text", [
    "The router is at 10.20.30.40.",
    "ssh admin@192.168.7.12 -p 22",
    "upstream http://172.20.1.5:8080/health",
    "subnet 192.168.44.0/24 for the cameras",
    "the tailnet node 100.101.102.103",
])
def test_a_private_ipv4_address_is_a_finding(text):
    assert rules(text) == [(1, "private-ipv4")]


@pytest.mark.parametrize("text", [
    "Release 10.2.3.4 fixes the bug.",            # a version after a version word
    "pip install tool==10.1.0.2",                 # a version pin
    "version: 192.168.1.1",                       # a version field
    "v10.0.0.1",                                  # a version with a v
    "OID 1.3.6.1.4.1.2021.10.1.3.1",              # an OID, not an address
    "Windows 10.0.19041.1",                       # octets above 255
    "a.10.0.0.5",                                 # part of a dotted name
    "Allow 10.0.0.0/8, 172.16.0.0/12 and 192.168.0.0/16.",  # the RFC 1918 blocks themselves
    "Docs: 192.0.2.10, 198.51.100.7, 203.0.113.99",  # RFC 5737 documentation ranges
    "Loopback 127.0.0.1 and ::1",                 # loopback
    "Public 8.8.8.8 and 1.1.1.1",                 # public addresses are not fleet data here
    "link-local 169.254.169.254",                 # the cloud metadata address in every guide
])
def test_versions_documentation_ranges_and_loopback_are_not_findings(text):
    assert rules(text) == []


def test_a_unique_local_ipv6_address_is_a_finding_and_the_documentation_prefix_is_not():
    assert rules("node fd12:3456:789a::17 is the gateway") == [(1, "private-ipv6")]
    assert rules("ULA FC00:1234:5678:9abc::1") == [(1, "private-ipv6")]
    assert rules("doc 2001:db8::1, loopback ::1, block fd00::/8, link fe80::1, MAC fc:aa:14:00:00:01") == []


@pytest.mark.parametrize("text,found", [
    ("Contact jane.doe@firma.com.tr for access.", True),
    ("Mail <ops+alerts@site-a.net>", True),
    ("user@host.local", True),
    ("Issuer: ACME <kb@acme.example>", False),        # RFC 2606 reserved names
    ("mail me at someone@example.com", False),
    ("Co-Authored-By: Claude <noreply@anthropic.com>", False),  # a no-reply service address
    ("123+bot@users.noreply.github.com", False),
    ("git clone git@github.com:org/repo.git", False),  # an ssh remote, not a mailbox
    ("ssh://git@gitlab.com/org/repo", False),
    ("icon@2x.png", False),                           # a file name
    ("npm i @scope/pkg@1.2.3", False),
])
def test_email_addresses(text, found):
    assert rules(text) == ([(1, "email")] if found else [])


@pytest.mark.parametrize("text,found", [
    ("Call +90 532 123 45 67 after 18:00.", True),
    ("+1 (202) 555-0143", True),
    ("+4930123456", True),
    ("Tel: 0212 555 12 34", True),
    ("telefon numarası: 0 (312) 555 66 77", True),
    ("tel:+33-1-23-45-67-89", True),
    ("Fax 030 1234567", True),
    ("2026-10-27 14:00 +0300", False),           # a time zone offset
    ("The gain is +10 000 000 units.", False),    # a grouped number
    ("id 4930123456 and 0212 555 12 34", False),  # digits without a + or a phone word
    ("score +12.5", False),
    ("Phone support is closed.", False),
])
def test_phone_numbers(text, found):
    assert rules(text) == ([(1, "phone")] if found else [])


def test_listed_names_match_whole_words_case_insensitive(tmp_path):
    listed = tmp_path / "names.txt"
    listed.write_text("# customers and sites\n\nOrnek Lojistik\nSITE-K7\n  Kuzey  Depo  \n", encoding="utf-8")
    names = datascan.load_names(listed)
    text = "Intro\nThe ornek   lojistik link.\nSite-K7 rack 2\nSITE-K70 is another site\nkuzey depo\n"
    assert rules(text, names) == [(2, "listed-name"), (3, "listed-name"), (5, "listed-name")]
    assert rules(text) == []                       # no list, no name findings


def test_a_names_file_with_no_names_or_a_short_name_is_refused(tmp_path):
    empty, short = tmp_path / "empty.txt", tmp_path / "short.txt"
    empty.write_text("# nothing\n\n", encoding="utf-8")
    short.write_text("Ornek\nX\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no names"):
        datascan.load_names(empty)
    with pytest.raises(ValueError, match="line 2"):
        datascan.load_names(short)


def test_findings_give_the_line_and_the_rule_never_the_text():
    text = "a\nmail ops@site-a.net\nip 10.1.2.3 and 10.1.2.4\n"
    assert datascan.findings(text) == [Finding(2, "email"), Finding(3, "private-ipv4")]  # one per line and rule
    assert all(set(vars(f)) == {"line", "rule"} for f in datascan.findings(text))
