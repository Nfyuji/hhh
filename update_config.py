import json
import os

config_path = 'c:\\Users\\Administrator\\Desktop\\facebook\\config.json'

if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        if 'youtube' in data and 'redirect_uri' in data['youtube']:
            print(f"Removing redirect_uri: {data['youtube']['redirect_uri']}")
            del data['youtube']['redirect_uri']
            
            with open(config_path, 'w') as f:
                json.dump(data, f, indent=4)
            print("Successfully updated config.json")
        else:
            print("redirect_uri not found in youtube config.")
            
    except Exception as e:
        print(f"Error updating config: {e}")
else:
    print("config.json not found")
