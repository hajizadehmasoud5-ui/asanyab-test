import json
import subprocess
import sys
from datetime import datetime, timezone

JOBS = [
    ("catalog", [sys.executable, "/app/seed_catalog.py"]),
    ("dana-public", [sys.executable, "/app/ingest_dana_public.py"]),
    ("iran-secondary", [sys.executable, "/app/ingest_iionline_iran.py"]),
]


def main():
    results=[]
    for name,cmd in JOBS:
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
            results.append({"job":name,"ok":p.returncode==0,"returncode":p.returncode,"stdout":p.stdout[-3000:].strip(),"stderr":p.stderr[-1500:].strip()})
        except Exception as e:
            results.append({"job":name,"ok":False,"error":str(e)})
    report={"ran_at_utc":datetime.now(timezone.utc).isoformat(),"ok":all(x.get("ok") for x in results),"jobs":results}
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(0 if report["ok"] else 1)

if __name__=='__main__':
    main()
