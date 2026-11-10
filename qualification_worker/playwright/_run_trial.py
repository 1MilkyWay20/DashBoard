import json
import sys
from pathlib import Path
import changeFileElm as elm

elm.closeChrom = lambda page: print("[trial] keep browser open", flush=True)
job = json.loads(Path("../tmp/job_elm_trial.json").read_text(encoding="utf-8"))
print("[trial] start", flush=True)
try:
    elm.run(
        job,
        Path("../licenses/job4_14697922.jpg"),
        hold=False,
        skip_photo=False,
        skip_submit=True,
    )
    print("[trial] done", flush=True)
except Exception as e:
    print(f"[trial] failed: {e}", flush=True)
    sys.exit(1)
