"""The case matrix: for every MCP tool and every HTTP route, which kinds of case the scenario must run.

A kind that applies is written "run"; one that does not carries the reason. scenario.py records at least one case
for every kind that applies (and checks that its outcome fits the kind); test_contract.py fails when a tool or route
has no entry here, when a kind that applies has no recorded case, or when this file changes without its snapshot
(matrix.json): coverage cannot shrink silently.

MCP kinds: ok, not_found (also refused or forbidden), bad_request (also an argument the input schema refuses).
HTTP kinds (the mount at `/`, the MCP transport, too): the same, and unauthorized (no token: 401); for a GET route also head_ok and head_error: the same
request with HEAD, for the ok and for the main error case.
"""
RUN = "run"
MCP_KINDS = ("ok", "not_found", "bad_request")
HTTP_KINDS = ("ok", "not_found", "bad_request", "unauthorized")
HEAD_KINDS = ("head_ok", "head_error")


def _row(kinds, reasons):
    unknown = set(reasons) - set(kinds)
    assert not unknown, unknown
    return {kind: reasons.get(kind, RUN) for kind in kinds}


def tool(**reasons):
    return _row(MCP_KINDS, reasons)


def route(method, **reasons):
    return _row(HTTP_KINDS + (HEAD_KINDS if method == "GET" else ()), reasons)


NO_ARGUMENT = "no argument can be refused: the tool takes none"
EMPTY_IS_OK = "no such failure: a search that finds nothing is an ok result with an empty list"
OPAQUE_ID = "the id is an opaque path part: any unknown value is a not found"
PUBLIC = "public: needs no token and has nothing to refuse"
BODY_FREE = "takes no body and no parameter that can be wrong"

MCP = {
    "search_library": tool(not_found=EMPTY_IS_OK),
    "open_citation": tool(),
    "ask_library": tool(not_found="no such failure: an answer the library cannot support is an ok result "
                                  "(status not_in_library)"),
    "reopen_answer": tool(),
    "read_document": tool(),
    "list_books": tool(not_found="no such failure: a book the caller may not read is left out of the list",
                       bad_request=NO_ARGUMENT),
    "list_files": tool(),
    "job_status": tool(),
    "job_result": tool(),
    "job_cancel": tool(),
    "propose_note": tool(),
    "link_notes": tool(),
    "verify_citations": tool(),
    "query_notes": tool(not_found=EMPTY_IS_OK),
    "neighbours": tool(),
    "record_outcome": tool(),
    "confirm_origin": tool(),
    "submit_package": tool(),
    "package_status": tool(),
}

HTTP = {
    # the mount at `/`: the MCP endpoint (/mcp, every tool above is called through it) and the protected-resource
    # metadata; its cases are JSON-RPC calls without a tool, plus a body that is not JSON and a missing token
    "MOUNT /": route("MOUNT"),
    "GET /healthz": route("GET", not_found=PUBLIC, bad_request=PUBLIC, unauthorized=PUBLIC, head_error=PUBLIC),
    "GET /v1/whoami": route("GET", not_found=BODY_FREE, bad_request=BODY_FREE),
    "GET /v1/health": route("GET", not_found=BODY_FREE, bad_request=BODY_FREE),
    "GET /v1/search": route("GET", not_found=EMPTY_IS_OK),
    "GET /v1/citation": route("GET"),
    "POST /v1/ask": route("POST", not_found="no such failure: an answer the library cannot support is an ok result "
                                            "(status not_in_library)"),
    "GET /v1/answers/{answer_id}": route("GET", bad_request=OPAQUE_ID),
    "GET /v1/jobs/{job_id}": route("GET", bad_request=OPAQUE_ID),
    "GET /v1/jobs/{job_id}/result": route("GET", bad_request=OPAQUE_ID),
    "POST /v1/jobs/{job_id}/cancel": route("POST", bad_request=OPAQUE_ID),
    "GET /v1/files/{book}/{content_id}/{path:path}": route("GET", bad_request="every part is an opaque path part: "
                                                           "any unknown value is a not found"),
    "GET /v1/books": route("GET", not_found="no such failure: a book the caller may not read is left out of the "
                           "list", bad_request=BODY_FREE),
    "GET /v1/books/{book}/files": route("GET"),
    "POST /v1/notes": route("POST"),
    "POST /v1/notes/links": route("POST"),
    "GET /v1/notes": route("GET", not_found=EMPTY_IS_OK),
    "GET /v1/notes/{book}/{id}/neighbours": route("GET"),
    "GET /v1/notes/{book}/{id}/confirmation": route("GET"),
    "POST /v1/outcomes": route("POST"),
    "POST /v1/citations/verify": route("POST"),
    "POST /v1/packages": route("POST"),
    "GET /v1/packages/{import_id}": route("GET"),
}

