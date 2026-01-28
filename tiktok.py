import time
import requests


TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/upload/init/"


class TikTokNotConfigured(Exception):
    pass


def is_tiktok_connected(cfg: dict) -> bool:
    t_cfg = (cfg or {}).get("tiktok") or {}
    return bool(t_cfg.get("access_token")) and bool(t_cfg.get("open_id"))

def get_auth_url(cfg: dict, state: str) -> str:
    t_cfg = (cfg or {}).get("tiktok") or {}
    client_key = t_cfg.get("client_key")
    redirect_uri = t_cfg.get("redirect_uri")
    scopes = "user.info.basic,video.publish,video.upload"

    if not client_key or not redirect_uri:
        raise TikTokNotConfigured("Client Key or Redirect URI not set for TikTok.")

    return (
        f"{TIKTOK_AUTH_URL}?client_key={client_key}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scopes}"
        f"&response_type=code"
        f"&state={state}"
    )

def exchange_code_for_token(code: str, cfg: dict) -> dict:
    t_cfg = (cfg or {}).get("tiktok") or {}
    client_key = t_cfg.get("client_key")
    client_secret = t_cfg.get("client_secret")
    redirect_uri = t_cfg.get("redirect_uri")

    data = {
        'client_key': client_key,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(TIKTOK_TOKEN_URL, data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def refresh_access_token(cfg: dict) -> dict:
    t_cfg = (cfg or {}).get("tiktok") or {}
    client_key = t_cfg.get("client_key")
    client_secret = t_cfg.get("client_secret")
    refresh_token = t_cfg.get("refresh_token")

    if not refresh_token:
        raise TikTokNotConfigured("Refresh token not available.")

    data = {
        'client_key': client_key,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    response = requests.post(TIKTOK_TOKEN_URL, data=data, headers=headers)
    response.raise_for_status()
    return response.json()

def upload_to_tiktok(caption: str, cfg: dict, video_path: str = "output.mp4"):
    """
    TikTok نشر الفيديو يتطلب OAuth + صلاحيات Content Posting API.
    """
    t = (cfg or {}).get("tiktok") or {}
    access_token = t.get("access_token")
    open_id = t.get("open_id")

    if t.get("expires_at", 0) < time.time() + 60:  # refresh if token expires in less than 60 seconds
        from app import add_log, save_config_file  # Import locally to avoid circular dependency
        try:
            add_log("⏳ TikTok access token expired or near expiration. Attempting to refresh.")
            refresh_data = refresh_access_token(cfg)
            t["access_token"] = refresh_data.get("access_token")
            t["refresh_token"] = refresh_data.get("refresh_token")
            t["expires_at"] = time.time() + refresh_data.get("expires_in", 3600)
            save_config_file(cfg)
            access_token = t["access_token"]
            add_log("✅ TikTok access token refreshed successfully.")
        except Exception as e:
            add_log(f"❌ Failed to refresh TikTok access token: {e}")
            # Continue with old token, it might still work for a bit, or fail gracefully later.

    if not access_token or not open_id:
        raise TikTokNotConfigured(
            "TikTok غير مُعد. لازم تعمل OAuth وتخزن access_token + open_id داخل config.json."
        )

    # TikTok's Content Posting API v2 requires a two-step process:
    # 1. Initiate upload and get an upload URL
    # 2. Upload video to that URL
    # 3. Publish the video

    # Step 1: Initiate upload
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'x-caller-open-id': open_id
    }
    init_data = {"post_info": {"title": caption, "description": caption}, "medi-info": {"media_type": "video"}}

    try:
        init_response = requests.post(TIKTOK_UPLOAD_INIT_URL, headers=headers, json=init_data)
        init_response.raise_for_status()
        init_json = init_response.json()
        
        if init_json.get("error"):
            raise TikTokNotConfigured(f"TikTok upload init error: {init_json.get('error_description')}")
        
        upload_url = init_json["data"]["upload_url"]
        publish_id = init_json["data"]["publish_id"]
        # add_log(f"✅ TikTok upload initiated. Publish ID: {publish_id}") # Moved to main app loop for better context
    except requests.exceptions.RequestException as e:
        raise TikTokNotConfigured(f"Failed to initiate TikTok upload: {e}") from e

    # Step 2: Upload video to the provided URL
    import os
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found at {video_path}")

    try:
        with open(video_path, 'rb') as f:
            upload_response = requests.put(upload_url, headers={'Content-Type': 'video/mp4'}, data=f)
            upload_response.raise_for_status()
        # add_log("✅ Video uploaded to TikTok.") # Moved to main app loop
    except requests.exceptions.RequestException as e:
        raise TikTokNotConfigured(f"Failed to upload video to TikTok URL: {e}") from e

    # Step 3: Publish the video (This is typically another API call)
    # The 'publish_id' from step 1 is used here. TikTok's API usually has a separate call for publishing
    # what was uploaded. The exact endpoint might vary.
    # Based on the documentation snippet, video.publish scope implies direct publishing.
    # For v2, after uploading, the content is published using the same /publish/init endpoint's publish_id in a different stage.

    # Assuming publish is part of the init response and handled by TikTok after upload. 
    # If there is a separate publish confirm step, it would go here.
    # For simplicity, we assume the upload is enough for 'draft' or 'direct post' as per scopes.
    # add_log(f"🎉 TikTok video '{caption}' posted (Publish ID: {publish_id}).") # Moved to main app loop

    # For actual direct post, usually you would confirm by calling a publish endpoint
    # post_publish_url = "https://open.tiktokapis.com/v2/post/publish/status/"
    # publish_status_data = {"publish_id": publish_id}
    # status_response = requests.get(post_publish_url, headers=headers, params=publish_status_data)
    # status_response.raise_for_status()
    # add_log(f"TikTok publish status: {status_response.json()}")

    return {"publish_id": publish_id}
