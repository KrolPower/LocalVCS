import sys
import os
import shutil
import zipfile
import datetime
import threading
import json
import hashlib
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QLabel, QPushButton, QLineEdit,
                            QComboBox, QProgressBar, QScrollArea, QFrame,
                            QFileDialog, QMessageBox, QGroupBox, QGridLayout,
                            QTextEdit, QTabWidget, QSplitter, QSizePolicy, QDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor, QPixmap, QIcon


"""
LocalVCS - Backup & Restore Manager
==================================

A powerful, user-friendly backup and restore management system built with Python and PyQt5.
LocalVCS provides comprehensive file backup, restore, comparison, and version control capabilities.

Author: KrolPower
License: MIT License
Version: 1.0
"""


class BackupThread(QThread):
    backup_completed = pyqtSignal(str)
    backup_failed = pyqtSignal(str)

    def __init__(self, source_dir, target_dir):
        super().__init__()
        self.source_dir = source_dir
        self.target_dir = target_dir

    def run(self):
        try:
            # Create timestamp for backup name
            timestamp = datetime.datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
            backup_name = f"BACKUP_{timestamp}"
            backup_path = os.path.join(self.target_dir, backup_name + ".zip")

            # Calculate file hashes before creating zip
            file_hashes = {}
            for root, dirs, files in os.walk(self.source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    file_hashes[rel_path] = self.calculate_file_hash(file_path)

            # Create zip file
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.source_dir)
                        zipf.write(file_path, arcname)

            # Save hash information
            hash_file_path = backup_path.replace('.zip', '_hashes.json')
            hash_data = {
                'backup_name': backup_name,
                'created_at': datetime.datetime.now().isoformat(),
                'file_hashes': file_hashes,
                'total_files': len(file_hashes),
                'source_directory': self.source_dir
            }
            with open(hash_file_path, 'w') as f:
                json.dump(hash_data, f, indent=2)

            self.backup_completed.emit(backup_path)

        except Exception as e:
            self.backup_failed.emit(str(e))

    def calculate_file_hash(self, file_path):
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return None


class RestoreThread(QThread):
    restore_completed = pyqtSignal(str)
    restore_failed = pyqtSignal(str)

    def __init__(self, backup_path, source_dir):
        super().__init__()
        self.backup_path = backup_path
        self.source_dir = source_dir

    def run(self):
        try:
            # Create temporary directory for extraction
            temp_dir = os.path.join(os.path.dirname(
                self.backup_path), "temp_restore")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)

            # Extract backup
            with zipfile.ZipFile(self.backup_path, 'r') as zipf:
                zipf.extractall(temp_dir)

            # Remove existing source directory contents
            if os.path.exists(self.source_dir):
                shutil.rmtree(self.source_dir)

            # Move extracted contents to source directory
            extracted_items = os.listdir(temp_dir)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
                # Single directory, move its contents
                shutil.move(os.path.join(
                    temp_dir, extracted_items[0]), self.source_dir)
            else:
                # Multiple items, move them directly
                os.makedirs(self.source_dir, exist_ok=True)
                for item in extracted_items:
                    shutil.move(os.path.join(temp_dir, item), self.source_dir)

            # Clean up temporary directory
            shutil.rmtree(temp_dir)

            self.restore_completed.emit(self.source_dir)

        except Exception as e:
            self.restore_failed.emit(str(e))


