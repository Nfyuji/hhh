import json
import os
import threading
import time
import base64
import hashlib
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
    "SERVER_HOST": "0.0.0.0",  # يسمح بالاستماع على أي IP
    "HTTPS_ENABLED": True,      # لأن Render يدعم https تلقائي
    "app_password": os.getenv("APP_PASSWORD", "admin"),  # من Environment Variable
    "facebook_page_id": os.getenv("FACEBOOK_PAGE_ID", ""),
    "facebook_access_token": os.getenv("FACEBOOK_ACCESS_TOKEN", ""),
    "publish_targets": {"facebook": True, "tiktok": False, "youtube": True},
    "youtube": {
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", ""),  # يجب أن يكون من Environment Variable
        "client_secret": "",  # لا يُحفظ في config.json، فقط من Environment Variable
        "token": None,
        "refresh_token": None,
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    },
    "tiktok": {
        "client_key": os.getenv("TIKTOK_CLIENT_KEY", ""),  # يجب أن يكون من Environment Variable
        "client_secret": "",  # لا يُحفظ في config.json، فقط من Environment Variable
        "redirect_uri": os.getenv("TIKTOK_REDIRECT_URI", ""),
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
        "font_path": "",  # Empty = auto-detect based on OS
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
        data = {}
    else:
        with open(CONFIG_FILE, 'r') as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}
    
    cfg = deep_merge(DEFAULT_CONFIG, data)

    # 🔒 SECURITY: Environment Variables have HIGHEST priority (for Render/Cloud)
    # المفاتيح الحساسة تُقرأ فقط من Environment Variables، وليس من config.json
    
    # Facebook
    if os.getenv("FACEBOOK_PAGE_ID"):
        cfg["facebook_page_id"] = os.getenv("FACEBOOK_PAGE_ID")
    if os.getenv("FACEBOOK_ACCESS_TOKEN"):
        cfg["facebook_access_token"] = os.getenv("FACEBOOK_ACCESS_TOKEN")
    
    # YouTube - المفاتيح الحساسة من Environment Variables فقط
    if os.getenv("YOUTUBE_CLIENT_ID"):
        cfg["youtube"]["client_id"] = os.getenv("YOUTUBE_CLIENT_ID")
    if os.getenv("YOUTUBE_CLIENT_SECRET"):
        cfg["youtube"]["client_secret"] = os.getenv("YOUTUBE_CLIENT_SECRET")
    if os.getenv("GOOGLE_REDIRECT_URI"):
        cfg["youtube"]["redirect_uri"] = os.getenv("GOOGLE_REDIRECT_URI")
        
    # TikTok - المفاتيح الحساسة من Environment Variables فقط
    if os.getenv("TIKTOK_CLIENT_KEY"):
        cfg["tiktok"]["client_key"] = os.getenv("TIKTOK_CLIENT_KEY")
    if os.getenv("TIKTOK_CLIENT_SECRET"):
        cfg["tiktok"]["client_secret"] = os.getenv("TIKTOK_CLIENT_SECRET")
    if os.getenv("TIKTOK_REDIRECT_URI"):
        cfg["tiktok"]["redirect_uri"] = os.getenv("TIKTOK_REDIRECT_URI")
    
    # App Password
    if os.getenv("APP_PASSWORD"):
        cfg["app_password"] = os.getenv("APP_PASSWORD")

    return cfg

def save_config_file(data):
    """Save config to file, but NEVER save sensitive secrets."""
    # Create a copy to avoid modifying the original
    safe_data = json.loads(json.dumps(data))  # Deep copy
    
    # 🔒 SECURITY: Remove sensitive secrets before saving
    # These should ONLY come from Environment Variables
    if "youtube" in safe_data:
        safe_data["youtube"]["client_secret"] = ""  # Never save to file
    if "tiktok" in safe_data:
        safe_data["tiktok"]["client_secret"] = ""  # Never save to file
        safe_data["tiktok"]["client_key"] = ""  # Never save to file (optional, but safer)
    if "facebook_access_token" in safe_data:
        safe_data["facebook_access_token"] = ""  # Never save to file
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(safe_data, f, indent=4)

