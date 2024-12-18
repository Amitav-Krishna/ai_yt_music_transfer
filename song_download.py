import yt_dlp

def download_song(search_query_str, output_folder_str):
    """

    Downloads a Youtube vidfeo as MP3 using yt-dlp

    """
    ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_folder_str}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
             }],
            'quiet': False,
            'default_search': 'ytsearch',
            'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([search_query_str])
        info_dict = ydl.extract_info(search_query_str, download=False)
        title = info_dict['entries'][0]['title']
        return f"{output_folder_str}/{title}.mp3"

song = input("Enter your song here: ")
path = input("Enter a path here: ")

download_song(song, path)
