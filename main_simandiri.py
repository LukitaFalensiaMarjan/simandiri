import cv2
import os
import json
import threading
import face_recognition
from ultralytics import YOLO
from gtts import gTTS
import pygame
from database import DatabaseManager
from config import (
    GATE_REQUIRED_APD, YOLO_MODEL_PATH, GATE_CAMERA_INDEX,
    CAMERA_WIDTH, CAMERA_HEIGHT, FACE_DATASET_PATH,
    MAX_PHOTOS_PER_PERSON, FACE_TOLERANCE, YOLO_CONFIDENCE, YOLO_IOU,
    HISTORY_THRESHOLD, HISTORY_INCREMENT, HISTORY_DECAY, MAX_HISTORY,
    PPE_STATUS_FILE
)
import time
from flask import Flask, Response

stream_app = Flask(__name__)
current_stream_frame = None

def generate_frames():
    global current_stream_frame
    while True:
        if current_stream_frame is not None:
            ret, buffer = cv2.imencode('.jpg', current_stream_frame)
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
    stream_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)

threading.Thread(target=run_stream_app, daemon=True).start()

pygame.mixer.init()

print("=" * 70)
print("  SIMANDIRI - SISTEM GERBANG CERDAS")
print("=" * 70)

print("\n Memuat Model YOLOv8...")
model_yolo = YOLO(YOLO_MODEL_PATH)

print(" Menghubungkan ke Database MySQL...")
try:
    db = DatabaseManager()
except Exception as e:
    print(f" Gagal koneksi database: {e}")
    print("   Pastikan MySQL server berjalan!")
    db = None

is_speaking = False

def play_audio(teks, filename="suara.mp3"):
    global is_speaking
    if is_speaking:
        return
    is_speaking = True 

    def proses_suara():
        global is_speaking
        try:
            tts = gTTS(text=teks, lang='id')
            tts.save(filename)
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload() 
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            pass
        finally:
            is_speaking = False

    threading.Thread(target=proses_suara, daemon=True).start()

def format_kata(daftar_kata):
    if len(daftar_kata) == 0:
        return ""
    elif len(daftar_kata) == 1:
        return daftar_kata[0]
    elif len(daftar_kata) == 2:
        return f"{daftar_kata[0]} dan {daftar_kata[1]}"
    else:
        return ", ".join(daftar_kata[:-1]) + f", dan {daftar_kata[-1]}"

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

print(f" Database: {len(known_face_encodings)} wajah dari {len(set(known_face_names))} pegawai")

# KONFIGURASI APD (dari config.py - helm dan baju saja, tanpa celana)
required_apd = GATE_REQUIRED_APD

print(" Sistem Siap! Membuka Kamera...")
print("=" * 70)

cap = cv2.VideoCapture(GATE_CAMERA_INDEX)

# Set resolusi webcam (720p untuk deteksi jarak jauh)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

last_detected_name = "Tidak Dikenal"
fase_interaksi = "MENUNGGU" 
frame_hilang_wajah = 0
BATAS_TOLERANSI = 40
sapaan_selesai = False
frame_count = 0
sudah_absen = False  # Flag untuk mencegah double-insert ke database

