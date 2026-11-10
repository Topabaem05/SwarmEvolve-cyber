#!/usr/bin/env python3
"""Size and staff a red-team round from the codebase itself.

    teamplan.py plan --target REPO [--round N] [--min-team 30] [--max-team 120]
                     [--weight-per-hunter 2500] [--critic-ratio 3] [--max-concurrency 30]
                     [--board-root RUN --previous PLAN.json] [--out PLAN.json]

The team is not a fixed number. It is derived from work units, and the unit list grows and shrinks
with the code and with what earlier rounds found:

    seam units      one per seam in the domain registry
    deferred units  coverage units an earlier run recorded as not investigated
    lead units      leads other agents posted on the board that nobody owns yet      (--board-root)
    shard units     the in-scope source, cut into pieces of bounded weight, where
                    weight = lines + risk_weight x (number of risky-sink pattern hits)

    hunters             = number of units kept this round (+ second opinions, see below)
    critics             = ceil(hunters / critic_ratio)
    chain investigators = min(chain-candidate groups, chain_top_k)
    team                = hunters + critics + chain investigators

Floor and ceiling:

- If the team is below --min-team (default 30), independent second-opinion hunters are added to the
  highest-priority units until the floor is met. Repeated independent passes find things one pass misses.
- If the team is above --max-team, the lowest-priority shard units are deferred and listed in the plan.
  Nothing is dropped silently.

This tool only plans. It starts no agent and reads no file outside the target and the run directory.
Standard library only.
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

DEFAULT_SCOPE = ("benchmarks", "baselines")
DEFAULT_EXCLUDE = ("/examples/", "/tests/", "/docs/", "/assets/", "/node_modules/", "/problems/eoh-problems/")
CODE_SUFFIXES = (".py", ".js", ".ts", ".html", ".sh", ".yml", ".yaml")
CODE_NAMES = ("Dockerfile", "Makefile")
MAX_FILE_BYTES = 4 * 1024 * 1024

# Places where lower-trust input usually meets a sensitive operation. A hit is a reason to look, not a finding.
RISK_PATTERNS = [re.compile(p) for p in (
    r"pickle\.loads?\(|cloudpickle|dill\.|np\.load\(|yaml\.(?:unsafe_)?load\(",
    r"\beval\(|\bexec\(|__import__\(|importlib|spec_from_file_location|compile\(",
    r"subprocess\.|os\.system\(|shell=True|create_subprocess",
    r"innerHTML|outerHTML|document\.write|insertAdjacentHTML|marked\.parse",
    r"@\w+\.(?:route|get|post)\(|do_GET|do_POST|BaseHTTPRequestHandler|app\.run\(",
    r"os\.path\.join\(|send_file|send_from_directory|\bopen\(",
    r"tempfile\.|gettempdir|sys\.path\.insert",
    r"requests\.|httpx\.|urllib\.request|verify(?:_ssl)?\s*[=:]\s*False",
    r"os\.environ|load_dotenv|getenv\(",
    r"sqlite3\.|\.execute\(",
    r"secrets\.|pull_request_target|issue_comment|id-token",
)]

# Mean tokens one agent used in audit run-1 (seven hunters: 201k-321k). An estimate, not a quote.
TOKENS_PER_AGENT_RUN1 = 245_000


def list_files(target, scope, exclude):
    target = Path(target)
    try:
        out = subprocess.run(["git", "-C", str(target), "ls-files", "-z", "--", *scope], capture_output=True,
                             check=True).stdout.decode("utf-8", "replace")
        names = [n for n in out.split("\0") if n]
    except (OSError, subprocess.CalledProcessError):
        names = []
        for s in scope:
            for root, dirs, files in os.walk(target / s):
                dirs[:] = sorted(d for d in dirs if d != ".git")
                names += [str(Path(root, f).relative_to(target)) for f in sorted(files)]
    keep = []
    for n in sorted(set(names)):
        probe = "/" + n
        if any(x in probe for x in exclude):
            continue
        if n.endswith(CODE_SUFFIXES) or Path(n).name in CODE_NAMES:
            keep.append(n)
    return keep


def measure(target, names, risk_weight):
    files = []
    for n in names:
        p = Path(target) / n
        try:
            if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        loc = sum(1 for line in text.splitlines() if line.strip())
        hits = sum(len(rx.findall(text)) for rx in RISK_PATTERNS)
        files.append({"path": n, "loc": loc, "risk_hits": hits, "weight": loc + risk_weight * hits})
    return files


def subsystem_of(path):
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def make_shards(files, budget):
    """Pack files into shards of at most `budget` weight without mixing subsystems or splitting directories
    more than needed. A file heavier than the budget becomes several line-range shards of its own."""
    shards = []

    def close(current):
        if current["files"]:
            shards.append(current)

    by_sub = {}
    for f in files:
        by_sub.setdefault(subsystem_of(f["path"]), []).append(f)
    for sub in sorted(by_sub):
        current = {"subsystem": sub, "files": [], "weight": 0, "loc": 0, "risk_hits": 0}
        for f in sorted(by_sub[sub], key=lambda x: (os.path.dirname(x["path"]), x["path"])):
            if f["weight"] > budget:
                close(current)
                current = {"subsystem": sub, "files": [], "weight": 0, "loc": 0, "risk_hits": 0}
                parts = math.ceil(f["weight"] / budget)
                step = math.ceil(max(f["loc"], 1) / parts)
                for i in range(parts):
                    shards.append({"subsystem": sub, "files": [f["path"]], "weight": math.ceil(f["weight"] / parts),
                                   "loc": math.ceil(f["loc"] / parts), "risk_hits": math.ceil(f["risk_hits"] / parts),
                                   "part": f"{i + 1}/{parts}",
                                   "approx_nonblank_line_range": [i * step + 1, min((i + 1) * step, f["loc"])]})
                continue
            if current["files"] and current["weight"] + f["weight"] > budget:
                close(current)
                current = {"subsystem": sub, "files": [], "weight": 0, "loc": 0, "risk_hits": 0}
            current["files"].append(f["path"])
            for k in ("weight", "loc", "risk_hits"):
                current[k] += f[k]
        close(current)
    return shards


def slug(text, limit=28):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].strip("-") or "x"


def load_json(path):
    if not path or not Path(path).is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_units(target, files, shards, registry, ledger, board_entries):
    """Return hunting units in priority order: seams, board leads, deferred units, then shards by risk density."""
    units = []
    for s in (registry or {}).get("seams", []):
        paths = sorted({loc.rsplit(":", 1)[0] for loc in s.get("candidate_locations", [])})
        units.append({"unit_id": s["seam_id"], "kind": "seam", "priority": 0, "title": s.get("hypothesis", ""),
                      "topics": [s["seam_id"]] + s.get("invariant_ids", []), "starting_paths": paths})
    owned = {t for u in units for t in u["topics"]}
    for e in board_entries:
        if e.get("kind") == "lead" and not (set(e["topics"]) & owned):
            uid = "LEAD-" + e["id"]
            units.append({"unit_id": uid, "kind": "lead", "priority": 0, "title": e["text"][:200],
                          "topics": e["topics"], "starting_paths": sorted({r.rsplit(":", 1)[0] for r in e["refs"]}),
                          "raised_by": e["agent"]})
            owned |= set(e["topics"])
    for u in ledger or []:
        if u.get("status") != "deferred":
            continue
        uid = "DEFERRED-" + hashlib.sha256(u["coverage_id"].encode()).hexdigest()[:8]
        units.append({"unit_id": uid, "kind": "deferred", "priority": 1, "title": u.get("surface", ""),
                      "topics": [uid], "starting_paths": u.get("starting_paths", []),
                      "attack_class": u.get("attack_class")})
    shard_units = []
    for i, sh in enumerate(sorted(shards, key=lambda s: (s["subsystem"], s["files"][0], s.get("part", "")))):
        uid = f"SHARD-{i + 1:03d}"
        density = sh["risk_hits"] / max(sh["loc"], 1)
        unit = {"unit_id": uid, "kind": "shard", "priority": 2, "title": f"{sh['subsystem']}: {len(sh['files'])} file(s)",
                "topics": [uid], "starting_paths": sh["files"], "loc": sh["loc"], "risk_hits": sh["risk_hits"],
                "risk_density": round(density, 4), "subsystem": sh["subsystem"]}
        for k in ("part", "approx_nonblank_line_range"):
            if k in sh:
                unit[k] = sh[k]
        shard_units.append(unit)
    shard_units.sort(key=lambda u: (-u["risk_density"], -u["risk_hits"], u["unit_id"]))
    return units + shard_units


def chain_groups(chains, mode):
    groups = {}
    for c in (chains or {}).get("candidates", []):
        if mode == "ready-only" and c["status"] != "ready_for_chain_review":
            continue
        groups.setdefault(c["ordered_node_ids"][0], []).append(c)
    return groups


def completed_units(previous, board_root):
    """Units whose hunter left a result file in the run directory during an earlier round."""
    done = set()
    if not previous or not board_root:
        return done
    for a in previous.get("agents", []):
        if a["role"] == "hunter" and (Path(board_root) / "agents" / a["agent_id"] / "scratch" / "result.json").is_file():
            done.add(a["unit"]["unit_id"])
    return done


def plan(target, round_no=1, min_team=30, max_team=120, weight_per_hunter=2500, risk_weight=40, critic_ratio=3,
         chain_top_k=8, chain_mode="include-blocked", max_concurrency=30, scope=DEFAULT_SCOPE,
         exclude=DEFAULT_EXCLUDE, registry=None, ledger=None, chains=None, board_entries=(), done=()):
    if min_team > max_team:
        raise ValueError("--min-team is larger than --max-team")
    if min(min_team, weight_per_hunter, critic_ratio, max_concurrency) < 1:
        raise ValueError("sizes and ratios must be positive")
    files = measure(target, list_files(target, scope, exclude), risk_weight)
    shards = make_shards(files, weight_per_hunter)
    units = [u for u in build_units(target, files, shards, registry, ledger, list(board_entries))
             if u["unit_id"] not in set(done)]
    groups = chain_groups(chains, chain_mode)
    chain_n = min(len(groups), chain_top_k)

    def team(h):
        return h + math.ceil(h / critic_ratio) + chain_n

    kept, deferred = list(units), []
    while kept and team(len(kept)) > max_team:
        # Defer from the end of the priority order. Seams, leads and deferred units go last.
        deferred.insert(0, kept.pop())
    hunters = [{"unit": u, "second_opinion": False} for u in kept]
    reason = "demand within limits"
    if deferred:
        reason = f"demand exceeded --max-team; {len(deferred)} lowest-priority unit(s) deferred"
    extra = 0
    while kept and team(len(hunters)) < min_team:
        hunters.append({"unit": kept[extra % len(kept)], "second_opinion": True})
        extra += 1
    if extra:
        reason = f"demand below --min-team; {extra} independent second-opinion hunter(s) added to the highest-priority units"

    agents, seen_ids = [], set()

    def add(agent_id, role, **fields):
        agent_id = agent_id[:64].rstrip("-_")
        if not AGENT_RE.match(agent_id) or agent_id in seen_ids:
            raise ValueError(f"bad or duplicate agent id: {agent_id}")
        seen_ids.add(agent_id)
        agents.append({"agent_id": agent_id, "role": role, **fields})
        return agent_id

    first_owner = {}
    for i, h in enumerate(hunters, 1):
        u = h["unit"]
        aid = f"r{round_no}-h{i:03d}-{slug(u['unit_id'])}"
        fields = {"unit": u, "brief": "security/redteam/briefs/hunter-brief-v2.md", "subscribe_topics": u["topics"]}
        if h["second_opinion"]:
            fields["second_opinion_of"] = first_owner[u["unit_id"]]
            fields["note"] = "Work this unit independently. Write your own ledger before reading the first owner's board entries."
        else:
            first_owner[u["unit_id"]] = aid
        add(aid, "hunter", **fields)
    hunter_ids = [a["agent_id"] for a in agents]
    critics_n = math.ceil(len(hunter_ids) / critic_ratio)
    for i in range(critics_n):
        add(f"r{round_no}-c{i + 1:03d}", "critic", reviews=hunter_ids[i::critics_n],
            brief="security/redteam/briefs/critic-brief.md")
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:chain_n]
    for i, (first, cands) in enumerate(ranked, 1):
        add(f"r{round_no}-k{i:03d}-{slug(first)}", "chain-planner", first_node=first,
            chain_ids=[c["chain_id"] for c in cands],
            task="Check each binding from source: is the capability the provider gains exactly what the consumer requires "
                 "(same object, principal and origin)? Source only; nothing is executed.")

    def waves(role):
        ids = [a["agent_id"] for a in agents if a["role"] == role]
        return [ids[i:i + max_concurrency] for i in range(0, len(ids), max_concurrency)]

    by_sub = {}
    for f in files:
        s = by_sub.setdefault(subsystem_of(f["path"]), {"files": 0, "loc": 0, "risk_hits": 0})
        s["files"] += 1
        s["loc"] += f["loc"]
        s["risk_hits"] += f["risk_hits"]
    total = len(agents)
    return {
        "schema_version": "1.0",
        "round": round_no,
        "note": "A plan only. No agent was started. Shard boundaries and risk hits are heuristics for dividing work, not findings.",
        "model_policy": {"mode": "same-model", "note": "Every agent of the round runs on the one model the operator selected. Agent entries carry no model field, and the runner rejects a plan that adds one."},
        "codebase": {"files": len(files), "loc": sum(f["loc"] for f in files),
                     "risk_hits": sum(f["risk_hits"] for f in files), "by_subsystem": dict(sorted(by_sub.items()))},
        "parameters": {"min_team": min_team, "max_team": max_team, "weight_per_hunter": weight_per_hunter,
                       "risk_weight": risk_weight, "critic_ratio": critic_ratio, "chain_top_k": chain_top_k,
                       "chain_mode": chain_mode, "max_concurrency": max_concurrency, "scope": list(scope),
                       "exclude": list(exclude)},
        "demand": {"seam_units": sum(1 for u in units if u["kind"] == "seam"),
                   "lead_units": sum(1 for u in units if u["kind"] == "lead"),
                   "deferred_units": sum(1 for u in units if u["kind"] == "deferred"),
                   "shard_units": sum(1 for u in units if u["kind"] == "shard"),
                   "chain_groups": len(groups), "units_completed_earlier": len(set(done))},
        "sizing": {"hunters": len(hunter_ids), "second_opinion_hunters": extra, "critics": critics_n,
                   "chain_investigators": len(ranked), "team": total, "reason": reason,
                   "rough_token_estimate": total * TOKENS_PER_AGENT_RUN1,
                   "token_estimate_basis": f"{TOKENS_PER_AGENT_RUN1} tokens per agent, the mean of the seven run-1 hunters"},
        "phases": [{"phase": "hunt", "waves": waves("hunter")},
                   {"phase": "critique", "waves": waves("critic"), "after": "hunt"},
                   {"phase": "chain", "waves": waves("chain-planner"), "after": "critique"}],
        "agents": agents,
        "deferred_units": deferred,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan")
    s.add_argument("--target", required=True)
    s.add_argument("--round", type=int, default=1)
    s.add_argument("--min-team", type=int, default=30)
    s.add_argument("--max-team", type=int, default=120)
    s.add_argument("--weight-per-hunter", type=int, default=2500)
    s.add_argument("--risk-weight", type=int, default=40)
    s.add_argument("--critic-ratio", type=int, default=3)
    s.add_argument("--chain-top-k", type=int, default=8)
    s.add_argument("--chain-mode", choices=("include-blocked", "ready-only"), default="include-blocked")
    s.add_argument("--max-concurrency", type=int, default=30)
    s.add_argument("--scope", action="append")
    s.add_argument("--exclude", action="append")
    s.add_argument("--registry")
    s.add_argument("--ledger")
    s.add_argument("--chains")
    s.add_argument("--board-root", help="run directory; unowned leads on the board become units")
    s.add_argument("--previous", help="plan of the previous round; units with a result file are not planned again")
    s.add_argument("--out")
    args = p.parse_args()

    target = Path(args.target).resolve()
    base = target / "security" / "redteam" / "registry"
    registry = load_json(args.registry or base / "domain-invariant-registry.json")
    chains = load_json(args.chains or base / "chain-candidates.json")
    ledger = load_json(args.ledger or target / "security" / "audit" / "run-1" / "coverage-ledger.json")
    entries, done = [], set()
    if args.board_root:
        sys.path.insert(0, str(HERE))
        import board  # noqa: E402  (sibling module)
        entries = board.load_all(args.board_root)[0]
        done = completed_units(load_json(args.previous), args.board_root)
    try:
        result = plan(target, args.round, args.min_team, args.max_team, args.weight_per_hunter, args.risk_weight,
                      args.critic_ratio, args.chain_top_k, args.chain_mode, args.max_concurrency,
                      tuple(args.scope or DEFAULT_SCOPE), tuple(args.exclude or DEFAULT_EXCLUDE),
                      registry, ledger, chains, entries, done)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write("\n")
    c, d, z = result["codebase"], result["demand"], result["sizing"]
    print(f"codebase : {c['files']} files, {c['loc']} non-blank lines, {c['risk_hits']} risky-sink pattern hits")
    print(f"units    : {d['seam_units']} seam + {d['lead_units']} lead + {d['deferred_units']} deferred + "
          f"{d['shard_units']} shard, {d['chain_groups']} chain group(s), {d['units_completed_earlier']} done earlier")
    print(f"team     : {z['team']} = {z['hunters']} hunters ({z['second_opinion_hunters']} second opinion) + "
          f"{z['critics']} critics + {z['chain_investigators']} chain investigators")
    print(f"why      : {z['reason']}")
    print(f"deferred : {len(result['deferred_units'])} unit(s)")
    print(f"waves    : " + ", ".join(f"{ph['phase']} {[len(w) for w in ph['waves']]}" for ph in result["phases"]))
    print(f"estimate : about {z['rough_token_estimate'] / 1e6:.1f}M tokens ({z['token_estimate_basis']})")


if __name__ == "__main__":
    main()
