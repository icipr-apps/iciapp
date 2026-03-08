import os, json, subprocess, re, cloudinary, cloudinary.uploader, requests

# ─── إعدادات البيئة ────────────────────────────────────────────
COOKIES_FILE = "/tmp/cookies.txt"
WEBHOOK_URL  = os.environ["WEBHOOK_URL"]
TARGET_W, TARGET_H = 1080, 1920

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

# ─── قراءة بيانات الفيديو من متغيرات البيئة ─────────────────────
VIDEO_URL        = os.environ.get("VIDEO_URL", "").strip()
VIDEO_TITLE      = os.environ.get("VIDEO_TITLE", "").strip()
VIDEO_LOCATION   = os.environ.get("VIDEO_LOCATION", "").strip()
VIDEO_DATE       = os.environ.get("VIDEO_DATE", "").strip()
VIDEO_VISIBILITY = os.environ.get("VIDEO_VISIBILITY", "متداول").strip()
VIDEO_PUBLISHER  = os.environ.get("VIDEO_PUBLISHER", "A").strip()

# ─── التحقق من المدخلات ──────────────────────────────────────────
if not VIDEO_URL:
    print("❌ خطأ: لم يتم تحديد رابط الفيديو (VIDEO_URL)")
    exit(1)
if not VIDEO_TITLE:
    print("❌ خطأ: لم يتم تحديد عنوان الفيديو (VIDEO_TITLE)")
    exit(1)

print(f"🎬 رابط الفيديو  : {VIDEO_URL}")
print(f"✏️  العنوان       : {VIDEO_TITLE}")
print(f"📍 المكان        : {VIDEO_LOCATION or '—'}")
print(f"📅 التاريخ       : {VIDEO_DATE or '—'}")
print(f"🔒 النوع         : {VIDEO_VISIBILITY}")
print(f"👤 الناشر        : {VIDEO_PUBLISHER}")


# ══════════════════════════════════════════════════════════════
#   دوال مساعدة
# ══════════════════════════════════════════════════════════════

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def get_font():
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Montserrat-Arabic-Bold.ttf")
    if os.path.exists(local):
        print("✅ الخط: Montserrat-Arabic-Bold")
        return local
    dv = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(dv):
        print("⚠️  استخدام الخط الاحتياطي: DejaVu")
        return dv
    print("⚠️  لم يُعثر على خط — سيُستخدم الخط الافتراضي")
    return None

def download_video(url):
    """تحميل الفيديو بـ yt-dlp — يجرب بدون كوكيز أولاً ثم معها"""
    out = "/tmp/main.mp4"
    for attempt, use_cookies in enumerate([False, True], 1):
        print(f"📥 محاولة التحميل {attempt}/2 {'(بدون كوكيز)' if not use_cookies else '(مع الكوكيز)'}...")
        cmd = ["yt-dlp", "-o", out, "--format", "best[ext=mp4]/best",
               "--no-warnings", "--no-playlist"]
        if use_cookies and os.path.exists(COOKIES_FILE):
            cmd += ["--cookies", COOKIES_FILE]
        cmd.append(url)
        subprocess.run(cmd, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 10000:
            print(f"✅ تم التحميل بنجاح ({os.path.getsize(out) // 1024} KB)")
            return True
        if os.path.exists(out):
            os.remove(out)
    print("❌ فشل تحميل الفيديو بعد محاولتين")
    return False

def get_video_info(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True
    )
    try:
        info = json.loads(probe.stdout)
        vs   = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
        w    = int(vs["width"])
        h    = int(vs["height"])
        dur  = float(info["format"].get("duration", 60))
        return w, h, dur
    except:
        return 1080, 1920, 60

def scale_to_target(src, out, tw=1080, th=1920):
    print(f"📐 تحجيم الفيديو إلى {tw}×{th}...")
    vf = (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
          f"crop={tw}:{th},setsar=1")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-vf", vf,
         "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم التحجيم بنجاح")
        return True
    print(f"  ❌ فشل التحجيم\n{r.stderr[-400:]}")
    return False


# ══════════════════════════════════════════════════════════════
#   رسم الـ Overlay الكامل (عنوان + مكان + تاريخ + نوع)
# ══════════════════════════════════════════════════════════════

