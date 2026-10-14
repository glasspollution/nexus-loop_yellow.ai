"""Ephemeral, approval-gated workflow used by the manager screen.

The batch pipeline still knows how to write submission artifacts.  The manager
screen is deliberately different: it analyses the source kit in this process,
keeps human decisions in memory, and only invokes replay after an approval.
Stopping the server discards every decision and replay result.
"""
import copy
import datetime
import hashlib
import json
import threading

from . import decisions, replay, screen
from .pipeline import _json_default, analyse
from .validate import contract_problems, schema_errors


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain(value):
    """Detach engine-owned values (including numpy scalars) into plain JSON."""
    return json.loads(json.dumps(value, default=_json_default))


def _hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def proposal_sha(_report, prescription):
    """Hash only what is proposed; live replay does not exist before approval."""
    body = {key: value for key, value in prescription.items() if key not in ("approval", "approval_meta")}
    return _hash(body)[:16]


class LiveSession:
    """One process-local analysis and its human-review state."""

    def __init__(self, replay_url=None, replay_team=None, replay_timeout=20, verifier=None):
        self.replay_url = replay_url
        self.replay_team = replay_team
        self.replay_timeout = replay_timeout
        self._verifier = verifier or replay.verify
        self._lock = threading.RLock()
        self._decision_lock = threading.Lock()
        self._ready = threading.Event()
        self._state = "idle"
        self._error = None
        self._base_report = None
        self._report = None
        self._corpus_id = None
        self._analysis_sha = None
        self._session_sha = None
        self._revision = 0
        self._events = []
        self._thread = None

    @classmethod
    def from_report(cls, report, replay_url=None, replay_team=None, replay_timeout=20, verifier=None,
                    corpus_id=None):
        session = cls(replay_url, replay_team, replay_timeout, verifier)
        session._install(report, corpus_id or replay.corpus_id(None, report))
        return session

    @property
    def state(self):
        with self._lock:
            return self._state

    def start_analysis(self, kit, cache_dir=None, team="nexus-loop"):
        """Run detect -> diagnose -> prescribe on the source corpus in the background."""
        with self._lock:
            if self._state not in ("idle", "failed"):
                raise RuntimeError("analysis has already started")
            self._state, self._error = "running", None
            self._ready.clear()

        def run():
            try:
                result = analyse(kit, cache_dir=cache_dir, team=team, run_replay=False)
                self._install(result["report"], result["corpus_id"])
            except Exception as exc:  # surfaced through health and API responses
                with self._lock:
                    self._state = "failed"
                    self._error = "%s: %s" % (type(exc).__name__, str(exc))
                    self._ready.set()

        self._thread = threading.Thread(target=run, name="nexus-live-analysis", daemon=True)
        self._thread.start()
        return self._thread

    def _install(self, report, corpus_id):
        base = _plain(report)
        # A saved report may contain results from an older run.  They are never
        # valid evidence for this new interactive session.
        base["verifications"] = []
        base.pop("decision_log", None)
        for prescription in base.get("prescriptions", []):
            prescription.pop("approval", None)
            prescription.pop("approval_meta", None)
        base["self_assessment"] = {"cycles": 0, "prescription_accuracy": {}}
        with self._lock:
            self._base_report = base
            self._report = copy.deepcopy(base)
            self._corpus_id = corpus_id
            self._analysis_sha = _hash(base)
            self._revision = 0
            self._events = []
            self._refresh_session_metadata()
            self._state, self._error = "ready", None
            self._ready.set()

    def _refresh_session_metadata(self):
        self._session_sha = _hash({"analysis": self._analysis_sha, "revision": self._revision,
                                   "events": self._events})
        self._report["decision_log"] = {
            "mode": "session-memory",
            "generated_report_sha256": self._session_sha,
            "analysis_sha256": self._analysis_sha,
            "session_revision": self._revision,
            "applied": [p["id"] for p in self._report.get("prescriptions", []) if p.get("approval")],
            "needs_reconfirmation": [],
            "orphaned": [],
        }

    def wait(self, timeout=30):
        self._ready.wait(timeout)
        with self._lock:
            if self._state == "ready":
                return
            if self._state == "running":
                raise decisions.DecisionError(503, "the live corpus analysis is still running; try again shortly")
            if self._state == "failed":
                raise decisions.DecisionError(500, "the live corpus analysis failed: %s" % self._error)
            raise decisions.DecisionError(503, "the live corpus analysis has not started")

    def health(self):
        with self._lock:
            return {"analysis_state": self._state, "analysis_error": self._error,
                    "session_revision": self._revision if self._state == "ready" else None,
                    "corpus": (self._report or {}).get("corpus")}

    def _screen_locked(self):
        return screen.build(copy.deepcopy(self._report), report_sha=self._session_sha,
                            generated_sha=self._session_sha, proposal_fingerprint=proposal_sha,
                            source_report="session-memory", source_mode="live-session")

    def screen(self, timeout=30):
        self.wait(timeout)
        with self._lock:
            return self._screen_locked()

    def report(self, generated=False, timeout=30):
        self.wait(timeout)
        with self._lock:
            return copy.deepcopy(self._base_report if generated else self._report)

    def events(self, timeout=30):
        self.wait(timeout)
        with self._lock:
            return copy.deepcopy(self._events)

    @staticmethod
    def _clean(text, field):
        if not isinstance(text, str):
            raise decisions.DecisionError(400, "%s must be text" % field)
        value = text.strip()
        if not value:
            raise decisions.DecisionError(400, "%s is required: a decision needs a name and a reason" % field)
        return value[:decisions.MAX_TEXT]

    def _replay_one(self, report, prescription):
        if not self.replay_url:
            return None, "no live replay engine is configured"
        replay_input = copy.deepcopy(report)
        replay_input["prescriptions"] = [copy.deepcopy(prescription)]
        replay_input["verifications"] = []
        golden_sets = (report.get("standard_manifest") or {}).get("golden_sets", {})
        rows, notes, trace = self._verifier(
            replay_input,
            golden_sets,
            endpoint=self.replay_url,
            team=self.replay_team or report.get("team") or "nexus-loop",
            cache_dir=None,
            corpus=self._corpus_id,
            max_calls=1,
            timeout=self.replay_timeout,
        )
        row = next((item for item in rows if item.get("prescription_id") == prescription.get("id")), None)
        if row:
            return row, None
        failed = next((item for item in trace if item.get("prescription_id") == prescription.get("id")), None)
        reason = (failed or {}).get("reason") or (notes[0] if notes else "the live replay returned no result")
        return None, reason

    def decide(self, prescription_ref, verdict, decided_by, reason, seen_session_sha, seen_proposal_sha,
               now=None, timeout=30):
        """Record a session-only decision; replay exactly once when entering accepted."""
        self.wait(timeout)
        if verdict not in decisions.VERDICTS:
            raise decisions.DecisionError(400, "verdict must be one of %s" % ", ".join(decisions.VERDICTS))
        decided_by = self._clean(decided_by, "decided_by")
        reason = self._clean(reason, "reason")
        with self._decision_lock:
            # Snapshot and validate quickly.  Screen/health requests remain responsive
            # while the separate replay service does its potentially slow work.
            with self._lock:
                prescription = next((p for p in self._report.get("prescriptions", [])
                                     if prescription_ref in (p.get("id"), p.get("fix_id"))), None)
                if prescription is None:
                    raise decisions.DecisionError(404, "no prescription %r in the live analysis" % prescription_ref)
                base_prescription = next(p for p in self._base_report["prescriptions"]
                                         if p["id"] == prescription["id"])
                current_proposal_sha = proposal_sha(self._base_report, base_prescription)
                duplicate = next((event for event in reversed(self._events)
                                  if event.get("based_on_session_sha256") == seen_session_sha
                                  and event.get("prescription_id") == prescription["id"]
                                  and event.get("proposal_sha") == seen_proposal_sha
                                  and event.get("verdict") == verdict
                                  and event.get("decided_by") == decided_by
                                  and event.get("reason") == reason), None)
                if duplicate:
                    return {"event": copy.deepcopy(duplicate), "duplicate": True,
                            "session_revision": self._revision,
                            "replay_status": duplicate.get("replay_status")}, self._screen_locked()
                if not isinstance(seen_session_sha, str) or seen_session_sha != self._session_sha:
                    raise decisions.DecisionError(
                        409, "the live analysis changed after this screen was loaded; reload before deciding")
                if not isinstance(seen_proposal_sha, str) or seen_proposal_sha != current_proposal_sha:
                    raise decisions.DecisionError(409, "this proposal changed after it was displayed; reload before deciding")
                based_on_session_sha = self._session_sha
                report_snapshot = copy.deepcopy(self._report)
                prescription_snapshot = copy.deepcopy(prescription)
                was_accepted = (prescription.get("approval") or {}).get("verdict") == "accepted"
                verification, replay_problem = None, None
                if verdict == "accepted" and was_accepted:
                    verification = next((copy.deepcopy(v) for v in self._report.get("verifications", [])
                                         if v.get("prescription_id") == prescription["id"]), None)
                    if not verification:
                        prefix = prescription["id"] + " not verified: "
                        prior = next((line for line in (self._report.get("self_assessment") or {}).get("unverified", [])
                                      if line.startswith(prefix)), None)
                        replay_problem = prior[len(prefix):] if prior else "the live replay returned no result"

            if verdict == "accepted" and not was_accepted:
                verification, replay_problem = self._replay_one(report_snapshot, prescription_snapshot)

            with self._lock:
                # Decision calls are serialized, but keep the explicit check so a
                # future source refresh cannot commit an outcome against stale data.
                if self._session_sha != based_on_session_sha:
                    raise decisions.DecisionError(
                        409, "the live analysis changed while replay was running; reload before deciding")
                prescription = next(p for p in self._report["prescriptions"]
                                    if p["id"] == prescription_snapshot["id"])
                event = {
                    "fingerprint": decisions.fingerprint(self._base_report, prescription),
                    "prescription_id": prescription["id"],
                    "fix_id": prescription.get("fix_id"),
                    "change_type": prescription.get("change_type"),
                    "target": prescription.get("target"),
                    "verdict": verdict,
                    "decided_by": decided_by,
                    "reason": reason,
                    "at": now or _now(),
                    "proposal_sha": current_proposal_sha,
                    "based_on_session_sha256": based_on_session_sha,
                    "storage": "session-memory",
                    "replay_status": "completed" if verification else "failed" if verdict == "accepted" else "not_run",
                }
                if verification:
                    event["replay_run_id"] = verification.get("replay_run_id")
                if replay_problem:
                    event["replay_error"] = replay_problem

                candidate = copy.deepcopy(self._report)
                candidate_p = next(p for p in candidate["prescriptions"] if p["id"] == prescription["id"])
                candidate_p["approval"] = {key: event[key] for key in ("verdict", "decided_by", "reason", "at")}
                candidate_p["approval_meta"] = {"fix_id": event["fingerprint"],
                                                  "proposal_sha": current_proposal_sha,
                                                  "storage": "session-memory"}
                candidate["verifications"] = [v for v in candidate.get("verifications", [])
                                               if v.get("prescription_id") != prescription["id"]]
                unverified = [line for line in (candidate.get("self_assessment") or {}).get("unverified", [])
                              if not line.startswith(prescription["id"] + " not verified:")]
                if verdict == "accepted" and verification:
                    candidate["verifications"].append(verification)
                elif verdict == "accepted" and replay_problem:
                    unverified.append("%s not verified: %s" % (prescription["id"], replay_problem))
                candidate.setdefault("self_assessment", {})["unverified"] = unverified

                problems = (schema_errors(candidate) or []) + contract_problems(candidate)
                if problems:
                    raise decisions.DecisionError(
                        422, "refusing an invalid session result: %s" % "; ".join(problems)[:800])

                self._report = candidate
                self._events.append(event)
                self._revision += 1
                self._refresh_session_metadata()
                result = {"event": copy.deepcopy(event), "duplicate": False,
                          "session_revision": self._revision, "replay_status": event["replay_status"]}
                return result, self._screen_locked()
