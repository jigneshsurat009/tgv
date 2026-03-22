import os
import threading
from flask import Flask

app = Flask(__name__)

@app.get("/")
def home():
    return "ok", 200

@app.get("/health")
def health():
    return {"ok": True}, 200

def start_bot():
    from run import main
    main()

if __name__ == "__main__":
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