# TRACKING & SMOOTHING untuk deteksi stabil
from collections import defaultdict
apd_detection_history = defaultdict(int)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    nama_terdeteksi = "Tidak Dikenal"

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=FACE_TOLERANCE)
        nama_terdeteksi = "Tidak Dikenal"
        warna_kotak = (0, 0, 255)

        if True in matches:
            first_match_index = matches.index(True)
            nama_terdeteksi = known_face_names[first_match_index]
            warna_kotak = (0, 255, 0)

        cv2.rectangle(frame, (left, top), (right, bottom), warna_kotak, 2)
        cv2.rectangle(frame, (left, bottom - 35), (right, bottom), warna_kotak, cv2.FILLED)
        cv2.putText(frame, nama_terdeteksi, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)

    if nama_terdeteksi != "Tidak Dikenal":
        frame_hilang_wajah = 0 
        
        if nama_terdeteksi != last_detected_name:
            last_detected_name = nama_terdeteksi
            fase_interaksi = "SAPAAN"
            sapaan_selesai = False
            sudah_absen = False  # Reset flag absensi untuk orang baru
            apd_detection_history.clear()  # Reset history untuk orang baru

        # Dapatkan ID kelas YOLO berdasarkan nama APD yang wajib saja
        required_classes_indices = [k for k, v in model_yolo.names.items() if v in required_apd]
        
        # Deteksi APD (hanya deteksi yang ada di required_apd)
        results = model_yolo(frame, conf=YOLO_CONFIDENCE, iou=YOLO_IOU, verbose=False, classes=required_classes_indices)
        annotated_frame = results[0].plot()
        
        # Ambil semua deteksi APD yang dicek
        current_detections = {}
        for box in results[0].boxes:
            class_name = model_yolo.names[int(box.cls[0])]
            confidence = float(box.conf[0])
            if class_name in required_apd:
                if class_name not in current_detections or confidence > current_detections[class_name]:
                    current_detections[class_name] = confidence
        
        # Update history untuk setiap APD
        for apd in required_apd:
            if apd in current_detections:
                apd_detection_history[apd] = min(apd_detection_history[apd] + HISTORY_INCREMENT, MAX_HISTORY)
            else:
                apd_detection_history[apd] = max(apd_detection_history[apd] - HISTORY_DECAY, 0)
        
        # Tentukan APD yang terdeteksi stabil
        apd_kurang = [apd for apd in required_apd if apd_detection_history[apd] < HISTORY_THRESHOLD]
        semua_lengkap = len(apd_kurang) == 0

        status_teks = "MENGANALISA..."
        warna_teks = (0, 255, 255)

        if fase_interaksi == "SAPAAN":
            status_teks = "MENYAPA PEGAWAI..."
            if not is_speaking and not sapaan_selesai:
                play_audio(f"Halo {nama_terdeteksi}, memulai pengecekan A P D.")
                sapaan_selesai = True
                fase_interaksi = "TUNGGU_SAPAAN_SELESAI"
                
        elif fase_interaksi == "TUNGGU_SAPAAN_SELESAI":
            status_teks = "MENYAPA PEGAWAI..."
            if not is_speaking:
                fase_interaksi = "PENGECEKAN"
                print(f"[DEBUG] Lanjut ke PENGECEKAN untuk {nama_terdeteksi}")

        elif fase_interaksi == "PENGECEKAN":
            if semua_lengkap:
                status_teks = "APD LENGKAP"
                warna_teks = (0, 255, 0)
                if not is_speaking:
                    play_audio(f"Hai {nama_terdeteksi}, A P D lengkap. Terimakasih, silahkan masuk.")
                    fase_interaksi = "DITERIMA"
                    # Catat absensi ke database (APD lengkap)
                    if db and not sudah_absen:
                        try:
                            apd_ada = list(required_apd)
                            db.catat_absensi(
                                nama=nama_terdeteksi,
                                status_apd='lengkap',
                                apd_terdeteksi=apd_ada,
                                apd_kurang=[]
                            )
                            sudah_absen = True
                        except Exception as e:
                            print(f"[DB ERROR] Gagal catat absensi: {e}")
            else:
                apd_ada = [apd for apd in required_apd if apd not in apd_kurang]
                kurang_teks = format_kata(apd_kurang)
                warna_teks = (0, 0, 255)
                
                if len(apd_kurang) == len(required_apd):
                    # Semua APD tidak terdeteksi
                    status_teks = "APD TIDAK TERDETEKSI"
                    if not is_speaking:
                        play_audio(f"Hai {nama_terdeteksi}, tidak ada A P D yang terdeteksi. Silahkan lengkapi A P D anda terlebih dahulu.")
                        # Catat absensi ke database (APD tidak lengkap)
                        if db and not sudah_absen:
                            try:
                                db.catat_absensi(
                                    nama=nama_terdeteksi,
                                    status_apd='tidak_lengkap',
                                    apd_terdeteksi=[],
                                    apd_kurang=list(apd_kurang)
                                )
                                sudah_absen = True
                            except Exception as e:
                                print(f"[DB ERROR] Gagal catat absensi: {e}")
                elif len(apd_kurang) >= 2:
                    # 2 item kurang - sebutkan yg terdeteksi dan yg kurang
                    ada_teks = format_kata(apd_ada)
                    status_teks = f"APD KURANG {kurang_teks.upper()}"
                    if not is_speaking:
                        play_audio(f"Hai {nama_terdeteksi}, {ada_teks} terdeteksi, namun {kurang_teks} tidak terdeteksi. Silahkan lengkapi A P D anda.")
                        # Catat absensi ke database
                        if db and not sudah_absen:
                            try:
                                db.catat_absensi(
                                    nama=nama_terdeteksi,
                                    status_apd='tidak_lengkap',
                                    apd_terdeteksi=apd_ada,
                                    apd_kurang=list(apd_kurang)
                                )
                                sudah_absen = True
                            except Exception as e:
                                print(f"[DB ERROR] Gagal catat absensi: {e}")
                else:
                    # 1 item kurang
                    status_teks = f"APD KURANG {kurang_teks.upper()}"
                    if not is_speaking:
                        play_audio(f"Hai {nama_terdeteksi}, {kurang_teks} tidak terdeteksi. Silahkan lengkapi A P D anda.")
                        # Catat absensi ke database
                        if db and not sudah_absen:
                            try:
                                db.catat_absensi(
                                    nama=nama_terdeteksi,
                                    status_apd='tidak_lengkap',
                                    apd_terdeteksi=apd_ada,
                                    apd_kurang=list(apd_kurang)
                                )
                                sudah_absen = True
                            except Exception as e:
                                print(f"[DB ERROR] Gagal catat absensi: {e}")
                    
        elif fase_interaksi == "DITERIMA":
            status_teks = "AKSES DIBERIKAN"
            warna_teks = (0, 255, 0)
            if not semua_lengkap:
                fase_interaksi = "PENGECEKAN"

        cv2.putText(annotated_frame, f"Pegawai: {nama_terdeteksi}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2)
        cv2.putText(annotated_frame, f"Status: {status_teks}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, warna_teks, 2)
        
        # Tampilkan status APD
        if semua_lengkap:
            apd_status = "APD: Lengkap"
        elif len(apd_kurang) == len(required_apd):
            apd_status = "APD: Tidak Terdeteksi"
        else:
            apd_status = f"APD: Kurang {format_kata(apd_kurang).capitalize()}"
        cv2.putText(annotated_frame, apd_status, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if semua_lengkap else (0, 0, 255), 2)

    else:
        annotated_frame = frame
        frame_hilang_wajah += 1
        
        if frame_hilang_wajah > BATAS_TOLERANSI:
            last_detected_name = "Tidak Dikenal"
            fase_interaksi = "MENUNGGU"
            sapaan_selesai = False  # Reset flag
            sudah_absen = False    # Reset flag absensi
            cv2.putText(annotated_frame, "Menunggu Pegawai...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        else:
            cv2.putText(annotated_frame, f"Pegawai: {last_detected_name} (Tracking...)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    current_stream_frame = annotated_frame.copy()

    # --- PPE STATE SHARING (untuk RFID access control) ---
    if nama_terdeteksi != "Tidak Dikenal":
        try:
            ppe_file = PPE_STATUS_FILE
            try:
                with open(ppe_file, 'r') as f:
                    ppe_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                ppe_data = {}

            apd_ada_list = [apd for apd in required_apd if apd_detection_history[apd] >= HISTORY_THRESHOLD]
            apd_kurang_list = [apd for apd in required_apd if apd_detection_history[apd] < HISTORY_THRESHOLD]
            ppe_data[nama_terdeteksi] = {
                'status': 'lengkap' if len(apd_kurang_list) == 0 else 'tidak_lengkap',
                'apd_terdeteksi': apd_ada_list,
                'apd_kurang': apd_kurang_list,
                'timestamp': time.time()
            }
            with open(ppe_file, 'w') as f:
                json.dump(ppe_data, f)
        except Exception:
            pass  # Non-critical, don't break main loop

    cv2.imshow("Simandiri - Sistem Gerbang Cerdas", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("\n Sistem ditutup. Terima kasih!")