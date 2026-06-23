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
import requests
import runpod
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SAFE = 150
TEAL = (22, 214, 198, 255)
TEAL_SOFT = (22, 214, 198, 90)
OBSIDIAN = (11, 11, 11)
GLASS = (11, 11, 11, 150)
FOOTER = (203, 209, 214, 255)
WHITE = (245, 245, 245, 255)
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


def fit(draw, text, path, start, maxw, max_lines, min_size=40):
          size = start
    while size >= min_size:
                  fnt = ImageFont.truetype(path, size)
                  lines = wrap(draw, text, fnt, maxw)
                  if len(lines) <= max_lines:
                                    return fnt, lines
                                size -= 4
    fnt = ImageFont.truetype(path, min_size)
    return fnt, wrap(draw, text, fnt, maxw)


def _corner(d, x, y, dx, dy, ln=46, th=4):
          d.line([(x, y), (x + dx * ln, y)], fill=TEAL, width=th)
    d.line([(x, y), (x, y + dy * ln)], fill=TEAL, width=th)


def build_overlay(hook, caption, path):
          img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    m = 40
    _corner(d, m, m, 1, 1)
    _corner(d, W - m, m, -1, 1)
    _corner(d, m, H - m, 1, -1)
    _corner(d, W - m, H - m, -1, -1)

    d.rounded_rectangle([54, 52, 98, 96], radius=12, fill=TEAL)
    d.rounded_rectangle([62, 60, 90, 88], radius=8, outline=OBSIDIAN, width=3)
    d.text((112, 56), "GLP BODYGUARD", font=ImageFont.truetype(BOLD, 34), fill=TEAL)
    d.line([(54, SAFE), (W - 54, SAFE)], fill=TEAL_SOFT, width=1)

    if hook:
                  f_hook, hlines = fit(d, hook, BOLD, 96, 960, 2)
        lh = f_hook.size * 1.12
        y = 620 - (len(hlines) * lh) / 2
        for ln in hlines:
                          tw = d.textlength(ln, font=f_hook)
                          d.text(((W - tw) / 2, y), ln, font=f_hook, fill=TEAL)
                          y += lh

    if caption:
                  f_cap, clines = fit(d, caption, REG, 50, 900, 3)
        lh = f_cap.size * 1.25
        y = 1500 - (len(clines) * lh) / 2
        for ln in clines:
                          tw = d.textlength(ln, font=f_cap)
                          d.text(((W - tw) / 2, y), ln, font=f_cap, fill=WHITE)
                          y += lh

    bar_top = 1762
    d.rounded_rectangle([40, bar_top, 1040, 1900], radius=22, fill=GLASS)
    d.line([(62, bar_top + 2), (1018, bar_top + 2)], fill=TEAL, width=3)
    d.line([(W // 2 - 45, bar_top + 26), (W // 2 + 45, bar_top + 26)], fill=TEAL, width=3)

    f_foot = ImageFont.truetype(REG, 21)
    y = bar_top + 44
    for ln in wrap(d, FOOTER_TEXT, f_foot, 920):
                  tw = d.textlength(ln, font=f_foot)
        d.text(((W - tw) / 2, y), ln, font=f_foot, fill=FOOTER)
        y += 28

    img.save(path)


def upload_to_supabase(local_path, name):
          base   = os.environ.get("SUPABASE_URL", "").rstrip("/")
    token  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = os.environ.get("SUPABASE_BUCKET", "renders")
    if not base or not token:
                  raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
    with open(local_path, "rb") as f:
                  r = requests.post(
                      f"{base}/storage/v1/object/{bucket}/{name}",
                      headers={
                                            "Authorization": f"Bearer {token}",
                                            "Content-Type": "video/mp4",
                                            "x-upsert": "true",
                      },
                      data=f.read(),
                      timeout=300,
    )
    r.raise_for_status()
    return f"{base}/storage/v1/object/public/{bucket}/{name}"


def handler(event):
          inp   = event.get("input", {}) or {}
    veo   = inp.get("veo_url")
    voice = inp.get("voice_url")
    if not veo or not voice:
                  return {"error": "veo_url and voice_url are required"}

    hook    = inp.get("hook", "")
    caption = inp.get("caption", "")
    name    = inp.get("output_name") or f"glp_{uuid.uuid4().hex[:10]}.mp4"

    work = tempfile.mkdtemp()
    vp = os.path.join(work, "veo.mp4")
    ap = os.path.join(work, "voice.mp3")
    op = os.path.join(work, "overlay.png")
    fp = os.path.join(work, name)

    try:
                  _download(veo, vp)
        _download(voice, ap)
except Exception as e:
        return {"error": f"download failed: {e}"}

    try:
                  build_overlay(hook, caption, op)
except Exception as e:
        return {"error": f"overlay render failed: {e}"}

    cmd = [
                  "ffmpeg", "-y",
                  "-stream_loop", "-1", "-i", vp,
                  "-loop", "1", "-i", op,
                  "-i", ap,
                  "-filter_complex",
                  "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                  "crop=1080:1920,setsar=1[bg];[1:v]scale=1080:1920[ov];"
                  "[bg][ov]overlay=0:0[v]",
                  "-map", "[v]", "-map", "2:a",
                  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-shortest", fp,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
                  return {"error": "ffmpeg failed", "stderr": proc.stderr[-2500:]}

    size = os.path.getsize(fp)

    try:
                  video_url = upload_to_supabase(fp, name)
except Exception as e:
        return {"error": f"supabase upload failed: {e}"}

    return {"status": "ok", "output_name": name, "bytes": size, "video_url": video_url}


runpod.serverless.start({"handler": handler})
