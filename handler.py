import runpod
import json
import os
import random

def handler(job):
    job_input = job['input']
    
    # Workflow dosyasını artık projenin içinden okuyoruz
    # Docker kopyaladığı için /ComfyUI/workflow.json yolunda olacak
    workflow_path = "workflow.json" 

    if not os.path.exists(workflow_path):
        return {"error": f"Workflow dosyası GitHub'dan kopyalanmamış! Yol: {os.getcwd()}/{workflow_path}"}

    with open(workflow_path, 'r') as f:
        workflow = json.load(f)

    # --- BASIT TEST AYARLARI ---
    # Kullanıcıdan gelen prompt varsa onu workflow'a işle (Node 6 = Positive Prompt)
    if "prompt" in job_input:
        workflow["6"]["inputs"]["text"] = job_input["prompt"]

    # Rastgele bir seed üret (Her resim farklı olsun)
    workflow["3"]["inputs"]["seed"] = random.randint(1, 1000000000000)

    # BURASI COMFYUI API'SINE GÖNDERİM KISMI
    # Şimdilik sadece workflow'u okuduğumuzu kanıtlıyoruz.
    # Gerçek resim üretimi için buraya websocket bağlantı kodları gelecek.
    
    return {
        "status": "success", 
        "message": "Workflow başarıyla okundu ve prompt güncellendi!",
        "debug_prompt": workflow["6"]["inputs"]["text"],
        "debug_seed": workflow["3"]["inputs"]["seed"]
    }

runpod.serverless.start({"handler": handler})