import runpod
import subprocess
import time
import json
import os
import requests
import boto3
import sys
import uuid

# --- R2 AYARLARI ---
R2_ACCESS_KEY   = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY   = os.environ.get("R2_SECRET_KEY")
BUCKET_NAME     = os.environ.get("BUCKET_NAME")
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL")

COMFY_URL   = "http://127.0.0.1:8188"
OUTPUT_DIR  = "/ComfyUI/output"
comfy_process = None

def log(msg):
    print(f"[Handler] {msg}", flush=True)

def start_comfyui():
    global comfy_process
    log("ComfyUI başlatılıyor...")
    try:
        comfy_process = subprocess.Popen(
            ["python", "main.py", "--listen", "127.0.0.1", "--port", "8188"],
            cwd="/ComfyUI",
            stdout=subprocess.PIPE,   # Hata ayıklama için PIPE yaptık
            stderr=subprocess.PIPE
        )
    except Exception as e:
        log(f"ComfyUI başlatılamadı: {e}")
        sys.exit(1)

def check_server_ready(timeout=120):
    log("ComfyUI hazır olana kadar bekleniyor...")
    for i in range(timeout):
        try:
            r = requests.get(f"{COMFY_URL}/system_stats", timeout=2)
            if r.status_code == 200:
                log("ComfyUI hazır!")
                return True
        except Exception:
            pass
        if i % 10 == 0:
            log(f"  ... {i}s geçti, bekleniyor.")
        time.sleep(1)
    log("HATA: ComfyUI {timeout} saniyede açılmadı.")
    return False

def upload_to_r2(file_path, file_name):
    if not R2_ACCESS_KEY:
        log("UYARI: R2 anahtarları eksik, upload atlandı.")
        return "R2_KEYS_MISSING"
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY,
            aws_secret_access_key=R2_SECRET_KEY
        )
        object_name = f"{int(time.time())}_{file_name}"
        s3.upload_file(file_path, BUCKET_NAME, object_name)
        return f"{R2_ENDPOINT_URL}/{BUCKET_NAME}/{object_name}"
    except Exception as e:
        return f"Upload Error: {str(e)}"

def queue_prompt(workflow):
    """Prompt'u kuyruğa gönder, prompt_id döndür."""
    # Her job için benzersiz client_id — karışıklığı önler
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    response = requests.post(f"{COMFY_URL}/prompt", json=payload, timeout=10)
    response.raise_for_status()
    prompt_id = response.json()["prompt_id"]
    log(f"Prompt kuyruğa alındı. ID: {prompt_id}")
    return prompt_id

def wait_for_completion(prompt_id, timeout=300):
    """
    /history endpoint'ini poll ederek prompt'un bitmesini bekle.
    Tamamlanınca çıktı dosya yollarını döndür.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=5)
            if r.status_code == 200:
                history = r.json()
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    # outputs içinde images olan ilk node'u bul
                    for node_id, node_output in outputs.items():
                        if "images" in node_output:
                            images = node_output["images"]
                            log(f"Resim(ler) hazır: {images}")
                            return images  # [{"filename": "...", "subfolder": "", "type": "output"}, ...]
        except Exception as e:
            log(f"History kontrol hatası: {e}")
        time.sleep(2)
    return None

def handler(job):
    job_input = job.get("input", {})

    # Workflow yükle
    if not os.path.exists("workflow.json"):
        return {"error": "workflow.json bulunamadı"}

    with open("workflow.json", "r") as f:
        workflow = json.load(f)

    # Prompt güncelle
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]

    workflow["3"]["inputs"]["seed"] = job_input.get("seed", int(time.time() * 1000) % (2**32))

    # LoRA bypass
    if not job_input.get("use_lora", False):
        workflow["3"]["inputs"]["model"] = ["4", 0]
        workflow["6"]["inputs"]["clip"]  = ["4", 1]
        workflow["7"]["inputs"]["clip"]  = ["4", 1]

    # Kuyruğa gönder
    try:
        prompt_id = queue_prompt(workflow)
    except Exception as e:
        return {"error": f"Prompt gönderilemedi: {e}"}

    # Tamamlanmasını bekle
    images = wait_for_completion(prompt_id, timeout=300)
    if not images:
        return {"status": "timeout", "prompt_id": prompt_id}

    # İlk resmi R2'ye yükle
    results = []
    for img in images:
        subfolder  = img.get("subfolder", "")
        filename   = img["filename"]
        file_path  = os.path.join(OUTPUT_DIR, subfolder, filename) if subfolder else os.path.join(OUTPUT_DIR, filename)

        if os.path.exists(file_path):
            url = upload_to_r2(file_path, filename)
            results.append(url)
            log(f"Yüklendi: {url}")
        else:
            log(f"UYARI: Dosya bulunamadı: {file_path}")
            results.append(f"FILE_NOT_FOUND: {file_path}")

    return {"status": "success", "images": results}


# --- BAŞLANGIÇ ---
start_comfyui()

if check_server_ready(timeout=120):
    runpod.serverless.start({"handler": handler})
else:
    log("ComfyUI açılamadı. Çıkılıyor.")
    sys.exit(1)