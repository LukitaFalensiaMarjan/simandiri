"""
GUARDVISION IOT - SISTEM CCTV INDOOR
=====================================
Monitoring real-time APD pegawai di dalam ruangan.
Mendeteksi pegawai yang melepas APD (helm) dan memberikan
peringatan suara serta mencatat pelanggaran ke database MySQL.

Jalankan: python cctv_monitor.py
Tekan 'q' untuk keluar.
"""

import cv2
import os
import time
import threading
try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    print("\n[WARNING] Module 'face_recognition' tidak ditemukan!")
    print("[WARNING] Menggunakan OpenCV Haar Cascade sebagai fallback.\n")
    HAS_FACE_RECOGNITION = False

    class MockFaceRecognition:
        def __init__(self):
            # Memuat haar cascade untuk deteksi wajah dasar
            self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
        def load_image_file(self, path):
            return None
            
        def face_encodings(self, image, known_face_locations=None):
            if known_face_locations is None:
                return []
            return [[] for _ in known_face_locations]
            
        def face_locations(self, image):
            # image berupa RGB
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            faces = self.cascade.detectMultiScale(gray, 1.1, 4)
            locs = []
            for (x, y, w, h) in faces:
                locs.append((y, x+w, y+h, x))
            return locs
            
        def compare_faces(self, encodings, face_encoding, tolerance=0.5):
            return [False] * len(encodings)

    face_recognition = MockFaceRecognition()

from ultralytics import YOLO

import os
from gtts import gTTS
import playsound
HAS_AUDIO = True
from collections import defaultdict
from database import DatabaseManager
from config import (
    CCTV_REQUIRED_APD, YOLO_MODEL_PATH, CCTV_CAMERA_INDEX,
    CAMERA_WIDTH, CAMERA_HEIGHT, FACE_DATASET_PATH,
    MAX_PHOTOS_PER_PERSON, FACE_TOLERANCE, YOLO_CONFIDENCE, YOLO_IOU,
    CCTV_WARNING_COOLDOWN, CCTV_MISSING_THRESHOLD, CCTV_CAMERA_NAME
)
from flask import Flask, Response

stream_app = Flask(__name__)
current_stream_frame = None

def generate_frames():
    global current_stream_frame
    while True:
        if current_stream_frame is not None:
            ret, buffer = cv2.imencode('.jpg', current_stream_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ret:
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.05)

@stream_app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_stream_app():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    # Jalankan stream server di port 5001
    stream_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)

threading.Thread(target=run_stream_app, daemon=True).start()




# ============================================================
#  INISIALISASI
# ============================================================

print("=" * 70)
print("  SIMANDIRI - SISTEM CCTV INDOOR")
print("  Monitoring APD Real-time di Dalam Ruangan")
print("=" * 70)

print("\n Memuat Model YOLOv8...")
model_yolo = YOLO(YOLO_MODEL_PATH)

print("  Menghubungkan ke Database MySQL...")
try:
    db = DatabaseManager()
except Exception as e:
    print(f" Gagal koneksi database: {e}")
    print("   Pastikan MySQL server berjalan!")
    db = None

# ============================================================
#  AUDIO (Text-to-Speech)
# ============================================================

is_speaking = False
audio_lock = threading.Lock()

def play_audio(teks, filename="suara_cctv.mp3"):
    """Putar peringatan suara menggunakan gTTS dan playsound."""
    global is_speaking
    
    with audio_lock:
        if is_speaking:
            return
        is_speaking = True

    def proses_suara():
        global is_speaking
        try:
            tts = gTTS(text=teks, lang='id')
            tts.save(filename)
            playsound.playsound(filename)
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"[AUDIO ERROR] {e}")
        finally:
            with audio_lock:
                is_speaking = False

    threading.Thread(target=proses_suara, daemon=True).start()

def format_kata(daftar_kata):
    """Format daftar kata menjadi string natural bahasa Indonesia."""
    if len(daftar_kata) == 0:
        return ""
    elif len(daftar_kata) == 1:
        return daftar_kata[0]
    elif len(daftar_kata) == 2:
        return f"{daftar_kata[0]} dan {daftar_kata[1]}"
    else:
        return ", ".join(daftar_kata[:-1]) + f", dan {daftar_kata[-1]}"

# ============================================================
#  FACE RECOGNITION DATABASE
# ============================================================

