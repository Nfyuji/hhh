import os
import random
import arabic_reshaper
from bidi.algorithm import get_display
# NOTE: moviepy/Pillow/numpy are imported lazily inside generate_video()
# so the Flask control panel can run even if video dependencies aren't installed yet.

# Configuration
TEXTS_FILE = 'texts.txt'
BASE_VIDEO = 'base.mp4'
OUTPUT_VIDEO = 'output.mp4'
FONT_PATH = 'C:\\Windows\\Fonts\\arial.ttf' # Standard Windows font
FONT_SIZE = 70
TEXT_COLOR = (255, 255, 255)
SHADOW_COLOR = (0, 0, 0)
VIDEO_DURATION = 10 # Seconds (if generating base video)
VIDEO_SIZE = (1080, 1920) # 9:16 format (Reels/TikTok style)

def _hex_to_rgb(hex_color: str, fallback=(255, 255, 255)):
    if not hex_color:
        return fallback
    s = str(hex_color).strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def _set_duration_compat(clip, duration):
    # MoviePy 1.x: set_duration, MoviePy 2.x: with_duration
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)
    if hasattr(clip, "with_duration"):
        return clip.with_duration(duration)
    raise AttributeError("Clip does not support setting duration")

def _set_fps_compat(clip, fps):
    # MoviePy 1.x: set_fps, MoviePy 2.x: with_fps
    if hasattr(clip, "set_fps"):
        return clip.set_fps(fps)
    if hasattr(clip, "with_fps"):
        return clip.with_fps(fps)
    raise AttributeError("Clip does not support setting fps")

def load_texts(filepath):
    """Load motivational texts from a file."""
    if not os.path.exists(filepath):
        return ["لا يوجد نصوص متاحة الآن"]
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines

def process_arabic_text(text):
    """Reshape and reorder Arabic text for correct display."""
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def _wrap_text_to_width(draw, text, font, max_width_px):
    # Simple word-wrap by spaces (works fine for Arabic sentences too)
    words = (text or "").split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for w in words[1:]:
        candidate = current + " " + w
        candidate_disp = process_arabic_text(candidate)
        bbox = draw.textbbox((0, 0), candidate_disp, font=font)
        if (bbox[2] - bbox[0]) <= max_width_px:
            current = candidate
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines

def _measure_text_block(draw, lines, font, line_spacing_px):
    disp_lines = [process_arabic_text(ln) for ln in lines]
    line_boxes = [draw.textbbox((0, 0), ln, font=font) for ln in disp_lines]
    line_sizes = [(b[2] - b[0], b[3] - b[1]) for b in line_boxes]
    total_h = sum(h for _, h in line_sizes) + max(0, (len(line_sizes) - 1) * int(line_spacing_px))
    max_w = max((w for w, _ in line_sizes), default=0)
    return disp_lines, line_sizes, max_w, total_h

