import requests
from dotenv import load_dotenv
import os

load_dotenv()
LAST_FM_KEY = os.getenv('LAST_FM_KEY')

def get_similar_songs(song_name, artist=None, limit=4):
    print("Fetching similar songs using last.fm")
    base_url = "http://ws.audioscrobbler.com/2.0/"
    params = {
            "method": "track.getsimilar",
            "track": song_name,
            "api_key": LAST_FM_KEY,
            "format": "json",
            "limit": limit
    }
    if artist:
        params["artist"] = artist

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if "similartracks" in data and "track" in data["similartracks"]:
            similar_tracks = data["similartracks"]["track"]
            return [f"{track['name']} by {track['artist']['name']}" for track in similar_tracks]
        else:
            print("No similar songs found.")
            return []
    else:
        print("Failed to fetch similar songs.")
        return []

print(get_similar_songs("All I want for Christmas is you", "Mariah Carey"))
