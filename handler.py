import runpod
import json
import os
import time
import requests
import subprocess
import boto3
import urllib.request
import urllib.error
import sys

# --- R2 AYARLARI ---
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

def upload_to_r2(file_path, file_name):
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        return "R2_CONFIG_MISSING"
    
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT_URL,
                      aws_access_key_id=R2_ACCESS_KEY,
                      aws_secret_access_key=R2_SECRET_KEY)
    try:
        unique_name = f"{int(time.time())}_{file_name}"
        s3.upload_file(file_path, BUCKET_NAME, unique_name)
        # Public URL yapısı (Eğer farklıysa burayı düzenle)
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{unique_name}"
    except Exception as e:
        return f"Upload Failed: {str(e)}"

def check_server(url):
    """Sunucunun cevap verip vermediğini kontrol eder"""
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except:
        return False

def handler(job):
    job_input = job['input']
    SERVER_URL = "http://127.0.0.1:8188"
    
    # 1. COMFYUI BAŞLATMA (GÜÇLENDİRİLMİŞ BEKLEME)
    if not check_server(SERVER_URL):
        print("--- ComfyUI Başlatılıyor (Flux Modu) ---")
        # --preview-method auto parametresi hızı artırır
        subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--preview-method", "auto"], cwd="/ComfyUI")
        
        # Bekleme Döngüsü (Maksimum 180 Saniye - 3 Dakika)
        server_ready = False
        print("Sunucunun açılması bekleniyor (Bu işlem 1-2 dakika sürebilir)...")
        
        for i in range(180):
            if check_server(SERVER_URL):
                print(f"✅ ComfyUI {i}. saniyede hazır oldu!")
                server_ready = True
                break
            
            # Her 5 saniyede bir log at ki yaşadığını bilelim
            if i % 5 == 0:
                print(f"Bekleniyor... {i}/180sn")
            time.sleep(1)
        
        if not server_ready:
            return {"status": "failed", "error": "TIMEOUT: ComfyUI 180 saniyede açılamadı. Logları kontrol edin."}
    
    # 2. WORKFLOW YÜKLEME
    workflow_path = "/ComfyUI/workflow.json"
    if not os.path.exists(workflow_path):
        return {"error": "workflow.json bulunamadı!"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # 3. PARAMETRELERİ GÜNCELLE
    # Prompt
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    # Seed
    seed = job_input.get("seed", int(time.time() * 1000))
    workflow["3"]["inputs"]["seed"] = seed

    # LoRA Devre Dışı Bırakma (Testler için)
    if job_input.get("use_lora", False) == False:
        # KSampler -> Checkpoint
        workflow["3"]["inputs"]["model"] = ["4", 0]
        # Text Encoders -> Checkpoint
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 4. İSTEĞİ GÖNDER
    p = {"prompt": workflow}
    data = json.dumps(p).encode('utf-8')
    
    try:
        req = urllib.request.Request(f"{SERVER_URL}/prompt", data=data)
        response = urllib.request.urlopen(req)
        # Cevabı oku ama işlem asenkron devam edecek
        resp_data = json.loads(response.read())
        print(f"İşlem ComfyUI kuyruğuna alındı: {resp_data}")
    except urllib.error.URLError as e:
        return {"status": "failed", "error": f"ComfyUI Bağlantı Hatası: {str(e)}"}

    # 5. SONUCU BEKLE (POLLING)
    # Çıktı klasörünü izle
    output_dir = "/ComfyUI/output"
    start_time = time.time()
    render_timeout = 300 # Render için 5 dakika tanı (Flux ağır olabilir)
    
    print("Resim üretimi bekleniyor...")
    while time.time() - start_time < render_timeout:
        # Klasördeki dosyaları kontrol et
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if files:
            # En son değiştirilen dosyayı bul
            latest_file = max(files, key=os.path.getmtime)
            
            # Dosya script başladıktan sonra mı oluştu? (Eski dosyaları yollamayalım)
            if os.path.getmtime(latest_file) > start_time:
                print(f"🎉 Resim bulundu: {latest_file}")
                
                # Biraz bekle ki dosya yazımı tamamen bitsin
                time.sleep(1)
                
                r2_url = upload_to_r2(latest_file, os.path.basename(latest_file))
                return {
                    "status": "success", 
                    "image_url": r2_url,
                    "seed": seed
                }
        
        time.sleep(1)

    return {"status": "timeout", "error": "Resim üretimi zaman aşımına uğradı (Render)."}

runpod.serverless.start({"handler": handler})
