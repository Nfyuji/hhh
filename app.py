import json
import os
import threading
import time
import base64
import hashlib
import secrets
import secrets
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
import post  # Import our existing video logic
import tiktok
import youtube

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CONFIG_FILE = 'config.json'
TEXTS_FILE = 'texts.txt'

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.start()

DEFAULT_CONFIG = {
    "SERVER_HOST": "127.0.0.1",
    "HTTPS_ENABLED": False, # Will be enabled by run.ps1 for TikTok OAuth
    "app_password": "admin",
    "facebook_page_id": "",
    "facebook_access_token": "",
    "publish_targets": {"facebook": True, "tiktok": False, "youtube": False},
    "youtube": {
        "client_id": "",
        "client_secret": "",
        "token": None,
        "refresh_token": None,
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    },
    "tiktok": {
        "client_key": "awhp5vrjkh90twlf",
        "client_secret": "fYr1YvrUSzYc2SRkmeHqFJp5TWo6OIHv",
        "redirect_uri": "http://127.0.0.1:5000/tiktok/callback", # Changed to HTTP for local test
        "access_token": "",
        "refresh_token": "",
        "expires_at": 0,
        "open_id": "",
    },
    "schedule_time": "09:00",
    "is_active": False,
    "paths": {
        "texts_file": "texts.txt",
        "base_video": "base.mp4",
        "output_video": "output.mp4",
        "uploads_dir": "uploads",
    },
    "video": {
        "max_duration_seconds": 15,
        "size": [1080, 1920],
        "fps": 24,
        "placeholder_bg_color": [20, 30, 60],
    },
    "text_overlay": {
        "font_path": "C:\\Windows\\Fonts\\arial.ttf",
        "font_size": 70,
        "color": "#FFFFFF",
        "shadow_color": "#000000",
        "shadow_offset": 2,
        "max_width_pct": 0.86,
        "line_spacing_px": 14,
        "align": "center",
        "position_mode": "preset",  # preset | manual
        "preset": "center",         # top | center | bottom
        "x_pct": 0.5,
        "y_pct": 0.5,
    },
}

_LOGS = []
def add_log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _LOGS.append(line)
    if len(_LOGS) > 300:
        del _LOGS[:50]

def deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, 'r') as f:
        try:
            data = json.load(f)
        except Exception:
            data = {}
    return deep_merge(DEFAULT_CONFIG, data)

