import requests
import json

try:
    response = requests.get('http://127.0.0.1:5000/logs')
    logs = response.json().get('logs', [])
    print("\n".join(logs[-20:])) # Print last 20 logs
except Exception as e:
    print(f"Failed to fetch logs: {e}")
