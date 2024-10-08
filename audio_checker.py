import sys
import os
import numpy as np
import pyloudnorm as pyln
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QScrollArea
)
from PyQt5.QtGui import QPixmap, QImage, QIcon
from PyQt5.QtCore import Qt
from pydub import AudioSegment
import music_tag

class AudioFileInfo:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_type = os.path.splitext(file_path)[1][1:].upper()
        self.lufs = None
        self.metadata_exists = False
        self.metadata = {}
        self.artwork = None
        self.load_info()

    def load_info(self):
        try:
            audio = AudioSegment.from_file(self.file_path)
            samples = np.array(audio.get_array_of_samples())
            sample_rate = audio.frame_rate
            if audio.channels > 1:
                samples = samples.reshape((-1, audio.channels))
            meter = pyln.Meter(sample_rate)
            self.lufs = meter.integrated_loudness(samples.astype(np.float32) / (2**15))
        except Exception as e:
            print(f"Error loading audio for LUFS calculation: {e}")
            self.lufs = None

        try:
            f = music_tag.load_file(self.file_path)
            self.metadata = {
                'Title': f['tracktitle'].value,
                'Artist': f['artist'].value,
                'Album': f['album'].value,
                'Genre': f['genre'].value,
                'Year': f['year'].value,
            }
            self.metadata_exists = all(self.metadata.values())
            if f['artwork']:
                art_data = f['artwork'].first.data
                image = QImage.fromData(art_data)
                self.artwork = QPixmap.fromImage(image)
            else:
                self.artwork = None
        except Exception as e:
            print(f"Error loading metadata: {e}")
            self.metadata_exists = False
            self.metadata = {}
            self.artwork = None

class AudioCheckerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio File Checker")
        self.setWindowIcon(QIcon("favicon.icns"))  # Add your icon file here
        self.resize(800, 600)
        self.audio_files = []
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Folder selection
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Folder:")
        self.folder_path_label = QLabel("")
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_path_label)
        folder_layout.addWidget(self.browse_button)
        main_layout.addLayout(folder_layout)

        # Check button
        self.check_button = QPushButton("Check Audio Files")
        self.check_button.clicked.connect(self.check_audio_files)
        self.check_button.setEnabled(False)
        main_layout.addWidget(self.check_button)

        # Audio file list
        self.audio_list = QListWidget()
        self.audio_list.itemClicked.connect(self.display_file_info)
        main_layout.addWidget(self.audio_list)

        # Detailed info display
        self.info_label = QLabel("Select a file to view details.")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignTop)
        self.info_label.setFixedHeight(200)

        # Artwork display
        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(200, 200)
        self.artwork_label.setStyleSheet("border: 1px solid black;")

        info_layout = QHBoxLayout()
        info_layout.addWidget(self.artwork_label)
        info_layout.addWidget(self.info_label)

        main_layout.addLayout(info_layout)

        self.setLayout(main_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Check Audio Files")
        if folder:
            self.folder_path_label.setText(folder)
            self.check_button.setEnabled(True)

    def check_audio_files(self):
        folder_path = self.folder_path_label.text()
        if not folder_path:
            QMessageBox.warning(self, "Error", "Please select a folder first.")
            return

        # Clear previous data
        self.audio_files.clear()
        self.audio_list.clear()
        self.info_label.setText("Select a file to view details.")
        self.artwork_label.clear()

        # Get audio files
        supported_formats = ('.mp3', '.wav', '.aiff', '.flac', '.ogg', '.m4a')
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(supported_formats):
                    file_path = os.path.join(root, file)
                    audio_info = AudioFileInfo(file_path)
                    self.audio_files.append(audio_info)
                    # Add to list widget
                    item_text = f"{audio_info.file_name} | {audio_info.lufs:.2f} LUFS | {'✔' if audio_info.metadata_exists else '✘'} | {audio_info.file_type}"
                    item = QListWidgetItem(item_text)
                    self.audio_list.addItem(item)

        # Check if all LUFS values are the same
        lufs_values = [audio.lufs for audio in self.audio_files if audio.lufs is not None]
        if lufs_values:
            first_lufs = lufs_values[0]
            all_same = all(np.isclose(lufs, first_lufs, atol=0.1) for lufs in lufs_values)
            if all_same:
                QMessageBox.information(self, "LUFS Check", f"All files have the same LUFS value: {first_lufs:.2f} LUFS")
            else:
                QMessageBox.warning(self, "LUFS Check", "Not all files have the same LUFS value.")

    def display_file_info(self, item):
        index = self.audio_list.row(item)
        audio_info = self.audio_files[index]

        # Display metadata
        metadata_text = f"File: {audio_info.file_name}\n"
        metadata_text += f"Type: {audio_info.file_type}\n"
        metadata_text += f"LUFS: {audio_info.lufs:.2f} LUFS\n\n"
        metadata_text += "Metadata:\n"
        for key, value in audio_info.metadata.items():
            metadata_text += f"  {key}: {value}\n"

        self.info_label.setText(metadata_text)

        # Display artwork
        if audio_info.artwork:
            pixmap = audio_info.artwork.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.artwork_label.setPixmap(pixmap)
        else:
            self.artwork_label.clear()
            self.artwork_label.setText("No Artwork")

def main():
    app = QApplication(sys.argv)
    checker_app = AudioCheckerApp()
    checker_app.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
