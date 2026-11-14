"""
SIMANDIRI - SISTEM GERBANG CERDAS v2.0
========================================
Alur Kerja:
  1. Kamera aktif terus (stream ke dashboard) - state: STANDBY
  2. Pegawai tap RFID → ESP32 kirim UID via MQTT → server cari nama pegawai
  3. State beralih ke MENCARI_WAJAH - kamera cari wajah pegawai yg tap
     - Wajah orang lain → peringatan suara
     - Timeout 10 detik → reset ke STANDBY
  4. Wajah cocok → state PENGECEKAN_APD - cek helm
  5. APD lengkap  → state DITERIMA  → kirim MQTT UNLOCK → TFT Diterima
     APD kurang   → state DITOLAK   → kirim MQTT LOCK   → TFT Ditolak
  6. Jeda 2 detik → suara selesai → kembali STANDBY

Komponen:
  - RFID-RC522 + Nextion TFT + Solenoid Door Lock (dikendalikan ESP32 via MQTT)
  - YOLOv8 (deteksi APD: Helm)
  - face_recognition (identifikasi pegawai)
  - paho-mqtt (komunikasi dengan ESP32)
"""

import cv2
import os
import json
import threading
import time
from collections import defaultdict

import face_recognition
from ultralytics import YOLO
from gtts import gTTS
import pygame
import paho.mqtt.client as mqtt

from flask import Flask, Response
from database import DatabaseManager
from config import (
    GATE_REQUIRED_APD, YOLO_MODEL_PATH, GATE_CAMERA_INDEX,
    CAMERA_WIDTH, CAMERA_HEIGHT, FACE_DATASET_PATH,
    MAX_PHOTOS_PER_PERSON, FACE_TOLERANCE, YOLO_CONFIDENCE, YOLO_IOU,
    HISTORY_THRESHOLD, HISTORY_INCREMENT, HISTORY_DECAY, MAX_HISTORY,
    PPE_STATUS_FILE, RFID_TRIGGER_FILE,
    MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_CLIENT_ID,
    MQTT_TOPIC_RFID_TAP, MQTT_TOPIC_GATE_LOCK,
    MQTT_TOPIC_NEXTION_PAGE, MQTT_TOPIC_NEXTION_NAME,
    NEXTION_PAGE_STANDBY, NEXTION_PAGE_VERIFIKASI,
    NEXTION_PAGE_DITERIMA, NEXTION_PAGE_DITOLAK,
    RFID_FACE_TIMEOUT, RFID_FINISH_DELAY, DOOR_UNLOCK_DURATION
)

# ============================================================
#  WEB STREAM (Flask MJPEG untuk dashboard)
# ============================================================

stream_app = Flask(__name__)
current_stream_frame = None

def generate_frames():
    global current_stream_frame
    while True:
        if current_stream_frame is not None:
            ret, buffer = cv2.imencode('.jpg', current_stream_frame,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if ret:
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.04)

@stream_app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

def run_stream_app():
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    stream_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)

threading.Thread(target=run_stream_app, daemon=True).start()

# ============================================================
#  INISIALISASI
# ============================================================

pygame.mixer.init()

print("=" * 70)
print("  SIMANDIRI - SISTEM GERBANG CERDAS v2.0")
print("  RFID + Face Recognition + APD Check + Nextion TFT")
print("=" * 70)

print("\n Memuat Model YOLOv8...")
model_yolo = YOLO(YOLO_MODEL_PATH)

print(" Menghubungkan ke Database MySQL...")
try:
    db = DatabaseManager()
except Exception as e:
    print(f" Gagal koneksi database: {e}")
    db = None

# ============================================================
#  AUDIO
# ============================================================

is_speaking = False
audio_lock = threading.Lock()

def play_audio(teks, filename="suara_gerbang.mp3"):
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
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f" [AUDIO] Gagal memutar suara: {e}")
        finally:
            is_speaking = False

    threading.Thread(target=proses_suara, daemon=True).start()

