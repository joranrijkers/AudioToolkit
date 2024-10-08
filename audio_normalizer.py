import sys
import os
import io
import time
import warnings  # Import warnings module
import logging
from datetime import datetime
from pathlib import Path

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QLineEdit, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import numpy as np
import pyloudnorm as pyln
from pydub import AudioSegment
import music_tag  # Added for metadata handling

# Suppress the specific warning from pyloudnorm
warnings.filterwarnings("ignore", message="Possible clipped samples in output.")


class NormalizationWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_folder, output_folder, target_loudness):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.target_loudness = target_loudness
        self.is_running = True

    def run(self):
        try:
            audio_files = self.get_audio_files(self.input_folder)
            total_files = len(audio_files)
            if total_files == 0:
                message = "No audio files found in the selected folder."
                self.status.emit(message)
                logging.warning(message)
                self.finished.emit()
                return

            message = f"Found {total_files} audio files."
            self.status.emit(message)
            logging.info(message)
            for idx, file_path in enumerate(audio_files, start=1):
                if not self.is_running:
                    break  # Allow for stopping the thread
                file_name = os.path.basename(file_path)
                output_path = os.path.join(self.output_folder, file_name)

                # Check if file already exists in the output folder
                if os.path.exists(output_path):
                    # If the file exists, check if metadata is present
                    self.status.emit(f"File '{file_name}' already exists. Checking metadata...")
                    logging.info(f"File '{file_name}' already exists. Checking metadata...")

                    if not self.check_metadata(output_path):
                        # If metadata is missing, copy metadata from the input file
                        self.copy_metadata(file_path, output_path)
                        message = f"Copied missing metadata to '{output_path}'."
                        self.status.emit(message)
                        logging.info(message)
                    else:
                        message = f"Skipping '{file_name}' (already exists with metadata)."
                        self.status.emit(message)
                        logging.info(message)
                    continue  # Skip to the next file

                message = f"Processing ({idx}/{total_files}): {file_name}"
                self.status.emit(message)
                logging.info(message)

                start_time = time.time()  # Start timing

                audio = self.load_audio(file_path)
                if audio is None:
                    continue

                samples, rate = self.audiosegment_to_numpy(audio)
                meter = pyln.Meter(rate)
                loudness = meter.integrated_loudness(samples)
                message = f"Original Loudness: {loudness:.2f} LUFS"
                self.status.emit(message)
                logging.info(message)

                # Normalize the audio
                normalized_audio = self.normalize_audio(audio, loudness, self.target_loudness)
                message = f"Normalized to: {self.target_loudness:.2f} LUFS"
                self.status.emit(message)
                logging.info(message)

                # Save normalized audio
                self.save_audio(normalized_audio, output_path, file_path)

                # Copy metadata from the original file to the normalized file
                self.copy_metadata(file_path, output_path)

                end_time = time.time()  # End timing
                elapsed_time = end_time - start_time
                message = f"Processed '{file_name}' in {elapsed_time:.2f} seconds."
                self.status.emit(message)
                logging.info(message)

                progress_percent = int((idx / total_files) * 100)
                self.progress.emit(progress_percent)

            message = "Normalization complete."
            self.status.emit(message)
            logging.info(message)
        except Exception as e:
            message = f"An error occurred: {e}"
            self.status.emit(message)
            logging.exception("Exception in NormalizationWorker.run")
        finally:
            self.finished.emit()

    def get_audio_files(self, folder_path):
        supported_formats = ('.mp3', '.wav', '.aiff', '.flac', '.ogg', '.m4a')
        audio_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path)
                       if f.lower().endswith(supported_formats)]
        return audio_files

    def load_audio(self, file_path):
        try:
            audio = AudioSegment.from_file(file_path)
            return audio
        except Exception as e:
            message = f"Error loading {file_path}: {e}"
            self.status.emit(message)
            logging.exception(f"Error loading file: {file_path}")
            return None

    def audiosegment_to_numpy(self, audio_segment):
        samples = np.array(audio_segment.get_array_of_samples())
        sample_width = audio_segment.sample_width  # in bytes
        max_val = float(2 ** (8 * sample_width - 1))
        samples = samples.astype(np.float32) / max_val
        if audio_segment.channels > 1:
            samples = samples.reshape((-1, audio_segment.channels))
        return samples, audio_segment.frame_rate

    def normalize_audio(self, audio_segment, loudness, target_loudness, max_gain_increase=6.0):
        samples, rate = self.audiosegment_to_numpy(audio_segment)
        gain_needed = target_loudness - loudness

        # Limit the gain increase
        if gain_needed > max_gain_increase:
            message = f"Limiting gain increase to {max_gain_increase} LU to avoid clipping."
            self.status.emit(message)
            logging.warning(message)
            target_loudness = loudness + max_gain_increase

        # Perform loudness normalization
        loudness_normalized = pyln.normalize.loudness(samples, loudness, target_loudness)
        normalized_samples = np.clip(loudness_normalized, -1.0, 1.0)

        sample_width = audio_segment.sample_width  # in bytes
        sample_width_to_dtype = {1: np.int8, 2: np.int16, 3: np.int32, 4: np.int32}
        dtype = sample_width_to_dtype.get(sample_width)
        if dtype is None:
            message = f"Unsupported sample width: {sample_width}"
            self.status.emit(message)
            logging.error(message)
            return audio_segment  # Return original audio if unsupported sample width

        max_val = float(2 ** (8 * sample_width - 1) - 1)
        int_samples = (normalized_samples * max_val).astype(dtype)

        if audio_segment.channels > 1:
            num_channels = audio_segment.channels
            interleaved = np.empty((int_samples.shape[0] * num_channels,), dtype=dtype)
            for i in range(num_channels):
                interleaved[i::num_channels] = int_samples[:, i]
            int_samples = interleaved
        else:
            int_samples = int_samples.flatten()

        normalized_audio = AudioSegment(
            int_samples.tobytes(),
            frame_rate=rate,
            sample_width=sample_width,
            channels=audio_segment.channels
        )
        return normalized_audio

    def save_audio(self, audio_segment, output_path, original_file_path):
        try:
            file_extension = Path(original_file_path).suffix[1:].lower()
            format_mapping = {
                'mp3': 'mp3',
                'wav': 'wav',
                'flac': 'flac',
                'ogg': 'ogg',
                'aiff': 'aiff',
                'aif': 'aiff',
                'm4a': 'mp4',
            }
            audio_format = format_mapping.get(file_extension, 'wav')
            audio_segment.export(output_path, format=audio_format)
            message = f"Saved normalized track to '{output_path}'"
            self.status.emit(message)
            logging.info(message)
        except Exception as e:
            message = f"Error saving {output_path}: {e}"
            self.status.emit(message)
            logging.exception(f"Error saving file: {output_path}")

    def check_metadata(self, file_path):
        try:
            f = music_tag.load_file(file_path)
            return all(f[tag].value for tag in ['tracktitle', 'artist', 'album'])
        except Exception as e:
            message = f"Error checking metadata for {file_path}: {e}"
            self.status.emit(message)
            logging.exception(f"Error checking metadata: {file_path}")
            return False

    def copy_metadata(self, input_path, output_path):
        try:
            f_input = music_tag.load_file(input_path)
            f_output = music_tag.load_file(output_path)

            # Copy essential metadata fields
            for tag in ['tracktitle', 'artist', 'album', 'genre', 'year']:
                if f_input[tag].value:
                    f_output[tag] = f_input[tag].value

            # Copy artwork if present
            if f_input['artwork']:
                f_output['artwork'] = f_input['artwork'].value

            f_output.save()
            logging.info(f"Copied metadata from '{input_path}' to '{output_path}'")
        except Exception as e:
            message = f"Error copying metadata from '{input_path}' to '{output_path}': {e}"
            self.status.emit(message)
            logging.exception(f"Error copying metadata.")

    def stop(self):
        self.is_running = False


class NormalizationApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Normalizer")
        self.setWindowIcon(QIcon("favicon.icns"))  # Add your icon file here
        self.resize(500, 300)
        self.init_ui()
        self.worker_thread = None

    def init_ui(self):
        layout = QVBoxLayout()

        # Input folder selection
        input_layout = QHBoxLayout()
        self.input_folder_label = QLabel("Input Folder:")
        self.input_folder_path = QLineEdit()
        self.input_folder_browse = QPushButton("Browse")
        self.input_folder_browse.clicked.connect(self.browse_input_folder)
        input_layout.addWidget(self.input_folder_label)
        input_layout.addWidget(self.input_folder_path)
        input_layout.addWidget(self.input_folder_browse)
        layout.addLayout(input_layout)

        # Output folder selection
        output_layout = QHBoxLayout()
        self.output_folder_label = QLabel("Output Folder:")
        self.output_folder_path = QLineEdit()
        self.output_folder_browse = QPushButton("Browse")
        self.output_folder_browse.clicked.connect(self.browse_output_folder)
        output_layout.addWidget(self.output_folder_label)
        output_layout.addWidget(self.output_folder_path)
        output_layout.addWidget(self.output_folder_browse)
        layout.addLayout(output_layout)

        # Target loudness input
        loudness_layout = QHBoxLayout()
        self.loudness_label = QLabel("Target Loudness (LUFS):")
        self.loudness_input = QLineEdit("-7")
        loudness_layout.addWidget(self.loudness_label)
        loudness_layout.addWidget(self.loudness_input)
        layout.addLayout(loudness_layout)

        # Start button
        self.start_button = QPushButton("Start Normalization")
        self.start_button.clicked.connect(self.start_normalization)
        layout.addWidget(self.start_button)

        # Progress bar and status
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self.input_folder_path.setText(folder)

    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder_path.setText(folder)

    def start_normalization(self):
        input_folder = self.input_folder_path.text().strip()
        output_folder = self.output_folder_path.text().strip()
        target_loudness_str = self.loudness_input.text().strip()

        if not input_folder or not os.path.isdir(input_folder):
            QMessageBox.warning(self, "Error", "Please select a valid input folder.")
            logging.warning("Invalid input folder selected.")
            return

        if not output_folder or not os.path.isdir(output_folder):
            QMessageBox.warning(self, "Error", "Please select a valid output folder.")
            logging.warning("Invalid output folder selected.")
            return

        try:
            target_loudness = float(target_loudness_str)
            if not (-60.0 <= target_loudness <= 0.0):
                QMessageBox.warning(self, "Error", "Please enter a target loudness between -60 and 0 LUFS.")
                logging.warning(f"Invalid target loudness value: {target_loudness}")
                return
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter a numerical value for target loudness.")
            logging.warning(f"Non-numerical target loudness value entered: {target_loudness_str}")
            return

        # Disable UI elements during processing
        self.start_button.setEnabled(False)
        self.input_folder_browse.setEnabled(False)
        self.output_folder_browse.setEnabled(False)
        self.loudness_input.setEnabled(False)

        # Start the worker thread
        self.worker_thread = NormalizationWorker(input_folder, output_folder, target_loudness)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.status.connect(self.update_status)
        self.worker_thread.finished.connect(self.processing_finished)
        self.worker_thread.start()

        logging.info("Normalization process started.")

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, message):
        self.status_label.setText(f"Status: {message}")
        logging.info(message)

    def processing_finished(self):
        QMessageBox.information(self, "Finished", "Normalization process completed.")
        self.progress_bar.setValue(100)
        self.status_label.setText("Status: Idle")
        # Re-enable UI elements
        self.start_button.setEnabled(True)
        self.input_folder_browse.setEnabled(True)
        self.output_folder_browse.setEnabled(True)
        self.loudness_input.setEnabled(True)
        self.worker_thread = None
        logging.info("Normalization process finished.")


def setup_logging():
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Create a unique log file name based on timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"log_{timestamp}.txt"

    # Clear existing handlers to prevent duplicate logs
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            # Uncomment the line below if you want logs printed to the console
            # logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    setup_logging()
    app = QApplication(sys.argv)
    normalization_app = NormalizationApp()
    normalization_app.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
