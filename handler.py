import runpod
import json
import os
import time
import base64
import requests
import boto3
import urllib.request
import subprocess

# --- R2 AYARLARI (Env Vars'dan Okur) ---
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

def upload_to_r2(file_path, file_name):
    """Resmi R2 Bucket'a yükler ve link döner."""
    if not R2_ACCESS_KEY or not R2_SECRET_KEY:
        print("UYARI: R2 bilgileri eksik, yükleme yapılmadı.")
        return "R2_CONFIG_MISSING"
    
    # Boto3 client oluştur
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT_URL,
                      aws_access_key_id=R2_ACCESS_KEY,
                      aws_secret_access_key=R2_SECRET_KEY)
    try:
        # Dosya ismine tarih ekleyerek benzersiz yapalım
        unique_name = f"{int(time.time())}_{file_name}"
        s3.upload_file(file_path, BUCKET_NAME, unique_name)
        
        # Public erişim linki (Eğer bucket public ise)
        # R2 Endpoint URL genellikle 'https://<accountid>.r2.cloudflarestorage.com' şeklindedir.
        # Public erişim için 'https://pub-<hash>.r2.dev' domaini kullanılır (Cloudflare panelinden bakılmalı).
        # Şimdilik standart URL döndürelim:
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{unique_name}"
    except Exception as e:
        print(f"R2 Upload Hatası: {e}")
        return f"Upload Failed: {str(e)}"

def check_server(url):
    """ComfyUI sunucusu açık mı kontrol eder."""
    try:
        response = requests.get(url)
        return response.status_code == 200
    except:
        return False

def handler(job):
    job_input = job['input']
    
    # 1. ComfyUI BAŞLATMA
    # Sunucu zaten açıksa tekrar açma (Cold start vs Warm start)
    if not check_server("http://127.0.0.1:8188"):
        print("ComfyUI başlatılıyor...")
        # Arka planda çalıştır
        subprocess.Popen(["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"], cwd="/ComfyUI")
        
        # Açılmasını bekle (Max 30 saniye)
        for _ in range(30):
            if check_server("http://127.0.0.1:8188"):
                print("ComfyUI hazır!")
                break
            time.sleep(1)
    
    # 2. WORKFLOW HAZIRLIĞI
    workflow_path = "/ComfyUI/workflow.json"
    if not os.path.exists(workflow_path):
        return {"error": "workflow.json dosyası bulunamadı!"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # --- PARAMETRELERİ GÜNCELLE ---
    
    # Prompt (Metin)
    if "prompt" in job_input:
        # 6 ID'li node CLIPTextEncode (Positive) varsayıyoruz
        workflow["6"]["inputs"]["text"] = job_input["prompt"]

    # Seed (Rastgelelik) - Eğer gönderilmezse rastgele üret
    seed = job_input.get("seed", int(time.time() * 1000))
    workflow["3"]["inputs"]["seed"] = seed

    # LoRA Kontrolü (Henüz indirmedik, o yüzden 'false' gelirse kapat)
    use_lora = job_input.get("use_lora", False)
    if not use_lora:
        print("LoRA devre dışı bırakılıyor...")
        # KSampler (3) -> Doğrudan Checkpoint (4)'e bağla
        workflow["3"]["inputs"]["model"] = ["4", 0]
        # CLIP Text (6 ve 7) -> Doğrudan Checkpoint (4)'e bağla
        workflow["6"]["inputs"]["clip"] = ["4", 1]
        workflow["7"]["inputs"]["clip"] = ["4", 1]

    # 3. İSTEĞİ GÖNDER (Queue Prompt)
    p = {"prompt": workflow}
    data = json.dumps(p).encode('utf-8')
    
    try:
        req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=data)
        response = urllib.request.urlopen(req)
        resp_data = json.loads(response.read())
        prompt_id = resp_data['prompt_id']
        print(f"İşlem başladı. Prompt ID: {prompt_id}")
    except Exception as e:
        return {"error": f"ComfyUI bağlantı hatası: {str(e)}"}

    # 4. SONUCU BEKLE (Basit Yöntem)
    # Çıktı klasörünü temizleyelim ki eski resim gelmesin
    output_dir = "/ComfyUI/output"
    
    # 30-60 saniye boyunca yeni dosya bekle
    # (Not: Profesyonel sistemde WebSocket dinlenir, bu 'polling' yöntemidir)
    timeout = 120 # 2 dakika limit
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Klasördeki dosyaları tarihe göre sırala
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        if not files:
            time.sleep(1)
            continue
            
        latest_file = max(files, key=os.path.getmtime)
        
        # Eğer dosya işlemden sonra oluştuysa (veya son 5 saniyede)
        if os.path.getmtime(latest_file) > start_time:
            print(f"Yeni dosya bulundu: {latest_file}")
            
            # R2'ye yükle
            file_name = os.path.basename(latest_file)
            r2_url = upload_to_r2(latest_file, file_name)
            
            return {
                "status": "success",
                "image_url": r2_url,
                "seed": seed
            }
        
        time.sleep(1)

    return {"status": "timeout", "error": "Resim üretimi zaman aşımına uğradı."}

runpod.serverless.start({"handler": handler})