def format_kata(daftar_kata):
    if not daftar_kata:
        return ""
    if len(daftar_kata) == 1:
        return daftar_kata[0]
    if len(daftar_kata) == 2:
        return f"{daftar_kata[0]} dan {daftar_kata[1]}"
    return ", ".join(daftar_kata[:-1]) + f", dan {daftar_kata[-1]}"

# ============================================================
#  STATE MACHINE GERBANG
# ============================================================

# State: STANDBY | MENCARI_WAJAH | PENGECEKAN_APD | DITERIMA | DITOLAK
gate_state     = "STANDBY"
rfid_nama      = None          # Nama pegawai yg tap RFID
rfid_uid_last  = None          # UID kartu yg tap
rfid_tap_time  = None          # Waktu tap RFID
finish_time    = None          # Waktu masuk state selesai (DITERIMA/DITOLAK)
wrong_face_warned = False      # Sudah beri peringatan wajah salah?
apd_detection_history = defaultdict(int)
sudah_absen    = False
apd_hasil      = {}            # Hasil APD terakhir untuk Nextion
state_lock     = threading.Lock()

def set_gate_state(new_state):
    global gate_state
    with state_lock:
        gate_state = new_state
    print(f"[GATE] State → {new_state}")

def get_gate_state():
    with state_lock:
        return gate_state

# ============================================================
#  MQTT CLIENT
# ============================================================

try:
    from paho.mqtt.enums import CallbackAPIVersion
    mqtt_client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
except ImportError:
    # Fallback untuk paho-mqtt versi lama
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f" [MQTT] Terhubung ke broker {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        client.subscribe(MQTT_TOPIC_RFID_TAP)
        print(f" [MQTT] Subscribe ke: {MQTT_TOPIC_RFID_TAP}")
    else:
        print(f" [MQTT] Gagal connect, kode: {reason_code}")

def on_mqtt_message(client, userdata, msg):
    """Callback saat ESP32 mengirim tap RFID."""
    global rfid_nama, rfid_uid_last, rfid_tap_time
    global wrong_face_warned, sudah_absen, apd_detection_history

    topic = msg.topic
    payload = msg.payload.decode('utf-8').strip()

    if topic == MQTT_TOPIC_RFID_TAP:
        # Hanya proses jika sedang STANDBY
        if get_gate_state() != "STANDBY":
            print(f" [MQTT] Tap RFID diterima ({payload}) tapi sistem sedang sibuk ({get_gate_state()})")
            return

        try:
            data = json.loads(payload)
            rfid_uid = data.get('rfid_uid', '').strip().upper()
        except (json.JSONDecodeError, AttributeError):
            rfid_uid = payload.strip().upper()

        print(f" [MQTT] RFID Tap: {rfid_uid}")

        # Cari pegawai berdasarkan UID
        if db:
            pegawai = db.get_pegawai_by_rfid(rfid_uid)
        else:
            pegawai = None

        if not pegawai:
            print(f" [RFID] UID {rfid_uid} tidak terdaftar!")
            play_audio("Kartu tidak terdaftar. Silakan hubungi admin.")
            mqtt_publish_nextion(NEXTION_PAGE_DITOLAK)
            time.sleep(2)
            mqtt_publish_nextion(NEXTION_PAGE_STANDBY)
            return

        # Simpan nama pegawai yg tap
        rfid_nama      = pegawai['nama']
        rfid_uid_last  = rfid_uid
        rfid_tap_time  = time.time()
        wrong_face_warned = False
        sudah_absen    = False
        apd_detection_history.clear()

        print(f" [RFID] Pegawai: {rfid_nama} — Mulai mencari wajah...")
        play_audio(f"Halo {rfid_nama}, silakan tatap kamera untuk pengecekan A P D.")
        mqtt_publish_nextion(NEXTION_PAGE_VERIFIKASI, rfid_nama)
        set_gate_state("MENCARI_WAJAH")


def mqtt_publish_nextion(page_name, nama=None):
    """Kirim perintah ke ESP32 untuk ganti halaman Nextion."""
    mqtt_client.publish(MQTT_TOPIC_NEXTION_PAGE, page_name)
    if nama:
        mqtt_client.publish(MQTT_TOPIC_NEXTION_NAME, nama)
    print(f" [MQTT] Nextion → {page_name}" + (f" ({nama})" if nama else ""))

