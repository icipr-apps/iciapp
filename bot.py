import os, json, subprocess, re, cloudinary, cloudinary.uploader, requests, time, sys

# ─── إعدادات ────────────────────────────────────────────────
COOKIES_FILE   = "/tmp/cookies.txt"
WEBHOOK_URL    = os.environ["WEBHOOK_URL"]
TARGET_W, TARGET_H = 1080, 1920

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

VIDEO_PUBLISHER = os.environ.get("VIDEO_PUBLISHER", "ALL").strip()
VIDEO_URL_INPUT = os.environ.get("VIDEO_URL", "").strip()
print(f"👤 {VIDEO_PUBLISHER}")


# ══════════════════════════════════════════════════════════════
#   خط Montserrat-Arabic
# ══════════════════════════════════════════════════════════════

def load_font(size):
    from PIL import ImageFont
    for path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Montserrat-Arabic-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size)
                print(f"  ✅ خط: {os.path.basename(path)} ({size}px)")
                return f
            except: continue
    return ImageFont.load_default()

def get_tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def wrap_text(draw, text, font, max_w):
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if get_tw(draw, test, font)[0] <= max_w:
            current.append(word)
        else:
            if current: lines.append(" ".join(current))
            current = [word]
    if current: lines.append(" ".join(current))
    return lines if lines else [text]


# ══════════════════════════════════════════════════════════════
#   رسم شريط العنوان (PNG شفاف)
# ══════════════════════════════════════════════════════════════

def render_title_overlay(title, color_hex, W, H):
    from PIL import Image, ImageDraw
    white    = (255, 255, 255, 255)
    hex_str  = color_hex.replace("0x","").replace("#","")
    title_bg = (int(hex_str[0:2],16), int(hex_str[2:4],16), int(hex_str[4:6],16), 217)

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if title:
        font_size = max(20, int(W * 0.042))   # خط أكبر
        font_t    = load_font(font_size)
        pad_h     = int(W * 0.05)
        pad_v     = int(H * 0.018)
        bar_w     = W - int(W * 0.25)         # عرض 75% — لا يحجب الشاشة كلها
        usable    = bar_w - 2 * pad_h

        lines  = wrap_text(draw, title, font_t, usable)
        line_h = int(font_size * 1.5)
        bar_h  = len(lines) * line_h + 2 * pad_v
        bar_x  = (W - bar_w) // 2
        bar_y  = H - bar_h - int(H * 0.22)    # مرفوع للأعلى بعيداً عن الفوتر

        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=title_bg)
        for i, line in enumerate(lines):
            lw, _ = get_tw(draw, line, font_t)
            tx = bar_x + (bar_w - lw) // 2
            ty = bar_y + pad_v + i * line_h
            draw.text((tx+2, ty+2), line, font=font_t, fill=(0,0,0,110))
            draw.text((tx,   ty),   line, font=font_t, fill=white)

    out = "/tmp/overlay_title.png"
    img.save(out, "PNG")
    print("✅ overlay_title.png")
    return out


# ══════════════════════════════════════════════════════════════
#   تطبيق PNG Frame الشفاف (إطار خاص بكل publisher)
# ══════════════════════════════════════════════════════════════

def apply_png_frame(main, frame_png, out, W, H):
    print("🖼️  PNG Frame...")
    fc = f"[1:v]scale={W}:{H}[frm];[0:v][frm]overlay=0:0[v]"
    for maps in [["-map","[v]","-map","0:a"], ["-map","[v]"]]:
        subprocess.run(
            ["ffmpeg", "-y", "-i", main, "-i", frame_png,
             "-filter_complex", fc,
             *maps, "-c:v","libx264","-c:a","copy","-preset","fast", out],
            capture_output=True, text=True, timeout=600
        )
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print("  ✅"); return True
        if os.path.exists(out): os.remove(out)
    print("  ❌"); return False


# ══════════════════════════════════════════════════════════════
#   شريط العنوان (fade-in ثم يختفي بعد 12 ثانية)
# ══════════════════════════════════════════════════════════════