def scheduled_job():
    """The job that runs automatically."""
    add_log("=" * 60)
    add_log("⏰ Scheduled job started!")
    import traceback
    
    config = load_config()
    if not config.get('is_active'):
        add_log("⏸ System inactive. Skipping.")
        return

    # Step 1: Check prerequisites
    add_log("📋 Checking prerequisites...")
    paths = config.get("paths") or {}
    base_video = paths.get("base_video", "base.mp4")
    texts_file = paths.get("texts_file", "texts.txt")
    output_video = paths.get("output_video", "output.mp4")
    
    if not os.path.exists(base_video):
        error_msg = f"❌ Base video not found: {base_video}"
        add_log(error_msg)
        add_log("⏹ Scheduled job aborted.")
        return
    
    if not os.path.exists(texts_file):
        error_msg = f"❌ Texts file not found: {texts_file}"
        add_log(error_msg)
        add_log("⏹ Scheduled job aborted.")
        return
    
    add_log(f"✅ Base video found: {base_video}")
    add_log(f"✅ Texts file found: {texts_file}")

    # Step 2: Generate video
    add_log("🎬 Starting video generation...")
    text = None
    try:
        text = post.generate_video(config=config)
        add_log(f"✅ Video generated successfully! Caption: {text}")
        
        # Verify output video exists
        if not os.path.exists(output_video):
            error_msg = f"❌ Output video was not created: {output_video}"
            add_log(error_msg)
            add_log("⏹ Scheduled job aborted.")
            return
        
        file_size = os.path.getsize(output_video)
        add_log(f"✅ Output video verified: {output_video} ({file_size / 1024 / 1024:.2f} MB)")
    except Exception as e:
        error_trace = traceback.format_exc()
        error_msg = f"❌ Video generation failed: {e}"
        add_log(error_msg)
        add_log(f"📋 Traceback: {error_trace}")
        add_log("⏹ Scheduled job aborted.")
        return

    # Step 3: Upload to platforms
    targets = config.get("publish_targets") or {}
    upload_success = False
    
    # Facebook
    if targets.get("facebook", True):
        add_log("📘 Uploading to Facebook...")
        try:
            post.upload_to_facebook(text, config)
            add_log("✅ Facebook upload completed!")
            upload_success = True
        except Exception as e:
            error_trace = traceback.format_exc()
            add_log(f"❌ Facebook upload failed: {e}")
            add_log(f"📋 Traceback: {error_trace}")
    
    # TikTok
    if targets.get("tiktok"):
        add_log("🎵 Uploading to TikTok...")
        try:
            tiktok.upload_to_tiktok(text, config, video_path=output_video)
            add_log("✅ TikTok upload completed!")
            upload_success = True
        except Exception as e:
            error_trace = traceback.format_exc()
            add_log(f"❌ TikTok upload failed: {e}")
            add_log(f"📋 Traceback: {error_trace}")
    
    # YouTube
    if targets.get("youtube"):
        add_log("📺 Uploading to YouTube...")
        try:
            youtube.upload_video(
                title=text, 
                description=text + " #shorts #quotes", 
                file_path=output_video, 
                config=config
            )
            add_log("✅ YouTube upload completed!")
            upload_success = True
        except Exception as e:
            error_trace = traceback.format_exc()
            add_log(f"❌ YouTube upload failed: {e}")
            add_log(f"📋 Traceback: {error_trace}")
    
    # Final status
    if upload_success:
        add_log("✅ Scheduled Task Completed Successfully!")
    else:
        add_log("⚠️ Scheduled Task Completed with errors (no successful uploads)")
    add_log("=" * 60)

