import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import shlex
import yt_dlp
import os
import glob
from threading import Thread
from queue import Queue, Empty
import pyperclip  # For copying text to clipboard
import re
from dotenv import load_dotenv
import openai
load_dotenv()

# OpenAI API Key (Replace with your own)
OPENAI_API_TOKEN = os.getenv("OPENAI_API_TOKEN")
YOUTUBE_API_TOKEN = os.getenv("YOUTUBE_API_TOKEN")
client = openai.OpenAI(api_key=OPENAI_API_TOKEN)

def sanitize_filename(filename):
    """
    Sanitize the filename by removing trailing numbers, special characters, and underscores.
    """
    filename = re.sub(r'[^a-zA-Z0-9]', '', filename)
    filename = re.sub(r'\d$', '', filename)
    return filename
def get_similar_songs(search_query, num_suggestions=2):
    """Use OpenAI's GPT model to suggest similar songs based on the search query."""
    try:
        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",  # Use a supported model
            prompt=f"Suggest {num_suggestions} songs similar to '{search_query}'. Do **NOT** append [NUM]. to the beginning.:",
            max_tokens=50,
            n=1,
            stop=None,
            temperature=0.7,
        )
        suggestions = response.choices[0].text.strip().split('\n')
        suggestions = [s.strip() for s in suggestions if s.strip()]

        # Remove any pattern that looks like a number followed by a period (e.g., "1.", "2.")
        suggestions = [re.sub(r'^\d+\.', '', s).strip() for s in suggestions]

        return suggestions if suggestions else ["No similar songs found", "No similar songs found"]
    except Exception as e:
        print(f"Error getting similar songs: {e}")
        return ["No similar songs found", "No similar songs found"]
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
        info = ydl.extract_info(search_query, download=True)
        original_title = info.get('title', search_query)  # Fallback to search_query if title is missing
        downloaded_files = glob.glob(f"{output_folder}/*.mp3")
        if not downloaded_files:
            raise FileNotFoundError("MP3 file not found after download.")

        # Get the most recently downloaded file
        original_file = max(downloaded_files, key=os.path.getctime)

        sanitized_title = sanitize_filename(original_title)
        new_file_name = f"{sanitized_title}.mp3"
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
        
        # Rescan the file on the Android device
        android_file_path = f"{android_folder}/{local_file_name}"
        print(f"File pushed to: {android_file_path}")  # Add this line to print the path
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