def apply_title_overlay(main, title_png, out, dur):
    print("✍️  شريط العنوان (يختفي بعد 12s)...")
    loop_dur   = dur + 2
    show_start = 1.2
    fade_in    = 0.8
    title_hide = 12.0
    fade_out   = 0.6

    fc = (
        f"[1:v]format=yuva420p,"
        f"fade=t=in:st={show_start}:d={fade_in}:alpha=1,"
        f"fade=t=out:st={title_hide}:d={fade_out}:alpha=1[ttl];"
        f"[0:v][ttl]overlay=0:0[v]"
    )
    for maps in [["-map","[v]","-map","0:a"], ["-map","[v]"]]:
        subprocess.run(
            ["ffmpeg", "-y", "-i", main,
             "-loop", "1", "-t", str(loop_dur), "-i", title_png,
             "-filter_complex", fc,
             *maps, "-c:v","libx264","-c:a","copy","-preset","fast","-shortest", out],
            capture_output=True, text=True, timeout=600
        )
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print("  ✅"); return True
        if os.path.exists(out): os.remove(out)
    print("  ❌"); return False


# ══════════════════════════════════════════════════════════════
#   دوال مساعدة
# ══════════════════════════════════════════════════════════════

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def clean_title(raw):
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) >= 3: return " | ".join(parts[1:-1]).strip()
    elif len(parts) == 2: return parts[1].strip()
    return raw.strip()

def fetch_latest_from_page(page_url):
    """يجلب رابط وعنوان آخر Reel من صفحة Facebook مع محاولات متعددة."""
    print(f"🔍 جلب آخر فيديو من: {page_url}")

    has_cookies = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 50
    attempts = []

    if has_cookies:
        attempts.append({
            "label": "print+cookies",
            "cmd": ["yt-dlp", "--playlist-items", "1",
                    "--print", "%(webpage_url)s",
                    "--print", "%(title)s",
                    "--cookies", COOKIES_FILE,
                    "--no-warnings", page_url]
        })

    attempts.append({
        "label": "print-no-cookies",
        "cmd": ["yt-dlp", "--playlist-items", "1",
                "--print", "%(webpage_url)s",
                "--print", "%(title)s",
                "--no-warnings", page_url]
    })

    if has_cookies:
        attempts.append({
            "label": "geturl+cookies",
            "cmd": ["yt-dlp", "--playlist-items", "1",
                    "--get-url", "--get-title",
                    "--format", "best[ext=mp4]/best",
                    "--cookies", COOKIES_FILE,
                    "--no-warnings", page_url]
        })

    attempts.append({
        "label": "geturl-no-cookies",
        "cmd": ["yt-dlp", "--playlist-items", "1",
                "--get-url", "--get-title",
                "--format", "best[ext=mp4]/best",
                "--no-warnings", page_url]
    })

    if has_cookies:
        attempts.append({
            "label": "flat+cookies",
            "cmd": ["yt-dlp", "--flat-playlist", "--playlist-items", "1",
                    "--print", "url",
                    "--cookies", COOKIES_FILE,
                    "--no-warnings", page_url]
        })

    for att in attempts:
        print(f"  ⏳ {att['label']}...")
        try:
            r = subprocess.run(att["cmd"], capture_output=True, text=True, timeout=120)
            lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
            if r.returncode != 0:
                print(f"    ⚠️ exit={r.returncode}: {r.stderr.strip()[-120:]}")

            if len(lines) >= 2:
                url   = lines[0] if lines[0].startswith("http") else lines[1]
                title = clean_title(lines[1] if lines[0].startswith("http") else lines[0])
                if url.startswith("http"):
                    print(f"  ✅ {title[:70]}")
                    return url, title

            elif len(lines) == 1 and lines[0].startswith("http"):
                print(f"  ✅ (رابط فقط بدون عنوان)")
                return lines[0], "بدون عنوان"

        except subprocess.TimeoutExpired:
            print(f"    ⏰ timeout")
        except Exception as e:
            print(f"    ❌ {e}")

    print("  ❌ فشلت جميع المحاولات")
    return None, None