class CompareThread(QThread):
    compare_completed = pyqtSignal(dict, str, str)
    compare_failed = pyqtSignal(str)

    def __init__(self, source_backup, compare_backup, target_dir):
        super().__init__()
        self.source_backup = source_backup
        self.compare_backup = compare_backup
        self.target_dir = target_dir

    def run(self):
        try:
            source_path = os.path.join(self.target_dir, self.source_backup)
            compare_path = os.path.join(self.target_dir, self.compare_backup)

            # Load hash files
            source_hash_path = source_path.replace('.zip', '_hashes.json')
            compare_hash_path = compare_path.replace('.zip', '_hashes.json')

            # Check if hash files exist
            if not os.path.exists(source_hash_path) or not os.path.exists(compare_hash_path):
                # Fall back to old method if hash files don't exist
                differences = self.compare_backups_legacy(
                    source_path, compare_path)
            else:
                # Load hash data
                with open(source_hash_path, 'r') as f:
                    source_hashes = json.load(f)
                with open(compare_hash_path, 'r') as f:
                    compare_hashes = json.load(f)

                # Compare using hashes
                differences = self.get_hash_based_differences(
                    source_hashes, compare_hashes)

            self.compare_completed.emit(
                differences, self.source_backup, self.compare_backup)

        except Exception as e:
            self.compare_failed.emit(str(e))

    def compare_backups_legacy(self, source_path, compare_path):
        """Legacy comparison method (original implementation)"""
        try:
            # Extract both backups to temporary directories
            temp_source = os.path.join(self.target_dir, "temp_compare_source")
            temp_compare = os.path.join(self.target_dir, "temp_compare_target")

            # Clean up any existing temp directories
            for temp_dir in [temp_source, temp_compare]:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)

            # Extract source backup
            with zipfile.ZipFile(source_path, 'r') as zipf:
                zipf.extractall(temp_source)

            # Extract compare backup
            with zipfile.ZipFile(compare_path, 'r') as zipf:
                zipf.extractall(temp_compare)

            # Compare the directories
            differences = self.get_directory_differences(
                temp_source, temp_compare)

            # Clean up temporary directories
            shutil.rmtree(temp_source)
            shutil.rmtree(temp_compare)

            return differences

        except Exception as e:
            # Clean up on error
            for temp_dir in [os.path.join(self.target_dir, "temp_compare_source"),
                             os.path.join(self.target_dir, "temp_compare_target")]:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            raise e

    def get_hash_based_differences(self, source_hashes, compare_hashes):
        """Get differences between two backups using hash comparison"""
        differences = {
            'added': [],
            'removed': [],
            'modified': [],
            'unchanged': []
        }

        source_files = set(source_hashes['file_hashes'].keys())
        compare_files = set(compare_hashes['file_hashes'].keys())

        # Find added and removed files
        differences['added'] = list(compare_files - source_files)
        differences['removed'] = list(source_files - compare_files)

        # Check for modified files using hash comparison
        common_files = source_files & compare_files
        for file in common_files:
            source_hash = source_hashes['file_hashes'][file]
            compare_hash = compare_hashes['file_hashes'][file]

            if source_hash != compare_hash:
                differences['modified'].append(file)
            else:
                differences['unchanged'].append(file)

        return differences

    def get_directory_differences(self, dir1, dir2):
        """Get differences between two directories"""
        differences = {
            'added': [],
            'removed': [],
            'modified': [],
            'unchanged': []
        }

        # Get all files from both directories
        files1 = set()
        files2 = set()

        for root, dirs, files in os.walk(dir1):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), dir1)
                files1.add(rel_path)

        for root, dirs, files in os.walk(dir2):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), dir2)
                files2.add(rel_path)

        # Find added and removed files
        differences['added'] = list(files2 - files1)
        differences['removed'] = list(files1 - files2)

        # Check for modified files
        common_files = files1 & files2
        for file in common_files:
            file1_path = os.path.join(dir1, file)
            file2_path = os.path.join(dir2, file)

            if self.files_differ(file1_path, file2_path):
                differences['modified'].append(file)
            else:
                differences['unchanged'].append(file)

        return differences

    def files_differ(self, file1_path, file2_path):
        """Check if two files are different"""
        try:
            # Compare file sizes first
            if os.path.getsize(file1_path) != os.path.getsize(file2_path):
                return True

            # Compare file contents
            with open(file1_path, 'rb') as f1, open(file2_path, 'rb') as f2:
                while True:
                    chunk1 = f1.read(8192)
                    chunk2 = f2.read(8192)
                    if chunk1 != chunk2:
                        return True
                    if not chunk1:  # End of file
                        break

            return False
        except Exception:
            return True  # Assume different if there's an error


class BackupRestoreApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalVCS - Backup & Restore Manager")
        self.setGeometry(100, 100, 1200, 800)

        # Configuration
        self.config_file = "backup_config.json"
        self.source_dir = ""
        self.target_dir = ""

        # Load configuration
        self.load_config()

        # Setup styling
        self.setup_styles()

        # Create GUI
        self.create_widgets()

        # Load existing backups
        self.load_backups()

    def setup_styles(self):
        """Setup modern styling for the application"""
        # Set application style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2c3e50;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton[class="primary"] {
                background-color: #3498db;
                color: black;
            }
            QPushButton[class="primary"]:hover {
                background-color: #2980b9;
            }
            QPushButton[class="secondary"] {
                background-color: #95a5a6;
                color: black;
            }
            QPushButton[class="secondary"]:hover {
                background-color: #7f8c8d;
            }
            QPushButton[class="danger"] {
                background-color: #e74c3c;
                color: black;
            }
            QPushButton[class="danger"]:hover {
                background-color: #c0392b;
            }
            QLineEdit {
                border: 2px solid #dee2e6;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #3498db;
            }
            QComboBox {
                border: 2px solid #dee2e6;
                border-radius: 6px;
                padding: 8px;
                background-color: white;
            }
            QComboBox:focus {
                border-color: #3498db;
            }
            QProgressBar {
                border: 2px solid #dee2e6;
                border-radius: 6px;
                text-align: center;
                background-color: #e9ecef;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 4px;
            }
        """)

    def load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.source_dir = config.get('source_dir', '')
                    self.target_dir = config.get('target_dir', '')
        except Exception as e:
            print(f"Error loading config: {e}")

    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'source_dir': self.source_dir,
                'target_dir': self.target_dir
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            print(f"Error saving config: {e}")

    def create_widgets(self):
        """Create the main GUI widgets with modern PyQt5 layout"""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Left side - Backups area with tabs
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title_label = QLabel("LocalVCS - Backup & Restore Manager")
        title_font = QFont("Segoe UI", 20, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        left_layout.addWidget(title_label)

        # Tab widget for backup list and comparison results
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                background-color: #f8f9fa;
            }
            QTabBar::tab {
                background-color: #bdc3c7;
                color: #2c3e50;
                padding: 8px 24px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #95a5a6;
            }
        """)

        # Backup list tab
        backup_tab = QWidget()
        backup_layout = QVBoxLayout(backup_tab)
        backup_layout.setContentsMargins(0, 0, 0, 0)

        # Backups scroll area
        self.backups_scroll = QScrollArea()
        self.backups_scroll.setWidgetResizable(True)
        self.backups_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.backups_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.backups_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f8f9fa;
            }
        """)

        # Backups container
        self.backups_container = QWidget()
        self.backups_layout = QVBoxLayout(self.backups_container)
        self.backups_layout.setAlignment(Qt.AlignTop)
        self.backups_layout.setSpacing(10)
        self.backups_layout.setContentsMargins(10, 10, 10, 10)

        self.backups_scroll.setWidget(self.backups_container)
        backup_layout.addWidget(self.backups_scroll)

        # Add backup tab to tab widget
        self.tab_widget.addTab(backup_tab, "📦 Backups")

        # Comparison results tab (initially empty)
        self.comparison_tab = QWidget()
        self.comparison_layout = QVBoxLayout(self.comparison_tab)
        self.comparison_layout.setContentsMargins(0, 0, 0, 0)

        # Title for comparison results
        self.comparison_title = QLabel("🔍 Comparison Results")
        comparison_font = QFont("Segoe UI", 18, QFont.Bold)
        self.comparison_title.setFont(comparison_font)
        self.comparison_title.setStyleSheet(
            "color: #2c3e50; margin-bottom: 20px;")
        self.comparison_layout.addWidget(self.comparison_title)

        # Comparison results content
        self.comparison_content = QWidget()
        self.comparison_content_layout = QVBoxLayout(self.comparison_content)

        # Add placeholder text
        placeholder_label = QLabel(
            "Select backups to compare and click 'Compare Backups' to see results here.")
        placeholder_label.setStyleSheet(
            "color: #7f8c8d; font-size: 16px; text-align: center; padding: 40px;")
        placeholder_label.setAlignment(Qt.AlignCenter)
        self.comparison_content_layout.addWidget(placeholder_label)

        self.comparison_layout.addWidget(self.comparison_content)

        # Add comparison tab to tab widget
        self.tab_widget.addTab(self.comparison_tab, "🔍 Comparison")

        left_layout.addWidget(self.tab_widget)

        # Right side - Controls
        right_widget = QWidget()
        right_widget.setFixedWidth(450)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)

        # Controls title
        controls_title = QLabel("Controls")
        controls_font = QFont("Segoe UI", 18, QFont.Bold)
        controls_title.setFont(controls_font)
        controls_title.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        right_layout.addWidget(controls_title)

        # Source directory section
        source_group = QGroupBox("Source Directory")
        source_layout = QVBoxLayout(source_group)

        source_label = QLabel("Directory to backup:")
        source_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        source_layout.addWidget(source_label)

        self.source_edit = QLineEdit()
        self.source_edit.setText(self.source_dir)
        self.source_edit.textChanged.connect(self.on_source_changed)
        source_layout.addWidget(self.source_edit)

        browse_source_btn = QPushButton("Browse Source")
        browse_source_btn.setProperty("class", "secondary")
        browse_source_btn.clicked.connect(self.browse_source)
        source_layout.addWidget(browse_source_btn)

        right_layout.addWidget(source_group)

        # Target directory section
        target_group = QGroupBox("Backup Location")
        target_layout = QVBoxLayout(target_group)

        target_label = QLabel("Where to store backups:")
        target_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        target_layout.addWidget(target_label)

        self.target_edit = QLineEdit()
        self.target_edit.setText(self.target_dir)
        self.target_edit.textChanged.connect(self.on_target_changed)
        target_layout.addWidget(self.target_edit)

        browse_target_btn = QPushButton("Browse Target")
        browse_target_btn.setProperty("class", "secondary")
        browse_target_btn.clicked.connect(self.browse_target)
        target_layout.addWidget(browse_target_btn)

        right_layout.addWidget(target_group)

        # Backup button
        self.backup_btn = QPushButton("Create Backup")
        self.backup_btn.setProperty("class", "primary")
        self.backup_btn.clicked.connect(self.start_backup)
        right_layout.addWidget(self.backup_btn)

        # Comparison section
        compare_group = QGroupBox("Compare Backups")
        compare_layout = QVBoxLayout(compare_group)

        source_backup_label = QLabel("Source backup:")
        source_backup_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        compare_layout.addWidget(source_backup_label)

        self.source_backup_combo = QComboBox()
        compare_layout.addWidget(self.source_backup_combo)

        compare_against_label = QLabel("Compare against:")
        compare_against_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        compare_layout.addWidget(compare_against_label)

        self.compare_backup_combo = QComboBox()
        compare_layout.addWidget(self.compare_backup_combo)

        self.compare_btn = QPushButton("Compare Backups")
        self.compare_btn.setProperty("class", "secondary")
        self.compare_btn.clicked.connect(self.start_compare)
        compare_layout.addWidget(self.compare_btn)

        right_layout.addWidget(compare_group)

        # Progress section
        progress_group = QGroupBox("Status")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("Ready")
        self.progress_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        right_layout.addWidget(progress_group)

        # Add widgets to main layout
        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_widget, 0)

    def on_source_changed(self, text):
        """Handle source directory text change"""
        self.source_dir = text
        self.save_config()

    def on_target_changed(self, text):
        """Handle target directory text change"""
        self.target_dir = text
        self.save_config()

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling"""
        if sys.platform == "win32":
            # Windows
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:
            # Linux/Mac
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * event.delta), "units")

    def browse_source(self):
        """Browse for source directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Source Directory")
        if directory:
            self.source_dir = directory
            self.source_edit.setText(directory)
            self.save_config()

    def browse_target(self):
        """Browse for target directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Target Directory")
        if directory:
            self.target_dir = directory
            self.target_edit.setText(directory)
            self.save_config()

    def start_backup(self):
        """Start backup process in a separate thread"""
        if not self.source_dir or not self.target_dir:
            QMessageBox.critical(
                self, "Error", "Please select both source and target directories")
            return

        if not os.path.exists(self.source_dir):
            QMessageBox.critical(
                self, "Error", "Source directory does not exist")
            return

        # Disable backup button and start progress
        self.backup_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_label.setText("Creating backup...")

        # Start backup in separate thread
        self.backup_thread = BackupThread(self.source_dir, self.target_dir)
        self.backup_thread.backup_completed.connect(self.backup_completed)
        self.backup_thread.backup_failed.connect(self.backup_failed)
        self.backup_thread.start()

    def create_backup(self):
        """Create a backup of the source directory"""
        try:
            # Create timestamp for backup name
            timestamp = datetime.datetime.now().strftime("%m_%d_%Y_%H_%M_%S")
            backup_name = f"BACKUP_{timestamp}"
            backup_path = os.path.join(self.target_dir, backup_name + ".zip")

            # Calculate file hashes before creating zip
            file_hashes = {}
            for root, dirs, files in os.walk(self.source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    file_hashes[rel_path] = self.calculate_file_hash(file_path)

            # Create zip file
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.source_dir)
                        zipf.write(file_path, arcname)

            # Save hash information
            hash_file_path = backup_path.replace('.zip', '_hashes.json')
            hash_data = {
                'backup_name': backup_name,
                'created_at': datetime.datetime.now().isoformat(),
                'file_hashes': file_hashes,
                'total_files': len(file_hashes),
                'source_directory': self.source_dir
            }
            with open(hash_file_path, 'w') as f:
                json.dump(hash_data, f, indent=2)

            # Update GUI in main thread
            self.root.after(0, self.backup_completed, backup_path)

        except Exception as e:
            self.root.after(0, self.backup_failed, str(e))

    def backup_completed(self, backup_path):
        """Called when backup is completed"""
        self.backup_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Backup completed successfully")
        self.load_backups()
        QMessageBox.information(
            self, "Success", f"Backup created: {os.path.basename(backup_path)}")

    def backup_failed(self, error_msg):
        """Called when backup fails"""
        self.backup_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Backup failed")
        QMessageBox.critical(self, "Error", f"Backup failed: {error_msg}")

    def load_backups(self):
        """Load and display existing backups"""
        # Clear existing backup cards
        for i in reversed(range(self.backups_layout.count())):
            self.backups_layout.itemAt(i).widget().setParent(None)

        if not self.target_dir or not os.path.exists(self.target_dir):
            return

        # Find all backup files
        backup_files = []
        for file in os.listdir(self.target_dir):
            if file.startswith("BACKUP_") and file.endswith(".zip"):
                file_path = os.path.join(self.target_dir, file)
                backup_files.append((file, file_path))

        # Sort by modification time (newest first)
        backup_files.sort(key=lambda x: os.path.getmtime(x[1]), reverse=True)

        # Update comparison dropdowns
        backup_names = [file for file, _ in backup_files]
        self.source_backup_combo.clear()
        self.source_backup_combo.addItems(backup_names)
        self.compare_backup_combo.clear()
        self.compare_backup_combo.addItems(backup_names)

        # Create backup cards
        for i, (backup_name, backup_path) in enumerate(backup_files):
            self.create_backup_card(backup_name, backup_path, i)

    def create_backup_card(self, backup_name, backup_path, index):
        """Create a modern card widget for a backup"""
        # Create card frame
        card_frame = QFrame()
        card_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin: 5px;
            }
        """)

        # Create main layout for card
        card_layout = QVBoxLayout(card_frame)
        card_layout.setContentsMargins(15, 15, 15, 15)
        card_layout.setSpacing(10)

        # Card header with backup name
        name_label = QLabel(backup_name)
        name_font = QFont("Segoe UI", 14, QFont.Bold)
        name_label.setFont(name_font)
        name_label.setStyleSheet("color: #2c3e50;")
        card_layout.addWidget(name_label)

        # Source directory
        source_dir = self.get_backup_source_directory(backup_path)
        if source_dir:
            # Truncate long paths for display
            display_path = source_dir
            if len(display_path) > 50:
                display_path = "..." + display_path[-47:]
            source_label = QLabel(f"📁 Source: {display_path}")
            source_label.setStyleSheet("color: #3498db; font-size: 11px;")
            source_label.setCursor(Qt.PointingHandCursor)
            source_label.mousePressEvent = lambda e, path=source_dir: self.open_in_explorer(
                path)
            card_layout.addWidget(source_label)

        # Backup location
        backup_dir = os.path.dirname(backup_path)
        backup_display = backup_dir
        if len(backup_display) > 50:
            backup_display = "..." + backup_display[-47:]
        backup_location_label = QLabel(f"💾 Location: {backup_display}")
        backup_location_label.setStyleSheet("color: #27ae60; font-size: 11px;")
        backup_location_label.setCursor(Qt.PointingHandCursor)
        backup_location_label.mousePressEvent = lambda e, path=backup_dir: self.open_in_explorer(
            path)
        card_layout.addWidget(backup_location_label)

        # Info section
        info_layout = QHBoxLayout()

        # Backup size
        size = os.path.getsize(backup_path)
        size_str = self.format_size(size)
        size_label = QLabel(f"📊 Size: {size_str}")
        size_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        info_layout.addWidget(size_label)

        # Modification date
        mod_time = datetime.datetime.fromtimestamp(
            os.path.getmtime(backup_path))
        date_str = mod_time.strftime("%Y-%m-%d %H:%M")
        date_label = QLabel(f"🕒 Created: {date_str}")
        date_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        info_layout.addWidget(date_label)

        card_layout.addLayout(info_layout)

        # Notes section
        notes_layout = QHBoxLayout()

        # Notes label
        notes_label = QLabel("📝 Notes:")
        notes_label.setStyleSheet(
            "color: #7f8c8d; font-size: 11px; font-weight: bold;")
        notes_layout.addWidget(notes_label)

        # Notes display/edit area
        notes_text = self.get_backup_notes(backup_path)
        if notes_text:
            # Truncate notes if longer than 30 characters
            display_text = notes_text
            if len(notes_text) > 30:
                display_text = notes_text[:30] + "..."
            notes_display = QLabel(display_text)
            notes_display.setStyleSheet(
                "color: #2c3e50; font-size: 11px; font-style: italic;")
            notes_layout.addWidget(notes_display)
        else:
            notes_display = QLabel("No notes")
            notes_display.setStyleSheet(
                "color: #bdc3c7; font-size: 11px; font-style: italic;")
            notes_layout.addWidget(notes_display)

        # Edit notes button
        edit_notes_btn = QPushButton("✏️ Edit")
        edit_notes_btn.setProperty("class", "secondary")
        edit_notes_btn.setMinimumWidth(80)
        edit_notes_btn.clicked.connect(
            lambda: self.edit_backup_notes(backup_path, notes_display))
        notes_layout.addWidget(edit_notes_btn)

        card_layout.addLayout(notes_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        # Restore button
        restore_btn = QPushButton("🔄 Restore")
        restore_btn.setProperty("class", "primary")
        restore_btn.clicked.connect(lambda: self.start_restore(backup_path))
        button_layout.addWidget(restore_btn)

        # Delete button
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.setProperty("class", "danger")
        delete_btn.clicked.connect(lambda: self.delete_backup(backup_path))
        button_layout.addWidget(delete_btn)

        card_layout.addLayout(button_layout)

        # Add card to backups layout
        self.backups_layout.addWidget(card_frame)

    def format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0B"
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f}{size_names[i]}"

    def get_backup_source_directory(self, backup_path):
        """Get the source directory used for a backup"""
        try:
            hash_file_path = backup_path.replace('.zip', '_hashes.json')
            if os.path.exists(hash_file_path):
                with open(hash_file_path, 'r') as f:
                    hash_data = json.load(f)
                    return hash_data.get('source_directory', '')
            return ''
        except Exception:
            return ''

    def get_backup_notes(self, backup_path):
        """Get notes for a backup"""
        try:
            notes_file_path = backup_path.replace('.zip', '_notes.txt')
            if os.path.exists(notes_file_path):
                with open(notes_file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return ''
        except Exception:
            return ''

    def save_backup_notes(self, backup_path, notes):
        """Save notes for a backup"""
        try:
            notes_file_path = backup_path.replace('.zip', '_notes.txt')
            with open(notes_file_path, 'w', encoding='utf-8') as f:
                f.write(notes)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save notes: {e}")

    def edit_backup_notes(self, backup_path, notes_display):
        """Open dialog to edit backup notes"""
        current_notes = self.get_backup_notes(backup_path)

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Backup Notes")
        dialog.setModal(True)
        dialog.setMinimumSize(400, 300)

        layout = QVBoxLayout(dialog)

        # Title
        title_label = QLabel(f"Notes for: {os.path.basename(backup_path)}")
        title_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Text area
        text_edit = QTextEdit()
        text_edit.setPlainText(current_notes)
        text_edit.setStyleSheet("""
            QTextEdit {
                border: 2px solid #bdc3c7;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTextEdit:focus {
                border-color: #3498db;
            }
        """)
        layout.addWidget(text_edit)

        # Buttons
        button_layout = QHBoxLayout()

        save_btn = QPushButton("Save")
        save_btn.setProperty("class", "primary")
        save_btn.clicked.connect(lambda: self.save_notes_and_close(
            dialog, backup_path, text_edit.toPlainText(), notes_display))
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "secondary")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        dialog.exec_()

    def save_notes_and_close(self, dialog, backup_path, notes, notes_display):
        """Save notes and update the display"""
        self.save_backup_notes(backup_path, notes)

        # Update the display with truncation
        if notes.strip():
            # Truncate notes if longer than 30 characters
            display_text = notes
            if len(notes) > 30:
                display_text = notes[:30] + "..."
            notes_display.setText(display_text)
            notes_display.setStyleSheet(
                "color: #2c3e50; font-size: 11px; font-style: italic;")
        else:
            notes_display.setText("No notes")
            notes_display.setStyleSheet(
                "color: #bdc3c7; font-size: 11px; font-style: italic;")

        dialog.accept()

    def get_file_diff(self, source_backup, compare_backup, file_path):
        """Get diff content for a specific file between two backups"""
        try:
            # Extract both backups to temporary directories
            temp_source = os.path.join(self.target_dir, "temp_diff_source")
            temp_compare = os.path.join(self.target_dir, "temp_diff_compare")

            # Clean up any existing temp directories
            for temp_dir in [temp_source, temp_compare]:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)

            # Extract source backup
            source_path = os.path.join(self.target_dir, source_backup)
            with zipfile.ZipFile(source_path, 'r') as zipf:
                zipf.extractall(temp_source)

            # Extract compare backup
            compare_path = os.path.join(self.target_dir, compare_backup)
            with zipfile.ZipFile(compare_path, 'r') as zipf:
                zipf.extractall(temp_compare)

            # Get file paths
            file1_path = os.path.join(temp_source, file_path)
            file2_path = os.path.join(temp_compare, file_path)

            # Check if both files exist
            if not os.path.exists(file1_path) or not os.path.exists(file2_path):
                return None

            # Read file contents
            with open(file1_path, 'r', encoding='utf-8', errors='ignore') as f1:
                lines1 = f1.readlines()
            with open(file2_path, 'r', encoding='utf-8', errors='ignore') as f2:
                lines2 = f2.readlines()

            # Generate diff
            import difflib
            diff = difflib.unified_diff(
                lines1, lines2,
                fromfile=f'{source_backup}/{file_path}',
                tofile=f'{compare_backup}/{file_path}',
                lineterm=''
            )

            # Clean up temporary directories
            shutil.rmtree(temp_source)
            shutil.rmtree(temp_compare)

            return list(diff)

        except Exception as e:
            # Clean up on error
            for temp_dir in [os.path.join(self.target_dir, "temp_diff_source"),
                             os.path.join(self.target_dir, "temp_diff_compare")]:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            return None

    def add_diff_to_widget(self, text_widget, diff_content):
        """Add diff content to text widget with syntax highlighting"""
        for line in diff_content:
            if line.startswith('+'):
                # Added line - green background
                text_widget.append(f"➕ {line[1:]}")
            elif line.startswith('-'):
                # Removed line - red background
                text_widget.append(f"➖ {line[1:]}")
            elif line.startswith('@'):
                # Diff header - blue
                text_widget.append(f"📍 {line}")
            elif line.startswith('---') or line.startswith('+++'):
                # File headers - gray
                text_widget.append(f"📄 {line}")
            else:
                # Context lines - normal
                text_widget.append(f"  {line}")

    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget"""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = ttk.Label(
                tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1)
            label.pack()

            def hide_tooltip(event):
                tooltip.destroy()

            widget.tooltip = tooltip
            widget.bind('<Leave>', hide_tooltip)
            tooltip.bind('<Leave>', hide_tooltip)

        widget.bind('<Enter>', show_tooltip)

    def open_in_explorer(self, path):
        """Open a directory in file explorer"""
        try:
            if os.path.exists(path):
                if os.name == 'nt':  # Windows
                    os.startfile(path)
                elif os.name == 'posix':  # macOS and Linux
                    import subprocess
                    subprocess.run(['open', path] if sys.platform ==
                                   'darwin' else ['xdg-open', path])
                else:
                    QMessageBox.information(self, "Info", f"Path: {path}")
            else:
                QMessageBox.critical(
                    self, "Error", f"Path does not exist: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open path: {e}")

    def start_restore(self, backup_path):
        """Start restore process"""
        # Get the original source directory from backup metadata
        original_source_dir = self.get_backup_source_directory(backup_path)

        if not original_source_dir:
            # Fallback to current source directory if no metadata
            if not self.source_dir:
                QMessageBox.critical(
                    self, "Error", "No source directory found for this backup and no current source directory set")
                return
            original_source_dir = self.source_dir

        # Confirm restore with source directory info
        result = QMessageBox.question(self, "Confirm Restore",
                                      f"This will restore to: {original_source_dir}\n\n"
                                      "This will replace all files in the source directory. Continue?",
                                      QMessageBox.Yes | QMessageBox.No)
        if result != QMessageBox.Yes:
            return

        # Disable backup button and start progress
        self.backup_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_label.setText("Restoring backup...")

        # Start restore in separate thread
        self.restore_thread = RestoreThread(backup_path, original_source_dir)
        self.restore_thread.restore_completed.connect(self.restore_completed)
        self.restore_thread.restore_failed.connect(self.restore_failed)
        self.restore_thread.start()

    def restore_completed(self, source_dir):
        """Called when restore is completed"""
        self.backup_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Restore completed successfully")
        QMessageBox.information(
            self, "Success", f"Backup restored successfully to:\n{source_dir}")

    def restore_failed(self, error_msg):
        """Called when restore fails"""
        self.backup_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Restore failed")
        QMessageBox.critical(self, "Error", f"Restore failed: {error_msg}")

    def delete_backup(self, backup_path):
        """Delete a backup file and its associated hash file and notes"""
        result = QMessageBox.question(self, "Confirm Delete",
                                      f"Delete backup: {os.path.basename(backup_path)}?",
                                      QMessageBox.Yes | QMessageBox.No)
        if result == QMessageBox.Yes:
            try:
                # Delete the backup file
                os.remove(backup_path)

                # Delete the associated hash file
                hash_file_path = backup_path.replace('.zip', '_hashes.json')
                if os.path.exists(hash_file_path):
                    os.remove(hash_file_path)

                # Delete the associated notes file
                notes_file_path = backup_path.replace('.zip', '_notes.txt')
                if os.path.exists(notes_file_path):
                    os.remove(notes_file_path)

                self.load_backups()
                QMessageBox.information(
                    self, "Success", "Backup deleted successfully")
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to delete backup: {e}")

    def start_compare(self):
        """Start comparison process"""
        source_backup = self.source_backup_combo.currentText()
        compare_backup = self.compare_backup_combo.currentText()

        if not source_backup or not compare_backup:
            QMessageBox.critical(
                self, "Error", "Please select both source and compare backups")
            return

        if source_backup == compare_backup:
            QMessageBox.critical(
                self, "Error", "Please select different backups to compare")
            return

        # Disable compare button and start progress
        self.compare_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_label.setText("Comparing backups...")

        # Start comparison in separate thread
        self.compare_thread = CompareThread(
            source_backup, compare_backup, self.target_dir)
        self.compare_thread.compare_completed.connect(
            self.show_comparison_results)
        self.compare_thread.compare_failed.connect(self.comparison_failed)
        self.compare_thread.start()

    def show_comparison_results(self, differences, source_backup, compare_backup):
        """Show comparison results in the comparison tab"""
        self.compare_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Comparison completed")

        # Update comparison title
        self.comparison_title.setText(
            f"🔍 Comparison Results: {source_backup} vs {compare_backup}")

        # Clear existing content
        for i in reversed(range(self.comparison_content_layout.count())):
            widget = self.comparison_content_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Create tab widget for results
        results_tab_widget = QTabWidget()
        results_tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #ecf0f1;
                color: #2c3e50;
                padding: 6px 16px;
                margin-right: 1px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                font-weight: bold;
                font-size: 11px;
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background-color: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #bdc3c7;
            }
        """)

        # Create tabs for each category
        categories = [
            ('Added Files', 'added', '#27ae60'),
            ('Removed Files', 'removed', '#e74c3c'),
            ('Modified Files', 'modified', '#f39c12'),
            ('Unchanged Files', 'unchanged', '#95a5a6')
        ]

        for title, key, color in categories:
            # Create text widget
            text_widget = QTextEdit()
            text_widget.setReadOnly(True)
            text_widget.setAcceptRichText(True)
            text_widget.setStyleSheet(f"""
                QTextEdit {{
                    border: none;
                    background-color: white;
                    color: #2c3e50;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 13px;
                    padding: 10px;
                }}
            """)

            # Add files to text widget
            files = differences[key]
            if files:
                if key == 'modified':
                    # For modified files, show detailed diff for .cs files
                    for file in sorted(files):
                        text_widget.append(f"📄 {file}")
                        # Check if it's a text file by extension
                        text_extensions = ['.txt', '.cs', '.py', '.js', '.html', '.css', '.xml', '.json', '.md', '.log', '.ini', '.cfg', '.conf', '.yml', '.yaml', '.sql', '.sh', '.bat', '.ps1', '.java', '.cpp', '.c', '.h', '.hpp', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.ts', '.tsx', '.jsx', '.vue', '.svelte']
                        if any(file.lower().endswith(ext) for ext in text_extensions):
                            # Get diff content for text files
                            diff_content = self.get_file_diff(
                                source_backup, compare_backup, file)
                            if diff_content:
                                text_widget.append("")
                                text_widget.append("Changes:")
                                text_widget.append("")
                                # Add diff content with syntax highlighting
                                self.add_diff_to_widget(
                                    text_widget, diff_content)
                                text_widget.append("")
                                text_widget.append("─" * 50)
                                text_widget.append("")
                            else:
                                text_widget.append("  (No differences found)")
                                text_widget.append("")
                        else:
                            text_widget.append(
                                "  (Binary or non-text file - diff not shown)")
                            text_widget.append("")
                else:
                    # For other categories, just show file names
                    for file in sorted(files):
                        text_widget.append(file)
            else:
                text_widget.append("No files in this category.")

            results_tab_widget.addTab(text_widget, title)

        self.comparison_content_layout.addWidget(results_tab_widget)

        # Add summary
        summary_text = f"Summary: {len(differences['added'])} added, {len(differences['removed'])} removed, {len(differences['modified'])} modified, {len(differences['unchanged'])} unchanged"
        summary_label = QLabel(summary_text)
        summary_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; padding: 10px; background-color: #ecf0f1; border-radius: 4px; color: #2c3e50;")
        self.comparison_content_layout.addWidget(summary_label)

        # Switch to comparison tab
        self.tab_widget.setCurrentIndex(1)

    def comparison_failed(self, error_msg):
        """Called when comparison fails"""
        self.compare_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setText("Comparison failed")
        QMessageBox.critical(self, "Error", f"Comparison failed: {error_msg}")


def main():
    app = QApplication(sys.argv)
    window = BackupRestoreApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