print(" Memuat Database Wajah...")
known_face_encodings = []
known_face_names = []
folder_wajah = FACE_DATASET_PATH

for nama_orang in os.listdir(folder_wajah):
    path_orang = os.path.join(folder_wajah, nama_orang)
    if os.path.isdir(path_orang):
        foto_count = 0
        for file_foto in sorted(os.listdir(path_orang)):
            if foto_count >= MAX_PHOTOS_PER_PERSON:
                break

            if not file_foto.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue

            path_foto = os.path.join(path_orang, file_foto)
            try:
                gambar = face_recognition.load_image_file(path_foto)
                encodings = face_recognition.face_encodings(gambar)
                if len(encodings) > 0:
                    known_face_encodings.append(encodings[0])
                    known_face_names.append(nama_orang.capitalize())
                    foto_count += 1
            except Exception as e:
                pass

print(f"Database: {len(known_face_encodings)} wajah dari {len(set(known_face_names))} pegawai")

# ============================================================
#  KONFIGURASI CCTV
# ============================================================

# APD yang dimonitor di CCTV (hanya helm)
required_apd = CCTV_REQUIRED_APD

print(f" APD yang dimonitor: {', '.join(required_apd)}")
print(" Sistem CCTV Siap! Membuka Kamera...")
print("=" * 70)

