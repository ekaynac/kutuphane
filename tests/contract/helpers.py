"""Two helpers of the contract scenario that must not be able to hang or to build a wrong connection string."""
import threading

from psycopg.conninfo import conninfo_to_dict, make_conninfo

STREAM_TIMEOUT = 15.0  # seconds a probe of a streaming endpoint may take to answer


def dsn_with_schema(dsn: str, schema: str) -> str:
    """The DSN with `-csearch_path=<schema>,public` added to its `options`. The DSN may be a URL (with or without a
    query) or key=value; existing parameters and existing `options` are kept. The result is in key=value form."""
    parts = conninfo_to_dict(dsn)
    option = f"-csearch_path={schema},public"
    parts["options"] = f"{parts['options']} {option}" if parts.get("options") else option
    return make_conninfo(**parts)


def stream_answer(client, method: str, path: str, headers: dict, *, timeout: float = STREAM_TIMEOUT) -> dict:
    """One request whose response may be an open event stream: {status, headers, body}, with a deadline.

    Starlette's TestClient hands the response over when the app has sent its headers and feeds the body through a
    zero-capacity stream, so an open event stream does not block the headers. That is a property of the TestClient
    version, so the request runs in a worker thread and fails with a clear message if it does not answer within
    `timeout`. An event stream that answers 2xx is closed without reading its body (`body` is None); any other
    response is read whole.
    """
    box: dict = {}

    def work():
        try:
            with client.stream(method, path, headers=headers) as r:  # leaving the block closes the stream
                answer = {"status": r.status_code, "headers": dict(r.headers), "body": None}
                if not (r.status_code < 400 and r.headers.get("content-type", "").startswith("text/event-stream")):
                    r.read()
                    answer["body"] = r.content
                box["answer"] = answer
        except BaseException as exc:  # reported in the calling thread
            box["error"] = exc

    worker = threading.Thread(target=work, daemon=True, name=f"probe {method} {path}")
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"{method} {path} did not answer within {timeout:g} s: the test client may buffer "
                           f"streaming responses, or the endpoint holds the request open")
    if "error" in box:
        raise box["error"]
    return box["answer"]
