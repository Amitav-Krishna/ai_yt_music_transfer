import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import shlex
import yt_dlp
import os
import glob
import difflib
from threading import Thread
from queue import Queue, Empty
import pyperclip  # For copying text to clipboard
import re
from datetime import datetime

# YouTube API Key (Replace with your own)
YOUTUBE_API_KEY = "AIzaSyDlXPyM-PdVDc8JtS9nyIc9mn8nXQQdZJg"

def sanitize_filename(filename):
    """Sanitize the filename by removing invalid characters and truncating it."""
    # Replace invalid characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    
    # Truncate the filename to first 10 and last 10 characters
    if len(sanitized) > 20:  # Only truncate if the filename is longer than 20 characters
        first_part = sanitized[:10]
        last_part = sanitized[-10:]
        sanitized = f"{first_part}...{last_part}"
    
    return sanitized
def get_similar_songs(search_query, num_suggestions=2):
    """Search for and return similar songs based on the search query."""
    ydl_opts = {
        'quiet': True,
        'default_search': 'ytsearch10',  # Get more results
        'noplaylist': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_results = ydl.extract_info(search_query, download=False)['entries']
    
    if not search_results:
        return ["No similar songs found", "No similar songs found"]
    
    original_title = search_results[0]['title'].lower()
    
    # Filter out remixes, live versions, and similar titles
    similar_songs = []
    for entry in search_results[1:]:
        title = entry['title'].lower()
        if difflib.SequenceMatcher(None, original_title, title).ratio() < 0.7:
            similar_songs.append(title)
        if len(similar_songs) == num_suggestions:
            break
    
    return similar_songs if similar_songs else ["No similar songs found", "No similar songs found"]

def download_song(search_query, output_folder):
    """Downloads a YouTube video as MP3 using yt-dlp and renames it based on the search query."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'default_search': 'ytsearch',
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(search_query, download=True)
        downloaded_files = glob.glob(f"{output_folder}/*.mp3")
        if not downloaded_files:
            raise FileNotFoundError("MP3 file not found after download.")
        
        # Get the most recently downloaded file
        original_file = max(downloaded_files, key=os.path.getctime)

        # Sanitize the search query and add a timestamp to ensure uniqueness
        sanitized_query = sanitize_filename(search_query)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_file_name = f"{sanitized_query}_{timestamp}.mp3"
        new_file_path = os.path.join(output_folder, new_file_name)

        # Rename the file
        os.rename(original_file, new_file_path)
        return new_file_path

def is_adb_working():
    """Check if ADB is connected and working."""
    try:
        result = subprocess.run("adb devices", shell=True, check=True, capture_output=True, text=True)
        return "device" in result.stdout
    except subprocess.CalledProcessError:
        return False

def transfer_to_android(local_file_path, android_folder):
    """Transfer the downloaded file to an Android device using ADB."""
    if not is_adb_working():
        raise RuntimeError("ADB is not running or no device is connected.")
    try:
        local_file_name = os.path.basename(local_file_path)
        android_folder = shlex.quote(android_folder)
        adb_push_command = f"adb push {shlex.quote(local_file_path)} {android_folder}"
        subprocess.run(adb_push_command, shell=True, check=True)
        android_file_path = f"{android_folder}/{local_file_name}"
        adb_rescan_command = f"adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{android_file_path}"
        subprocess.run(adb_rescan_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ADB transfer failed: {e}")

class DownloadThread(Thread):
    """Thread class for handling the download and transfer operations."""
    def __init__(self, queue, search_query, output_folder, android_folder):
        Thread.__init__(self)
        self.queue = queue
        self.search_query = search_query
        self.output_folder = output_folder
        self.android_folder = android_folder

    def run(self):
        try:
            # Get similar songs
            self.queue.put(("status", "Searching for similar songs..."))
            similar_songs = get_similar_songs(self.search_query)
            self.queue.put(("similar", similar_songs))

            # Download song
            self.queue.put(("status", "Downloading the song..."))
            downloaded_file = download_song(self.search_query, self.output_folder)

            # Transfer to Android
            self.queue.put(("status", "Transferring to Android device..."))
            transfer_to_android(downloaded_file, self.android_folder)

            self.queue.put(("success", f"Song '{self.search_query}' successfully downloaded and transferred!"))
        except Exception as e:
            self.queue.put(("error", str(e)))
        finally:
            self.queue.put(("enable_button", None))

class SongDownloaderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Song Downloader")
        self.root.geometry("600x600")
        
        # Initialize message queue
        self.message_queue = Queue()
        
        # Track previously searched songs
        self.previously_searched_songs = set()
        
        self.create_widgets()
        self.start_update_cycle()
    
    def create_widgets(self):
        """Create and arrange all GUI widgets."""
        # Song Name Entry
        tk.Label(self.root, text="Song Name:").pack(pady=5)
        self.song_name_var = tk.StringVar()
        tk.Entry(self.root, textvariable=self.song_name_var, width=50).pack(pady=5)

        # Output Folder Selection
        tk.Label(self.root, text="Output Folder:").pack(pady=5)
        self.output_folder_var = tk.StringVar()
        tk.Entry(self.root, textvariable=self.output_folder_var, width=50).pack(pady=5)
        tk.Button(self.root, text="Browse", command=self.browse_output_folder).pack(pady=5)

        # Android Folder Entry
        tk.Label(self.root, text="Android Device Folder:").pack(pady=5)
        self.android_folder_var = tk.StringVar(value="/sdcard/Music")
        tk.Entry(self.root, textvariable=self.android_folder_var, width=50).pack(pady=5)

        # Similar Songs Labels and Copy Buttons
        self.similar_song_1 = tk.StringVar(value="Similar 1: None")
        self.similar_song_2 = tk.StringVar(value="Similar 2: None")
        tk.Label(self.root, textvariable=self.similar_song_1, fg="blue").pack(pady=5)
        self.copy_button_1 = tk.Button(self.root, text="Copy", command=lambda: self.copy_to_clipboard(self.similar_song_1.get()))
        self.copy_button_1.pack(pady=5)
        tk.Label(self.root, textvariable=self.similar_song_2, fg="blue").pack(pady=5)
        self.copy_button_2 = tk.Button(self.root, text="Copy", command=lambda: self.copy_to_clipboard(self.similar_song_2.get()))
        self.copy_button_2.pack(pady=5)

        # Download Button and Status Label
        self.download_button = tk.Button(self.root, text="Download & Transfer", command=self.download_and_transfer)
        self.download_button.pack(pady=20)
        
        tk.Button(self.root, text="Exit", command=self.root.quit).pack(pady=5)
        
        self.status_label = tk.Label(self.root, text="", fg="green")
        self.status_label.pack(pady=10)

    def browse_output_folder(self):
        """Open a folder selection dialog."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.output_folder_var.set(folder_selected)

    def copy_to_clipboard(self, text):
        """Copy the given text to the clipboard."""
        # Remove the "Similar X: " prefix before copying
        if text.startswith("Similar 1: ") or text.startswith("Similar 2: "):
            text = text.split(": ", 1)[1]
        pyperclip.copy(text)
        messagebox.showinfo("Copied", f"'{text}' copied to clipboard!")

    def download_and_transfer(self):
        """Start the download process in a separate thread."""
        search_query = self.song_name_var.get()
        output_folder = self.output_folder_var.get()
        android_folder = self.android_folder_var.get()

        if not search_query or not output_folder or not android_folder:
            messagebox.showerror("Error", "All fields are required.")
            return

        # Add the current search query to the previously searched songs
        self.previously_searched_songs.add(search_query.lower())

        # Disable the download button while processing
        self.download_button.config(state="disabled")
        
        # Start the download thread
        download_thread = DownloadThread(self.message_queue, search_query, output_folder, android_folder)
        download_thread.daemon = True
        download_thread.start()

    def update_gui(self):
        """Process any pending messages from the download thread."""
        try:
            while True:  # Process all pending messages
                try:
                    msg_type, msg_content = self.message_queue.get_nowait()
                    
                    if msg_type == "status":
                        self.status_label.config(text=msg_content)
                    elif msg_type == "similar":
                        # Filter out previously searched songs
                        similar_songs = [song for song in msg_content if song.lower() not in self.previously_searched_songs]
                        if len(similar_songs) >= 1:
                            self.similar_song_1.set(f"Similar 1: {similar_songs[0]}")
                        else:
                            self.similar_song_1.set("Similar 1: None")
                        if len(similar_songs) >= 2:
                            self.similar_song_2.set(f"Similar 2: {similar_songs[1]}")
                        else:
                            self.similar_song_2.set("Similar 2: None")
                    elif msg_type == "success":
                        self.status_label.config(text="")
                        messagebox.showinfo("Success", msg_content)
                    elif msg_type == "error":
                        self.status_label.config(text="")
                        messagebox.showerror("Error", f"An error occurred: {msg_content}")
                    elif msg_type == "enable_button":
                        self.download_button.config(state="normal")
                    
                    self.message_queue.task_done()
                except Empty:
                    break  # Exit the loop if the queue is empty
        finally:
            # Schedule the next update
            self.root.after(100, self.update_gui)

    def start_update_cycle(self):
        """Start the GUI update cycle."""
        self.root.after(100, self.update_gui)

    def run(self):
        """Start the main application loop."""
        self.root.mainloop()

if __name__ == "__main__":
    app = SongDownloaderApp()
    app.run()
