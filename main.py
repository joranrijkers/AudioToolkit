import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt
import subprocess


class MainLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Tools Launcher")
        self.setWindowIcon(QIcon("favicon.icns"))  # Add your icon file here
        self.resize(400, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Title for the launcher
        title = QLabel("Audio Tools Suite")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(title)

        # Audio Checker
        checker_button = QPushButton("Launch Audio Checker")
        checker_button.clicked.connect(self.launch_audio_checker)
        layout.addWidget(checker_button)

        checker_description = QLabel("The Audio Checker scans audio files, checks LUFS levels, metadata, and file types.")
        checker_description.setStyleSheet("font-size: 12px; color: grey; margin-bottom: 20px;")
        layout.addWidget(checker_description)

        # Audio Converter
        converter_button = QPushButton("Launch Audio Converter")
        converter_button.clicked.connect(self.launch_audio_converter)
        layout.addWidget(converter_button)

        converter_description = QLabel("The Audio Converter converts audio files into different formats while preserving metadata.")
        converter_description.setStyleSheet("font-size: 12px; color: grey; margin-bottom: 20px;")
        layout.addWidget(converter_description)

        # Audio File Editor
        editor_button = QPushButton("Launch Audio File Editor")
        editor_button.clicked.connect(self.launch_audio_file_editor)
        layout.addWidget(editor_button)

        editor_description = QLabel("The Audio File Editor allows manual editing of metadata (title, artist, artwork) for audio files.")
        editor_description.setStyleSheet("font-size: 12px; color: grey; margin-bottom: 20px;")
        layout.addWidget(editor_description)

        # Audio Normalizer
        normalizer_button = QPushButton("Launch Audio Normalizer")
        normalizer_button.clicked.connect(self.launch_audio_normalizer)
        layout.addWidget(normalizer_button)

        normalizer_description = QLabel("The Audio Normalizer adjusts the loudness (LUFS) of audio files to a target level for consistency.")
        normalizer_description.setStyleSheet("font-size: 12px; color: grey; margin-bottom: 20px;")
        layout.addWidget(normalizer_description)

        self.setLayout(layout)

    # Function to launch the Audio Checker script
    def launch_audio_checker(self):
        subprocess.Popen(["python", "audio_checker.py"])

    # Function to launch the Audio Converter script
    def launch_audio_converter(self):
        subprocess.Popen(["python", "audio_converter.py"])

    # Function to launch the Audio File Editor script
    def launch_audio_file_editor(self):
        subprocess.Popen(["python", "audio_file_editor.py"])

    # Function to launch the Audio Normalizer script
    def launch_audio_normalizer(self):
        subprocess.Popen(["python", "audio_normalizer.py"])


def main():
    app = QApplication(sys.argv)
    launcher = MainLauncher()
    launcher.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