# Lists that stay empty in a result, by the name of the field, and why. A list that is empty in a case named "(empty)"
# is that case's point and is not listed. test_contract.py fails for an empty list that is not here, and for an entry
# whose list is no longer empty.
EMPTY_COLLECTIONS = {
    "quoted_records": "needs a data-scanned record file (quotes.py) in the book; the fixture book has none",
    "candidates": "a candidate is a searchable, approved note with the same text; every note of the fixture is "
                  "pending, and approving one is a curator act",
    "left": "tombstones of notes that left the requested sets by a Standing change; the fixture has no curator "
            "decision on a note",
}


# --- the names of cases --------------------------------------------------------------------------------------------

def kind_of(name: str) -> str:
    inner = name.split("[", 1)[1].rstrip("]") if "[" in name else name.split(":", 1)[1]
    return inner.split(" ")[0]


def entry_of(name: str) -> str:
    """The matrix key of a case: the tool, or `METHOD route` (a HEAD case belongs to its GET route)."""
    if "[" in name:
        return ("GET " + name[5:] if name.startswith("HEAD ") else name).split(" [", 1)[0]
    return name.split(":", 1)[0]


def label(tool_or_route, kind, variant=None):
    name = kind + (f" ({variant})" if variant else "")
    return f"[{name}]" if " " in tool_or_route else f":{name}"


def empty_lists(value, field="<root>"):
    """The names of the fields that hold an empty list, anywhere in a shape."""
    if isinstance(value, list):
        return {field} if not value else set().union(*(empty_lists(v, field) for v in value))
    if isinstance(value, dict):
        return set().union(set(), *(empty_lists(v, field if k == "any_of" else k.rstrip("?")) for k, v in value.items()))
    return set()


def problems(tools: list[str], routes: list[dict], mcp: dict, http: dict) -> list[str]:
    """What is missing or wrong in the coverage; [] when the matrix and the recorded cases agree."""
    found = []
    wanted = {f"{m} {r['path']}" if "mount" not in r else f"MOUNT {r['path']}": 0 for r in routes
              for m in (r.get("methods") or ["MOUNT"]) if m != "HEAD"}
    for key in sorted(set(wanted) - set(HTTP)):
        found.append(f"route without a matrix entry: {key}")
    for key in sorted(set(HTTP) - set(wanted)):
        found.append(f"matrix entry of a route that does not exist: {key}")
    for key in sorted(set(tools) - set(MCP)):
        found.append(f"tool without a matrix entry: {key}")
    for key in sorted(set(MCP) - set(tools)):
        found.append(f"matrix entry of a tool that does not exist: {key}")
    for matrix, recorded, what in ((MCP, mcp, "tool"), (HTTP, http, "route")):
        kinds_run = {}
        for case in recorded:
            if entry_of(case) not in matrix:
                found.append(f"recorded case of no matrix entry: {case}")
                continue
            kinds_run.setdefault(entry_of(case), set()).add(kind_of(case))
        pairs = 0
        for entry, row in matrix.items():
            for kind, how in row.items():
                if how == RUN:
                    pairs += 1
                    if kind not in kinds_run.get(entry, ()):
                        found.append(f"{what} {entry}: no case of kind {kind}")
                elif kind in kinds_run.get(entry, ()):
                    found.append(f"{what} {entry}: a case of kind {kind}, which the matrix says does not apply")
        if len(recorded) < pairs:
            found.append(f"{what}s: {len(recorded)} recorded cases, fewer than the {pairs} kinds that apply")
    empty = set()
    for recorded in (mcp, http):
        for case, outcome in recorded.items():
            if "(empty)" not in case:
                empty |= empty_lists(outcome)
    for field in sorted(empty - set(EMPTY_COLLECTIONS)):
        found.append(f"an empty list in a result that the matrix does not explain: {field}")
    for field in sorted(set(EMPTY_COLLECTIONS) - empty):
        found.append(f"the matrix says {field} stays empty, but it has an element in every result")
    return found


def snapshot() -> dict:
    return {"mcp": MCP, "http": HTTP, "empty_collections": EMPTY_COLLECTIONS}