def update_scheduler():
    """Update job timing based on config"""
    config = load_config()
    scheduler.remove_all_jobs()
    
    if config.get('is_active') and config.get('schedule_time'):
        try:
            # Parse time string (format: "HH:MM")
            schedule_time = config['schedule_time'].strip()
            if ':' not in schedule_time:
                add_log(f"❌ Invalid schedule_time format: {schedule_time}. Expected HH:MM")
                return
            
            hour_str, minute_str = schedule_time.split(':')
            hour = int(hour_str)
            minute = int(minute_str)
            
            # Validate time range
            if hour < 0 or hour > 23:
                add_log(f"❌ Invalid hour: {hour}. Must be 0-23")
                return
            if minute < 0 or minute > 59:
                add_log(f"❌ Invalid minute: {minute}. Must be 0-59")
                return
            
            # Add job with integer hour and minute
            scheduler.add_job(
                scheduled_job, 
                'cron', 
                hour=hour, 
                minute=minute,
                id='daily_post',
                replace_existing=True,
                misfire_grace_time=300,  # Allow job to run up to 5 minutes late
                max_instances=1,  # Only one instance at a time
                coalesce=True  # Combine multiple pending runs into one
            )
            add_log(f"✅ Job scheduled successfully for {hour:02d}:{minute:02d} daily (24h format)")
            
            # Log next run time
            jobs = scheduler.get_jobs()
            if jobs:
                next_run = jobs[0].next_run_time
                if next_run:
                    add_log(f"⏰ Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        except ValueError as e:
            add_log(f"❌ Error parsing schedule_time '{config.get('schedule_time')}': {e}")
        except Exception as e:
            add_log(f"❌ Error scheduling job: {e}")
            import traceback
            add_log(f"📋 Traceback: {traceback.format_exc()}")
    else:
        add_log("📅 No active jobs scheduled (is_active=False or schedule_time not set).")

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

def get_base_url():
    """Detect if running on Render or locally."""
    from flask import has_request_context, request as flask_request
    
    # Check if running on Render (has RENDER environment variable or PORT from Render)
    is_render = bool(os.getenv("RENDER") or (os.getenv("PORT") and os.getenv("PORT") != "5000"))
    
    if is_render:
        # Get the service URL from environment
        render_service_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_service_url:
            return render_service_url.rstrip('/')
        # Fallback: try to get from request if available
        if has_request_context():
            scheme = 'https' if flask_request.is_secure or os.getenv("HTTPS_ENABLED") == "true" else 'http'
            host = flask_request.host
            return f"{scheme}://{host}"
        # Last fallback: construct from common Render pattern
        return "https://hhh-ftzf.onrender.com"
    
    # Local development
    cfg = load_config()
    if cfg.get("HTTPS_ENABLED"):
        return "https://127.0.0.1:5000"
    return "http://127.0.0.1:5000"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage/facebook')
def manage_facebook():
    """صفحة إدارة Facebook"""
    return render_template('manage_facebook.html')

@app.route('/manage/tiktok')
def manage_tiktok():
    """صفحة إدارة TikTok"""
    return render_template('manage_tiktok.html')

@app.route('/manage/youtube')
def manage_youtube():
    """صفحة إدارة YouTube"""
    return render_template('manage_youtube.html')

@app.route('/test/facebook', methods=['POST'])
def test_facebook():
    """اختبار الاتصال بـ Facebook API"""
    try:
        data = request.json
        page_id = data.get('page_id')
        access_token = data.get('access_token')
        
        if not page_id or not access_token:
            return jsonify({"status": "error", "message": "Page ID و Access Token مطلوبان"}), 400
        
        import requests
        # Test API call
        url = f"https://graph.facebook.com/v18.0/{page_id}?fields=name,id&access_token={access_token}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            page_data = response.json()
            return jsonify({
                "status": "success",
                "message": f"✅ الاتصال ناجح! الصفحة: {page_data.get('name', 'غير معروف')}"
            })
        else:
            error_data = response.json() if response.content else {}
            return jsonify({
                "status": "error",
                "message": f"❌ فشل الاتصال: {error_data.get('error', {}).get('message', 'خطأ غير معروف')}"
            }), 400
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"❌ خطأ: {str(e)}"}), 500

