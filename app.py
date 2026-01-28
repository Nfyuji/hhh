import json
import os
import threading
import time
import secrets
from flask import Flask, render_template, request, jsonify, send_file, redirect
from apscheduler.schedulers.background import BackgroundScheduler
import post
import tiktok
import requests

app = Flask(__name__)

CONFIG_FILE = 'config.json'
TEXTS_FILE = 'texts.txt'

# =========================
# Scheduler
# =========================
scheduler = BackgroundScheduler()
scheduler.start()

# =========================
# Default Config
# =========================
DEFAULT_CONFIG = {
    "publish_targets": {
        "facebook": True,
        "tiktok": False
    },
    "tiktok": {
        "access_token": "",
        "refresh_token": "",
        "expires_at": 0,
        "open_id": ""
    },
    "schedule_time": "09:00",
    "is_active": False,
    "paths": {
        "texts_file": "texts.txt",
        "base_video": "base.mp4",
        "output_video": "output.mp4",
        "uploads_dir": "uploads"
    },
    "video": {
        "max_duration_seconds": 15,
        "size": [1080, 1920],
        "fps": 24
    }
}

# =========================
# Helpers
# =========================
_LOGS = []

def add_log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _LOGS.append(line)
    if len(_LOGS) > 300:
        _LOGS.pop(0)

def deep_merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and k in a:
            a[k] = deep_merge(a.get(k, {}), v)
        else:
            a[k] = v
    return a

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return deep_merge(dict(DEFAULT_CONFIG), json.load(f))

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

# =========================
# Scheduler Job
# =========================
def scheduled_job():
    add_log("⏰ Scheduled job started")
    cfg = load_config()

    if not cfg.get("is_active"):
        add_log("⏸ System inactive")
        return

    try:
        caption = post.generate_video(config=cfg)

        if cfg["publish_targets"].get("facebook"):
            post.upload_to_facebook(caption, cfg)

        if cfg["publish_targets"].get("tiktok"):
            video_path = cfg["paths"]["output_video"]
            tiktok.upload_to_tiktok(caption, cfg, video_path)

        add_log("✅ Job completed")
    except Exception as e:
        add_log(f"❌ Job error: {e}")

def update_scheduler():
    scheduler.remove_all_jobs()
    cfg = load_config()

    if cfg.get("is_active"):
        h, m = cfg["schedule_time"].split(":")
        scheduler.add_job(
            scheduled_job,
            "cron",
            hour=h,
            minute=m,
            id="daily_job"
        )
        add_log(f"📅 Job scheduled at {h}:{m}")

# =========================
# Routes
# =========================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_config")
def get_config():
    return jsonify(load_config())

@app.route("/save_config", methods=["POST"])
def save_cfg():
    cfg = deep_merge(load_config(), request.json or {})
    save_config(cfg)
    update_scheduler()
    return jsonify({"status": "ok"})

@app.route("/logs")
def logs():
    return jsonify(_LOGS[-200:])

# =========================
# TikTok OAuth
# =========================
@app.route("/tiktok/login")
def tiktok_login():
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    base_url = os.environ.get("BASE_URL")

    state = secrets.token_urlsafe(16)
    auth_url = (
        "https://www.tiktok.com/v2/auth/authorize"
        f"?client_key={client_key}"
        f"&response_type=code"
        f"&scope=user.info.basic video.publish video.upload"
        f"&redirect_uri={base_url}/tiktok/callback"
        f"&state={state}"
    )

    return redirect(auth_url)

@app.route("/tiktok/callback")
def tiktok_callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"TikTok error: {error}", 400

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    data = {
        "client_key": os.environ.get("TIKTOK_CLIENT_KEY"),
        "client_secret": os.environ.get("TIKTOK_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": f"{os.environ.get('BASE_URL')}/tiktok/callback"
    }

    r = requests.post(token_url, data=data)
    r.raise_for_status()
    token = r.json()

    cfg = load_config()
    cfg["tiktok"]["access_token"] = token["access_token"]
    cfg["tiktok"]["refresh_token"] = token["refresh_token"]
    cfg["tiktok"]["expires_at"] = time.time() + token["expires_in"]
    cfg["tiktok"]["open_id"] = token["open_id"]

    save_config(cfg)
    add_log("✅ TikTok OAuth success")

    return "TikTok connected successfully 🎉"

# =========================
# Run Once
# =========================
@app.route("/run_now", methods=["POST"])
def run_now():
    threading.Thread(target=scheduled_job).start()
    return jsonify({"status": "started"})

# =========================
# Main
# =========================
if __name__ == "__main__":
    update_scheduler()
    port = int(os.environ.get("PORT", 5000))
    add_log(f"🚀 Running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