def create_text_image(text, size, font_path, font_size, color, shadow_color=(0, 0, 0), shadow_offset=2, max_width_pct=0.86, max_height_pct=0.55, line_spacing_px=14, align="center", position=None, min_font_size=38):
    """Create a transparent image with centered text using Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np

    # Create image with transparent background
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    max_width_px = int(size[0] * float(max_width_pct))
    max_height_px = int(size[1] * float(max_height_pct))

    # Auto-fit: shrink font until wrapped text fits inside max width/height
    fitted = False
    current_size = int(font_size)
    font = None
    raw_lines = None
    disp_lines = None
    line_sizes = None
    total_h = None

    while current_size >= int(min_font_size):
        try:
            font = ImageFont.truetype(font_path, current_size)
        except IOError:
            print(f"Warning: Font not found at {font_path}. Using default.")
            font = ImageFont.load_default()

        raw_lines = _wrap_text_to_width(draw, text, font, max_width_px=max_width_px)
        disp_lines, line_sizes, max_w, total_h = _measure_text_block(draw, raw_lines, font, line_spacing_px)

        if max_w <= max_width_px and total_h <= max_height_px:
            fitted = True
            break
        current_size -= 2

    if not fitted:
        # Use the smallest size we reached; keep wrapping as best-effort
        if font is None:
            try:
                font = ImageFont.truetype(font_path, int(min_font_size))
            except IOError:
                font = ImageFont.load_default()
        raw_lines = raw_lines or _wrap_text_to_width(draw, text, font, max_width_px=max_width_px)
        disp_lines, line_sizes, _, total_h = _measure_text_block(draw, raw_lines, font, line_spacing_px)

    # Position is (x_center_px, y_center_px) by default
    if not position:
        position = (int(size[0] * 0.5), int(size[1] * 0.5))
    x_center, y_center = position

    y = int(y_center - total_h / 2)
    for (w, h), ln in zip(line_sizes, disp_lines):
        if align == "left":
            x = int(x_center - max_width_px / 2)
        elif align == "right":
            x = int(x_center + max_width_px / 2 - w)
        else:
            x = int(x_center - w / 2)

        # Shadow then main text
        draw.text((x + int(shadow_offset), y + int(shadow_offset)), ln, font=font, fill=shadow_color)
        draw.text((x, y), ln, font=font, fill=color)
        y += h + int(line_spacing_px)
    
    return np.array(img)

def generate_video(config=None):
    """Main function to generate the daily video."""
    print("--- 🚀 Starting Video Automation System ---")

    try:
        # MoviePy 2.x no longer exposes moviepy.editor. Support both 1.x and 2.x.
        try:
            from moviepy.editor import VideoFileClip, ColorClip, ImageClip, CompositeVideoClip  # type: ignore
        except Exception:
            from moviepy.video.io.VideoFileClip import VideoFileClip
            from moviepy.video.VideoClip import ColorClip, ImageClip
            from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    except Exception as e:
        raise RuntimeError(
            "Missing dependency: moviepy. Install it inside your venv with: "
            "python -m pip install moviepy"
        ) from e

    paths = (config or {}).get("paths") or {}
    video_cfg = (config or {}).get("video") or {}
    text_cfg = (config or {}).get("text_overlay") or {}

    texts_file = paths.get("texts_file", TEXTS_FILE)
    base_video = paths.get("base_video", BASE_VIDEO)
    output_video = paths.get("output_video", OUTPUT_VIDEO)

    max_duration_seconds = int(video_cfg.get("max_duration_seconds", 15))
    video_size = tuple(video_cfg.get("size", list(VIDEO_SIZE)))
    fps = int(video_cfg.get("fps", 24))
    placeholder_bg = tuple(video_cfg.get("placeholder_bg_color", [20, 30, 60]))

    font_path = text_cfg.get("font_path", FONT_PATH)
    font_size = int(text_cfg.get("font_size", FONT_SIZE))
    min_font_size = int(text_cfg.get("min_font_size", 38))
    color = _hex_to_rgb(text_cfg.get("color"), fallback=TEXT_COLOR)
    shadow_color = _hex_to_rgb(text_cfg.get("shadow_color"), fallback=SHADOW_COLOR)
    shadow_offset = int(text_cfg.get("shadow_offset", 2))
    max_width_pct = float(text_cfg.get("max_width_pct", 0.86))
    max_height_pct = float(text_cfg.get("max_height_pct", 0.55))
    line_spacing_px = int(text_cfg.get("line_spacing_px", 14))
    align = str(text_cfg.get("align", "center")).lower()

    position_mode = str(text_cfg.get("position_mode", "preset")).lower()
    preset = str(text_cfg.get("preset", "center")).lower()
    x_pct = float(text_cfg.get("x_pct", 0.5))
    y_pct = float(text_cfg.get("y_pct", 0.5))
    
    # 1. Select Text
    texts = load_texts(texts_file)
    selected_text = random.choice(texts)
    print(f"📝 Selected Text: {selected_text}")
    
    # 2. Prepare Base Video
    if os.path.exists(base_video):
        print(f"🎬 Loading base video: {base_video}")
        clip = VideoFileClip(base_video)
        # If the video is longer than 60s, maybe cut it, but for now we take it as is or limit duration?
        # Let's keep it simple: take subclip up to 15s if it's too long, or loop if too short?
        # For now, just use it.
        if max_duration_seconds > 0 and clip.duration > max_duration_seconds:
            clip = clip.subclip(0, max_duration_seconds)
    else:
        print(f"⚠️ {base_video} not found! Generating a placeholder background.")
        # Create a dynamic-looking background (e.g., gradient or solid color)
        # For simplicity: Dark Blue solid color
        duration = max_duration_seconds if max_duration_seconds > 0 else VIDEO_DURATION
        clip = ColorClip(size=video_size, color=placeholder_bg, duration=duration)
        clip = _set_fps_compat(clip, fps)

    # 3. Create Text Overlay
    # We generate an image for the text to ensure complex scripts (Arabic) render correctly without ImageMagick issues
    w, h = clip.size
    if position_mode == "manual":
        pos = (int(w * x_pct), int(h * y_pct))
    else:
        if preset == "top":
            pos = (int(w * 0.5), int(h * 0.22))
        elif preset == "bottom":
            pos = (int(w * 0.5), int(h * 0.78))
        else:
            pos = (int(w * 0.5), int(h * 0.5))

    txt_img_array = create_text_image(
        selected_text,
        clip.size,
        font_path,
        font_size,
        color,
        shadow_color=shadow_color,
        shadow_offset=shadow_offset,
        max_width_pct=max_width_pct,
        max_height_pct=max_height_pct,
        line_spacing_px=line_spacing_px,
        align=align,
        position=pos,
        min_font_size=min_font_size,
    )
    
    txt_clip = _set_duration_compat(ImageClip(txt_img_array), clip.duration)
    
    # 4. Composite
    final_video = CompositeVideoClip([clip, txt_clip])
    
    # 5. Export
    print(f"💾 Exporting to {output_video}...")
    final_video.write_videofile(output_video, codec='libx264', audio_codec='aac', fps=fps)
    print("✅ Video generated successfully!")
    
    return selected_text

def upload_to_facebook(caption, config=None):
    """Uploads the generated video to Facebook."""
    
    # Load from config if passed, otherwise look for local logic or defaults
    if config:
        PAGE_ID = config.get('facebook_page_id')
        ACCESS_TOKEN = config.get('facebook_access_token')
    else:
        # Fallback or manual run
        PAGE_ID = 'YOUR_PAGE_ID'
        ACCESS_TOKEN = 'YOUR_ACCESS_TOKEN'
    
    if not PAGE_ID or not ACCESS_TOKEN or PAGE_ID == 'YOUR_PAGE_ID':
        print("⚠️ Facebook credentials not set. Video generated but not uploaded.")
        return

    print("🚀 Uploading to Facebook...")
    url = f"https://graph-video.facebook.com/v18.0/{PAGE_ID}/videos"
    
    try:
        # Open file safely
        with open(OUTPUT_VIDEO, 'rb') as video_file:
            files = {
                'file': video_file
            }
            data = {
                'description': caption,
                'access_token': ACCESS_TOKEN
            }
            
            import requests
            response = requests.post(url, files=files, data=data)
            
            if response.status_code == 200:
                print("✅ Upload successful! Video ID:", response.json().get('id'))
            else:
                print(f"❌ Upload failed: {response.text}")
                
    except Exception as e:
        print(f"❌ Error uploading: {e}")

if __name__ == "__main__":
    text = generate_video()
    # To test upload manually, you'd need to pass a config dict here or edit the defaults
    # upload_to_facebook(text, {'facebook_page_id': '...', 'facebook_access_token': '...'})
