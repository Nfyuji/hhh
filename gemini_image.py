"""
Gemini Image Generation Module
Generates images using Google Gemini API and converts them to videos for YouTube upload.
"""

import os
import time
import sys

def generate_image_with_gemini(topic: str, api_key: str, output_path: str = None, style_prompt: str = "") -> str:
    """
    Search for a high-quality AI generated image from Lexica.art based on the topic.
    (Used as a 100% reliable free alternative since Gemini Imagen requires a paid tier).
    """
    import urllib.request
    import urllib.parse
    import json
    import random
    import os
    import time
    
    if not output_path:
        os.makedirs("uploads", exist_ok=True)
        timestamp = int(time.time())
        output_path = f"uploads/ai_image_{timestamp}.png"
    
    # Translate Arabic topic to English for better search results, or just use the topic directly
    search_query = topic
    if style_prompt:
        search_query += f" {style_prompt}"
        
    print(f"🎨 Searching high-quality AI images for: {search_query}")
    
    encoded_query = urllib.parse.quote(search_query)
    url = f"https://lexica.art/api/v1/search?q={encoded_query}"
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            images = data.get('images', [])
            
            if not images:
                # Fallback to a generic beautiful background if no results found
                fallback_query = urllib.parse.quote("beautiful nature landscape sunset")
                req = urllib.request.Request(
                    f"https://lexica.art/api/v1/search?q={fallback_query}", 
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req) as fallback_response:
                    data = json.loads(fallback_response.read().decode('utf-8'))
                    images = data.get('images', [])
            
            if images:
                # Pick a random image from the top 5 results to keep it varied
                selected_image = random.choice(images[:5])
                image_url = selected_image.get('src')
                
                print(f"📥 Downloading image from: {image_url}")
                
                # Download the actual image
                img_req = urllib.request.Request(
                    image_url, 
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(img_req) as img_res:
                    with open(output_path, "wb") as f:
                        f.write(img_res.read())
                        
                print(f"✅ Image saved to: {output_path}")
                return output_path
            else:
                raise RuntimeError("No images found in the Lexica database.")
                
    except Exception as e:
        raise RuntimeError(f"Failed to fetch AI image: {str(e)}")


def create_video_from_image(image_path: str, output_path: str = "output.mp4",
                           duration: int = 12, text: str = "", config: dict = None) -> str:
    """
    Convert a generated image into a short video with optional text overlay.
    
    Args:
        image_path: Path to the source image
        output_path: Where to save the output video
        duration: Video duration in seconds
        text: Optional text overlay
        config: Optional config dict for video/text settings
    
    Returns:
        Path to the generated video file
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    # Import video libraries
    try:
        try:
            from moviepy.editor import ImageClip, CompositeVideoClip
        except Exception:
            from moviepy.video.VideoClip import ImageClip
            from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
    except Exception as e:
        raise RuntimeError(
            "Missing dependency: moviepy. Install it with: pip install moviepy"
        ) from e
    
    from PIL import Image
    import numpy as np
    
    print(f"🎬 Creating video from image: {image_path}")
    
    # Load and resize image to 1080x1920 (9:16)
    video_cfg = (config or {}).get("video", {})
    target_size = tuple(video_cfg.get("size", [1080, 1920]))
    fps = int(video_cfg.get("fps", 24))
    
    img = Image.open(image_path)
    img = img.convert("RGB")
    
    # Resize to target size maintaining aspect ratio, then crop/pad
    img_ratio = img.width / img.height
    target_ratio = target_size[0] / target_size[1]
    
    if img_ratio > target_ratio:
        # Image is wider - fit height, crop width
        new_height = target_size[1]
        new_width = int(new_height * img_ratio)
    else:
        # Image is taller - fit width, crop height
        new_width = target_size[0]
        new_height = int(new_width / img_ratio)
    
    img = img.resize((new_width, new_height), Image.LANCZOS)
    
    # Center crop to target size
    left = (new_width - target_size[0]) // 2
    top = (new_height - target_size[1]) // 2
    img = img.crop((left, top, left + target_size[0], top + target_size[1]))
    
    img_array = np.array(img)
    
    # Create video clip from image
    clip = ImageClip(img_array)
    
    # Set duration
    if hasattr(clip, "set_duration"):
        clip = clip.set_duration(duration)
    elif hasattr(clip, "with_duration"):
        clip = clip.with_duration(duration)
    
    # Set fps
    if hasattr(clip, "set_fps"):
        clip = clip.set_fps(fps)
    elif hasattr(clip, "with_fps"):
        clip = clip.with_fps(fps)
    
    # Add text overlay if provided
    if text and text.strip():
        from post import create_text_image
        text_cfg = (config or {}).get("text_overlay", {})
        
        # Get font settings from config
        font_path = text_cfg.get("font_path", "")
        if not font_path or not os.path.exists(font_path):
            from post import find_font_path, FONT_PATH
            font_path = find_font_path() or FONT_PATH
        
        font_size = int(text_cfg.get("font_size", 45))
        min_font_size = int(text_cfg.get("min_font_size", 38))
        
        from post import _hex_to_rgb
        color = _hex_to_rgb(text_cfg.get("color"), fallback=(255, 255, 255))
        shadow_color = _hex_to_rgb(text_cfg.get("shadow_color"), fallback=(0, 0, 0))
        shadow_offset = int(text_cfg.get("shadow_offset", 2))
        max_width_pct = float(text_cfg.get("max_width_pct", 0.86))
        max_height_pct = float(text_cfg.get("max_height_pct", 0.55))
        line_spacing_px = int(text_cfg.get("line_spacing_px", 14))
        align = str(text_cfg.get("align", "center")).lower()
        
        # Position at bottom for better readability over image
        pos = (target_size[0] // 2, int(target_size[1] * 0.78))
        
        txt_img_array = create_text_image(
            text, target_size, font_path, font_size, color,
            shadow_color=shadow_color, shadow_offset=shadow_offset,
            max_width_pct=max_width_pct, max_height_pct=max_height_pct,
            line_spacing_px=line_spacing_px, align=align,
            position=pos, min_font_size=min_font_size,
        )
        
        txt_clip = ImageClip(txt_img_array)
        if hasattr(txt_clip, "set_duration"):
            txt_clip = txt_clip.set_duration(duration)
        elif hasattr(txt_clip, "with_duration"):
            txt_clip = txt_clip.with_duration(duration)
        
        clip = CompositeVideoClip([clip, txt_clip])
    
    # Export video
    print(f"💾 Exporting video to: {output_path}")
    
    output_dir = os.path.dirname(output_path) if os.path.dirname(output_path) else "."
    if output_dir and output_dir != "." and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    try:
        clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            fps=fps,
            logger=None
        )
        
        if not os.path.exists(output_path):
            raise RuntimeError(f"Video file was not created: {output_path}")
        
        file_size = os.path.getsize(output_path)
        print(f"✅ Video created! Size: {file_size / 1024 / 1024:.2f} MB")
    finally:
        try:
            clip.close()
        except:
            pass
    
    return output_path


def generate_and_upload_to_youtube(topic: str, config: dict, 
                                   title: str = None, description: str = None,
                                   add_text_overlay: bool = True) -> dict:
    """
    Complete flow: Generate image with Gemini → Create video → Upload to YouTube.
    
    Args:
        topic: The topic for image generation
        config: Full config dict
        title: Custom title (default: auto-generated from topic)
        description: Custom description (default: auto-generated from topic)
        add_text_overlay: Whether to add text on the video
    
    Returns:
        dict with keys: image_path, video_path, youtube_video_id
    """
    import youtube as yt
    
    gemini_cfg = config.get("gemini", {})
    style_prompt = gemini_cfg.get("image_style", "")
    
    result = {
        "image_path": None,
        "video_path": None,
        "youtube_video_id": None,
    }
    
    # Step 1: Generate image
    print("=" * 50)
    print("📸 Step 1: Generating image with AI (Lexica)...")
    image_path = generate_image_with_gemini(
        topic=topic,
        api_key="", # No longer needed
        style_prompt=style_prompt
    )
    result["image_path"] = image_path
    
    # Step 2: Create video from image
    print("🎬 Step 2: Creating video from image...")
    output_video = (config.get("paths", {}).get("output_video", "output.mp4"))
    duration = int(config.get("video", {}).get("max_duration_seconds", 12))
    
    video_path = create_video_from_image(
        image_path=image_path,
        output_path=output_video,
        duration=duration,
        text=topic if add_text_overlay else "",
        config=config
    )
    result["video_path"] = video_path
    
    # Step 3: Upload to YouTube
    print("📺 Step 3: Uploading to YouTube...")
    
    # Auto-generate title and description if not provided
    if not title:
        title = topic[:100]  # YouTube title limit
    if not description:
        description = f"{topic}\n\n#shorts #motivation #quotes #تحفيز #حكم"
    
    video_id = yt.upload_video(
        title=title,
        description=description,
        file_path=video_path,
        config=config
    )
    result["youtube_video_id"] = video_id
    
    print("=" * 50)
    if video_id:
        print(f"🎉 Success! YouTube Video ID: {video_id}")
        print(f"🔗 URL: https://youtube.com/shorts/{video_id}")
    else:
        print("⚠️ Upload completed but no video ID returned")
    
    return result
