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
    
    # 1. COMFYUI BAŞLATMA VE BEKLEME (GÜÇLENDİRİLMİŞ)
    if not check_server(SERVER_URL):
        print("--- ComfyUI Başlatılıyor... ---")
        # Logları görmek için stdout/stderr yönlendirmesi yapılabilir
        subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"], cwd="/ComfyUI")
        
        # Bekleme Döngüsü (Maksimum 60 Saniye)
        server_ready = False
        for i in range(60):
            if check_server(SERVER_URL):
                print(f"ComfyUI {i}. saniyede hazır oldu!")
                server_ready = True
                break
            time.sleep(1)
            print(f"Server bekleniyor... {i}/60")
        
        if not server_ready:
            print("HATA: ComfyUI 60 saniye içinde açılamadı.")
            # Log dosyası varsa içeriğini okumak burada iyi olurdu
            return {"status": "failed", "error": "Server Timeout: ComfyUI başlatılamadı."}
    
    # 2. WORKFLOW HAZIRLIĞI
    workflow_path = "/ComfyUI/workflow.json"
    if not os.path.exists(workflow_path):
        return {"error": "workflow.json bulunamadı!"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # Parametreleri Güncelle
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    workflow["3"]["inputs"]["seed"] = job_input.get("seed", int(time.time() * 1000))

    # LoRA Bypass (Eğer 'use_lora': false ise)
    if job_input.get("use_lora", False) == False:
        workflow["3"]["inputs"]["model"] = ["4", 0]
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 3. İSTEĞİ GÖNDER
    p = {"prompt": workflow}
    data = json.dumps(p).encode('utf-8')
    
    try:
        req = urllib.request.Request(f"{SERVER_URL}/prompt", data=data)
        response = urllib.request.urlopen(req)
        print("Prompt ComfyUI'ye iletildi.")
    except urllib.error.URLError as e:
        return {"status": "failed", "error": f"Bağlantı Hatası: {str(e)}"}

    # 4. SONUCU BEKLE (POLLING)
    output_dir = "/ComfyUI/output"
    start_time = time.time()
    timeout = 120 # 2 dakika render süresi tanı
    
    while time.time() - start_time < timeout:
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        
        if files:
            latest_file = max(files, key=os.path.getmtime)
            # Dosya script başladıktan sonra mı oluştu?
            if os.path.getmtime(latest_file) > start_time:
                print(f"Resim üretildi: {latest_file}")
                r2_url = upload_to_r2(latest_file, os.path.basename(latest_file))
                return {"status": "success", "image_url": r2_url}
        
        time.sleep(1)

    return {"status": "timeout", "error": "Resim üretimi zaman aşımına uğradı."}

runpod.serverless.start({"handler": handler})