@app.route('/api/base_url')
def api_base_url():
    """API endpoint to get the base URL for the current environment."""
    try:
        from flask import has_request_context, request as flask_request
        
        # Check if running on Render
        is_render = bool(os.getenv("RENDER") or (os.getenv("PORT") and os.getenv("PORT") != "5000"))
        
        if is_render:
            # Try to get from environment first
            render_service_url = os.getenv("RENDER_EXTERNAL_URL")
            if render_service_url:
                base_url = render_service_url.rstrip('/')
            elif has_request_context():
                # Get from request
                scheme = 'https' if flask_request.is_secure or os.getenv("HTTPS_ENABLED") == "true" else 'http'
                host = flask_request.host
                base_url = f"{scheme}://{host}"
            else:
                # Fallback
                base_url = "https://hhh-ftzf.onrender.com"
        else:
            # Local
            cfg = load_config()
            if cfg.get("HTTPS_ENABLED"):
                base_url = "https://127.0.0.1:5000"
            else:
                base_url = "http://127.0.0.1:5000"
        
        return jsonify({
            "base_url": base_url,
            "is_render": is_render,
            "is_local": not is_render
        })
    except Exception as e:
        # Fallback on error
        return jsonify({
            "base_url": "https://hhh-ftzf.onrender.com",
            "is_render": True,
            "is_local": False
        })

@app.route('/get_config')
def get_config():
    # Allow access without login for initial load, but protect sensitive operations
    cfg = load_config()
    
    # 🔒 SECURITY: Mask all sensitive data before sending to frontend
    # Mask Facebook Access Token
    if cfg.get("facebook_access_token"):
        cfg["facebook_access_token"] = "********"
    
    # Mask YouTube credentials
    if cfg.get("youtube", {}).get("client_secret"):
        cfg["youtube"]["client_secret"] = "********"
    cid = cfg.get("youtube", {}).get("client_id", "")
    if cid and len(cid) > 10:
        cfg["youtube"]["client_id"] = cid[:5] + "..." + cid[-5:]
    elif cid:
        cfg["youtube"]["client_id"] = "********"
    
    # Mask TikTok credentials
    if cfg.get("tiktok", {}).get("client_key"):
        cfg["tiktok"]["client_key"] = "********"
    if cfg.get("tiktok", {}).get("client_secret"):
        cfg["tiktok"]["client_secret"] = "********"
    
    # Mask app password
    if cfg.get("app_password"):
        cfg["app_password"] = "********"

    return jsonify(cfg)

