"""Worker script: runs a Revit script in the open Revit model through the pyRevit Agent Runtime."""
import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
job = json.loads((root / "job.json").read_text(encoding="utf-8"))

mode = job.get("mode", "query")
if mode not in ("query", "dry_run", "modify"):
    raise ValueError("Invalid mode: " + mode)

pyrevit = shutil.which("pyrevit") or os.path.expandvars(r"%APPDATA%\pyRevit-Master\bin\pyrevit.exe")
command = [
    pyrevit, "agent", "run", str(root / "revit_task.py"),
    "--mode=" + mode,
    "--title=" + job.get("title", "VIKTOR"),
    "--inputs=" + json.dumps(job.get("inputs", {})),
    "--timeout=" + str(job.get("timeout", 240)),
]
if job.get("revit"):
    command.append("--revit=" + str(job["revit"]))  # Revit year, when several versions are running

process = subprocess.run(command, capture_output=True, text=True, timeout=job.get("timeout", 240) + 30)
try:
    response = json.loads(process.stdout[process.stdout.find("{"):])
except ValueError:
    response = {"status": "error", "error": (process.stderr or process.stdout).strip()}

(root / "output.json").write_text(json.dumps(response, indent=2), encoding="utf-8")
