import runpod
import subprocess
import time
import json
import os
import requests
import boto3
import sys

# --- R2 AYARLARI --
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

# Global değişken
comfy_process = None

def log(msg):
    print(f"[Handler] {msg}", flush=True)

def start_comfyui():
    global comfy_process
    log("ComfyUI başlatılıyor...")
    try:
        # ComfyUI'yi arka planda başlat
        comfy_process = subprocess.Popen(
            ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
            cwd="/ComfyUI",
            stdout=subprocess.DEVNULL, # Log kirliliğini önle (Test bitince açılabilir)
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        log(f"ComfyUI başlatılamadı: {e}")
        sys.exit(1)

def check_server_ready():
    for i in range(120): # 2 dakika bekle
        try:
            r = requests.get("http://127.0.0.1:8188", timeout=1)
            if r.status_code == 200:
                log("ComfyUI Hazır!")
                return True
        except:
            pass
        if i % 5 == 0:
            log("Server bekleniyor...")
        time.sleep(1)
    return False

def upload_to_r2(file_path, file_name):
    if not R2_ACCESS_KEY:
        return "R2_KEYS_MISSING"
    
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT_URL,
                      aws_access_key_id=R2_ACCESS_KEY,
                      aws_secret_access_key=R2_SECRET_KEY)
    try:
        object_name = f"{int(time.time())}_{file_name}"
        s3.upload_file(file_path, BUCKET_NAME, object_name)
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{object_name}"
    except Exception as e:
        return f"Upload Error: {str(e)}"

# Handler Başlangıcı
def handler(job):
    job_input = job['input']
    
    # Workflow yükle
    if not os.path.exists("workflow.json"):
        return {"error": "workflow.json bulunamadı"}
    
    with open("workflow.json", "r") as f:
        workflow = json.load(f)

    # Prompt güncelle
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    workflow["3"]["inputs"]["seed"] = job_input.get("seed", int(time.time()*1000))

    # LoRA Bypass (Hata almamak için şimdilik kapalı başlatılabilir
    if job_input.get("use_lora", False) == False:
        workflow["3"]["inputs"]["model"] = ["4", 0]
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # ComfyUI API'ye gönder
    try:
        p = {"prompt": workflow}
        response = requests.post("http://127.0.0.1:8188/prompt", json=p)
        log("Prompt gönderildi.")
    except Exception as e:
        return {"error": f"API Hatası: {e}"}

    # Çıktı bekleme (Basit dosya takibi)
    output_dir = "/ComfyUI/output"
    start_time = time.time()
    
    while time.time() - start_time < 300: # 5 dk timeout
        files = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))], key=os.path.getmtime)
        if files:
            last_file = files[-1]
            if os.path.getmtime(last_file) > start_time:
                log(f"Resim bulundu: {last_file}")
                url = upload_to_r2(last_file, os.path.basename(last_file))
                return {"status": "success", "image_url": url}
        time.sleep(1)

    return {"status": "timeout"}

# --- ANA MOTOR ---
# Script başladığında ComfyUI'yi ayağa kaldırıyoruz.
start_comfyui()

# Server hazır olana kadar RunPod handler'ı başlatmıyoruz.
# Böylece "Starting" ekranında takılıyorsa sorunun ComfyUI açılışında olduğunu anlarız.
if check_server_ready():
    runpod.serverless.start({"handler": handler})
else:
    log("ComfyUI açılamadı, Handler başlatılmıyor.")
    sys.exit(1)
