import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

print("Python executable:", sys.executable)
print("Current working directory:", os.getcwd())

try:
    print("Attempting to import moviepy...")
    # Try 2.x import
    try:
        from moviepy.editor import VideoFileClip
        print("Imported moviepy.editor (v1.x style or compatibility)")
    except ImportError:
        try:
             from moviepy.video.io.VideoFileClip import VideoFileClip
             print("Imported moviepy.video.io.VideoFileClip (v2.x style)")
        except ImportError as e:
            print("Failed to import VideoFileClip:", e)
            raise

    import post
    print("Imported post.py")
    
    # Mock config
    config = {
        "paths": {
            "texts_file": "texts.txt",
            "base_video": "uploads/base.mp4",
            "output_video": "debug_output.mp4"
        },
        "video": {
            "max_duration_seconds": 5
        },
        "text_overlay": {
            "font_path": "C:\\Windows\\Fonts\\arial.ttf"
        }
    }

    if not os.path.exists("uploads/base.mp4"):
        print("ERROR: uploads/base.mp4 does not exist!")
    else:
        print("uploads/base.mp4 found.")

    print("Calling post.generate_video()...")
    post.generate_video(config)
    print("SUCCESS: Video generated.")

except Exception as e:
    print("CAUGHT EXCEPTION:")
    print(e)
    import traceback
    traceback.print_exc()
