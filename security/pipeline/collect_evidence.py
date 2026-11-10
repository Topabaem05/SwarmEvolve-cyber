#!/usr/bin/env python3
"""Copy verification evidence into the repository after checking it.

    python3 security/pipeline/collect_evidence.py <artifact-dir> <dest-dir>

The artifact is data produced by a run that executed PoC code, so it is not trusted as a directory
tree. Only `<slug>/<stamp>/result.json` files are taken, and only when each one is a regular file of
bounded size that parses as JSON with the fields the runner writes. Nothing else is copied.
"""
import json
import os
import re
import stat
import sys

MAX_BYTES = 2 * 1024 * 1024
MAX_FILES = 200
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
REQUIRED = ("fingerprint", "verdict", "reason", "attempts", "binding", "approval")
VERDICTS = ("reproduced", "not_reproduced", "inconclusive", "blocked")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dest = sys.argv[1], sys.argv[2]
    copied = 0
    for slug in sorted(os.listdir(src)):
        slug_dir = os.path.join(src, slug)
        if not NAME_RE.match(slug) or slug.startswith(".") or os.path.islink(slug_dir) or not os.path.isdir(slug_dir):
            continue
        for stamp in sorted(os.listdir(slug_dir)):
            leaf = os.path.join(slug_dir, stamp, "result.json")
            if not NAME_RE.match(stamp) or stamp.startswith(".") or os.path.islink(os.path.join(slug_dir, stamp)):
                continue
            try:
                fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError:
                continue
            with os.fdopen(fd, "rb") as f:
                st = os.fstat(f.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > MAX_BYTES:
                    print(f"skipped (not a bounded regular file): {slug}/{stamp}")
                    continue
                raw = f.read(MAX_BYTES + 1)
            try:
                record = json.loads(raw)
            except ValueError:
                print(f"skipped (not JSON): {slug}/{stamp}")
                continue
            if not isinstance(record, dict) or any(k not in record for k in REQUIRED) \
                    or record["verdict"] not in VERDICTS:
                print(f"skipped (unexpected shape): {slug}/{stamp}")
                continue
            if copied >= MAX_FILES:
                sys.exit(f"more than {MAX_FILES} evidence files; refusing to continue")
            out_dir = os.path.join(dest, slug, stamp)
            os.makedirs(out_dir, exist_ok=True)
            # Re-serialise instead of copying bytes, so the stored file is exactly the validated record.
            with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as out:
                json.dump(record, out, indent=2, ensure_ascii=False)
                out.write("\n")
            copied += 1
            print(f"recorded {record['verdict']:<15} {slug}/{stamp}")
    print(f"{copied} evidence file(s) recorded")


if __name__ == "__main__":
    main()
