import yt_dlp

def download_song(search_query, output_folder):
    """

    Downloads a Youtube vidfeo as MP3 using yt-dlp

    """
    ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_folder}/%{title}s.%{ext}s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
             }]
            'quiet': False,
            'default_search': 'ytsearch',
            'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([search_query])
        info_dict = ydl.extract_info(search_query, download=False)
        title = info_dict['entries'][0]['title']
        return f"{output_folder}/{title}.mp3"