def download_video(url):
    out = "/tmp/main.mp4"
    has_cookies = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 50
    attempts = []

    if has_cookies:
        attempts.append(("cookies+mp4",
            ["yt-dlp", "-o", out, "--format", "best[ext=mp4]/best",
             "--cookies", COOKIES_FILE, "--no-warnings", "--no-playlist", url]))

    attempts.append(("direct+mp4",
        ["yt-dlp", "-o", out, "--format", "best[ext=mp4]/best",
         "--no-warnings", "--no-playlist", url]))

    attempts.append(("direct+best",
        ["yt-dlp", "-o", out, "--format", "best",
         "--no-warnings", "--no-playlist", url]))

    if "fbcdn" in url or url.endswith(".mp4"):
        attempts.append(("wget-direct", None))

    for label, cmd in attempts:
        print(f"📥 {label}...")
        try:
            if label == "wget-direct":
                subprocess.run(["wget", "-q", "-O", out, url], timeout=300)
            else:
                subprocess.run(cmd, timeout=300)
            if os.path.exists(out) and os.path.getsize(out) > 10000:
                print(f"  ✅ {os.path.getsize(out)//1024} KB"); return True
            if os.path.exists(out): os.remove(out)
        except subprocess.TimeoutExpired:
            print(f"  ⏰ timeout")
        except Exception as e:
            print(f"  ❌ {e}")

    print("❌ فشل التحميل"); return False

def get_video_info(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True
    )
    try:
        info = json.loads(r.stdout)
        vs   = next(s for s in info["streams"] if s["codec_type"] == "video")
        return int(vs["width"]), int(vs["height"]), float(info["format"].get("duration", 60))
    except:
        return 1080, 1920, 60

def scale_to_target(src, out, tw=1080, th=1920):
    print(f"📐 {tw}×{th}...")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src,
         "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅" if ok else f"  ❌\n{r.stderr[-200:]}"); return ok

def download_from_cloudinary(public_id, out, resource_type="video"):
    ext = "png" if resource_type == "image" else "mp4"
    url = (f"https://res.cloudinary.com/"
           f"{os.environ['CLOUDINARY_CLOUD_NAME']}/{resource_type}/upload/{public_id}.{ext}")
    subprocess.run(["wget", "-q", "-O", out, url], timeout=90)
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    if not ok: print(f"  ⚠️ فشل: {public_id}")
    return ok

