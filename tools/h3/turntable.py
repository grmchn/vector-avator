"""MiniMax H3 FL2VA turntable through the ComfyUI API (first and last frame = the same front
image, the character turns once in place). Optional step: an angle reference for the parts.

Only the HTTP API is used (upload the image, queue the workflow, download the video), so ComfyUI
may run on another machine. The model file names are those of the ComfyUI MiniMax H3 example
workflow; change them with the options if yours differ.

usage: python tools/h3/turntable.py <front.png> <prompt.txt> <out.mp4>
         [--seconds 8] [--size 640] [--seed 1] [--steps 20] [--server http://127.0.0.1:8188]"""
import argparse
import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def frames_for(seconds):
    n = max(5, round(seconds * 24))
    return n + (5 - n % 17) % 17


def call(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def upload(server, path):
    """POST /upload/image (multipart) and return the stored file name."""
    boundary = uuid.uuid4().hex
    name = f"turntable_{uuid.uuid4().hex[:8]}{Path(path).suffix}"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode() + Path(path).read_bytes() + \
           f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{server}/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["name"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image"); ap.add_argument("prompt"); ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=8); ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--clip", default="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")
    ap.add_argument("--unet", default="MiniMax/minimax_h3_fl2va_pruned_bf16.safetensors")
    ap.add_argument("--vae", default="minimax_h3_video_vae_fp16.safetensors")
    ap.add_argument("--audio-vae", default="minimax_h3_audio_vae_fp32.safetensors")
    a = ap.parse_args()
    name = upload(a.server, a.image)
    g = {
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": a.clip, "type": "minimax", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": a.vae}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": a.audio_vae}},
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": a.unet, "weight_dtype": "default"}},
        "img": {"class_type": "LoadImage", "inputs": {"image": name}},
        "cond": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["clip", 0], "vae": ["vae", 0], "prompt": Path(a.prompt).read_text(encoding="utf-8"),
                 "width": a.size, "height": a.size, "length": frames_for(a.seconds), "first_frame": ["img", 0], "last_frame": ["img", 0]}},
        "guider": {"class_type": "BasicGuider", "inputs": {"model": ["unet", 0], "conditioning": ["cond", 0]}},
        "sched": {"class_type": "BasicScheduler", "inputs": {"model": ["unet", 0], "scheduler": "simple", "steps": a.steps, "denoise": 1.0}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": a.seed}},
        "sample": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0], "sigmas": ["sched", 0], "latent_image": ["cond", 1]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}},
        "adec": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["sample", 0], "vae": ["avae", 0]}},
        "video": {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "audio": ["adec", 0], "fps": 24.0, "bit_depth": 8}},
        "save": {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": "vector-avator/turntable", "format": "auto", "format.codec": "auto"}},
    }
    pid = call(f"{a.server}/prompt", {"prompt": g, "client_id": "vector-avator"})["prompt_id"]
    t0 = time.time()
    while True:
        h = call(f"{a.server}/history/{pid}")
        if pid in h and h[pid].get("status", {}).get("completed") is not None:
            break
        time.sleep(5)
    st = h[pid]["status"]
    if st.get("status_str") != "success":
        raise SystemExit(f"failed: {st}")
    files = [f for node in h[pid]["outputs"].values() for k in ("images", "videos", "gifs") for f in node.get(k, [])]
    if not files:
        raise SystemExit("no output file in the ComfyUI history")
    f = files[0]
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{a.server}/view?{q}") as r:
        Path(a.out).write_bytes(r.read())
    print(f"OUTPUT {a.out}")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