@app.route('/save_config', methods=['POST'])
def save_config():
    # Allow saving config without login (for easier management)
    # Sensitive data is still protected (see security checks below)
    
    new_data = request.json
    if not new_data:
        return jsonify({"error": "No data provided"}), 400
    
    current_config = load_config()
    
    # 🔒 SECURITY: Never save sensitive credentials from UI
    # Handle Masked YouTube Credentials
    incoming_cid = new_data.get("youtube", {}).get("client_id", "")
    if "***" in incoming_cid or incoming_cid == "********":
        # Keep existing value (which comes from env var)
        new_data["youtube"]["client_id"] = current_config.get("youtube", {}).get("client_id", "")
        
    # Check Client Secret - NEVER save from UI
    incoming_secret = new_data.get("youtube", {}).get("client_secret", "")
    if incoming_secret == "********" or incoming_secret:
        # Always remove from save - must come from Environment Variable
        new_data["youtube"]["client_secret"] = ""
    
    # 🔒 TikTok - Never save client_key or client_secret from UI
    if "tiktok" in new_data:
        new_data["tiktok"]["client_key"] = ""
        new_data["tiktok"]["client_secret"] = ""
    
    # 🔒 Facebook Access Token - Handle masked tokens
    if "facebook_access_token" in new_data:
        incoming_token = new_data["facebook_access_token"]
        # If it's masked or empty, keep existing value from env var
        if incoming_token == "********" or not incoming_token:
            new_data["facebook_access_token"] = current_config.get("facebook_access_token", "")
        # If it's a real token, allow saving (user is setting it manually)

    # Validate schedule_time format if provided
    if "schedule_time" in new_data:
        schedule_time = new_data["schedule_time"]
        if schedule_time:
            try:
                # Validate time format (HH:MM)
                if ':' not in str(schedule_time):
                    return jsonify({"status": "error", "message": "تنسيق الوقت غير صحيح. استخدم HH:MM (مثال: 14:30)"}), 400
                
                hour_str, minute_str = str(schedule_time).split(':')
                hour = int(hour_str)
                minute = int(minute_str)
                
                if hour < 0 or hour > 23:
                    return jsonify({"status": "error", "message": f"الساعة {hour} غير صحيحة. يجب أن تكون بين 0 و 23"}), 400
                if minute < 0 or minute > 59:
                    return jsonify({"status": "error", "message": f"الدقيقة {minute} غير صحيحة. يجب أن تكون بين 0 و 59"}), 400
                
                # Normalize format to HH:MM (with leading zeros)
                new_data["schedule_time"] = f"{hour:02d}:{minute:02d}"
            except ValueError as e:
                return jsonify({"status": "error", "message": f"تنسيق الوقت غير صحيح: {schedule_time}. استخدم HH:MM"}), 400

    # Merge and save
    merged = deep_merge(current_config, new_data)
    save_config_file(merged)
    
    # Update scheduler immediately
    update_scheduler()
    
    # Log what was saved
    add_log(f"💾 Config saved: schedule_time={merged.get('schedule_time')}, is_active={merged.get('is_active')}, publish_targets={merged.get('publish_targets')}")
    return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح"})

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

