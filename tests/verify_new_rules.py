"""Ad-hoc verification of the 8 new rules against the harvested corpus.

Run: python tests/verify_new_rules.py
(kept out of the pytest suite on purpose -- it depends on the gitignored
harvested corpus; the permanent pins live in tests/test_gaps.py)
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd.parser.report import parse_file          # noqa: E402
from mcd.rules.engine import RuleSet, run_rules   # noqa: E402

rs = RuleSet.load()
print(f"rules loaded: {len(rs.rules)}   load errors: {rs.errors}")

EXPECT = {
    "mod.binary-incompat": ["sodium/3711", "fabric-api/5363", "fabric-loader/611"],
    "mod.linkage-duplicate": ["fabric-loader/1132", "quilt-loader/232"],
    "quilt.config-broken": ["quilt-loader/244", "quilt-loader/261"],
    "loader.namespace-missing": ["quilt-loader/497"],
    "mixin.injection-failed": ["fabric-api/5097", "fabric-api/5279"],
    "crash.registry-load-failed": ["fabric-api/4862", "fabric-api/5049"],
    "net.connectivity": ["quilt-loader/344", "fabric-api/4707"],
    "env.headless-jvm": ["quilt-loader/398"],
}

idx = {}
for f in glob.glob("corpus/github/**/*.crash.txt", recursive=True):
    rel = os.path.relpath(f, "corpus/github").replace(os.sep, "/")
    # "FabricMC__fabric-api/5363.crash.txt" -> "fabric-api/5363"
    key = rel.split("__", 1)[-1].replace(".crash.txt", "")
    idx[key] = {fd.rule_id for fd in run_rules(parse_file(f), rs)}

print("\nnew-rule hit check:")
allok = True
for rid, samples in EXPECT.items():
    hit = [s for s in samples if rid in idx.get(s, set())]
    ok = len(hit) == len(samples)
    allok &= ok
    miss = [s for s in samples if s not in hit]
    print(f"  {'OK ' if ok else 'MISS'} {rid:26} {len(hit)}/{len(samples)}"
          + (f"   missing: {miss}" if miss else ""))

# Regression guard: a new rule must only fire where its OWN evidence line is
# present. The aternos corpus legitimately contains NoSuchMethodError /
# injection failures / registry errors (it is real server logs), so firing
# there is correct -- what we check is that every firing is evidence-backed.
EVIDENCE = {
    "mod.binary-incompat": r"NoSuchFieldError|NoSuchMethodError|does not have member",
    "mod.linkage-duplicate": r"LinkageError|loader constraint violation|duplicate class definition",
    "quilt.config-broken": r"MalformedSyntaxException|ParsingException|invalid JSON5?|Not enough data available",
    "loader.namespace-missing": r"Requested target namespace \w+ not loaded",
    "mixin.injection-failed": r"Critical injection failure|has incompatible changes|could not find",
    "crash.registry-load-failed": r"Failed to load registries",
    "net.connectivity": r"UnknownHostException|CertificateException|SSLHandshakeException|subject alternative DNS name",
    "env.headless-jvm": r"UnsatisfiedLinkError|HeadlessException|Can't load library|libawt",
}

import re  # noqa: E402

unsupported = []
checked = 0
for f in sorted(glob.glob("corpus/aternos/**/*.log", recursive=True)):
    rep = parse_file(f)
    fired = {fd.rule_id for fd in run_rules(rep, rs)} & set(EXPECT)
    if not fired:
        continue
    checked += 1
    for rid in fired:
        if not re.search(EVIDENCE[rid], rep.full_text, re.I):
            unsupported.append((os.path.basename(f), rid))
print(f"\naternos files where a new rule fired: {checked}")
print(f"firings WITHOUT a supporting evidence line: {len(unsupported)}")
for u in unsupported[:6]:
    print("   !", u)

ok = allok and not unsupported
print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
