import sys
import os
import uuid
import base64
import json
import time
import requests
import threading

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QProgressBar, QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject

import openai
import openai.error
from pydub import AudioSegment
from cryptography.fernet import Fernet
import music_tag
from PIL import Image  # Ensure Pillow is installed

# Suppress macOS Tkinter warning (optional)
os.environ['TK_SILENCE_DEPRECATION'] = '1'

# ===============================
# Implementations of All Functions
# ===============================

def get_system_unique_key():
    # Generate a unique key based on the system's MAC address
    mac = uuid.getnode()
    mac_bytes = mac.to_bytes(6, 'little')
    key = base64.urlsafe_b64encode(mac_bytes.ljust(32, b'\0'))
    return key

def encrypt_api_key(api_key, key):
    fernet = Fernet(key)
    encrypted_api_key = fernet.encrypt(api_key.encode())
    return encrypted_api_key

def decrypt_api_key(encrypted_api_key, key):
    fernet = Fernet(key)
    api_key = fernet.decrypt(encrypted_api_key).decode()
    return api_key

def test_api_key(api_key):
    try:
        openai.api_key = api_key
        # Attempt to list models
        openai.Model.list()
        print("API key is valid.")
        return True
    except openai.error.AuthenticationError:
        print("Invalid API key.")
        return False
    except Exception as e:
        print(f"An error occurred while testing the API key: {e}")
        return False

def get_api_key():
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.enc')
    system_key = get_system_unique_key()

    while True:
        if os.path.exists(key_file):
            # Read and decrypt the API key
            try:
                with open(key_file, 'rb') as f:
                    encrypted_api_key = f.read()
                api_key = decrypt_api_key(encrypted_api_key, system_key)
                # Test the API key
                if test_api_key(api_key):
                    return api_key
                else:
                    print("Invalid API key stored. Please enter a valid API key.")
                    os.remove(key_file)
            except Exception as e:
                print(f"Error decrypting API key: {e}")
                os.remove(key_file)
        else:
            # Prompt user to enter the API key
            api_key = input("Enter your OpenAI API key: ").strip()
            # Test the API key
            if test_api_key(api_key):
                # Encrypt and save the API key
                encrypted_api_key = encrypt_api_key(api_key, system_key)
                with open(key_file, 'wb') as f:
                    f.write(encrypted_api_key)
                print("API key saved securely.")
                return api_key
            else:
                print("Invalid API key. Please try again.")

