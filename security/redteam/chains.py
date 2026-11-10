#!/usr/bin/env python3
"""Deterministic chain-candidate planner over a capability view of leads and primitives.

    chains.py plan --capabilities security/redteam/registry/capabilities.json [--out FILE]
                   [--max-length 4] [--max-successors 4] [--beam-width 64] [--max-candidates 200]

The method follows ZeroMDASH (docs/CHAIN.md): each node states the capabilities it requires and the
capabilities it gains; a chain is an ordered list of nodes in which every requirement is met by the
attacker's entry capabilities or by a capability an earlier node gained, and the last node has a
direct confidentiality, integrity or availability impact.

What this tool produces is a list of HYPOTHESES to investigate, never a finding:

- Matching is exact on (kind, scope) inside a fixed vocabulary. `custom` capabilities never match.
- A candidate lists the components that are not confirmed yet in `blocked_on`. Only a candidate whose
  components are all confirmed is `ready_for_chain_review`; the rest wait for validation first.
- The search is bounded, so the output is not exhaustive. Pruning is counted in the result.

Standard library only.
"""
import argparse
import hashlib
import json
import sys

AUTO_KINDS = frozenset((
    "controlled_request", "authenticated_session", "credential_access", "object_reference",
    "address_disclosure", "relative_file_read", "arbitrary_file_read", "relative_file_write",
    "arbitrary_file_write", "relative_memory_read", "arbitrary_memory_read", "relative_memory_write",
    "arbitrary_memory_write", "command_execution", "code_execution", "identity_impersonation",
    "privilege_gain", "sandbox_escape", "security_boundary_bypass", "denial_trigger",
))
CONFIRMED = ("confirmed", "confirmed_primitive", "standalone_finding")


def key(cap):
    """The identity used for automatic matching, or None when the capability may not auto-match."""
    if not isinstance(cap, dict) or cap.get("kind") not in AUTO_KINDS or not cap.get("scope"):
        return None
    return (cap["kind"], cap["scope"])


def validate(data):
    if not isinstance(data.get("entry_profiles"), dict) or not isinstance(data.get("nodes"), list):
        raise ValueError("capabilities file needs entry_profiles and nodes")
    ids = set()
    for n in data["nodes"]:
        for field in ("id", "status", "required_capabilities", "capabilities_gained"):
            if field not in n:
                raise ValueError(f"node missing {field}: {n.get('id')}")
        if n["id"] in ids:
            raise ValueError(f"duplicate node id: {n['id']}")
        ids.add(n["id"])
    return data


def chain_id(profile, node_ids):
    return "chain_" + hashlib.sha256(json.dumps([profile, node_ids]).encode()).hexdigest()[:16]


def plan(data, max_length=4, max_successors=4, beam_width=64, max_candidates=200):
    validate(data)
    nodes = sorted(data["nodes"], key=lambda n: n["id"])
    by_id = {n["id"]: n for n in nodes}
    candidates, pruned = [], {"beam": 0, "successors": 0, "candidates": 0}

    for profile in sorted(data["entry_profiles"]):
        entry = {k for k in (key(c) for c in data["entry_profiles"][profile]["capabilities"]) if k}
        # frontier item: (ordered node ids, {capability key: provider node id})
        frontier = [((), {})]
        for _ in range(max_length):
            nxt = []
            for path, provided in frontier:
                per_capability = {}  # successors already taken per consumed capability, for this path
                for n in nodes:
                    if n["id"] in path:
                        continue
                    reqs = [key(c) for c in n["required_capabilities"]]
                    if not reqs or any(r is None for r in reqs):
                        continue  # nothing to bind, or a requirement that may not auto-match
                    if not all(r in entry or r in provided for r in reqs):
                        continue
                    bindings = [{"consumer": n["id"], "required": list(r),
                                 "provider": provided[r] if r in provided else f"entry:{profile}"} for r in reqs]
                    # After the first node, a step must consume something an earlier node gained;
                    # otherwise it is an independent lead, not a link of this chain.
                    consumed = [r for r in reqs if r in provided]
                    if path and not consumed:
                        continue
                    # Cap the fan-out per consumed capability. Entry steps are not capped: every lead an
                    # attacker position reaches directly stays a possible first step.
                    if consumed and all(per_capability.get(r, 0) >= max_successors for r in consumed):
                        pruned["successors"] += 1
                        continue
                    for r in consumed:
                        per_capability[r] = per_capability.get(r, 0) + 1
                    new_path = path + (n["id"],)
                    new_provided = dict(provided)
                    for c in n["capabilities_gained"]:
                        k = key(c)
                        if k and k not in entry:
                            new_provided.setdefault(k, n["id"])
                    nxt.append((new_path, new_provided, bindings))
            if len(nxt) > beam_width:
                pruned["beam"] += len(nxt) - beam_width
                nxt = nxt[:beam_width]
            for new_path, new_provided, bindings in nxt:
                last = by_id[new_path[-1]]
                if len(new_path) >= 2 and last.get("terminal_impact"):
                    if len(candidates) >= max_candidates:
                        pruned["candidates"] += 1
                        continue
                    blocked = [i for i in new_path if by_id[i]["status"] not in CONFIRMED]
                    all_bindings = []
                    prov = {}
                    for i in new_path:  # rebuild the full binding list in order
                        node = by_id[i]
                        for c in node["required_capabilities"]:
                            k = key(c)
                            all_bindings.append({"consumer": i, "required": list(k),
                                                 "provider": prov.get(k, f"entry:{profile}")})
                        for c in node["capabilities_gained"]:
                            k = key(c)
                            if k and k not in entry:
                                prov.setdefault(k, i)
                    # Every node before the last must feed a later node; otherwise it is dead weight.
                    used = {b["provider"] for b in all_bindings}
                    if any(i not in used for i in new_path[:-1]):
                        continue
                    candidates.append({
                        "chain_id": chain_id(profile, list(new_path)),
                        "entry_profile": profile,
                        "attacker": data["entry_profiles"][profile].get("description", ""),
                        "ordered_node_ids": list(new_path),
                        "bindings": all_bindings,
                        "expected_terminal_impact": last["terminal_impact"],
                        "status": "ready_for_chain_review" if not blocked else "blocked_on_unconfirmed_components",
                        "blocked_on": blocked,
                    })
            frontier = [(p, pr) for p, pr, _ in nxt]
            if not frontier:
                break
    return {"schema_version": "1.0",
            "note": "Chain candidates are hypotheses for investigation. None of them is a finding.",
            "limits": {"max_length": max_length, "max_successors_per_step": max_successors,
                       "beam_width": beam_width, "max_candidates": max_candidates},
            "pruned": pruned, "candidates": candidates}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("plan")
    s.add_argument("--capabilities", required=True)
    s.add_argument("--out")
    s.add_argument("--max-length", type=int, default=4)
    s.add_argument("--max-successors", type=int, default=4)
    s.add_argument("--beam-width", type=int, default=64)
    s.add_argument("--max-candidates", type=int, default=200)
    args = p.parse_args()
    try:
        with open(args.capabilities, encoding="utf-8") as f:
            result = plan(json.load(f), args.max_length, args.max_successors, args.beam_width, args.max_candidates)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    for c in result["candidates"]:
        print(f"{c['status']:<34} {c['entry_profile']:<22} {' -> '.join(c['ordered_node_ids'])}")
    print(f"{len(result['candidates'])} candidate(s); pruned: {result['pruned']}")


if __name__ == "__main__":
    main()
