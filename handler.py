import sys, traceback, threading

def _hook(et, ev, tb):
    sys.stdout.write("STARTUP_CRASH: " + repr(ev) + "\n")
    traceback.print_exception(et, ev, tb, file=sys.stdout)
    sys.stdout.flush()

sys.excepthook = _hook

def _thread_hook(args):
    sys.stdout.write("THREAD_CRASH: " + repr(args.exc_value) + "\n")
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=sys.stdout)
    sys.stdout.flush()

threading.excepthook = _thread_hook

import os
import uuid
import tempfile
import subprocess
import time
import requests
import runpod
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SAFE = 150
TEAL = (22, 214, 198, 255)
TEAL_SOFT = (22, 214, 198, 90)
OBSIDIAN = (11, 11, 11)
GLASS = (11, 11, 11, 150)

FOOTER_TEXT = (
    "GLP BodyGuard is an educational self-tracking tool developed by "
    "R3 Integrated Health Plus LLC. It is not a medical device, does not "
    "diagnose or treat any condition, and does not provide medical advice."
)

BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _download(url, path):
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for c in r.iter_content(1 << 16):
                if c:
                    f.write(c)


def wrap(draw, text, fnt, maxw):
    out = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        for w in words:
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=fnt) <= maxw:
                cur = t
            else:
                if cur:
                    out.append(cur)
                cur = w
        out.append(cur)
    return out


def build_overlay(duration_s, patient_name, drug_name, dose_str, week_label, out_path):
    img = Image.new("RGBA", (W, H), (*OBSIDIAN, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    draw.rectangle([(0, 0), (8, H)], fill=TEAL)

    draw.rectangle([(0, 0), (W, 160)], fill=GLASS)
    try:
        fnt_h = ImageFont.truetype(BOLD, 48)
    except Exception:
        fnt_h = ImageFont.load_default()
    draw.text((SAFE, 30), "GLP BodyGuard", font=fnt_h, fill=TEAL)
    try:
        fnt_sub = ImageFont.truetype(REG, 28)
    except Exception:
        fnt_sub = ImageFont.load_default()
    draw.text((SAFE, 95), f"{drug_name}  |  {dose_str}  |  {week_label}", font=fnt_sub, fill=(200, 200, 200, 255))

    try:
        fnt_name = ImageFont.truetype(BOLD, 38)
    except Exception:
        fnt_name = ImageFont.load_default()
    draw.text((SAFE, 190), patient_name, font=fnt_name, fill=(240, 240, 240, 255))

    draw.rectangle([(0, H - 140), (W, H)], fill=GLASS)
    try:
        fnt_foot = ImageFont.truetype(REG, 22)
    except Exception:
        fnt_foot = ImageFont.load_default()
    lines = wrap(draw, FOOTER_TEXT, fnt_foot, W - 2 * SAFE)
    y = H - 130
    for line in lines:
        draw.text((SAFE, y), line, font=fnt_foot, fill=(160, 160, 160, 255))
        y += 30

    img.save(out_path, "PNG")


def upload_to_supabase(local_path):
    base   = os.environ.get("SUPABASE_URL", "")
    token  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.environ.get("SUPABASE_BUCKET", "renders")
    key    = f"glp_prod_{int(time.time())}.mp4"
    with open(local_path, "rb") as f:
        r = requests.post(
            f"{base}/storage/v1/object/{bucket}/{key}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "x-upsert": "true",
            },
            data=f.read(),
            timeout=120,
        )
    r.raise_for_status()
    return f"{base}/storage/v1/object/public/{bucket}/{key}"


def handler(job):
    inp = job.get("input", {})

    video_url  = inp.get("video_url", "")
    audio_url  = inp.get("audio_url", "")
    patient    = inp.get("patient_name", "Patient")
    drug       = inp.get("drug_name", "Semaglutide")
    dose       = inp.get("dose_str", "0.25 mg")
    week       = inp.get("week_label", "Week 1")

    with tempfile.TemporaryDirectory() as tmp:
        vid_path     = os.path.join(tmp, "input_video.mp4")
        aud_path     = os.path.join(tmp, "input_audio.mp3")
        overlay_path = os.path.join(tmp, "overlay.png")
        final_path   = os.path.join(tmp, "final.mp4")

        _download(video_url, vid_path)
        _download(audio_url, aud_path)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", vid_path],
            capture_output=True, text=True, timeout=30
        )
        duration = float(probe.stdout.strip() or "60")

        build_overlay(duration, patient, drug, dose, week, overlay_path)

        cmd = [
            "ffmpeg", "-y",
            "-i", vid_path,
            "-i", aud_path,
            "-i", overlay_path,
            "-filter_complex",
            "[0:v][2:v]overlay=0:0[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            final_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return {"error": "ffmpeg failed", "stderr": result.stderr[-2000:]}

        video_url_out = upload_to_supabase(final_path)

    return {"video_url": video_url_out}


runpod.serverless.start({"handler": handler})
