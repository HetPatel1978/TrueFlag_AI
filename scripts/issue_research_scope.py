"""Owner tool: replace the native runtime's academic research scope with up to 3 named cases.

Run by the owner/admin after the demo CSV is imported. Without --confirm it only previews.

  .venv-windows/Scripts/python.exe -B scripts/issue_research_scope.py \
      --cases SYN-01-STRUCTURING SYN-04-SAVER SYN-06-PARTIAL --actors windowsanalyst
  (review the preview, then repeat with --confirm, then restart the runtime)

With --confirm it archives the current scope file (renamed with a timestamp, never deleted),
writes a new scope with the same fields and limits the application enforces (purpose,
database, cluster, source proposal hash, as-of date, at most 3 cases, at most 4 actors,
production_publication_authorized=false), and stores its SHA-256 in the runtime state. The
running processes read the scope hash at start, so stop and supervise the runtime afterwards.

It does not approve any request, change the spending cap or the approver list, or send
anything. The owner's approver policy (owner-ai-approvers.json) is bound to the scope hash, so
after re-scoping no request can be approved until the owner records a new approver policy
for the new hash. Each AI request still needs its own in-app approval by the named approver.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
import windows_runtime  # noqa: E402

PROPOSAL_SHA = "832f42eafdc27a1e7847a8acf21c4b0615c8ca129f3117df969ec116fefc84c1"


def resolve(state, sources, usernames):
    """Case IDs for imported SYN- sources and user IDs for active usernames (read-only)."""
    with windows_runtime.connection(state) as c:
        cluster = c.execute("SELECT system_identifier::text FROM pg_control_system()").fetchone()[0]
        database = c.execute("SELECT current_database()").fetchone()[0]
        cases = {}
        for source in sources:
            rows = c.execute(
                "SELECT c.id::text FROM cases c JOIN alerts a ON a.id = c.alert_id "
                "WHERE a.source_id = %s AND a.data_classification = 'synthetic'",
                (source,),
            ).fetchall()
            if len(rows) != 1:
                raise SystemExit(f"{source}: expected exactly one imported case, found {len(rows)}")
            cases[source] = rows[0][0]
        actors = {}
        for name in usernames:
            row = c.execute(
                "SELECT id::text FROM users WHERE username = %s AND active", (name,)
            ).fetchone()
            if row is None:
                raise SystemExit(f"{name}: no active user")
            actors[name] = row[0]
    return cluster, database, cases, actors


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", nargs="+", required=True, help="SYN- source IDs (at most 3)")
    parser.add_argument("--actors", nargs="+", required=True, help="usernames (at most 4)")
    parser.add_argument("--confirm", action="store_true", help="write the new scope")
    options = parser.parse_args()
    if len(options.cases) > 3 or len(options.actors) > 4:
        raise SystemExit("the application allows at most 3 cases and 4 actors per scope")
    directory, state = windows_runtime.current()
    research = state.get("research") or {}
    if not research.get("scope_file"):
        raise SystemExit("research mode is not installed in this runtime")
    proposal = hashlib.sha256((ROOT / "contracts/regulatory_source_proposals.json").read_bytes())
    if proposal.hexdigest() != PROPOSAL_SHA:
        raise SystemExit("source proposal identity changed; refusing")
    cluster, database, cases, actors = resolve(state, options.cases, options.actors)
    scope = {
        "purpose": "academic_research_unapproved_v1",
        "database": database,
        "cluster_id": cluster,
        "source_proposal_sha256": PROPOSAL_SHA,
        "as_of": "2026-11-02",
        "actors": list(actors.values()),
        "cases": list(cases.values()),
        "production_publication_authorized": False,
        "authority": "Owner re-scoped isolated academic research mode to the named demo cases; "
        "not a regulatory approval or paid-request approval.",
    }
    preview = {"database": database, "cases": cases, "actors": actors, "write": options.confirm}
    print(json.dumps(preview, indent=2))
    if not options.confirm:
        print("Preview only. Repeat with --confirm to write the scope.")
        return
    scopefile = Path(research["scope_file"])
    archived = scopefile.with_name(f"research-scope.{time.strftime('%Y%m%dT%H%M%S')}.json")
    scopefile.rename(archived)
    with scopefile.open("x", encoding="utf-8") as stream:
        json.dump(scope, stream, indent=2)
    state["research"]["scope_sha256"] = hashlib.sha256(scopefile.read_bytes()).hexdigest()
    temporary = directory / "state.new.json"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(state, stream, indent=2)
    temporary.replace(directory / "state.json")
    print(
        json.dumps(
            {
                "status": "scope_written",
                "archived_previous": archived.name,
                "new_scope_sha256": state["research"]["scope_sha256"],
                "approvals": "disabled until the owner records an approver policy whose "
                "scope_sha256 equals new_scope_sha256 (owner decision; not done by this tool)",
                "next": "windows_runtime.py stop, then supervise, so the new scope hash is loaded",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
