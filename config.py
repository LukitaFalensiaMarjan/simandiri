# ============================================================
#  SIMANDIRI - KONFIGURASI PUSAT
# ============================================================
# File ini digunakan oleh semua komponen sistem:
# - main_simandiri.py  (Sistem Gerbang)
# - cctv_monitor.py    (Sistem CCTV Indoor)
# - web/app.py         (Website Dashboard)
# ============================================================

# --- DATABASE MySQL ---
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '',
    'database': 'simandiri_db'
}

# --- MODEL YOLO ---
YOLO_MODEL_PATH = "runs/detect/simandiri_apd_v2/weights/best.pt"

# --- KONFIGURASI APD ---
# APD yang dicek di gerbang (main_simandiri.py) - hanya helm
GATE_REQUIRED_APD = ["helm"]

# APD yang dicek di CCTV indoor (cctv_monitor.py) - hanya helm
CCTV_REQUIRED_APD = ["helm"]

# --- KONFIGURASI KAMERA ---
GATE_CAMERA_INDEX = 1       # Webcam untuk gerbang (1 untuk eksternal, 0 untuk bawaan)
CCTV_CAMERA_INDEX = 1       # Webcam eksternal untuk CCTV indoor

# Resolusi kamera
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

# --- FACE RECOGNITION ---
FACE_DATASET_PATH = "dataset_wajah"
MAX_PHOTOS_PER_PERSON = 5
FACE_TOLERANCE = 0.55

# --- PARAMETER DETEKSI YOLO ---
YOLO_CONFIDENCE = 0.25
YOLO_IOU = 0.4

# --- PARAMETER TRACKING (Stabilitas deteksi) ---
HISTORY_THRESHOLD = 2       # APD harus terdeteksi N frame berturut-turut
HISTORY_INCREMENT = 3       # Naik cepat saat terdeteksi
HISTORY_DECAY = 1           # Turun lambat saat tidak terdeteksi
MAX_HISTORY = 10            # Batas maksimal counter

# --- CCTV MONITORING ---
CCTV_WARNING_COOLDOWN = 30  # Detik antar peringatan untuk orang/APD yang sama
CCTV_MISSING_THRESHOLD = 8  # Frame berturut-turut sebelum trigger peringatan
CCTV_CAMERA_NAME = "CCTV-Indoor-1"  # Nama kamera untuk logging

# --- RFID ACCESS CONTROL ---
PPE_STATUS_FILE = 'ppe_status.json'       # Shared PPE state file (written by main_simandiri.py)
PPE_STATUS_MAX_AGE = 60                   # Max age in seconds before PPE data is considered stale
RFID_REQUIRE_PPE_COMPLETE = True          # Require full PPE for room entry

# --- WEB DASHBOARD ---
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000
WEB_DEBUG = True

# --- ABSENSI & SHIFT ---
SHIFT_START_TIME = '08:00:00'             # Waktu batas absensi tepat waktu
