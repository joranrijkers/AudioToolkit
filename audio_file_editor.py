import sys
import os
import io
import re
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QDialog, QLineEdit,
    QFormLayout, QDialogButtonBox
)
from PyQt5.QtGui import QPixmap, QImage, QIcon
from PyQt5.QtCore import Qt
import music_tag
from PIL import Image

def select_files():
    files, _ = QFileDialog.getOpenFileNames(
        None,
        "Select Audio Files",
        "",
        "Audio Files (*.mp3 *.wav *.aiff *.flac);;All Files (*)"
    )
    return files

def pil_image_to_qpixmap(pil_image):
    """Convert PIL Image to QPixmap."""
    pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "RGBA")
    w, h = pil_image.size
    qimage = QImage(data, w, h, QImage.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimage)
    return pixmap

class MetadataEditorDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Metadata")
        self.setWindowIcon(QIcon("favicon.icns"))  # Add your icon file here
        self.file_path = file_path
        self.updated_file_path = self.file_path  # Initialize updated_file_path
        self.artwork_data = None  # To store new artwork data
        self.init_ui()
        self.load_metadata()

    def init_ui(self):
        layout = QVBoxLayout()

        # Form layout for title and artist
        form_layout = QFormLayout()
        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        form_layout.addRow("Title:", self.title_edit)
        form_layout.addRow("Artist:", self.artist_edit)
        layout.addLayout(form_layout)

        # Artwork display
        self.artwork_label = QLabel("No artwork available")
        self.artwork_label.setAlignment(Qt.AlignCenter)
        self.artwork_label.setFixedSize(300, 300)
        layout.addWidget(self.artwork_label)

        # Buttons for artwork
        artwork_buttons_layout = QHBoxLayout()
        self.upload_artwork_button = QPushButton("Upload Artwork")
        self.remove_artwork_button = QPushButton("Remove Artwork")
        artwork_buttons_layout.addWidget(self.upload_artwork_button)
        artwork_buttons_layout.addWidget(self.remove_artwork_button)
        layout.addLayout(artwork_buttons_layout)

        self.upload_artwork_button.clicked.connect(self.upload_artwork)
        self.remove_artwork_button.clicked.connect(self.remove_artwork)

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_metadata)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    def load_metadata(self):
        try:
            f = music_tag.load_file(self.file_path)
            self.title_edit.setText(f['tracktitle'].value or '')
            self.artist_edit.setText(f['artist'].value or '')

            if f['artwork']:
                artwork = f['artwork'].first
                artwork_data = artwork.data
                image = Image.open(io.BytesIO(artwork_data))
                image.thumbnail((300, 300), Image.LANCZOS)

                # Convert to QPixmap using custom function
                pixmap = pil_image_to_qpixmap(image)
                self.artwork_label.setPixmap(pixmap)
                self.artwork_label.setText('')
                self.artwork_data = artwork_data  # Keep the existing artwork
            else:
                self.artwork_label.setPixmap(QPixmap())
                self.artwork_label.setText("No artwork available")
                self.artwork_data = None
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error loading metadata: {e}")

    def upload_artwork(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Artwork Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if file_name:
            try:
                image = Image.open(file_name)
                image.thumbnail((300, 300), Image.LANCZOS)

                # Convert to QPixmap using custom function
                pixmap = pil_image_to_qpixmap(image)
                self.artwork_label.setPixmap(pixmap)
                self.artwork_label.setText('')
                # Save the image data
                with open(file_name, 'rb') as img_file:
                    self.artwork_data = img_file.read()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error loading image: {e}")

    def remove_artwork(self):
        self.artwork_label.setPixmap(QPixmap())
        self.artwork_label.setText("No artwork available")
        self.artwork_data = None

    def save_metadata(self):
        try:
            f = music_tag.load_file(self.file_path)
            original_title = f['tracktitle'].value or ''
            original_artist = f['artist'].value or ''

            new_title = self.title_edit.text()
            new_artist = self.artist_edit.text()

            title_changed = new_title != original_title
            artist_changed = new_artist != original_artist

            # Update metadata
            f['tracktitle'] = new_title
            f['artist'] = new_artist

            if self.artwork_data is not None:
                f['artwork'] = self.artwork_data
            else:
                f['artwork'] = None  # Remove artwork

            f.save()

            # If title or artist has changed, rename the file
            if title_changed or artist_changed:
                # Construct new file name
                # Get the directory and extension
                dir_name = os.path.dirname(self.file_path)
                ext = os.path.splitext(self.file_path)[1]

                # Create a safe new filename
                new_filename = f"{new_title} - {new_artist}{ext}"
                # Replace invalid characters in filename
                new_filename = re.sub(r'[<>:"/\\|?*]', '_', new_filename).strip()
                new_file_path = os.path.join(dir_name, new_filename)

                # Ensure the new file path does not already exist
                if not os.path.exists(new_file_path):
                    os.rename(self.file_path, new_file_path)
                    # Update the file_path to the new path
                    self.file_path = new_file_path
                    self.updated_file_path = new_file_path
                    QMessageBox.information(self, "Success", f"Metadata saved and file renamed to '{new_filename}'.")
                else:
                    QMessageBox.warning(self, "Warning", f"Cannot rename file, '{new_filename}' already exists.")
            else:
                QMessageBox.information(self, "Success", "Metadata saved successfully.")

            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error saving metadata: {e}")

class MetadataEditorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Metadata Editor")
        self.resize(600, 400)
        self.file_paths = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Button to select files
        self.select_files_button = QPushButton("Select Audio Files")
        self.select_files_button.clicked.connect(self.select_files)
        layout.addWidget(self.select_files_button)

        # List widget to display files
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemDoubleClicked.connect(self.edit_metadata)
        layout.addWidget(self.file_list_widget)

        self.setLayout(layout)

    def select_files(self):
        files = select_files()
        if files:
            self.file_paths = files
            self.populate_file_list()
        else:
            QMessageBox.information(self, "No Files Selected", "No audio files were selected.")

    def populate_file_list(self):
        self.file_list_widget.clear()
        for file_path in self.file_paths:
            file_name = os.path.basename(file_path)
            item = QListWidgetItem(file_name)
            item.setData(Qt.UserRole, file_path)
            self.file_list_widget.addItem(item)

    def edit_metadata(self, item):
        file_path = item.data(Qt.UserRole)
        dialog = MetadataEditorDialog(file_path, self)
        if dialog.exec_():
            # Update the item text and data in case the file was renamed
            try:
                f = music_tag.load_file(dialog.file_path)
                title = f['tracktitle'].value or os.path.basename(dialog.file_path)
                item.setText(title)
                # Update the item's data if the file was renamed
                if dialog.file_path != file_path:
                    item.setData(Qt.UserRole, dialog.file_path)
            except Exception as e:
                print(f"Error updating item text: {e}")

    def populate_file_list(self):
        self.file_list_widget.clear()
        for file_path in self.file_paths:
            file_name = os.path.basename(file_path)
            item = QListWidgetItem(file_name)
            item.setData(Qt.UserRole, file_path)
            self.file_list_widget.addItem(item)

def main():
    app = QApplication(sys.argv)
    editor_app = MetadataEditorApp()
    editor_app.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    # Check if required libraries are installed
    try:
        import music_tag
        from PIL import Image
    except ImportError as e:
        print(f"Required library not found: {e}. Please install it using 'pip install music-tag Pillow'")
        sys.exit(1)
    main()
