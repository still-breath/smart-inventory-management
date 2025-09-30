import sys
import os
import time
import threading
import subprocess
import cv2 as cv
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox, QGridLayout,
    QSpinBox, QListWidget, QProgressBar, QTabWidget, QFileDialog,
    QComboBox, QStackedWidget
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QImage, QPixmap
from scanner import scan_camera
from background_service import BackgroundCameraService, VideoPreviewService

class SetupFromVideoThread(QThread):
    status_updated = pyqtSignal(str)
    setup_finished = pyqtSignal()

    def __init__(self, frame, devices_dir, video_path):
        super().__init__()
        self.frame = frame
        self.devices_dir = devices_dir
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_name = f"{base_name}.jpg"
        output_path = os.path.join(self.devices_dir, output_name)
        
        counter = 1
        while os.path.exists(output_path):
            output_name = f"{base_name}_{counter}.jpg"
            output_path = os.path.join(self.devices_dir, output_name)
            counter += 1
            
        self.output_frame_path = output_path

    def run(self):
        try:
            self.status_updated.emit("Memulai proses setup dari frame video...")
            os.makedirs(self.devices_dir, exist_ok=True)

            self.status_updated.emit(f"Menyimpan frame ke: {self.output_frame_path}")
            cv.imwrite(self.output_frame_path, self.frame)
            if not os.path.exists(self.output_frame_path):
                self.status_updated.emit("ERROR: Gagal menyimpan frame.")
                return

            self.status_updated.emit("Menjalankan 'shelf_scan.py setup'...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            shelf_scan_script = os.path.join(project_root, 'product_scan', 'shelf_scan.py')

            if not os.path.exists(shelf_scan_script):
                shelf_scan_script = os.path.join(project_root, 'shelf_scan.py')
                if not os.path.exists(shelf_scan_script):
                    self.status_updated.emit(f"ERROR: 'shelf_scan.py' tidak ditemukan.")
                    return

            process = subprocess.Popen(
                [sys.executable, shelf_scan_script, "setup"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            for line in process.stdout:
                self.status_updated.emit(line.strip())

            process.wait()
            self.status_updated.emit("Proses setup selesai.")

        except Exception as e:
            self.status_updated.emit(f"Terjadi error saat setup: {e}")
        finally:
            self.setup_finished.emit()


class ScannerServiceThread(QThread):
    status_updated = pyqtSignal(str)
    scanner_started = pyqtSignal()
    scanner_stopped = pyqtSignal()
    frame_saved = pyqtSignal(str)

    def __init__(self, video_preview_service, devices_dir, video_path):
        super().__init__()
        self.video_preview_service = video_preview_service
        self.devices_dir = devices_dir
        self.video_path = video_path
        self.is_running = False
        self.scanner_process = None
        self.base_name = os.path.splitext(os.path.basename(video_path))[0]
        
        # Setup paths for product info copying
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        app_root = os.path.join(project_root, 'retruxosaproject', 'app_root')
        self.product_info_dir = os.path.join(app_root, 'product_information')
        self.last_state_dir = os.path.join(app_root, 'last_state')
        
    def run(self):
        try:
            self.is_running = True
            self.scanner_started.emit()
            self.status_updated.emit("🔍 Scanner Service dimulai...")
            
            # Check if base setup exists
            base_product_info = os.path.join(self.product_info_dir, f"{self.base_name}.json")
            if not os.path.exists(base_product_info):
                self.status_updated.emit("⚠️ Setup belum dilakukan! Jalankan Setup terlebih dahulu.")
                return
            
            # Start shelf_scan service in background
            self.start_scanner_service()
            
            # Main loop untuk menyimpan frame dengan timestamp
            frame_counter = 0
            while self.is_running:
                if self.video_preview_service and self.video_preview_service.isRunning():
                    current_frame = self.video_preview_service.get_current_frame()
                    if current_frame is not None:
                        # Strategy 1: Use fixed filename (recommended)
                        # Always overwrite the same file so shelf_scan can monitor it
                        fixed_frame_filename = f"{self.base_name}.jpg"
                        fixed_frame_path = os.path.join(self.devices_dir, fixed_frame_filename)
                        
                        # Strategy 2: Also save timestamp version for history
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        timestamp_filename = f"{self.base_name}_{timestamp}.jpg"
                        timestamp_path = os.path.join(self.devices_dir, timestamp_filename)
                        
                        # Save both versions
                        cv.imwrite(fixed_frame_path, current_frame)  # For shelf_scan monitoring
                        cv.imwrite(timestamp_path, current_frame)    # For history/backup
                        
                        self.frame_saved.emit(fixed_frame_filename)
                        self.status_updated.emit(f"📸 Frame disimpan: {fixed_frame_filename} & {timestamp_filename}")
                        
                        frame_counter += 1
                        
                # Wait 5 seconds before next frame capture
                for i in range(50):  # 5 seconds = 50 * 0.1 seconds
                    if not self.is_running:
                        break
                    time.sleep(0.1)
                        
        except Exception as e:
            self.status_updated.emit(f"❌ Error pada Scanner Service: {e}")
        finally:
            self.stop_scanner_service()
            self.scanner_stopped.emit()
            self.status_updated.emit("🛑 Scanner Service dihentikan.")

    def start_scanner_service(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            shelf_scan_script = os.path.join(project_root, 'product_scan', 'shelf_scan.py')

            if not os.path.exists(shelf_scan_script):
                shelf_scan_script = os.path.join(project_root, 'shelf_scan.py')

            if os.path.exists(shelf_scan_script):
                self.scanner_process = subprocess.Popen(
                    [sys.executable, shelf_scan_script, "service"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                self.status_updated.emit("🚀 Shelf Scanner Service dimulai di background")
            else:
                self.status_updated.emit("⚠️ shelf_scan.py tidak ditemukan, hanya menyimpan frame")
                
        except Exception as e:
            self.status_updated.emit(f"⚠️ Tidak bisa memulai scanner service: {e}")

    def stop_scanner_service(self):
        if self.scanner_process:
            try:
                self.scanner_process.terminate()
                self.scanner_process.wait(timeout=5)
                self.status_updated.emit("🔚 Scanner Service process dihentikan")
            except subprocess.TimeoutExpired:
                self.scanner_process.kill()
                self.status_updated.emit("🔪 Scanner Service process dipaksa berhenti")
            except Exception as e:
                self.status_updated.emit(f"⚠️ Error menghentikan scanner process: {e}")

    def stop(self):
        self.is_running = False


class CameraServiceThread(QThread):
    status_updated = pyqtSignal(str)
    camera_found = pyqtSignal(list)
    service_started = pyqtSignal()
    service_stopped = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.running = False
        self.services = []
        self.root_directory = None

    def set_root_directory(self, root_dir):
        self.root_directory = root_dir

    def scan_cameras(self, search_limit=10):
        self.status_updated.emit("Scanning for cameras...")
        valid_cameras = scan_camera(search_limit)
        self.camera_found.emit(valid_cameras)
        self.status_updated.emit(f"Found {len(valid_cameras)} valid cameras")

    def start_services(self, camera_ids):
        if not self.root_directory:
            self.status_updated.emit("Root directory not set")
            return

        import shutil
        if os.path.exists(self.root_directory):
            shutil.rmtree(self.root_directory, ignore_errors=True)
        os.makedirs(self.root_directory, exist_ok=True)

        self.status_updated.emit(f"Starting services for {len(camera_ids)} cameras...")

        for camera_id in camera_ids:
            camera_str = str(camera_id).zfill(3)
            latest_frame_file = os.path.join(self.root_directory, f'camera_{camera_str}_frame.jpg')

            camera_service = BackgroundCameraService(camera_str, camera_id, latest_frame_file)
            self.services.append(camera_service)

        for i, camera_service in enumerate(self.services):
            self.status_updated.emit(f"Starting camera {camera_service.camera_id}...")
            camera_service.start()
            time.sleep(1.5)

        self.running = True
        self.service_started.emit()
        self.status_updated.emit("All camera services started")

    def stop_services(self):
        self.running = False
        self.status_updated.emit("Stopping all camera services...")

        for service in self.services:
            service.stop()

        for service in self.services:
            if service.thread.is_alive():
                service.thread.join(timeout=3)

        self.services.clear()
        self.service_stopped.emit()
        self.status_updated.emit("All camera services stopped")


class CameraServiceWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Retrux Camera Service Control")
        self.setGeometry(100, 100, 1200, 800)

        self.service_thread = CameraServiceThread()
        self.service_thread.status_updated.connect(self.log_status)
        self.service_thread.camera_found.connect(self.update_camera_list)
        self.service_thread.service_started.connect(self.on_service_started)
        self.service_thread.service_stopped.connect(self.on_service_stopped)

        self.valid_cameras = []
        self.video_preview_service = None
        self.setup_thread = None
        self.scanner_thread = None
        self.current_video_path = None

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        title = QLabel("Camera Service Control Panel")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        service_tab = QWidget()
        service_layout = QVBoxLayout(service_tab)

        service_type_group = QGroupBox("Service Type")
        service_type_layout = QHBoxLayout(service_type_group)
        self.service_type_combo = QComboBox()
        self.service_type_combo.addItems(["Camera", "Video"])
        self.service_type_combo.currentIndexChanged.connect(self.on_service_type_changed)
        service_type_layout.addWidget(self.service_type_combo)
        service_layout.addWidget(service_type_group)

        self.stacked_widget = QStackedWidget()
        service_layout.addWidget(self.stacked_widget)

        camera_controls_widget = QWidget()
        camera_controls_layout = QVBoxLayout(camera_controls_widget)
        self.stacked_widget.addWidget(camera_controls_widget)

        discovery_group = QGroupBox("Camera Discovery")
        discovery_controls = QGridLayout(discovery_group)
        discovery_controls.addWidget(QLabel("Search Limit:"), 0, 0)
        self.search_limit_spin = QSpinBox()
        self.search_limit_spin.setRange(1, 100)
        self.search_limit_spin.setValue(10)
        discovery_controls.addWidget(self.search_limit_spin, 0, 1)
        self.scan_btn = QPushButton("Scan for Cameras")
        self.scan_btn.clicked.connect(self.scan_cameras)
        discovery_controls.addWidget(self.scan_btn, 0, 2)
        camera_controls_layout.addWidget(discovery_group)

        camera_list_group = QGroupBox("Detected Cameras")
        camera_list_layout = QVBoxLayout(camera_list_group)
        self.camera_list = QListWidget()
        camera_list_layout.addWidget(self.camera_list)
        camera_controls_layout.addWidget(camera_list_group)

        button_layout = QHBoxLayout()
        self.start_service_btn = QPushButton("Start Camera Services")
        self.start_service_btn.clicked.connect(self.start_services)
        self.start_service_btn.setEnabled(False)
        self.stop_service_btn = QPushButton("Stop Camera Services")
        self.stop_service_btn.clicked.connect(self.stop_services)
        self.stop_service_btn.setEnabled(False)
        button_layout.addWidget(self.start_service_btn)
        button_layout.addWidget(self.stop_service_btn)
        camera_controls_layout.addLayout(button_layout)

        video_controls_widget = QWidget()
        video_controls_layout = QVBoxLayout(video_controls_widget)
        self.stacked_widget.addWidget(video_controls_widget)

        video_group = QGroupBox("Video Preview")
        video_controls = QVBoxLayout(video_group)
        self.select_video_btn = QPushButton("Select Video File")
        self.select_video_btn.clicked.connect(self.select_video_file)
        video_controls.addWidget(self.select_video_btn)
        self.video_preview_label = QLabel("No video selected")
        self.video_preview_label.setMinimumSize(640, 480)
        self.video_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_preview_label.setStyleSheet("border: 1px solid #ccc; background-color: #000;")
        video_controls.addWidget(self.video_preview_label)

        # Button layout for setup and scanner
        video_button_layout = QHBoxLayout()
        
        self.run_setup_btn = QPushButton("⚙️ Run Setup")
        self.run_setup_btn.clicked.connect(self.run_setup_from_video)
        self.run_setup_btn.setVisible(False)
        self.run_setup_btn.setStyleSheet("background-color: #4CAF50; font-weight: bold;")
        
        self.run_scanner_btn = QPushButton("🔍 Run Scanner")
        self.run_scanner_btn.clicked.connect(self.run_scanner_service)
        self.run_scanner_btn.setVisible(False)
        self.run_scanner_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        
        self.stop_scanner_btn = QPushButton("🛑 Stop Scanner")
        self.stop_scanner_btn.clicked.connect(self.stop_scanner_service)
        self.stop_scanner_btn.setVisible(False)
        self.stop_scanner_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        
        video_button_layout.addWidget(self.run_setup_btn)
        video_button_layout.addWidget(self.run_scanner_btn)
        video_button_layout.addWidget(self.stop_scanner_btn)
        
        video_controls.addLayout(video_button_layout)
        video_controls_layout.addWidget(video_group)
        self.tab_widget.addTab(service_tab, "Service Control")
        layout.addWidget(self.tab_widget)

        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)

        self.status_log = QTextEdit()
        self.status_log.setMaximumHeight(200)
        self.status_log.setReadOnly(True)
        log_layout.addWidget(self.status_log)

        layout.addWidget(log_group)
        self.log_status("Camera Service Control Panel initialized")

    def run_setup_from_video(self):
        if not self.video_preview_service or not self.video_preview_service.isRunning():
            self.log_status("ERROR: Video preview tidak berjalan.")
            return

        current_frame = self.video_preview_service.get_current_frame()
        if current_frame is None:
            self.log_status("ERROR: Tidak bisa mengambil frame saat ini dari video.")
            return
            
        if self.current_video_path is None:
            self.log_status("ERROR: Path video tidak ditemukan.")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        devices_dir = os.path.join(project_root, 'retruxosaproject', 'app_root', 'active_state', 'devices')

        self.run_setup_btn.setEnabled(False)
        self.run_setup_btn.setText("⏳ Setup Running...")

        self.setup_thread = SetupFromVideoThread(current_frame, devices_dir, self.current_video_path)
        self.setup_thread.status_updated.connect(self.log_status)
        self.setup_thread.setup_finished.connect(self.on_setup_finished)
        self.setup_thread.start()

    def run_scanner_service(self):
        if not self.video_preview_service or not self.video_preview_service.isRunning():
            self.log_status("ERROR: Video preview tidak berjalan.")
            return
            
        if self.current_video_path is None:
            self.log_status("ERROR: Path video tidak ditemukan.")
            return

        if self.scanner_thread and self.scanner_thread.isRunning():
            self.log_status("Scanner service sudah berjalan.")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        devices_dir = os.path.join(project_root, 'retruxosaproject', 'app_root', 'active_state', 'devices')
        os.makedirs(devices_dir, exist_ok=True)

        self.scanner_thread = ScannerServiceThread(
            self.video_preview_service, 
            devices_dir, 
            self.current_video_path
        )
        
        self.scanner_thread.status_updated.connect(self.log_status)
        self.scanner_thread.scanner_started.connect(self.on_scanner_started)
        self.scanner_thread.scanner_stopped.connect(self.on_scanner_stopped)
        self.scanner_thread.frame_saved.connect(self.on_frame_saved)
        
        self.scanner_thread.start()

    def stop_scanner_service(self):
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.stop()
            self.scanner_thread.wait(5000)  # Wait up to 5 seconds
            if self.scanner_thread.isRunning():
                self.scanner_thread.terminate()
            self.log_status("🛑 Scanner service dihentikan")
        else:
            self.log_status("Scanner service tidak berjalan")

    def on_scanner_started(self):
        self.run_scanner_btn.setVisible(False)
        self.stop_scanner_btn.setVisible(True)
        self.run_scanner_btn.setText("🔍 Run Scanner")
        self.log_status("✅ Scanner Service berhasil dimulai")

    def on_scanner_stopped(self):
        self.run_scanner_btn.setVisible(True)
        self.stop_scanner_btn.setVisible(False)
        self.log_status("✅ Scanner Service berhasil dihentikan")

    def on_frame_saved(self, filename):
        # Optional: You can add additional logic here when a frame is saved
        pass

    def on_setup_finished(self):
        self.log_status("Thread setup selesai.")
        self.run_setup_btn.setEnabled(True)
        self.run_setup_btn.setText("⚙️ Run Setup")
        self.setup_thread = None

    def on_tab_changed(self, index):
        if self.video_preview_service and self.video_preview_service.isRunning():
            self.video_preview_service.stop()
            self.run_setup_btn.setVisible(False)
            self.run_scanner_btn.setVisible(False)
            self.stop_scanner_btn.setVisible(False)

    def on_service_type_changed(self, index):
        self.stacked_widget.setCurrentIndex(index)
        if self.video_preview_service and self.video_preview_service.isRunning():
            self.video_preview_service.stop()
            self.run_setup_btn.setVisible(False)
            self.run_scanner_btn.setVisible(False)
            self.stop_scanner_btn.setVisible(False)

    def select_video_file(self):
        if self.video_preview_service and self.video_preview_service.isRunning():
            self.video_preview_service.stop()
        
        # Stop scanner if running
        self.stop_scanner_service()
        
        self.run_setup_btn.setVisible(False)
        self.run_scanner_btn.setVisible(False)
        self.stop_scanner_btn.setVisible(False)

        file_dialog = QFileDialog()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        video_dir = os.path.join(project_root, "retruxosaproject", "app_root", "testing")
        
        video_path, _ = file_dialog.getOpenFileName(self, "Select Video File", video_dir, "Video Files (*.mp4 *.mov)")
        if video_path:
            self.current_video_path = video_path
            self.video_preview_service = VideoPreviewService(video_path)
            self.video_preview_service.frame_ready.connect(self.update_video_preview)
            self.video_preview_service.start()
            self.log_status(f"Starting video preview for {video_path}")
            self.run_setup_btn.setVisible(True)
            self.run_scanner_btn.setVisible(True)

    def update_video_preview(self, image):
        pixmap = QPixmap.fromImage(image)
        self.video_preview_label.setPixmap(pixmap.scaled(
            self.video_preview_label.width(), self.video_preview_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio
        ))

    def scan_cameras(self):
        self.scan_btn.setEnabled(False)
        self.camera_list.clear()

        search_limit = self.search_limit_spin.value()
        scan_thread = threading.Thread(
            target=lambda: self.service_thread.scan_cameras(search_limit)
        )
        scan_thread.start()

    def update_camera_list(self, cameras):
        self.valid_cameras = cameras
        self.camera_list.clear()

        for camera_id in cameras:
            self.camera_list.addItem(f"Camera {camera_id}")

        self.scan_btn.setEnabled(True)
        self.start_service_btn.setEnabled(len(cameras) > 0)

    def start_services(self):
        if not self.valid_cameras:
            self.log_status("No cameras available to start")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        root_dir = os.path.join(project_root, 'retruxosaproject', 'app_root', 'active_state', 'devices')

        self.service_thread.set_root_directory(root_dir)
        start_thread = threading.Thread(
            target=lambda: self.service_thread.start_services(self.valid_cameras)
        )
        start_thread.start()
        self.start_service_btn.setEnabled(False)

    def stop_services(self):
        stop_thread = threading.Thread(
            target=self.service_thread.stop_services
        )
        stop_thread.start()
        self.stop_service_btn.setEnabled(False)

    def on_service_started(self):
        self.log_status("Status Layanan Kamera: Berjalan")
        self.stop_service_btn.setEnabled(True)

    def on_service_stopped(self):
        self.log_status("Status Layanan Kamera: Berhenti")
        self.start_service_btn.setEnabled(len(self.valid_cameras) > 0)

    def log_status(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.status_log.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        # Stop all services before closing
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.stop_scanner_service()
            
        if self.service_thread.running:
            self.stop_services()
            self.service_thread.wait(3000)
            
        if self.video_preview_service and self.video_preview_service.isRunning():
            self.video_preview_service.stop()
            
        if self.setup_thread and self.setup_thread.isRunning():
            self.setup_thread.quit()
            self.setup_thread.wait()
            
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = CameraServiceWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())