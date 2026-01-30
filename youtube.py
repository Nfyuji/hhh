import os
import time
import unicodedata
# Google API libraries (installed via requirements.txt)
from google_auth_oauthlib.flow import Flow  # type: ignore
from google.oauth2.credentials import Credentials  # type: ignore
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.http import MediaFileUpload  # type: ignore
from google.auth.transport.requests import Request  # type: ignore

# Define the scopes required for the application
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

class YouTubeNotConfigured(Exception):
    pass

def is_youtube_connected(config: dict) -> bool:
    """Check if we have valid-looking credentials for YouTube."""
    y_cfg = (config or {}).get("youtube") or {}
    return bool(y_cfg.get("refresh_token"))

def get_flow(config: dict, state: str = None):
    """Create a Flow instance from config."""
    y_cfg = (config or {}).get("youtube") or {}
    client_id = y_cfg.get("client_id")
    client_secret = y_cfg.get("client_secret")
    redirect_uri = y_cfg.get("redirect_uri")

    if not client_id or not client_secret:
        raise YouTubeNotConfigured("Client ID or Client Secret not set for YouTube.")

    # Create client config dictionary dynamically
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    if state:
        flow.state = state
    return flow

def get_auth_url(config: dict, state: str) -> str:
    """Generate the authorization URL for the user to visit."""
    flow = get_flow(config, state=state)
    # prompt='consent' to ensure we get a refresh token
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return auth_url

def exchange_code_for_credentials(config: dict, code: str) -> dict:
    """Exchange the authorization code for credentials."""
    flow = get_flow(config)
    flow.fetch_token(code=code)
    creds = flow.credentials
    return credentials_to_dict(creds)

def credentials_to_dict(creds):
    """Serialize credentials to a dictionary."""
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

def get_authenticated_service(config: dict):
    """Build the YouTube service object using stored credentials."""
    y_cfg = (config or {}).get("youtube") or {}
    
    # We prioritize the refresh token to reconstruct credentials
    if not y_cfg.get("refresh_token") and not y_cfg.get("token"):
        raise YouTubeNotConfigured("No tokens found. Please connect YouTube account first.")

    creds_data = {
        'token': y_cfg.get("token"),
        'refresh_token': y_cfg.get("refresh_token"),
        'token_uri': y_cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        'client_id': y_cfg.get("client_id"),
        'client_secret': y_cfg.get("client_secret"),
        'scopes': y_cfg.get("scopes", SCOPES),
    }

    creds = Credentials.from_authorized_user_info(creds_data)
    
    # Refresh if needed
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            from app import add_log # Import locally to avoid circular dependency issues sometimes
            try:
                creds.refresh(Request())
                add_log("✅ YouTube access token refreshed.")
                # Ideally, we should save the new access token back to config here
                # But for now, we'll let the service run.
                # In a robust app, we'd callback to `save_config` with new token.
            except Exception as e:
                 raise YouTubeNotConfigured(f"Failed to refresh YouTube token: {e}")
        else:
             raise YouTubeNotConfigured("Token expired and no refresh token available.")

    return build("youtube", "v3", credentials=creds)

def upload_video(title: str, description: str, file_path: str, config: dict):
    """Uploads a video to YouTube."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    from app import add_log
    
    try:
        youtube = get_authenticated_service(config)
    except Exception as e:
        add_log(f"❌ YouTube Auth Error: {e}")
        return

    # 🔤 Fix Arabic text encoding for YouTube
    # Ensure text is properly encoded as UTF-8 string
    def ensure_utf8(text):
        """Ensure text is properly encoded UTF-8 string for YouTube API."""
        if text is None:
            return ""
        # If it's bytes, decode it
        if isinstance(text, bytes):
            try:
                text = text.decode('utf-8')
            except UnicodeDecodeError:
                # Try with error handling
                text = text.decode('utf-8', errors='replace')
        # Ensure it's a string (Unicode)
        text = str(text)
        # Normalize Unicode (NFD to NFC) to ensure consistent encoding
        try:
            text = unicodedata.normalize('NFC', text)
        except:
            pass
        # Clean and strip
        text = text.strip()
        # Remove any zero-width characters that might cause issues
        text = text.replace('\u200b', '')  # Zero-width space
        text = text.replace('\u200c', '')  # Zero-width non-joiner
        text = text.replace('\u200d', '')  # Zero-width joiner
        return text
    
    # Clean and ensure UTF-8 encoding
    clean_title = ensure_utf8(title)
    clean_description = ensure_utf8(description)
    
    # Limit title to 100 characters (YouTube limit)
    clean_title = clean_title[:100]
    
    # Add hashtags to description
    if clean_description:
        clean_description = clean_description + " #shorts #quotes #motivation"
    else:
        clean_description = "#shorts #quotes #motivation"

    body = {
        "snippet": {
            "title": clean_title,
            "description": clean_description,
            "tags": ["shorts", "motivation", "quotes", "تحفيز", "حكم"],
            "categoryId": "22" # People & Blogs
        },
        "status": {
            "privacyStatus": "public", 
            "selfDeclaredMadeForKids": False
        }
    }

    add_log(f"🚀 Starting YouTube upload: {clean_title}")
    
    # Debug: Log the text to ensure it's correct (UTF-8)
    try:
        add_log(f"📝 Title: {clean_title}")
        add_log(f"📝 Description preview: {clean_description[:50]}...")
    except Exception as e:
        add_log(f"⚠️ Encoding debug error: {e}")
    
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    
    # The googleapiclient library handles UTF-8 encoding automatically
    # We just need to ensure the strings are proper Unicode strings (which they are)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                # You could log progress here: int(status.progress() * 100)
                pass
        
        if "id" in response:
            add_log(f"✅ YouTube Upload Successful! Video ID: {response['id']}")
            return response['id']
        else:
            add_log(f"⚠️ YouTube upload finished but no ID returned: {response}")
            return None

    except Exception as e:
        add_log(f"❌ YouTube Upload Failed: {e}")
        raise e
