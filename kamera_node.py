import cv2
import time
import requests
import json
import threading
from flask import Flask, Response

# ====================================================================
# KONFIGURASI CLIENT (NODE KAMERA)
# ====================================================================

# Alamat Server Pusat (Ganti dengan IP Laptop Utama yang menjalankan app.py)
SERVER_URL = "http://192.168.1.8:5000"

# Identitas Kamera ini
CAMERA_ID = "SIMANDIRI-CAM-03"
CAMERA_NAME = "Kamera Produksi 1"

# Kamera (0 untuk webcam bawaan, 1/2 untuk eksternal)
CAMERA_INDEX = 1

# (Opsional) Jika menggunakan YOLO di node ini:
# from ultralytics import YOLO
# model = YOLO("best.pt")

app = Flask(__name__)

def generate_frames():
    """Generator untuk streaming MJPEG ke Dashboard Pusat"""
    cap = cv2.VideoCapture(CAMERA_INDEX)
    
    # Atur resolusi
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_api_call = time.time()

    while True:
        success, frame = cap.read()
        if not success:
            break
            
        # ==========================================================
        # 1. PROSES DETEKSI YOLO & WAJAH DI SINI (Contoh Sederhana)
        # ==========================================================
        # results = model(frame)
        # ... logika deteksi APD ...
        
        # Simulasi variabel dari hasil deteksi:
        ada_pelanggaran = False 
        nama_pegawai = "Budi"
        apd_dilepas = ["Helm"]

        # ==========================================================
        # 2. KIRIM DATA KE SERVER PUSAT (Throttled, misal tiap 5 detik)
        # ==========================================================
        current_time = time.time()
        if ada_pelanggaran and (current_time - last_api_call > 5):
            payload = {
                "nama_pegawai": nama_pegawai,
                "kamera": CAMERA_NAME,
                "apd_dilepas": apd_dilepas,
                # Tambahkan parameter lain jika API server mendukung
            }
            try:
                # Mengirim POST ke API Server Pusat
                # requests.post(f"{SERVER_URL}/api/pelanggaran", json=payload, timeout=2)
                pass
            except Exception as e:
                print(f"Gagal kirim ke server pusat: {e}")
            last_api_call = current_time

        # ==========================================================
        # 3. STREAM VIDEO (MJPEG)
        # ==========================================================
        # Tampilkan teks nama kamera di frame
        cv2.putText(frame, CAMERA_NAME, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.route('/video_feed')
def video_feed():
    """Endpoint yang akan diakses oleh tag <img> di dashboard pusat"""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return f"<h1>{CAMERA_NAME} Node is running!</h1><p>Stream URL: /video_feed</p>"

if __name__ == '__main__':
    print(f"[*] Menjalankan Node {CAMERA_NAME}...")
    print("[*] Untuk melihat stream, buka http://localhost:5001/video_feed")
    # Jalankan di port 5001 agar tidak bentrok jika dites di laptop yang sama
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
