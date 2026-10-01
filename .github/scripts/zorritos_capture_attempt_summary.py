"""Publish the Zorritos ANA capture-attempt report as annotation, step summary and output."""
import json
import os
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["geometry_fabricated"] is False, "geometry must never be fabricated"
assert report["map_publishable"] is False and report["targets_promoted"] == [], "attempt must never promote"
status, blocker = report["status"], report.get("blocker_class")
level = "notice" if status == "CAPTURE_COMPLETE_NOT_ADJUDICATED" else "warning"
print(f"::{level} title=Zorritos ANA capture attempt::ZORRITOS_ANA_CAPTURE status={status} "
      f"blocker={blocker} failed_url={report.get('failed_url')} targets={json.dumps(report['targets'])}")
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
        fh.write("## Zorritos ANA capture attempt\n\n```json\n" + json.dumps(report, indent=2, ensure_ascii=False) + "\n```\n")
if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"status={status}\n")