def render_full_overlay(title, location, date_str, visibility, color_hex, video_w, video_h):
    """
    يرسم صورة RGBA بنفس حجم الفيديو تحتوي على:
    - شريط العنوان أسفل الفيديو (لون حسب color_hex)
    - مربع المكان والتاريخ أعلى اليمين
    - شارة النوع (متداول/خاص) أعلى اليسار
    """
    from PIL import Image, ImageDraw, ImageFont

    img  = Image.new("RGBA", (video_w, video_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── تحليل اللون ──
    hex_str   = color_hex.split("@")[0].replace("0x", "").replace("#", "")
    alpha_val = int(float(color_hex.split("@")[1]) * 255) if "@" in color_hex else 217
    title_bg  = (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), alpha_val)

    # ── تحميل الخطوط ──
    font_path = get_font()
    base_sz  = max(22, int(video_w * 0.036))
    info_sz  = max(16, int(video_w * 0.027))
    badge_sz = max(14, int(video_w * 0.024))

    def load_font(sz):
        if font_path:
            try: return ImageFont.truetype(font_path, sz)
            except: pass
        return ImageFont.load_default()

    font_title = load_font(base_sz)
    font_info  = load_font(info_sz)
    font_badge = load_font(badge_sz)

    pad = int(video_w * 0.038)

    def tw(text, font):
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    # ══ 1. شارة النوع — أعلى اليسار ══
    if visibility:
        badge_text  = visibility  # "متداول" أو "خاص"
        badge_color = (16, 185, 129, 215) if visibility == "متداول" else (220, 38, 38, 215)
        bw, bh = tw(badge_text, font_badge)
        bp = int(badge_sz * 0.55)
        rx0, ry0 = pad, pad
        rx1, ry1 = rx0 + bw + bp * 2, ry0 + bh + bp
        draw.rectangle([rx0, ry0, rx1, ry1], fill=badge_color)
        draw.text((rx0 + bp, ry0 + bp // 2), badge_text,
                  font=font_badge, fill=(255, 255, 255, 255))

    # ══ 2. المكان والتاريخ — أعلى اليمين ══
    info_items = []
    if location:
        info_items.append(location)
    if date_str:
        info_items.append(date_str)

    if info_items:
        widths  = [tw(t, font_info)[0] for t in info_items]
        heights = [tw(t, font_info)[1] for t in info_items]
        box_inner_w = max(widths)
        box_inner_h = sum(heights) + (len(info_items) - 1) * 7
        box_pad = int(info_sz * 0.55)
        box_w   = box_inner_w + box_pad * 2
        box_h   = box_inner_h + box_pad

        bx = video_w - box_w - pad
        by = pad

        # ظل ثم مستطيل الخلفية
        draw.rectangle([bx - 3, by - 3, bx + box_w + 3, by + box_h + 3],
                       fill=(0, 0, 0, 70))
        draw.rectangle([bx, by, bx + box_w, by + box_h],
                       fill=(0, 0, 0, 170))

        y = by + box_pad // 2
        for i, (line, lw_val, lh_val) in enumerate(zip(info_items, widths, heights)):
            # نص من اليمين داخل الصندوق
            tx = bx + box_w - lw_val - box_pad
            draw.text((tx + 1, y + 1), line, font=font_info, fill=(0, 0, 0, 120))
            draw.text((tx,     y),     line, font=font_info, fill=(255, 255, 255, 240))
            y += lh_val + 7

    # ══ 3. شريط العنوان — أسفل الفيديو ══
    if title:
        bar_w  = video_w - int(video_w * 0.08)
        usable = bar_w - 2 * pad

        words = title.split()
        lines, current = [], []
        for word in words:
            test = " ".join(current + [word])
            tw_test, _ = tw(test, font_title)
            if tw_test <= usable:
                current.append(word)
            else:
                if current: lines.append(" ".join(current))
                current = [word]
        if current: lines.append(" ".join(current))

        line_h = int(base_sz * 1.55)
        bar_h  = len(lines) * line_h + 2 * pad
        bar_x  = (video_w - bar_w) // 2
        bar_y  = video_h - bar_h - int(video_h * 0.12)

        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                       fill=title_bg)

        for i, line in enumerate(lines):
            lw_val, _ = tw(line, font_title)
            tx = bar_x + (bar_w - lw_val) // 2
            ty = bar_y + pad + i * line_h
            draw.text((tx + 2, ty + 2), line, font=font_title, fill=(0, 0, 0, 110))
            draw.text((tx,     ty),     line, font=font_title, fill=(255, 255, 255, 255))

    out_path = "/tmp/full_overlay.png"
    img.save(out_path, "PNG")
    print(f"✅ تم رسم الـ Overlay: {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════
#   تطبيق الـ Overlay على الفيديو
# ══════════════════════════════════════════════════════════════

def apply_overlay(main, overlay_png, out):
    print("✍️  تطبيق الـ Overlay على الفيديو...")
    show_start   = 1.5
    fade_in_dur  = 0.8
    show_end     = 13.0
    fade_out_dur = 0.8
    fout_st      = show_end - fade_out_dur

    fc = (
        f"[1:v]format=yuva420p,"
        f"fade=t=in:st={show_start}:d={fade_in_dur}:alpha=1,"
        f"fade=t=out:st={fout_st}:d={fade_out_dur}:alpha=1[ovr];"
        f"[0:v][ovr]overlay=0:0[v]"
    )
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", main,
         "-loop", "1", "-t", str(show_end + 1), "-i", overlay_png,
         "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", "-shortest", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم تطبيق الـ Overlay بنجاح")
        return True

    # Fallback: بدون fade
    print("  ⚠️  جاري محاولة احتياطية بدون fade...")
    fc2 = (
        f"[1:v]format=yuva420p[ovr];"
        f"[0:v][ovr]overlay=0:0:enable='between(t,{show_start},{show_end})'[v]"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", main,
         "-loop", "1", "-t", str(show_end + 1), "-i", overlay_png,
         "-filter_complex", fc2,
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", "-shortest", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم تطبيق الـ Overlay (احتياطي)")
        return True

    print(f"  ❌ فشل تطبيق الـ Overlay\n{r.stderr[-400:]}")
    return False


# ══════════════════════════════════════════════════════════════
#   دوال Green Screen والـ Outro
# ══════════════════════════════════════════════════════════════

def download_from_cloudinary(public_id, out_path):
    url = (f"https://res.cloudinary.com/"
           f"{os.environ['CLOUDINARY_CLOUD_NAME']}/video/upload/{public_id}.mp4")
    subprocess.run(["wget", "-q", "-O", out_path, url], timeout=90)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return True
    print(f"  ⚠️  فشل تحميل {public_id} من Cloudinary")
    return False

def apply_green_screen(main, gs, out, w, h, dur):
    print("🎨 إضافة Green Screen...")
    fc = (
        f"[1:v]trim=duration={dur},scale={w}:{h},"
        f"colorkey=0x00FF00:0.3:0.1,setpts=PTS-STARTPTS[g];"
        f"[0:v][g]overlay=0:0[v]"
    )
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", main, "-i", gs, "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم تطبيق Green Screen بنجاح")
        return True
    # Fallback بدون صوت من الـ GS
    subprocess.run(
        ["ffmpeg", "-y", "-i", main, "-i", gs, "-filter_complex", fc,
         "-map", "[v]",
         "-c:v", "libx264", "-shortest", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم تطبيق Green Screen (احتياطي)")
        return True
    print(f"  ❌ فشل Green Screen\n{r.stderr[-300:]}")
    return False

def add_outro(main, outro, out, w, h):
    print("🎬 إضافة الـ Outro...")
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", outro],
        capture_output=True, text=True
    )
    has_audio, outro_dur = False, 5
    try:
        info      = json.loads(probe.stdout)
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        outro_dur = float(info.get("format", {}).get("duration", 5))
    except:
        pass

    if has_audio:
        fc   = (f"[0:v]scale={w}:{h},setsar=1[v0];[1:v]scale={w}:{h},setsar=1[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map", "[ov]", "-map", "[oa]"]
    else:
        fc   = (f"[0:v]scale={w}:{h},setsar=1[v0];[1:v]scale={w}:{h},setsar=1[v1];"
                f"aevalsrc=0:d={outro_dur}[sl];"
                f"[v0][0:a][v1][sl]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map", "[ov]", "-map", "[oa]"]

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", main, "-i", outro, "-filter_complex", fc,
         *maps, "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم إضافة الـ Outro بنجاح")
        return True

    # Fallback بالـ concat
    print("  ⚠️  جاري المحاولة الاحتياطية (concat)...")
    with open("/tmp/concat.txt", "w") as f:
        f.write(f"file '{main}'\nfile '{outro}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "/tmp/concat.txt",
         "-vf", f"scale={w}:{h},setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم إضافة الـ Outro (احتياطي)")
        return True
    print(f"  ❌ فشل إضافة الـ Outro\n{r.stderr[-300:]}")
    return False


# ══════════════════════════════════════════════════════════════
#   رفع وإرسال
# ══════════════════════════════════════════════════════════════

def upload_and_send(video_path, publisher_name):
    print(f"☁️  رفع الفيديو النهائي على Cloudinary...")
    safe   = re.sub(r"[^a-z0-9]", "_", publisher_name.lower())
    result = cloudinary.uploader.upload(
        video_path,
        resource_type = "video",
        public_id     = f"final_{safe}",
        overwrite     = True
    )
    video_url = result["secure_url"]
    print(f"✅ تم الرفع: {video_url}")

    print(f"📤 إرسال البيانات للـ Webhook...")
    payload = {
        "video_url":  video_url,
        "title":      VIDEO_TITLE,
        "location":   VIDEO_LOCATION,
        "date":       VIDEO_DATE,
        "visibility": VIDEO_VISIBILITY,
        "publisher":  publisher_name,
        "source_url": VIDEO_URL,
    }
    r = requests.post(WEBHOOK_URL, json=payload, timeout=30)
    print(f"✅ تم الإرسال للـ Webhook (HTTP {r.status_code})")
    return video_url


def cleanup():
    for f in ["/tmp/main.mp4", "/tmp/main_scaled.mp4",
              "/tmp/overlay_applied.mp4", "/tmp/gs_applied.mp4",
              "/tmp/with_outro.mp4", "/tmp/full_overlay.png",
              "/tmp/gs.mp4", "/tmp/outro.mp4", "/tmp/concat.txt"]:
        if os.path.exists(f):
            os.remove(f)


# ══════════════════════════════════════════════════════════════
#   التنفيذ الرئيسي
# ══════════════════════════════════════════════════════════════

print("\n🤖 بدء معالجة الفيديو...\n" + "=" * 50)

# 1. تحميل الإعدادات
config = load_config()
publisher = next(
    (p for p in config["publishers"] if p["name"] == VIDEO_PUBLISHER),
    config["publishers"][0]
)
print(f"📋 الناشر المختار: {publisher['name']}")

# 2. تحميل الفيديو
if not download_video(VIDEO_URL):
    exit(1)

# 3. معلومات الفيديو + التحجيم
src_w, src_h, dur = get_video_info("/tmp/main.mp4")
print(f"📏 المقاس الأصلي: {src_w}×{src_h} | المدة: {dur:.1f}s")

if src_w == TARGET_W and src_h == TARGET_H:
    main_ready = "/tmp/main.mp4"
    print("  ✅ المقاس صحيح — لا حاجة لتحجيم")
else:
    main_ready = "/tmp/main_scaled.mp4"
    if not scale_to_target("/tmp/main.mp4", main_ready, TARGET_W, TARGET_H):
        main_ready = "/tmp/main.mp4"

current = main_ready
W, H = TARGET_W, TARGET_H

# 4. رسم وتطبيق الـ Overlay الكامل
try:
    color = publisher.get("title_color", "0x1a237e@0.85")
    overlay_png = render_full_overlay(
        title      = VIDEO_TITLE,
        location   = VIDEO_LOCATION,
        date_str   = VIDEO_DATE,
        visibility = VIDEO_VISIBILITY,
        color_hex  = color,
        video_w    = W,
        video_h    = H
    )
    ovr_out = "/tmp/overlay_applied.mp4"
    if apply_overlay(current, overlay_png, ovr_out):
        current = ovr_out
    else:
        print("⚠️  تخطي الـ Overlay — استمرار بدونه")
except Exception as e:
    print(f"⚠️  خطأ في الـ Overlay: {e}")
    import traceback; traceback.print_exc()

# 5. Green Screen
gs_path = "/tmp/gs.mp4"
if download_from_cloudinary(publisher["green_screen_id"], gs_path):
    gs_out = "/tmp/gs_applied.mp4"
    if apply_green_screen(current, gs_path, gs_out, W, H, dur):
        current = gs_out

# 6. Outro
outro_path = "/tmp/outro.mp4"
if download_from_cloudinary(publisher["outro_id"], outro_path):
    outro_out = "/tmp/with_outro.mp4"
    if add_outro(current, outro_path, outro_out, W, H):
        current = outro_out

# 7. رفع وإرسال
print(f"\n🎞️  الفيديو النهائي: {current} ({os.path.getsize(current) // 1024} KB)")
final_url = upload_and_send(current, publisher["name"])

# 8. تنظيف
cleanup()

print("\n🎉 اكتملت العملية بنجاح!")
print(f"🔗 رابط الفيديو النهائي: {final_url}")
