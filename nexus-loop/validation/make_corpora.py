#!/usr/bin/env python
"""Build the validation corpora into validation/data/ (git-ignored, reproducible).

  sealed-<phrase>   the organisers' own generator in sealed mode: the day-6 test with an answer key we can see.
                    Each is checked with the kit's verify.py; a layout that breaks a fault's signature is reported.
  clean-practice    the practice kit with every planted-fault cohort-window and load-event day removed: any
                    regression found here is a false positive.
  day6-layout       the practice kit exactly as the Makefile's `distribute` target ships it: no ground truth.

    python validation/make_corpora.py [--phrases p1 p2 p3] [--force]
"""
import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys

from _common import DATA, PRACTICE_KIT, TOOLS, find_ground_truth, utf8_stdout

DEFAULT_PHRASES = ("delta-fresh-one", "echo-fresh-two", "foxtrot-fresh-three")
DISTRIBUTED = ("corpus", "labels", "catalog.json", "asks.md", "manifest.json")


def sealed(phrase, force):
    out = os.path.join(DATA, "sealed-" + re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-"))
    if force and os.path.isdir(out):
        shutil.rmtree(out)
    if not os.path.exists(os.path.join(out, "manifest.json")):
        subprocess.run([sys.executable, "generate.py", "--sealed", phrase, "--out", out], cwd=TOOLS, check=True,
                       stdout=subprocess.DEVNULL)
    v = subprocess.run([sys.executable, "verify.py", "--kit", out], cwd=TOOLS, capture_output=True, text=True)
    print("%-32s verify.py %s" % (os.path.basename(out), "OK" if v.returncode == 0 else "FAILED\n" + v.stdout))
    return v.returncode == 0


def clean_practice(force):
    out = os.path.join(DATA, "clean-practice")
    if os.path.exists(os.path.join(out, "corpus", "agent_steps.jsonl.gz")) and not force:
        print("%-32s exists" % "clean-practice")
        return
    shutil.rmtree(out, ignore_errors=True)
    gt = json.load(open(find_ground_truth(PRACTICE_KIT), encoding="utf-8"))

    def dropped(s):
        for f in gt["faults"]:
            if s["tenant"] == f["tenant"] and f["onset_day"] <= s["day"] < f["onset_day"] + f["duration_days"] \
                    and any(k != "tool" and s.get(k) == v for k, v in f["cohort"].items()):
                return True
        return any(d["kind"] == "load_event" and s["tenant"] == d["tenant"]
                   and d["onset_day"] <= s["day"] < d["onset_day"] + d["duration_days"] for d in gt["decoys"])

    os.makedirs(os.path.join(out, "corpus"))
    for f in ("catalog.json", "manifest.json", "asks.md"):
        shutil.copy(os.path.join(PRACTICE_KIT, f), out)
    shutil.copytree(os.path.join(PRACTICE_KIT, "labels"), os.path.join(out, "labels"))
    for f in ("config_timeline.csv", "feedback.csv"):
        shutil.copy(os.path.join(PRACTICE_KIT, "corpus", f), os.path.join(out, "corpus"))
    keep, total = set(), 0
    with gzip.open(os.path.join(PRACTICE_KIT, "corpus", "sessions.jsonl.gz"), "rt", encoding="utf-8") as fi, \
            gzip.open(os.path.join(out, "corpus", "sessions.jsonl.gz"), "wt", encoding="utf-8", compresslevel=1) as fo:
        for line in fi:
            total += 1
            s = json.loads(line)
            if not dropped(s):
                keep.add(s["session_id"])
                fo.write(line)
    with gzip.open(os.path.join(PRACTICE_KIT, "corpus", "agent_steps.jsonl.gz"), "rt", encoding="utf-8") as fi, \
            gzip.open(os.path.join(out, "corpus", "agent_steps.jsonl.gz"), "wt", encoding="utf-8", compresslevel=1) as fo:
        for line in fi:
            if json.loads(line)["session_id"] in keep:
                fo.write(line)
    print("%-32s kept %d of %d sessions" % ("clean-practice", len(keep), total))


def day6_layout(force):
    out = os.path.join(DATA, "day6-layout")
    if os.path.isdir(out) and not force:
        print("%-32s exists" % "day6-layout")
        return
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for item in DISTRIBUTED:
        src = os.path.join(PRACTICE_KIT, item)
        (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(out, item))
    assert find_ground_truth(out) is None
    print("%-32s copied without ground truth" % "day6-layout")


def main():
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrases", nargs="+", default=list(DEFAULT_PHRASES))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    ok = [sealed(p, a.force) for p in a.phrases]
    clean_practice(a.force)
    day6_layout(a.force)
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