cap = cv2.VideoCapture(CCTV_CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

if not cap.isOpened():
    print(f" Tidak bisa membuka kamera index {CCTV_CAMERA_INDEX}")
    print("   Pastikan webcam eksternal terhubung!")
    print(f"   Coba ubah CCTV_CAMERA_INDEX di config.py (sekarang: {CCTV_CAMERA_INDEX})")
    exit(1)

# ============================================================
#  STATE TRACKING PER PEGAWAI
# ============================================================

class EmployeeTracker:
    """Track status APD per pegawai secara real-time."""

    def __init__(self):
        # {nama: {apd_item: count}} - counter deteksi APD stabil
        self.apd_history = defaultdict(lambda: defaultdict(int))
        # {nama: {apd_item: True/False}} - status APD terakhir yang stabil
        self.apd_confirmed = defaultdict(lambda: defaultdict(bool))
        # {nama: {apd_item: timestamp}} - waktu peringatan terakhir
        self.last_warning_time = defaultdict(lambda: defaultdict(float))
        # {nama: int} - frame terakhir orang terlihat
        self.last_seen_frame = defaultdict(int)
        # {nama: bool} - apakah pegawai pernah terdeteksi dengan helm
        self.pernah_pakai_helm = defaultdict(bool)

    def update_apd(self, nama, detected_apd_set, frame_num):
        """Update status APD untuk seorang pegawai."""
        self.last_seen_frame[nama] = frame_num

        for apd in required_apd:
            if apd in detected_apd_set:
                # APD terdeteksi - naikkan counter
                self.apd_history[nama][apd] = min(
                    self.apd_history[nama][apd] + 3, 10
                )
            else:
                # APD tidak terdeteksi - turunkan counter
                self.apd_history[nama][apd] = max(
                    self.apd_history[nama][apd] - 1, 0
                )

            # Update status confirmed berdasarkan threshold
            was_confirmed = self.apd_confirmed[nama][apd]
            is_confirmed = self.apd_history[nama][apd] >= 2

            if is_confirmed and not was_confirmed:
                # APD baru saja dikonfirmasi terdeteksi
                self.apd_confirmed[nama][apd] = True
                if apd == "helm":
                    self.pernah_pakai_helm[nama] = True
                print(f"   ✅ {nama}: {apd} terdeteksi")

            elif not is_confirmed and was_confirmed:
                # APD baru saja hilang (dilepas)
                self.apd_confirmed[nama][apd] = False

        # Deteksi pelanggaran (APD yang dilepas)
        apd_dilepas = []
        for apd in required_apd:
            # Hanya dianggap pelanggaran jika:
            # 1. Counter sudah 0 (benar-benar hilang)
            # 2. Pegawai PERNAH pakai helm sebelumnya
            if (self.apd_history[nama][apd] == 0 and
                    self.pernah_pakai_helm[nama]):
                apd_dilepas.append(apd)

        return apd_dilepas

    def should_warn(self, nama, apd_item):
        """Cek apakah boleh memberi peringatan (cooldown check)."""
        now = time.time()
        last_warn = self.last_warning_time[nama][apd_item]
        if now - last_warn >= CCTV_WARNING_COOLDOWN:
            self.last_warning_time[nama][apd_item] = now
            return True
        return False

    def get_status(self, nama):
        """Ambil status APD saat ini untuk display."""
        status = {}
        for apd in required_apd:
            status[apd] = self.apd_confirmed[nama][apd]
        return status

    def cleanup_stale(self, current_frame, threshold=60):
        """Bersihkan data pegawai yang sudah lama tidak terlihat."""
        stale = [
            nama for nama, last_frame in self.last_seen_frame.items()
            if current_frame - last_frame > threshold
        ]
        for nama in stale:
            del self.apd_history[nama]
            del self.apd_confirmed[nama]
            del self.last_seen_frame[nama]
            # JANGAN hapus pernah_pakai_helm dan last_warning_time
            # agar tracking tetap konsisten jika pegawai kembali

tracker = EmployeeTracker()

# ============================================================
#  HELPER: Spatial matching APD ke wajah
# ============================================================

def find_apd_for_face(face_box, apd_detections):
    """
    Cari APD yang berhubungan dengan wajah tertentu berdasarkan posisi spasial.
    face_box: (left, top, right, bottom) dalam koordinat frame asli
    apd_detections: list of (class_name, confidence, x1, y1, x2, y2)
    Returns: set of detected APD class names
    """
    face_left, face_top, face_right, face_bottom = face_box
    face_center_x = (face_left + face_right) / 2
    face_width = face_right - face_left
    face_height = face_bottom - face_top

    detected = set()

    for class_name, conf, x1, y1, x2, y2 in apd_detections:
        if class_name not in required_apd:
            continue

        apd_center_x = (x1 + x2) / 2

        if class_name == "helm":
            # Helm harus di atas wajah atau overlapping bagian atas
            # Horizontal: center helm harus dalam range face width * 1.5
            h_distance = abs(apd_center_x - face_center_x)
            if h_distance > face_width * 1.2:
                continue
            # Vertical: bagian bawah helm harus di atas atau sedikit overlap dengan wajah
            if y2 > face_bottom + face_height * 0.3:
                continue
            # Helm seharusnya di atas wajah
            if y1 > face_bottom:
                continue
            detected.add("helm")

    return detected

# ============================================================
#  MAIN LOOP CCTV
# ============================================================

frame_count = 0
peringatan_counter = 0  # Total peringatan yang sudah diberikan

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    # Resize untuk face recognition (lebih cepat)
    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Deteksi wajah
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings_list = face_recognition.face_encodings(rgb_small_frame, face_locations)

    # Dapatkan ID kelas YOLO berdasarkan nama APD yang wajib saja
    required_classes_indices = [k for k, v in model_yolo.names.items() if v in required_apd]
    
    # Deteksi APD menggunakan YOLO pada frame penuh (hanya kelas yang dibutuhkan)
    results = model_yolo(frame, conf=YOLO_CONFIDENCE, iou=YOLO_IOU, verbose=False, classes=required_classes_indices)
    annotated_frame = results[0].plot()

    # Kumpulkan semua deteksi APD
    all_apd_detections = []
    for box in results[0].boxes:
        class_name = model_yolo.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        all_apd_detections.append((class_name, confidence, x1, y1, x2, y2))

    # Proses setiap wajah yang terdeteksi
    pegawai_dalam_frame = []

    for idx, ((top, right, bottom, left), face_encoding) in enumerate(zip(face_locations, face_encodings_list)):
        # Scale kembali ke ukuran frame asli
        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        # Identifikasi wajah
        matches = face_recognition.compare_faces(
            known_face_encodings, face_encoding, tolerance=FACE_TOLERANCE
        )
        nama = "Tidak Dikenal"
        warna_kotak = (0, 0, 255)

        if True in matches:
            first_match_index = matches.index(True)
            nama = known_face_names[first_match_index]
            warna_kotak = (0, 255, 0)

        # Gambar kotak wajah
        cv2.rectangle(annotated_frame, (left, top), (right, bottom), warna_kotak, 2)
        cv2.rectangle(annotated_frame, (left, bottom - 30), (right, bottom), warna_kotak, cv2.FILLED)
        cv2.putText(annotated_frame, nama, (left + 6, bottom - 8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1)

        if nama == "Tidak Dikenal":
            # Berikan nama unik sementara agar tetap dilacak status APD-nya
            nama = f"Orang_{idx+1}"
            warna_kotak = (0, 165, 255) # Warna orange untuk fallback

        # Cari APD yang terkait dengan wajah ini
        face_box = (left, top, right, bottom)
        detected_apd = find_apd_for_face(face_box, all_apd_detections)

        # Update tracker
        apd_dilepas = tracker.update_apd(nama, detected_apd, frame_count)

        # Ambil status APD terkini
        status = tracker.get_status(nama)

        # Tampilkan status APD di samping wajah
        y_offset = top - 10
        for apd in required_apd:
            if status[apd]:
                label = f"[V] {apd.upper()}"
                color = (0, 255, 0)
            else:
                if tracker.pernah_pakai_helm[nama]:
                    label = f"[X] {apd.upper()} - DILEPAS!"
                    color = (0, 0, 255)
                else:
                    label = f"[?] {apd.upper()}"
                    color = (0, 255, 255)

            cv2.putText(annotated_frame, label, (left, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            y_offset -= 22

        # Proses pelanggaran
        if apd_dilepas:
            for apd_item in apd_dilepas:
                if tracker.should_warn(nama, apd_item):
                    peringatan_counter += 1
                    apd_teks = format_kata(apd_dilepas)

                    # Peringatan suara
                    if not is_speaking:
                        play_audio("tolong lengkapi APD anda")

                    # Catat ke database
                    if db:
                        try:
                            db.catat_pelanggaran(
                                nama=nama,
                                apd_dilepas=apd_dilepas,
                                kamera=CCTV_CAMERA_NAME
                            )
                        except Exception as e:
                            print(f"[DB ERROR] Gagal catat pelanggaran: {e}")

                    print(f"  PELANGGARAN #{peringatan_counter}: "
                          f"{nama} melepas {apd_teks} "
                          f"[Kamera: {CCTV_CAMERA_NAME}]")
                    break  # Satu peringatan per cycle cukup

        pegawai_dalam_frame.append({
            'nama': nama,
            'status': status,
            'apd_dilepas': apd_dilepas
        })

    # Bersihkan data pegawai yang sudah lama tidak terlihat
    if frame_count % 120 == 0:  # Setiap ~4 detik
        tracker.cleanup_stale(frame_count)

    # ============================================================
    #  OVERLAY UI
    # ============================================================

    # Header
    overlay = annotated_frame.copy()
    cv2.rectangle(overlay, (0, 0), (annotated_frame.shape[1], 50), (0, 0, 0), cv2.FILLED)
    cv2.addWeighted(overlay, 0.6, annotated_frame, 0.4, 0, annotated_frame)
    cv2.putText(annotated_frame, f"CCTV MONITOR | {CCTV_CAMERA_NAME} | APD: Helm",
                (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)

    # Status bar di bawah
    h = annotated_frame.shape[0]
    overlay2 = annotated_frame.copy()
    cv2.rectangle(overlay2, (0, h - 40), (annotated_frame.shape[1], h), (0, 0, 0), cv2.FILLED)
    cv2.addWeighted(overlay2, 0.6, annotated_frame, 0.4, 0, annotated_frame)

    status_text = f"Pegawai Terdeteksi: {len(pegawai_dalam_frame)} | Peringatan: {peringatan_counter}"
    cv2.putText(annotated_frame, status_text, (10, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # Peringatan besar jika ada pelanggaran aktif
    ada_pelanggaran = any(p['apd_dilepas'] for p in pegawai_dalam_frame)
    if ada_pelanggaran:
        # Flash efek merah
        if frame_count % 20 < 10:
            overlay3 = annotated_frame.copy()
            cv2.rectangle(overlay3, (0, 50), (annotated_frame.shape[1], 90), (0, 0, 200), cv2.FILLED)
            cv2.addWeighted(overlay3, 0.5, annotated_frame, 0.5, 0, annotated_frame)
            cv2.putText(annotated_frame, "!! PELANGGARAN APD TERDETEKSI !!",
                        (annotated_frame.shape[1] // 2 - 250, 78),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # Simpan frame untuk web streaming
    current_stream_frame = annotated_frame.copy()

    cv2.imshow(f"Simandiri - {CCTV_CAMERA_NAME}", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print(f"\n Sistem CCTV ditutup. Total peringatan: {peringatan_counter}")