def save_config_file(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def scheduled_job():
    """The job that runs automatically."""
    add_log("⏰ Scheduled job started!")
    config = load_config()
    if not config.get('is_active'):
        add_log("⏸ System inactive. Skipping.")
        return

    try:
        # Generate and Upload
        text = post.generate_video(config=config)
        targets = config.get("publish_targets") or {}
        if targets.get("facebook", True):
            post.upload_to_facebook(text, config)
        if targets.get("tiktok"):
            try:
                video_path = (config.get("paths") or {}).get("output_video", "output.mp4")
                tiktok.upload_to_tiktok(text, config, video_path=video_path)
            except Exception as e:
                add_log(f"❌ TikTok upload failed: {e}")
        if targets.get("youtube"):
            try:
                video_path = (config.get("paths") or {}).get("output_video", "output.mp4")
                youtube.upload_video(title=text, description=text + " #shorts #quotes", file_path=video_path, config=config)
            except Exception as e:
                add_log(f"❌ YouTube upload failed: {e}")
        add_log("✅ Scheduled Task Completed Successfully.")
    except Exception as e:
        add_log(f"❌ Error in scheduled job: {e}")

def update_scheduler():
    """Update job timing based on config"""
    config = load_config()
    scheduler.remove_all_jobs()
    
    if config.get('is_active') and config.get('schedule_time'):
        hour, minute = config['schedule_time'].split(':')
        scheduler.add_job(
            scheduled_job, 
            'cron', 
            hour=hour, 
            minute=minute,
            id='daily_post'
        )
        add_log(f"📅 Job rescheduled for {hour}:{minute} daily.")
    else:
        add_log("📅 No active jobs scheduled.")

def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/check_auth')
def check_auth():
    return jsonify({"logged_in": session.get('logged_in', False)})

@app.route('/login', methods=['POST'])
def login():
    pwd = request.json.get('password')
    cfg = load_config()
    real_pwd = cfg.get('app_password', 'admin')
    if pwd == real_pwd:
        session['logged_in'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Incorrect password"}), 401

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_config')
def get_config():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401
    
    cfg = load_config()
    # Mask sensitive data
    if cfg.get("youtube", {}).get("client_secret"):
        cfg["youtube"]["client_secret"] = "********"
    
    # Mask client ID partially if it exists
    cid = cfg.get("youtube", {}).get("client_id", "")
    if cid and len(cid) > 10:
         cfg["youtube"]["client_id"] = cid[:5] + "..." + cid[-5:]
    elif cid:
         cfg["youtube"]["client_id"] = "********"

    return jsonify(cfg)

@app.route('/save_config', methods=['POST'])
def save_config():
    if not session.get('logged_in'):
        return jsonify({"error": "Unauthorized"}), 401

    new_data = request.json
    current_config = load_config()
    
    # Handle Masked YouTube Credentials
    # Check Client ID
    incoming_cid = new_data.get("youtube", {}).get("client_id", "")
    if "***" in incoming_cid or incoming_cid == "********":
        new_data["youtube"]["client_id"] = current_config.get("youtube", {}).get("client_id", "")
        
    # Check Client Secret
    incoming_secret = new_data.get("youtube", {}).get("client_secret", "")
    if incoming_secret == "********":
        new_data["youtube"]["client_secret"] = current_config.get("youtube", {}).get("client_secret", "")

    merged = deep_merge(current_config, new_data)
    save_config_file(merged)
    update_scheduler()
    return jsonify({"status": "success", "message": "Config saved"})

@app.route('/add_quote', methods=['POST'])
def add_quote():
    text = request.json.get('text')
    if text:
        cfg = load_config()
        texts_file = (cfg.get("paths") or {}).get("texts_file", TEXTS_FILE)
        with open(texts_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{text}")
    return jsonify({"status": "success"})

@app.route('/logs')
def logs():
    return jsonify({"logs": _LOGS[-200:]})

@app.route('/texts')
def list_texts():
    cfg = load_config()
    texts_file = (cfg.get("paths") or {}).get("texts_file", TEXTS_FILE)
    if not os.path.exists(texts_file):
        return jsonify({"texts": [], "file": texts_file})
    with open(texts_file, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return jsonify({"texts": lines, "file": texts_file})

@app.route('/delete_text', methods=['POST'])
def delete_text():
    idx = request.json.get("index")
    cfg = load_config()
    texts_file = (cfg.get("paths") or {}).get("texts_file", TEXTS_FILE)
    if idx is None:
        return jsonify({"status": "error", "message": "Missing index"}), 400
    if not os.path.exists(texts_file):
        return jsonify({"status": "error", "message": "Texts file not found"}), 404
    with open(texts_file, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f.readlines()]
    cleaned = [ln for ln in lines if ln.strip()]
    if idx < 0 or idx >= len(cleaned):
        return jsonify({"status": "error", "message": "Index out of range"}), 400
    del cleaned[idx]
    with open(texts_file, "w", encoding="utf-8") as f:
        f.write("\n".join(cleaned) + ("\n" if cleaned else ""))
    return jsonify({"status": "success"})

@app.route('/upload_base_video', methods=['POST'])
def upload_base_video():
    cfg = load_config()
    uploads_dir = (cfg.get("paths") or {}).get("uploads_dir", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Missing file"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"status": "error", "message": "Empty filename"}), 400
    # Save as a stable name
    target_path = os.path.join(uploads_dir, "base.mp4")
    f.save(target_path)
    # Update config to use uploaded base video
    cfg["paths"]["base_video"] = target_path.replace("\\", "/")
    save_config_file(cfg)
    add_log(f"🎬 Base video uploaded: {cfg['paths']['base_video']}")
    return jsonify({"status": "success", "base_video": cfg["paths"]["base_video"]})

@app.route('/preview', methods=['POST'])
def preview():
    cfg = load_config()
    try:
        text = post.generate_video(config=cfg)
        out_path = (cfg.get("paths") or {}).get("output_video", "output.mp4")
        return jsonify({"status": "success", "caption": text, "output_video": out_path})
    except Exception as e:
        add_log(f"❌ Preview failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_last')
def download_last():
    cfg = load_config()
    out_path = (cfg.get("paths") or {}).get("output_video", "output.mp4")
    if not os.path.exists(out_path):
        return jsonify({"status": "error", "message": "No output video yet"}), 404
    return send_file(out_path, as_attachment=True)

@app.route('/tiktok/login')
def tiktok_login():
    cfg = load_config()
    tiktok_cfg = cfg.get("tiktok") or {}
    client_key = tiktok_cfg.get("client_key")
    redirect_uri = tiktok_cfg.get("redirect_uri")
    
    if not client_key or not redirect_uri:
        add_log("❌ TikTok login failed: Client Key or Redirect URI not set.")
        return jsonify({"status": "error", "message": "TikTok Client Key or Redirect URI not set in config."}), 400

    # Generate PKCE code_verifier and code_challenge
    code_verifier = secrets.token_urlsafe(64)
    # S256 method requires SHA256 hash of code_verifier, then base64url-encoded
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')

    # Store code_verifier in config for later use in callback
    cfg["tiktok"]["code_verifier"] = code_verifier
    save_config_file(cfg)

    # Scopes needed for Content Posting API: user.info.basic, video.publish, video.upload
    # See: https://developers.tiktok.com/doc/content-posting-api-v2-overview
    scopes = "user.info.basic,video.publish,video.upload"
    state = "my_random_state_string" # TODO: Generate and store a secure random state

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize?client_key={client_key}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&response_type=code"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    add_log(f"🚀 Redirecting to TikTok for OAuth: {auth_url}")
    from flask import redirect
    return redirect(auth_url)

@app.route('/tiktok/callback')
def tiktok_callback():
    cfg = load_config()
    tiktok_cfg = cfg.get("tiktok") or {}
    client_key = tiktok_cfg.get("client_key")
    client_secret = tiktok_cfg.get("client_secret")
    redirect_uri = tiktok_cfg.get("redirect_uri")

    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    # TODO: Verify state for CSRF protection
    # if state != stored_state:
    #    add_log("❌ TikTok OAuth callback: CSRF state mismatch.")
    #    return jsonify({"status": "error", "message": "CSRF state mismatch"}), 400

    if error:
        add_log(f"❌ TikTok OAuth callback error: {error}")
        return jsonify({"status": "error", "message": f"TikTok OAuth error: {error}"}), 400

    if not code:
        add_log("❌ TikTok OAuth callback: No authorization code received.")
        return jsonify({"status": "error", "message": "No authorization code received"}), 400

    # Exchange code for access token
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    
    # Retrieve code_verifier and clear it
    code_verifier = cfg["tiktok"].pop("code_verifier", None)
    save_config_file(cfg)

    if not code_verifier:
        add_log("❌ TikTok OAuth callback: Missing code_verifier.")
        return jsonify({"status": "error", "message": "Missing code_verifier"}), 400

    data = {
        'client_key': client_key,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier, # Add code_verifier for PKCE
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    import requests
    try:
        response = requests.post(token_url, data=data, headers=headers)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        token_data = response.json()
        add_log(f"✅ TikTok token exchange response: {token_data}")

        if token_data.get("error"):
            add_log(f"❌ TikTok token error: {token_data.get('error_description')}")
            return jsonify({"status": "error", "message": token_data.get("error_description")}), 400

        # Store tokens and open_id
        cfg["tiktok"]["access_token"] = token_data.get("access_token")
        cfg["tiktok"]["refresh_token"] = token_data.get("refresh_token")
        cfg["tiktok"]["expires_at"] = time.time() + token_data.get("expires_in", 3600)
        cfg["tiktok"]["open_id"] = token_data.get("open_id")
        save_config_file(cfg)

        add_log("✅ TikTok OAuth successful! Tokens and Open ID saved.")
        return render_template("tiktok_auth_success.html") # Or redirect to main page
    except requests.exceptions.RequestException as e:
        add_log(f"❌ TikTok token exchange request failed: {e}")
        return jsonify({"status": "error", "message": f"Failed to exchange token: {e}"}), 500

@app.route('/youtube/login')
def youtube_login():
    cfg = load_config()
    state = "some_random_state" # Should be random
    try:
        auth_url = youtube.get_auth_url(cfg, state=state)
        add_log(f"🚀 Redirecting to YouTube for OAuth: {auth_url}")
        from flask import redirect
        return redirect(auth_url)
    except Exception as e:
         add_log(f"❌ YouTube login setup failed: {e}")
         return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/youtube/callback')
def youtube_callback():
    cfg = load_config()
    # verify state...
    code = request.args.get('code')
    if not code:
        return "Missing code", 400
    
    try:
        creds_dict = youtube.exchange_code_for_credentials(cfg, code)
        # Update config with new credentials
        # We need to preserve client_id/secret if not returned (usually they are in creds object though)
        # deep_merge might overwrite everything, let's be careful.
        
        y_cfg = cfg.get("youtube", {})
        y_cfg["token"] = creds_dict.get("token")
        y_cfg["refresh_token"] = creds_dict.get("refresh_token")
        y_cfg["token_uri"] = creds_dict.get("token_uri")
        y_cfg["scopes"] = creds_dict.get("scopes")
        # client_id/secret usually static, but let's keep them if they are in creds
        if creds_dict.get("client_id"): y_cfg["client_id"] = creds_dict.get("client_id")
        if creds_dict.get("client_secret"): y_cfg["client_secret"] = creds_dict.get("client_secret")

        cfg["youtube"] = y_cfg
        save_config_file(cfg)
        
        add_log("✅ YouTube OAuth successful! Tokens saved.")
        return render_template("tiktok_auth_success.html") # Reuse existing success page or make a new one
    except Exception as e:
        add_log(f"❌ YouTube callback failed: {e}")
        return f"Error: {e}", 500
@app.route('/run_now', methods=['POST'])
def run_now():
    # Run in separate thread to not block request
    def runner():
        config = load_config()
        try:
            text = post.generate_video(config=config)
            # Pass config explicitly so we don't need to save globally in post.py
            targets = config.get("publish_targets") or {}
            if targets.get("facebook", True):
                post.upload_to_facebook(text, config)
            if targets.get("tiktok"):
                video_path = (config.get("paths") or {}).get("output_video", "output.mp4")
                tiktok.upload_to_tiktok(text, config, video_path=video_path)
            if targets.get("youtube"):
                video_path = (config.get("paths") or {}).get("output_video", "output.mp4")
                youtube.upload_video(title=text, description=text + " #shorts #quotes", file_path=video_path, config=config)
        except Exception as e:
            add_log(f"❌ Run now error: {e}")

    thread = threading.Thread(target=runner)
    thread.start()
    return jsonify({"status": "started", "message": "جاري النشر في الخلفية... راقب الترمينال"})

if __name__ == '__main__':
    # Initial schedule setup
    update_scheduler()
    cfg = load_config()
    host = cfg.get("SERVER_HOST", "127.0.0.1")
    port = 5000
    if cfg.get("HTTPS_ENABLED"):
        add_log(f"🚀 Web Interface running on https://{host}:{port}")
        ssl_context = 'adhoc'
    else:
        add_log(f"🚀 Web Interface running on http://{host}:{port}")
        ssl_context = None
    app.run(debug=True, use_reloader=False, host=host, port=port, ssl_context=ssl_context)