def mqtt_lock_door(unlock=False):
    """Kirim perintah kunci/buka pintu ke ESP32."""
    cmd = "UNLOCK" if unlock else "LOCK"
    mqtt_client.publish(MQTT_TOPIC_GATE_LOCK, cmd)
    print(f" [MQTT] Door Lock → {cmd}")

def run_mqtt():
    """Thread MQTT - berjalan di background."""
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_message = on_mqtt_message
    try:
        mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        mqtt_client.loop_forever()
    except Exception as e:
        print(f" [MQTT] Gagal terhubung ke broker: {e}")
        print("   Pastikan Mosquitto broker berjalan di laptop ini!")
        print(f"   Install: https://mosquitto.org/download/")

threading.Thread(target=run_mqtt, daemon=True).start()

# ============================================================
#  MUAT DATABASE WAJAH
# ============================================================

print(" Memuat Database Wajah...")
known_face_encodings = []
known_face_names     = []

for nama_orang in os.listdir(FACE_DATASET_PATH):
    path_orang = os.path.join(FACE_DATASET_PATH, nama_orang)
    if not os.path.isdir(path_orang):
        continue
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
            if encodings:
                known_face_encodings.append(encodings[0])
                known_face_names.append(nama_orang.capitalize())
                foto_count += 1
        except Exception:
            pass

print(f" Database: {len(known_face_encodings)} wajah dari {len(set(known_face_names))} pegawai")

required_apd = GATE_REQUIRED_APD
required_classes_indices = []  # Akan diisi saat model sudah dimuat

print(" Sistem Siap! Membuka Kamera...")
print("=" * 70)

# ============================================================
#  BUKA KAMERA
# ============================================================

cap = cv2.VideoCapture(GATE_CAMERA_INDEX)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

if not cap.isOpened():
    print(f" GAGAL membuka kamera index {GATE_CAMERA_INDEX}!")
    print("   Coba ubah GATE_CAMERA_INDEX di config.py (0 = bawaan, 1 = eksternal)")
    exit(1)

# Cache class indices YOLO agar tidak hitung ulang tiap frame
required_classes_indices = [k for k, v in model_yolo.names.items() if v in required_apd]
print(f" YOLO akan mendeteksi kelas: {[model_yolo.names[i] for i in required_classes_indices]}")

# Kirim Nextion ke Standby saat pertama kali start
time.sleep(2)  # Tunggu MQTT terhubung
mqtt_publish_nextion(NEXTION_PAGE_STANDBY)

# ============================================================
#  MAIN LOOP KAMERA
# ============================================================

frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    current_state = get_gate_state()

    # Resize kecil untuk face recognition (lebih cepat)
    small_frame    = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small      = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    display_frame  = frame.copy()
    nama_frame     = "Tidak Dikenal"

    # --- Deteksi & gambar semua wajah ---
    for (top, right, bottom, left), enc in zip(face_locations, face_encodings):
        top *= 2; right *= 2; bottom *= 2; left *= 2

        matches  = face_recognition.compare_faces(known_face_encodings, enc, tolerance=FACE_TOLERANCE)
        nama_det = "Tidak Dikenal"
        warna    = (0, 0, 255)

        if True in matches:
            nama_det = known_face_names[matches.index(True)]
            warna    = (0, 255, 0)

        cv2.rectangle(display_frame, (left, top), (right, bottom), warna, 2)
        cv2.rectangle(display_frame, (left, bottom - 32), (right, bottom), warna, cv2.FILLED)
        cv2.putText(display_frame, nama_det, (left + 6, bottom - 8),
                    cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

        if nama_det != "Tidak Dikenal":
            nama_frame = nama_det

    # ============================================================
    #  STATE: STANDBY
    # ============================================================
    if current_state == "STANDBY":
        cv2.putText(display_frame, "STANDBY - Tap Kartu RFID Anda",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    # ============================================================
    #  STATE: MENCARI_WAJAH
    # ============================================================
    elif current_state == "MENCARI_WAJAH":
        elapsed = time.time() - rfid_tap_time
        sisa    = max(0, RFID_FACE_TIMEOUT - elapsed)

        cv2.putText(display_frame, f"Mencari wajah: {rfid_nama}  ({sisa:.0f}s)",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        if nama_frame.lower() == str(rfid_nama).lower():
            # Wajah cocok — mulai pengecekan APD
            print(f" [WAJAH] {rfid_nama} terdeteksi! Mulai cek APD...")
            set_gate_state("PENGECEKAN_APD")
            wrong_face_warned = False

        elif nama_frame != "Tidak Dikenal" and not wrong_face_warned:
            # Wajah orang lain
            wrong_face_warned = True
            print(f" [WAJAH] Wajah salah ({nama_frame}) — berikan peringatan")
            play_audio("Hai, tolong melakukan absensi dengan benar sesuai aturan.")

        elif elapsed >= RFID_FACE_TIMEOUT:
            # Timeout
            print(f" [TIMEOUT] Waktu habis, {rfid_nama} tidak ditemukan")
            play_audio("Waktu sudah habis, silahkan yang selanjutnya.")
            mqtt_publish_nextion(NEXTION_PAGE_STANDBY)
            rfid_nama = None
            set_gate_state("STANDBY")

    # ============================================================
    #  STATE: PENGECEKAN_APD
    # ============================================================
    elif current_state == "PENGECEKAN_APD":
        # Jalankan YOLO hanya saat wajah target masih ada
        if nama_frame.lower() == str(rfid_nama).lower():

            results        = model_yolo(frame, conf=YOLO_CONFIDENCE, iou=YOLO_IOU,
                                         verbose=False, classes=required_classes_indices)
            display_frame  = results[0].plot()

            # Overlay wajah kembali (setelah YOLO menimpa frame)
            for (top, right, bottom, left), enc in zip(face_locations, face_encodings):
                top *= 2; right *= 2; bottom *= 2; left *= 2
                matches  = face_recognition.compare_faces(known_face_encodings, enc, tolerance=FACE_TOLERANCE)
                nama_det = "Tidak Dikenal"
                warna    = (0, 0, 255)
                if True in matches:
                    nama_det = known_face_names[matches.index(True)]
                    warna    = (0, 255, 0)
                cv2.rectangle(display_frame, (left, top), (right, bottom), warna, 2)
                cv2.rectangle(display_frame, (left, bottom - 32), (right, bottom), warna, cv2.FILLED)
                cv2.putText(display_frame, nama_det, (left + 6, bottom - 8),
                            cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

            # Update history APD
            current_detections = {}
            for box in results[0].boxes:
                cname = model_yolo.names[int(box.cls[0])]
                conf  = float(box.conf[0])
                if cname in required_apd:
                    if cname not in current_detections or conf > current_detections[cname]:
                        current_detections[cname] = conf

            for apd in required_apd:
                if apd in current_detections:
                    apd_detection_history[apd] = min(apd_detection_history[apd] + HISTORY_INCREMENT, MAX_HISTORY)
                else:
                    apd_detection_history[apd] = max(apd_detection_history[apd] - HISTORY_DECAY, 0)

            apd_kurang  = [a for a in required_apd if apd_detection_history[a] < HISTORY_THRESHOLD]
            semua_ok    = len(apd_kurang) == 0
            apd_ada     = [a for a in required_apd if a not in apd_kurang]

            # Overlay status
            status_txt  = "MENGANALISA APD..." if not semua_ok else "APD LENGKAP ✓"
            status_warna = (0, 255, 0) if semua_ok else (0, 165, 255)
            cv2.putText(display_frame, f"{rfid_nama} | {status_txt}",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_warna, 2)

            if semua_ok and not is_speaking and not sudah_absen:
                # ✅ APD Lengkap
                sudah_absen = True
                if db:
                    try:
                        db.catat_absensi(nama=rfid_nama, status_apd='lengkap',
                                         apd_terdeteksi=apd_ada, apd_kurang=[])
                    except Exception as e:
                        print(f" [DB] Gagal catat absensi: {e}")

                play_audio(f"Hai {rfid_nama}, A P D lengkap. Terima kasih, silahkan masuk.")
                mqtt_publish_nextion(NEXTION_PAGE_DITERIMA)
                mqtt_lock_door(unlock=True)
                finish_time = time.time()
                set_gate_state("DITERIMA")

            elif not semua_ok and len(apd_kurang) > 0 and not is_speaking and not sudah_absen:
                # ❌ APD Kurang — beri peringatan sekali lalu pindah ke DITOLAK
                sudah_absen = True
                kurang_teks = format_kata(apd_kurang)
                if db:
                    try:
                        db.catat_absensi(nama=rfid_nama, status_apd='tidak_lengkap',
                                         apd_terdeteksi=apd_ada, apd_kurang=apd_kurang)
                    except Exception as e:
                        print(f" [DB] Gagal catat absensi: {e}")

                play_audio(f"Hai {rfid_nama}, {kurang_teks} tidak terdeteksi. Akses ditolak, lengkapi A P D Anda.")
                mqtt_publish_nextion(NEXTION_PAGE_DITOLAK)
                mqtt_lock_door(unlock=False)
                finish_time = time.time()
                set_gate_state("DITOLAK")

        else:
            # Wajah target hilang dari frame
            cv2.putText(display_frame, f"Menunggu {rfid_nama}...",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    # ============================================================
    #  STATE: DITERIMA / DITOLAK (jeda 2 detik lalu kembali)
    # ============================================================
    elif current_state in ("DITERIMA", "DITOLAK"):
        warna_overlay = (0, 200, 0) if current_state == "DITERIMA" else (0, 0, 200)
        label = "✓ AKSES DIBERIKAN" if current_state == "DITERIMA" else "✗ AKSES DITOLAK"
        cv2.putText(display_frame, label,
                    (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, warna_overlay, 3)

        elapsed_finish = time.time() - finish_time
        if elapsed_finish >= RFID_FINISH_DELAY and not is_speaking:
            play_audio("Pengecekan selesai, silahkan orang selanjutnya.")
            
            # Buat thread untuk menunggu suara selesai baru kunci pintu
            state_saat_ini = current_state
            def tunggu_suara_selesai():
                time.sleep(1) # Beri waktu thread audio untuk mulai
                while is_speaking:
                    time.sleep(0.5)
                
                # Suara sudah selesai, kunci pintu
                if state_saat_ini == "DITERIMA":
                    mqtt_lock_door(unlock=False)
                
                # Kembalikan Nextion ke Standby
                mqtt_publish_nextion(NEXTION_PAGE_STANDBY)

            threading.Thread(target=tunggu_suara_selesai, daemon=True).start()
            
            rfid_nama  = None
            sudah_absen = False
            apd_detection_history.clear()
            set_gate_state("STANDBY")

    # Tulis state saat ini di sudut kiri bawah frame
    h, w = display_frame.shape[:2]
    cv2.rectangle(display_frame, (0, h - 30), (300, h), (0, 0, 0), cv2.FILLED)
    cv2.putText(display_frame, f"State: {current_state}",
                (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    # Update stream frame
    current_stream_frame = display_frame.copy()

    # --- PPE STATE SHARING untuk web API ---
    if rfid_nama and current_state in ("PENGECEKAN_APD", "DITERIMA", "DITOLAK"):
        try:
            apd_ada_l  = [a for a in required_apd if apd_detection_history.get(a, 0) >= HISTORY_THRESHOLD]
            apd_kurang_l = [a for a in required_apd if apd_detection_history.get(a, 0) < HISTORY_THRESHOLD]
            ppe_entry  = {
                'status': 'lengkap' if not apd_kurang_l else 'tidak_lengkap',
                'apd_terdeteksi': apd_ada_l,
                'apd_kurang': apd_kurang_l,
                'timestamp': time.time()
            }
            try:
                with open(PPE_STATUS_FILE, 'r') as f:
                    ppe_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                ppe_data = {}
            ppe_data[rfid_nama] = ppe_entry
            with open(PPE_STATUS_FILE, 'w') as f:
                json.dump(ppe_data, f)
        except Exception:
            pass

    cv2.imshow("Simandiri - Sistem Gerbang Cerdas v2.0", display_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()