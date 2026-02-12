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
import threading

# --- R2 AYARLARI ---
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

# Global değişken
comfy_process = None

def log_reader(proc, prefix):
    """ComfyUI'nin iç sesini (stdout) RunPod loglarına aktarır."""
    for line in iter(proc.stdout.readline, ''):
        print(f"[{prefix}] {line.strip()}", flush=True)

def upload_to_r2(file_path, file_name):
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        return "R2_CONFIG_MISSING"
    
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT_URL,
                      aws_access_key_id=R2_ACCESS_KEY,
                      aws_secret_access_key=R2_SECRET_KEY)
    try:
        unique_name = f"{int(time.time())}_{file_name}"
        s3.upload_file(file_path, BUCKET_NAME, unique_name)
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{unique_name}"
    except Exception as e:
        return f"Upload Failed: {str(e)}"

def check_server(url):
    """Sunucu ayakta mı kontrol eder."""
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except:
        return False

def start_comfyui():
    """ComfyUI'yi başlatır ve hazır olana kadar bekler."""
    global comfy_process
    SERVER_URL = "http://127.0.0.1:8188"
    
    if check_server(SERVER_URL):
        print("✅ ComfyUI zaten çalışıyor.")
        return True

    print("--- ComfyUI Başlatılıyor (Flux Modu) ---")
    
    # ComfyUI'yi başlat ve logları yakala
    comfy_process = subprocess.Popen(
        ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--preview-method", "auto"],
        cwd="/ComfyUI",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Logları okumak için ayrı thread (Bloklamasın diye)
    t = threading.Thread(target=log_reader, args=(comfy_process, "ComfyUI"))
    t.daemon = True
    t.start()

    # Bekleme Döngüsü (Maksimum 300 Saniye - 5 Dakika)
    # Flux modeli ilk açılışta VRAM'e yüklenirken uzun sürer.
    print("Sunucunun açılması bekleniyor (Bu işlem 2-3 dakika sürebilir)...")
    
    for i in range(300):
        if comfy_process.poll() is not None:
            print(f"!!! HATA: ComfyUI {i}. saniyede ÇÖKTÜ (Kod: {comfy_process.returncode}) !!!")
            return False

        if check_server(SERVER_URL):
            print(f"✅ ComfyUI {i}. saniyede HAZIR OLDU!")
            return True
        
        if i % 10 == 0:
            print(f"Bekleniyor... {i}/300sn")
        time.sleep(1)
    
    return False

def handler(job):
    job_input = job['input']
    SERVER_URL = "http://127.0.0.1:8188"
    
    # 1. ComfyUI'yi Kontrol Et / Başlat
    if not start_comfyui():
        return {"status": "failed", "error": "ComfyUI başlatılamadı veya çöktü. Loglara bakın."}

    # 2. Workflow Yükle
    workflow_path = "workflow.json"
    if not os.path.exists(workflow_path):
        # Belki Docker /ComfyUI içine kopyalamıştır
        workflow_path = "/ComfyUI/workflow.json"
        
    if not os.path.exists(workflow_path):
        return {"error": f"workflow.json bulunamadı! Yol: {os.getcwd()}"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # 3. Parametreleri İşle
    # Prompt
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    # Seed
    seed = job_input.get("seed", int(time.time() * 1000))
    workflow["3"]["inputs"]["seed"] = seed

    # LoRA Bypass Mantığı
    # Eğer inputta "use_lora": false gelirse veya LoRA dosyası yoksa
    if job_input.get("use_lora", False) == False:
        print("ℹ️ LoRA devre dışı bırakılıyor (Bypass)...")
        # KSampler (3) -> Checkpoint (4)
        workflow["3"]["inputs"]["model"] = ["4", 0]
        # Positive Prompt (6) -> Checkpoint (4)
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        # Negative Prompt (7) -> Checkpoint (4)
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 4. İsteği Gönder
    p = {"prompt": workflow}
    try:
        response = requests.post(f"{SERVER_URL}/prompt", json=p)
        resp_data = response.json()
        print(f"🚀 İşlem ComfyUI'ye iletildi. Prompt ID: {resp_data.get('prompt_id')}")
    except Exception as e:
        return {"status": "failed", "error": f"API Hatası: {str(e)}"}

    # 5. Sonucu Bekle (Dosya takibi)
    output_dir = "/ComfyUI/output"
    start_time = time.time()
    render_timeout = 300 # 5 dakika render süresi tanı
    
    while time.time() - start_time < render_timeout:
        # Klasördeki dosyaları kontrol et
        try:
            files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
            if files:
                latest_file = max(files, key=os.path.getmtime)
                # Yeni dosya mı?
                if os.path.getmtime(latest_file) > start_time:
                    print(f"🎉 Resim bulundu: {latest_file}")
                    # Dosya yazımı bitsin diye ufak bekleme
                    time.sleep(1)
                    r2_url = upload_to_r2(latest_file, os.path.basename(latest_file))
                    return {"status": "success", "image_url": r2_url, "seed": seed}
        except Exception as e:
            print(f"Dosya okuma hatası: {e}")
            
        time.sleep(1)

    return {"status": "timeout", "error": "Resim üretimi zaman aşımına uğradı."}

runpod.serverless.start({"handler": handler})