def get_name_artist(filename):
    prompt = f"""
Given the filename: '{filename}', extract the song title and artist, following these rules:

- The song title should not include phrases like "Original Mix", "Extended Mix", or similar.

- If the song is a remix, include the type of remix in the title within brackets. For example, "Song Title (Remix Type)".

- If the remixer is mentioned in the filename and it's a remix, set the artist to the remixer's name.

- The artist should be the primary artist. If multiple artists are listed (e.g., "Artist 1 & Artist 2"), use "Artist 1" as the artist.

IMPORTANT:

- Return only the JSON object with keys "title" and "artist".

- Do not include any additional text or explanations.

- Ensure the JSON is in a single line.

Example of the required format:

{{"title": "Song Title", "artist": "Artist Name"}}
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0,
        )
        content = response.choices[0].message.content.strip()
        print("OpenAI API response:", content)  # Debugging line

        # Ensure the response is valid JSON
        try:
            result = json.loads(content)
            title = result.get('title', '').strip()
            artist = result.get('artist', '').strip()
            if not title or not artist:
                raise ValueError("Title or artist is missing in the response.")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from OpenAI response: {e}")
            print("Response was:", content)
            title = ''
            artist = ''
        except ValueError as e:
            print(f"Invalid response from OpenAI: {e}")
            print("Response was:", content)
            title = ''
            artist = ''
        # Use only the primary artist
        artist = artist.split('&')[0].split(',')[0].strip()
        return title, artist
    except openai.error.RateLimitError as e:
        print("Error: You have exceeded your API quota or rate limit.")
        print("Please check your OpenAI account's billing and usage details.")
        return '', ''
    except openai.error.OpenAIError as e:
        print(f"An error occurred while communicating with OpenAI: {e}")
        return '', ''
    except Exception as e:
        print(f"Unexpected error in get_name_artist: {e}")
        return '', ''

def generate_image_prompt(title, artist):
    # Generate a prompt that creates a vibrant album cover without text
    return f"An abstract, vibrant album cover without any text, representing the mood and style of the song '{title}' by '{artist}'. Digital art, colorful, modern design."

# Define signals for communication between threads
class WorkerSignals(QObject):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal()

class ConversionWorker(threading.Thread):
    def __init__(self, input_files, output_dir, signals):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.signals = signals

    def run(self):
        total_files = len(self.input_files)
        for idx, file_path in enumerate(self.input_files, start=1):
            file = os.path.basename(file_path)
            status_text = f"Processing file {idx}/{total_files}: {file}"
            progress_percent = int((idx - 1) / total_files * 100)
            self.signals.progress.emit(status_text, progress_percent)

            # Load the audio file
            try:
                audio = AudioSegment.from_file(file_path)
            except Exception as e:
                error_msg = f"Error loading {file}: {e}"
                self.signals.progress.emit(error_msg, progress_percent)
                continue

            # Get the base filename without extension
            base_filename = os.path.splitext(file)[0]

            # Use OpenAI API to get name and artist
            title, artist = get_name_artist(base_filename)
            if not title:
                title = base_filename  # Use the base filename as the title
            if not artist:
                artist = "Unknown Artist"
            status_text = f"Extracted Title: '{title}', Artist: '{artist}'"
            self.signals.progress.emit(status_text, progress_percent)

            # Create the new filename
            new_filename = f"{title} - {artist}.aiff"
            aiff_path = os.path.join(self.output_dir, new_filename)

            # Convert to AIFF and save in output directory
            try:
                audio.export(aiff_path, format='aiff')
                self.signals.progress.emit(f"Converted {file} to {new_filename}", progress_percent)
            except Exception as e:
                error_msg = f"Error converting {file} to AIFF: {e}"
                self.signals.progress.emit(error_msg, progress_percent)
                continue

            # Set metadata using music-tag and add artwork if available
            try:
                # Load the AIFF file
                f = music_tag.load_file(aiff_path)
                f['tracktitle'] = title
                f['artist'] = artist

                # Load the original file to get artwork
                original_file = music_tag.load_file(file_path)
                # Check if artwork exists
                if original_file['artwork']:
                    # Assign the artwork from the original file to the AIFF file
                    f['artwork'] = original_file['artwork'].value
                    self.signals.progress.emit(f"Artwork added to {new_filename}", progress_percent)
                else:
                    self.signals.progress.emit(f"No artwork found in {file}, generating artwork...", progress_percent)
                    # Generate an image using OpenAI API with retry logic
                    image_prompt = generate_image_prompt(title, artist)
                    max_retries = 3
                    retry_delay = 5  # seconds
                    for attempt in range(1, max_retries + 1):
                        try:
                            response = openai.Image.create(
                                prompt=image_prompt,
                                n=1,
                                size="1024x1024",
                                response_format="url"
                            )
                            image_url = response['data'][0]['url']
                            # Download the image data
                            image_response = requests.get(image_url)
                            if image_response.status_code == 200:
                                image_data = image_response.content
                                f['artwork'] = image_data
                                self.signals.progress.emit(f"Generated and added artwork to {new_filename}", progress_percent)
                                break  # Exit the retry loop on success
                            else:
                                error_msg = f"Failed to download image. Status code: {image_response.status_code}"
                                self.signals.progress.emit(error_msg, progress_percent)
                                if attempt < max_retries:
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff
                        except openai.error.OpenAIError as e:
                            error_msg = f"Error generating artwork: {e}"
                            self.signals.progress.emit(error_msg, progress_percent)
                            if attempt < max_retries:
                                time.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                            else:
                                self.signals.progress.emit("Max retries reached. Skipping artwork.", progress_percent)
                        except Exception as e:
                            error_msg = f"Unexpected error generating artwork: {e}"
                            self.signals.progress.emit(error_msg, progress_percent)
                            if attempt < max_retries:
                                time.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                            else:
                                self.signals.progress.emit("Max retries reached. Skipping artwork.", progress_percent)

                # Save the metadata changes
                f.save()
                self.signals.progress.emit(f"Metadata updated for {new_filename}", progress_percent)
            except Exception as e:
                error_msg = f"Error setting metadata for {new_filename}: {e}"
                self.signals.progress.emit(error_msg, progress_percent)
                continue

            # Update progress
            progress_percent = int(idx / total_files * 100)
            self.signals.progress.emit(status_text, progress_percent)

        self.signals.finished.emit()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Converter and Metadata Editor")
        self.setWindowIcon(QIcon("favicon.icns"))  # Add your icon file here
        self.resize(600, 400)
        self.input_files = []
        self.output_dir = ""
        self.worker = None

        self.init_ui()
        self.setup_api_key()

    def init_ui(self):
        # Input Files Section
        self.input_label = QLabel("No input files selected.")
        self.select_input_button = QPushButton("Select Input Files")
        self.select_input_button.clicked.connect(self.select_input_files)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_label)
        input_layout.addWidget(self.select_input_button)

        # Output Directory Section
        self.output_label = QLabel("No output folder selected.")
        self.select_output_button = QPushButton("Select Output Folder")
        self.select_output_button.clicked.connect(self.select_output_folder)

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_label)
        output_layout.addWidget(self.select_output_button)

        # Convert Button
        self.convert_button = QPushButton("Convert")
        self.convert_button.clicked.connect(self.start_conversion)
        self.convert_button.setEnabled(False)

        # Progress Bar and Status
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(input_layout)
        main_layout.addLayout(output_layout)
        main_layout.addWidget(self.convert_button)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(QLabel("Status:"))
        main_layout.addWidget(self.status_text)

        self.setLayout(main_layout)

    def select_input_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Input Audio Files", "", "Audio Files (*.mp3 *.wav *.aiff *.flac);;All Files (*)"
        )
        if files:
            self.input_files = files
            self.input_label.setText(f"{len(self.input_files)} files selected.")
        else:
            self.input_files = []
            self.input_label.setText("No input files selected.")
        self.update_convert_button_state()

    def select_output_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if directory:
            self.output_dir = directory
            self.output_label.setText(f"Output folder: {self.output_dir}")
        else:
            self.output_dir = ""
            self.output_label.setText("No output folder selected.")
        self.update_convert_button_state()

    def update_convert_button_state(self):
        if self.input_files and self.output_dir:
            self.convert_button.setEnabled(True)
        else:
            self.convert_button.setEnabled(False)

    def setup_api_key(self):
        # Implement your API key setup logic here
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            openai.api_key = get_api_key()
        else:
            if not test_api_key(openai.api_key):
                print("Invalid API key from environment variable.")
                openai.api_key = get_api_key()

    def start_conversion(self):
        self.convert_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_text.clear()

        self.signals = WorkerSignals()
        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.conversion_finished)

        self.worker = ConversionWorker(self.input_files, self.output_dir, self.signals)
        self.worker.start()

    def update_progress(self, message, progress):
        self.status_text.append(message)
        self.progress_bar.setValue(progress)

    def conversion_finished(self):
        QMessageBox.information(self, "Conversion Complete", "Processing complete.")
        self.convert_button.setEnabled(True)

def main():
    # Ensure required libraries are installed
    try:
        import openai
        from pydub import AudioSegment
        from cryptography.fernet import Fernet
        import music_tag
        from PIL import Image
    except ImportError as e:
        print(f"Required library not found: {e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
