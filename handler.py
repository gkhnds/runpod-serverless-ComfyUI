import runpod
import json
import os
import time
import base64
import requests
import boto3
from io import BytesIO
import urllib.request
import urllib.parse
import traceback

# --- R2 CONFIG ---
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

def upload_to_r2(file_path, file_name):
    if not R2_ACCESS_KEY:
        print("R2 Keys missing, skipping upload.")
        return "R2_NOT_CONFIGURED"
    
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT_URL,
                      aws_access_key_id=R2_ACCESS_KEY,
                      aws_secret_access_key=R2_SECRET_KEY)
    try:
        s3.upload_file(file_path, BUCKET_NAME, file_name)
        # Eğer custom domain varsa burayı güncelle, yoksa R2 public linki:
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{file_name}"
    except Exception as e:
        print(f"R2 Upload Error: {e}")
        return str(e)

def check_server(url):
    try:
        response = requests.get(url)
        return response.status_code == 200
    except:
        return False

def handler(job):
    job_input = job['input']
    
    # 1. ComfyUI Başlatma Kontrolü
    if not check_server("http://127.0.0.1:8188"):
        print("ComfyUI başlatılıyor...")
        import subprocess
        subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"], cwd="/ComfyUI")
        time.sleep(5) # Açılması için bekle
    
    # 2. Workflow Yükle
    workflow_path = "workflow.json"
    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # 3. Girdileri İşle (Prompt & Image)
    # Prompt Ayarı
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]
    
    # Resim Ayarı (Base64 gelirse)
    if "image_base64" in job_input:
        img_data = base64.b64decode(job_input["image_base64"])
        with open("/ComfyUI/input/input_image.png", "wb") as f:
            f.write(img_data)
        workflow["11"]["inputs"]["image"] = "input_image.png"
    
    # LoRA Bypass (Eğer LoRA indirmedikse hata vermesin diye)
    # Eğer inputta "use_lora": false gelirse LoRA'yı atla
    if job_input.get("use_lora", False) == False:
         workflow["3"]["inputs"]["model"] = ["4", 0] # KSampler'ı direkt Checkpoint'e bağla
         workflow["6"]["inputs"]["clip"] = ["4", 1]  # Prompt'u direkt Checkpoint'e bağla
         workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 4. İsteği ComfyUI'ye Gönder
    p = {"prompt": workflow}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=data)
    response = urllib.request.urlopen(req)
    
    # 5. Sonucu Bekle (Basit wait loop)
    # Gerçek sistemde WebSocket dinlenmeli ama şimdilik dosya takibi yapıyoruz
    print("Resim üretiliyor...")
    time.sleep(1) # İşlemin başlaması için
    
    # Output klasörünü izle
    output_dir = "/ComfyUI/output"
    # En son dosyayı bulma mantığı eklenebilir.
    # Şimdilik 20 saniye sabit bekleme (Test için)
    time.sleep(15) 
    
    # En son dosyayı bul
    files = os.listdir(output_dir)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(output_dir, x)))
    last_file = files[-1] if files else None

    if last_file:
        file_path = os.path.join(output_dir, last_file)
        r2_url = upload_to_r2(file_path, last_file)
        return {"status": "success", "image_url": r2_url}
    else:
        return {"status": "failed", "error": "Resim üretilemedi"}

runpod.serverless.start({"handler": handler})