"""Start RavenQuill:  python run.py   then open http://localhost:8000"""
import os
import sys

import uvicorn

if __name__ == "__main__":
    # 127.0.0.1 = only this computer can connect. Your manuscript stays local.
    uvicorn.run("ravenquill.api:app", host=os.environ.get("RAVENQUILL_HOST", "127.0.0.1"),
                port=int(os.environ.get("RAVENQUILL_PORT", 8000)), reload="--reload" in sys.argv)