@app.route('/get_schedule_info')
def get_schedule_info():
    """Get information about the current schedule"""
    config = load_config()
    jobs = scheduler.get_jobs()
    
    info = {
        "is_active": config.get('is_active', False),
        "schedule_time": config.get('schedule_time', '09:00'),
        "next_run": None,
        "has_job": len(jobs) > 0
    }
    
    if jobs:
        next_run = jobs[0].next_run_time
        if next_run:
            info["next_run"] = next_run.strftime('%Y-%m-%d %H:%M:%S')
            info["next_run_iso"] = next_run.isoformat()
    
    return jsonify(info)

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
        import traceback
        add_log("🎬 Starting preview generation...")
        
        # Check if base video exists
        base_video = (cfg.get("paths") or {}).get("base_video", "base.mp4")
        if not os.path.exists(base_video):
            error_msg = f"❌ Base video not found: {base_video}"
            add_log(error_msg)
            return jsonify({"status": "error", "message": error_msg}), 400
        
        # Check if texts file exists
        texts_file = (cfg.get("paths") or {}).get("texts_file", "texts.txt")
        if not os.path.exists(texts_file):
            error_msg = f"❌ Texts file not found: {texts_file}"
            add_log(error_msg)
            return jsonify({"status": "error", "message": error_msg}), 400
        
        add_log(f"📝 Generating video with base: {base_video}")
        text = post.generate_video(config=cfg)
        out_path = (cfg.get("paths") or {}).get("output_video", "output.mp4")
        
        if not os.path.exists(out_path):
            error_msg = f"❌ Output video was not created: {out_path}"
            add_log(error_msg)
            return jsonify({"status": "error", "message": error_msg}), 500
        
        add_log(f"✅ Preview generated successfully: {out_path}")
        return jsonify({"status": "success", "caption": text, "output_video": out_path})
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_msg = f"❌ Preview failed: {str(e)}"
        add_log(error_msg)
        add_log(f"📋 Traceback: {error_trace}")
        # Return detailed error in development, simplified in production
        is_render = bool(os.getenv("RENDER") or os.getenv("PORT"))
        if is_render:
            # On Render, return simplified error
            return jsonify({"status": "error", "message": f"خطأ في توليد الفيديو: {str(e)}"}), 500
        else:
            # Local, return detailed error
            return jsonify({"status": "error", "message": str(e), "traceback": error_trace}), 500

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
    
    # Auto-detect redirect URI based on environment
    base_url = get_base_url()
    redirect_uri = f"{base_url}/tiktok/callback"
    
    # Override with environment variable if set
    if os.getenv("TIKTOK_REDIRECT_URI"):
        redirect_uri = os.getenv("TIKTOK_REDIRECT_URI")
    elif tiktok_cfg.get("redirect_uri"):
        redirect_uri = tiktok_cfg.get("redirect_uri")
    
    if not client_key:
        add_log("❌ TikTok login failed: Client Key not set.")
        return jsonify({"status": "error", "message": "TikTok Client Key not set in environment variables."}), 400

    # Generate PKCE code_verifier and code_challenge
    code_verifier = secrets.token_urlsafe(64)
    # S256 method requires SHA256 hash of code_verifier, then base64url-encoded
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')

    # Store code_verifier in config for later use in callback
    cfg["tiktok"]["code_verifier"] = code_verifier
    cfg["tiktok"]["redirect_uri"] = redirect_uri  # Save detected redirect URI
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
    
    # Auto-detect redirect URI based on environment
    base_url = get_base_url()
    redirect_uri = f"{base_url}/youtube/callback"
    
    # Override with environment variable if set
    if os.getenv("GOOGLE_REDIRECT_URI"):
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    elif cfg.get("youtube", {}).get("redirect_uri"):
        redirect_uri = cfg.get("youtube", {}).get("redirect_uri")
    
    # Update config with detected redirect URI
    cfg["youtube"]["redirect_uri"] = redirect_uri
    save_config_file(cfg)
    
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
        # Use the same scheduled_job function to ensure consistency
        scheduled_job()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "جاري النشر في الخلفية... راقب السجلات"})

@app.route('/test_scheduled_job', methods=['POST'])
def test_scheduled_job():
    """Test the scheduled job function manually"""
    add_log("🧪 Manual test of scheduled job triggered")
    thread = threading.Thread(target=scheduled_job, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "تم تشغيل المهمة المجدولة للاختبار... راقب السجلات"})

if __name__ == '__main__':
    # Initial schedule setup
    update_scheduler()
    cfg = load_config()
    host = cfg.get("SERVER_HOST", "127.0.0.1")
    # Render uses PORT environment variable, fallback to 5000 for local
    port = int(os.getenv("PORT", 5000))
    
    # Detect environment
    is_render = bool(os.getenv("RENDER") or os.getenv("PORT"))
    
    if is_render:
        # On Render: HTTPS is automatic, no SSL context needed
        add_log(f"🌐 Running on Render: https://{os.getenv('RENDER_EXTERNAL_URL', 'render.com')}")
        add_log(f"🚀 Web Interface available on port {port}")
        ssl_context = None
        # On Render, HTTPS_ENABLED should be True but we don't use ssl_context
        # because Render handles HTTPS automatically
    else:
        # Local: use config setting
        if cfg.get("HTTPS_ENABLED"):
            add_log(f"🚀 Web Interface running on https://{host}:{port}")
            ssl_context = 'adhoc'
        else:
            add_log(f"🚀 Web Interface running on http://{host}:{port}")
            ssl_context = None
    
    app.run(debug=not is_render, use_reloader=False, host=host, port=port, ssl_context=ssl_context)
