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

def log_reader(proc, prefix):
    """Subprocess çıktılarını ana loga yönlendirir"""
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
    try:
        response = requests.get(url, timeout=1)
        return response.status_code == 200
    except:
        return False

def handler(job):
    job_input = job['input']
    SERVER_URL = "http://127.0.0.1:8188"
    
    # 1. COMFYUI BAŞLATMA (LOGLARI GÖSTEREN MOD)
    if not check_server(SERVER_URL):
        print("--- ComfyUI Başlatılıyor (DEBUG MODU) ---")
        
        # stdout ve stderr'i PIPE ile yakalıyoruz
        process = subprocess.Popen(
            ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188", "--preview-method", "auto"],
            cwd="/ComfyUI",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Logları okumak için ayrı bir thread başlat (Bloklamasın diye)
        t = threading.Thread(target=log_reader, args=(process, "ComfyUI"))
        t.daemon = True
        t.start()
        
        # Bekleme Döngüsü (180 Saniye)
        server_ready = False
        print("Sunucunun açılması bekleniyor...")
        
        for i in range(180):
            # ÖNCE: Süreç öldü mü kontrol et?
            if process.poll() is not None:
                print(f"!!! KRİTİK HATA: ComfyUI {i}. saniyede ÇÖKTÜ (Exit Code: {process.returncode}) !!!")
                return {"status": "failed", "error": "ComfyUI başlatılamadı, süreç sonlandı. Logları inceleyin."}

            if check_server(SERVER_URL):
                print(f"✅ ComfyUI {i}. saniyede hazır!")
                server_ready = True
                break
            
            if i % 10 == 0:
                print(f"Bekleniyor... {i}/180sn")
            time.sleep(1)
        
        if not server_ready:
            return {"status": "failed", "error": "TIMEOUT: 180 saniyede açılamadı."}

    # 2. WORKFLOW YÜKLEME
    workflow_path = "/ComfyUI/workflow.json"
    if not os.path.exists(workflow_path):
        return {"error": "workflow.json bulunamadı!"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # 3. PARAMETRELER
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    workflow["3"]["inputs"]["seed"] = job_input.get("seed", int(time.time() * 1000))

    if job_input.get("use_lora", False) == False:
        workflow["3"]["inputs"]["model"] = ["4", 0]
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 4. İSTEK GÖNDERME
    p = {"prompt": workflow}
    data = json.dumps(p).encode('utf-8')
    
    try:
        req = urllib.request.Request(f"{SERVER_URL}/prompt", data=data)
        response = urllib.request.urlopen(req)
        print("Prompt gönderildi.")
    except Exception as e:
        return {"status": "failed", "error": f"Bağlantı Hatası: {str(e)}"}

    # 5. BEKLEME (Render)
    output_dir = "/ComfyUI/output"
    start_time = time.time()
    
    while time.time() - start_time < 300:
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        if files:
            latest = max(files, key=os.path.getmtime)
            if os.path.getmtime(latest) > start_time:
                print(f"🎉 Resim bulundu: {latest}")
                time.sleep(1)
                r2_url = upload_to_r2(latest, os.path.basename(latest))
                return {"status": "success", "image_url": r2_url}
        time.sleep(1)

    return {"status": "timeout", "error": "Render süresi doldu."}

runpod.serverless.start({"handler": handler})
