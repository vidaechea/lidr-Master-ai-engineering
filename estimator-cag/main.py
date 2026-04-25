import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("UVICORN_HOST", "127.0.0.1")
    port = int(os.getenv("UVICORN_PORT", "8000"))
    reload_enabled = os.getenv("UVICORN_RELOAD", "false").lower() in ("1", "true", "yes", "on")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload_enabled)

