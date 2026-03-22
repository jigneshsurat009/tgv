import os
import threading
from flask import Flask

app = Flask(name)

@app.get("/")
def home():
    return "ok", 200

@app.get("/health")
def health():
    return {"ok": True}, 200

def start_bot():
    # replace this import with your real bot start function
    # example: from app.main import run_bot
    # run_bot()
    from main import run_bot
    run_bot()

if name == "main":
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