def add_outro(main, outro, out, W, H):
    print("🎬 Outro...")
    r = subprocess.run(
        ["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",outro],
        capture_output=True, text=True
    )
    has_audio, outro_dur = False, 5
    try:
        info      = json.loads(r.stdout)
        has_audio = any(s["codec_type"]=="audio" for s in info["streams"])
        outro_dur = float(info.get("format",{}).get("duration",5))
    except: pass

    if has_audio:
        fc   = (f"[0:v]scale={W}:{H},setsar=1[v0];[1:v]scale={W}:{H},setsar=1[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map","[ov]","-map","[oa]"]
    else:
        fc   = (f"[0:v]scale={W}:{H},setsar=1[v0];[1:v]scale={W}:{H},setsar=1[v1];"
                f"aevalsrc=0:d={outro_dur}[sl];[v0][0:a][v1][sl]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map","[ov]","-map","[oa]"]

    subprocess.run(
        ["ffmpeg","-y","-i",main,"-i",outro,"-filter_complex",fc,
         *maps,"-c:v","libx264","-c:a","aac","-preset","fast",out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅"); return True

    with open("/tmp/concat.txt","w") as f:
        f.write(f"file '{main}'\nfile '{outro}'\n")
    subprocess.run(
        ["ffmpeg","-y","-f","concat","-safe","0","-i","/tmp/concat.txt",
         "-vf",f"scale={W}:{H},setsar=1","-c:v","libx264","-c:a","aac","-preset","fast",out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅ (concat)" if ok else "  ❌"); return ok

def upload_and_send(video_path, pub_name, title, source_url):
    """رفع الفيديو بالجودة الأصلية بدون ضغط — الحل الرئيسي لمشكلة الجودة"""
    mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"  📤 رفع بالجودة الأصلية — {mb:.1f}MB")

    safe      = re.sub(r"[^a-z0-9]", "_", pub_name.lower())
    public_id = f"tmp_{safe}"

    result = cloudinary.uploader.upload(
        video_path, resource_type="video",
        public_id=public_id, overwrite=True,
    )
    url = result["secure_url"]
    print(f"  ✅ رُفع: {url[:70]}")

    requests.post(WEBHOOK_URL, json={
        "video_url":  url,
        "title":      title,
        "publisher":  pub_name,
        "source_url": source_url,
    }, timeout=30)
    print(f"  📡 Webhook أُرسل → {pub_name}")

    # انتظر 60 ثانية ثم احذف من Cloudinary لتوفير المساحة
    time.sleep(20)
    try:
        cloudinary.uploader.destroy(public_id, resource_type="video")
        print(f"  🗑️  حُذف من Cloudinary")
    except Exception as e:
        print(f"  ⚠️ فشل الحذف: {e}")

    return url

def cleanup_pub(name):
    for f in [f"/tmp/frame_{name}.png", f"/tmp/framed_{name}.mp4",
              f"/tmp/titled_{name}.mp4", f"/tmp/outro_{name}.mp4",
              f"/tmp/final_{name}.mp4"]:
        if os.path.exists(f): os.remove(f)

def cleanup_global():
    for f in ["/tmp/main.mp4", "/tmp/main_scaled.mp4",
              "/tmp/overlay_title.png", "/tmp/concat.txt"]:
        if os.path.exists(f): os.remove(f)


# ══════════════════════════════════════════════════════════════
#   التنفيذ الرئيسي
# ══════════════════════════════════════════════════════════════

print("\n🤖 بدء المعالجة\n" + "═"*50)

config      = load_config()
all_pubs    = config["publishers"]
target_pubs = all_pubs if VIDEO_PUBLISHER.upper() == "ALL" else \
              ([p for p in all_pubs if p["name"] == VIDEO_PUBLISHER] or all_pubs)
sources     = config.get("sources", [])

print(f"📋 الصفحات: {[p['name'] for p in target_pubs]}")

# ─── دعم رابط مباشر من واجهة PHP ──────────────────────────
if VIDEO_URL_INPUT:
    print(f"🔗 رابط مباشر من الواجهة: {VIDEO_URL_INPUT[:80]}")
    video_url   = VIDEO_URL_INPUT
    video_title = os.environ.get("VIDEO_TITLE", "بدون عنوان").strip()
else:
    if not sources:
        print("❌ لا توجد sources في config.json"); exit(1)
    source   = sources[0]
    page_url = source["url"]
    video_url, video_title = fetch_latest_from_page(page_url)

if not video_url:
    print("❌ فشل جلب الفيديو"); exit(1)

print(f"✏️  العنوان: {video_title}")

# تحميل الفيديو
if not download_video(video_url): exit(1)

# معلومات وتحجيم
src_w, src_h, dur = get_video_info("/tmp/main.mp4")
print(f"📏 {src_w}×{src_h} | {dur:.1f}s")

main_ready = "/tmp/main.mp4"
if src_w != TARGET_W or src_h != TARGET_H:
    if scale_to_target("/tmp/main.mp4", "/tmp/main_scaled.mp4", TARGET_W, TARGET_H):
        main_ready = "/tmp/main_scaled.mp4"

W, H = TARGET_W, TARGET_H

print(f"\n🏭 معالجة {len(target_pubs)} صفحة...\n" + "─"*40)

success = 0
for pub in target_pubs:
    name  = pub["name"]
    color = pub.get("title_color", "#1a237e")
    print(f"\n📺 {name}")
    current = main_ready

    # ── PNG Frame خاص بكل publisher ───────────────────────────
    frame_local = f"/tmp/frame_{name}.png"
    framed_out  = f"/tmp/framed_{name}.mp4"
    if download_from_cloudinary(pub["frame_png_id"], frame_local, resource_type="image"):
        if apply_png_frame(current, frame_local, framed_out, W, H):
            current = framed_out
    else:
        print(f"  ⚠️ PNG Frame غير متاح — سيُنشر بدونه")

    # ── شريط العنوان بلون خاص بكل publisher ──────────────────
    title_png  = render_title_overlay(video_title, color, W, H)
    titled_out = f"/tmp/titled_{name}.mp4"
    if apply_title_overlay(current, title_png, titled_out, dur):
        current = titled_out

    # ── Outro خاص بكل publisher ───────────────────────────────
    outro_in  = f"/tmp/outro_{name}.mp4"
    final_out = f"/tmp/final_{name}.mp4"
    if download_from_cloudinary(pub["outro_id"], outro_in):
        if add_outro(current, outro_in, final_out, W, H):
            current = final_out

    # ── رفع وإرسال بالجودة الأصلية ────────────────────────────
    try:
        upload_and_send(current, name, video_title, video_url)
        success += 1
        print(f"  🎉 {name} نُشر بنجاح")
    except Exception as e:
        print(f"  ❌ {name}: {e}")

    cleanup_pub(name)

cleanup_global()
print(f"\n{'═'*50}\n🎉 {success}/{len(target_pubs)} صفحات نُشرت بنجاح")
