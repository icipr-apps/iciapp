import os, json, subprocess, re, cloudinary, cloudinary.uploader, requests

# ─── إعدادات ────────────────────────────────────────────────
COOKIES_FILE = "/tmp/cookies.txt"
WEBHOOK_URL  = os.environ["WEBHOOK_URL"]
TARGET_W, TARGET_H = 1080, 1920

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

VIDEO_URL        = os.environ.get("VIDEO_URL", "").strip()
VIDEO_TITLE      = os.environ.get("VIDEO_TITLE", "").strip()
VIDEO_LOCATION   = os.environ.get("VIDEO_LOCATION", "").strip()
VIDEO_DATE       = os.environ.get("VIDEO_DATE", "").strip()
VIDEO_VISIBILITY = os.environ.get("VIDEO_VISIBILITY", "متداول").strip()
VIDEO_PUBLISHER  = os.environ.get("VIDEO_PUBLISHER", "ALL").strip()

if not VIDEO_URL:
    print("❌ خطأ: لم يتم تحديد رابط الفيديو (VIDEO_URL)"); exit(1)
if not VIDEO_TITLE:
    print("❌ خطأ: لم يتم تحديد عنوان الفيديو (VIDEO_TITLE)"); exit(1)

print(f"🎬 رابط   : {VIDEO_URL}")
print(f"✏️  عنوان  : {VIDEO_TITLE}")
print(f"📍 مكان   : {VIDEO_LOCATION or '—'}")
print(f"📅 تاريخ  : {VIDEO_DATE or '—'}")
print(f"🔒 نوع    : {VIDEO_VISIBILITY}")
print(f"👤 ناشر   : {VIDEO_PUBLISHER}")


# ══════════════════════════════════════════════════════════════
#   تشكيل النص العربي بشكل صحيح
# ══════════════════════════════════════════════════════════════

def arabic(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except:
        return str(text)


def load_font(size):
    from PIL import ImageFont
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Montserrat-Arabic-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


# ══════════════════════════════════════════════════════════════
#   رسم الـ Overlay الكامل
# ══════════════════════════════════════════════════════════════

def render_overlay(title, location, date_str, visibility, color_hex, W, H):
    """
    يرسم صورة RGBA بنفس حجم الفيديو تحتوي على:
    - شريط عمودي أقصى اليسار: متداول/خاص (ملوّن، نص مقلوب 90°)
    - مربع أعلى اليمين: المكان + التاريخ
    - شريط العنوان: أسفل الفيديو فوق منطقة الـ Green Screen بـ 22%
    """
    from PIL import Image, ImageDraw

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = int(W * 0.038)

    # لون العنوان
    hex_str   = color_hex.split("@")[0].replace("0x", "").replace("#", "")
    alpha_val = int(float(color_hex.split("@")[1]) * 255) if "@" in color_hex else 217
    title_bg  = (int(hex_str[0:2],16), int(hex_str[2:4],16), int(hex_str[4:6],16), alpha_val)

    def tw(draw_obj, text, font):
        bb = draw_obj.textbbox((0,0), text, font=font)
        return bb[2]-bb[0], bb[3]-bb[1]

    # ══ 1. شريط متداول/خاص — أقصى اليسار عمودياً في المنتصف ══
    if visibility:
        badge_sz = max(28, int(W * 0.03))
        font_b   = load_font(badge_sz)
        vis_ar   = arabic(visibility)
        bw, bh   = tw(draw, vis_ar, font_b)

        strip_w  = int(badge_sz * 2.4)
        strip_h  = bw + int(badge_sz * 4)
        strip_x  = 0
        strip_y  = (H - strip_h) // 2

        strip_color = (16, 185, 129, 230) if visibility in ("متداول",) else (220, 38, 38, 230)
        draw.rectangle([strip_x, strip_y, strip_x + strip_w, strip_y + strip_h],
                       fill=strip_color)

        # رسم النص على صورة مؤقتة ثم تدويرها
        tmp = Image.new("RGBA", (strip_h, strip_w), (0, 0, 0, 0))
        td  = ImageDraw.Draw(tmp)
        tx  = (strip_h - bw) // 2
        ty  = (strip_w - bh) // 2
        td.text((tx+1, ty+1), vis_ar, font=font_b, fill=(0,0,0,100))
        td.text((tx, ty),     vis_ar, font=font_b, fill=(255,255,255,255))
        rotated = tmp.rotate(90, expand=True)
        img.paste(rotated, (strip_x, strip_y), rotated)

    # ══ 2. المكان + التاريخ — أعلى اليمين ══
    info_sz = max(30, int(W * 0.033))
    font_i  = load_font(info_sz)

    info_lines = []
    if location: info_lines.append("📍 " + location)
    if date_str: info_lines.append("📅 " + date_str)

    if info_lines:
        ar_lines = [arabic(l) for l in info_lines]
        widths   = [tw(draw, l, font_i)[0] for l in ar_lines]
        heights  = [tw(draw, l, font_i)[1] for l in ar_lines]
        gap      = int(info_sz * 0.5)
        bpw      = int(info_sz * 0.65)
        bph      = int(info_sz * 0.4)
        box_w    = max(widths) + bpw * 2
        box_h    = sum(heights) + (len(heights)-1)*gap + bph*2

        bx = W - box_w - pad
        by = pad

        draw.rectangle([bx-2, by-2, bx+box_w+2, by+box_h+2], fill=(0,0,0,50))
        draw.rectangle([bx, by, bx+box_w, by+box_h],          fill=(0,0,0,170))

        y = by + bph
        for line_ar, lw_val, lh_val in zip(ar_lines, widths, heights):
            tx_pos = bx + bpw
            draw.text((tx_pos+1, y+1), line_ar, font=font_i, fill=(0,0,0,120))
            draw.text((tx_pos,   y),   line_ar, font=font_i, fill=(255,255,255,240))
            y += lh_val + gap

    # ══ 3. شريط العنوان — فوق فوتر الـ Green Screen ══
    if title:
        title_sz = max(38, int(W * 0.044))
        font_t   = load_font(title_sz)
        ar_title = arabic(title)

        bar_w  = W
        usable = bar_w - pad * 2

        words = ar_title.split()
        lines, current = [], []
        for word in words:
            test = " ".join(current + [word])
            ww, _ = tw(draw, test, font_t)
            if ww <= usable:
                current.append(word)
            else:
                if current: lines.append(" ".join(current))
                current = [word]
        if current: lines.append(" ".join(current))
        if not lines: lines = [ar_title]

        line_h = int(title_sz * 1.65)
        vpad   = int(title_sz * 0.7)
        bar_h  = len(lines) * line_h + vpad * 2

        # يرفع الشريط فوق فوتر الـ Green Screen
        # الـ GS footer يأخذ قرابة 20% من الأسفل فنضيف هامشاً إضافياً
        bar_y = H - bar_h - int(H * 0.22)
        bar_x = 0

        draw.rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], fill=title_bg)

        for i, line in enumerate(lines):
            lw_val, _ = tw(draw, line, font_t)
            tx_pos    = (bar_w - lw_val) // 2
            ty_pos    = bar_y + vpad + i * line_h
            draw.text((tx_pos+2, ty_pos+2), line, font=font_t, fill=(0,0,0,110))
            draw.text((tx_pos,   ty_pos),   line, font=font_t, fill=(255,255,255,255))

    out = "/tmp/full_overlay.png"
    img.save(out, "PNG")
    print(f"✅ الـ Overlay: {out}")
    return out


# ══════════════════════════════════════════════════════════════
#   دوال الفيديو
# ══════════════════════════════════════════════════════════════

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def download_video(url):
    out = "/tmp/main.mp4"
    for use_cookies in [False, True]:
        print(f"📥 تحميل {'(كوكيز)' if use_cookies else '(مباشر)'}...")
        cmd = ["yt-dlp", "-o", out, "--format", "best[ext=mp4]/best",
               "--no-warnings", "--no-playlist"]
        if use_cookies and os.path.exists(COOKIES_FILE):
            cmd += ["--cookies", COOKIES_FILE]
        cmd.append(url)
        subprocess.run(cmd, timeout=300)
        if os.path.exists(out) and os.path.getsize(out) > 10000:
            print(f"  ✅ {os.path.getsize(out)//1024} KB"); return True
        if os.path.exists(out): os.remove(out)
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
    print(f"📐 تحجيم {tw}×{th}...")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", src,
         "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅ تم" if ok else f"  ❌ فشل\n{r.stderr[-300:]}"); return ok

def apply_overlay(main, overlay_png, out):
    print("✍️  تطبيق الـ Overlay...")
    fc = ("[1:v]format=yuva420p,"
          "fade=t=in:st=1.5:d=0.8:alpha=1,"
          "fade=t=out:st=11.2:d=0.8:alpha=1[ovr];"
          "[0:v][ovr]overlay=0:0[v]")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", main,
         "-loop", "1", "-t", "12", "-i", overlay_png,
         "-filter_complex", fc,
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", "-shortest", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم"); return True
    fc2 = ("[1:v]format=yuva420p[ovr];"
           "[0:v][ovr]overlay=0:0:enable='between(t,1.5,12)'[v]")
    subprocess.run(
        ["ffmpeg", "-y", "-i", main,
         "-loop", "1", "-t", "12", "-i", overlay_png,
         "-filter_complex", fc2,
         "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-c:a", "copy", "-preset", "fast", "-shortest", out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅ (احتياطي)" if ok else f"  ❌ فشل\n{r.stderr[-300:]}"); return ok

def download_from_cloudinary(public_id, out):
    url = (f"https://res.cloudinary.com/"
           f"{os.environ['CLOUDINARY_CLOUD_NAME']}/video/upload/{public_id}.mp4")
    subprocess.run(["wget", "-q", "-O", out, url], timeout=90)
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    if not ok: print(f"  ⚠️ فشل تحميل {public_id}")
    return ok

def apply_green_screen(main, gs, out, W, H, dur):
    print("🎨 Green Screen...")
    fc = (f"[1:v]trim=duration={dur},scale={W}:{H},"
          f"colorkey=0x00FF00:0.3:0.1,setpts=PTS-STARTPTS[g];"
          f"[0:v][g]overlay=0:0[v]")
    for maps in [["-map", "[v]", "-map", "0:a"], ["-map", "[v]"]]:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", main, "-i", gs, "-filter_complex", fc,
             *maps, "-c:v", "libx264", "-c:a", "aac", "-shortest", "-preset", "fast", out],
            capture_output=True, text=True, timeout=600
        )
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print("  ✅ تم"); return True
        if os.path.exists(out): os.remove(out)
    print(f"  ❌ فشل"); return False

def add_outro(main, outro, out, W, H):
    print("🎬 Outro...")
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", outro],
        capture_output=True, text=True
    )
    has_audio, dur = False, 5
    try:
        info      = json.loads(r.stdout)
        has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
        dur       = float(info.get("format", {}).get("duration", 5))
    except: pass

    if has_audio:
        fc   = (f"[0:v]scale={W}:{H},setsar=1[v0];[1:v]scale={W}:{H},setsar=1[v1];"
                f"[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map", "[ov]", "-map", "[oa]"]
    else:
        fc   = (f"[0:v]scale={W}:{H},setsar=1[v0];[1:v]scale={W}:{H},setsar=1[v1];"
                f"aevalsrc=0:d={dur}[sl];"
                f"[v0][0:a][v1][sl]concat=n=2:v=1:a=1[ov][oa]")
        maps = ["-map", "[ov]", "-map", "[oa]"]

    subprocess.run(
        ["ffmpeg", "-y", "-i", main, "-i", outro, "-filter_complex", fc,
         *maps, "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅ تم"); return True
    with open("/tmp/concat.txt", "w") as f:
        f.write(f"file '{main}'\nfile '{outro}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "/tmp/concat.txt",
         "-vf", f"scale={W}:{H},setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-preset", "fast", out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅ (احتياطي)" if ok else "  ❌ فشل"); return ok

def upload_and_send(video_path, pub_name):
    import time
    print(f"☁️  رفع ({pub_name})...")
    safe   = re.sub(r"[^a-z0-9]", "_", pub_name.lower())
    result = cloudinary.uploader.upload(
        video_path,
        resource_type = "video",
        public_id     = f"final_{safe}_{int(time.time())}",
        overwrite     = False
    )
    url = result["secure_url"]
    print(f"  ✅ {url[:70]}...")
    requests.post(WEBHOOK_URL, json={
        "video_url":  url,
        "title":      VIDEO_TITLE,
        "location":   VIDEO_LOCATION,
        "date":       VIDEO_DATE,
        "visibility": VIDEO_VISIBILITY,
        "publisher":  pub_name,
        "source_url": VIDEO_URL,
    }, timeout=30)
    print(f"  📤 Webhook → {pub_name}")
    return url

def cleanup_pub(name):
    for f in [f"/tmp/gs_{name}.mp4", f"/tmp/gs_{name}_done.mp4",
              f"/tmp/ovr_{name}.mp4", f"/tmp/outro_{name}.mp4",
              f"/tmp/final_{name}.mp4", f"/tmp/overlay_{name}.png"]:
        if os.path.exists(f): os.remove(f)

def cleanup_global():
    for f in ["/tmp/main.mp4", "/tmp/main_scaled.mp4",
              "/tmp/overlaid_base.mp4", "/tmp/full_overlay.png", "/tmp/concat.txt"]:
        if os.path.exists(f): os.remove(f)


# ══════════════════════════════════════════════════════════════
#   التنفيذ الرئيسي
# ══════════════════════════════════════════════════════════════

print("\n🤖 بدء المعالجة\n" + "═"*50)

config       = load_config()
all_pubs     = config["publishers"]
target_pubs  = all_pubs if VIDEO_PUBLISHER.upper() == "ALL" else \
               [p for p in all_pubs if p["name"] == VIDEO_PUBLISHER] or all_pubs

print(f"📋 الصفحات: {[p['name'] for p in target_pubs]}")

# 1. تحميل الفيديو
if not download_video(VIDEO_URL): exit(1)

# 2. معلومات وتحجيم
src_w, src_h, dur = get_video_info("/tmp/main.mp4")
print(f"📏 {src_w}×{src_h} | {dur:.1f}s")

main_ready = "/tmp/main.mp4"
if src_w != TARGET_W or src_h != TARGET_H:
    main_ready = "/tmp/main_scaled.mp4"
    if not scale_to_target("/tmp/main.mp4", main_ready, TARGET_W, TARGET_H):
        main_ready = "/tmp/main.mp4"

W, H = TARGET_W, TARGET_H

# 3. رسم الـ Overlay (بلون الصفحة الأولى — مشترك)
print("\n🖌️  رسم الـ Overlay...")
first_color = target_pubs[0].get("title_color", "0x1a237e@0.85")
overlay_png = render_overlay(VIDEO_TITLE, VIDEO_LOCATION, VIDEO_DATE,
                              VIDEO_VISIBILITY, first_color, W, H)

# 4. تطبيق الـ Overlay على نسخة أساسية
overlaid_base = "/tmp/overlaid_base.mp4"
if not apply_overlay(main_ready, overlay_png, overlaid_base):
    overlaid_base = main_ready

# 5. معالجة كل Publisher
print(f"\n🏭 معالجة {len(target_pubs)} صفحة...\n" + "─"*40)

success = 0
for pub in target_pubs:
    name  = pub["name"]
    color = pub.get("title_color", first_color)
    print(f"\n📺 صفحة: {name}")

    current = overlaid_base

    # overlay مخصص إذا اللون مختلف
    if color != first_color:
        custom_png = render_overlay(VIDEO_TITLE, VIDEO_LOCATION, VIDEO_DATE,
                                     VIDEO_VISIBILITY, color, W, H)
        custom_ovr = f"/tmp/ovr_{name}.mp4"
        if apply_overlay(main_ready, custom_png, custom_ovr):
            current = custom_ovr
        if os.path.exists(custom_png): os.remove(custom_png)

    # Green Screen
    gs_in  = f"/tmp/gs_{name}.mp4"
    gs_out = f"/tmp/gs_{name}_done.mp4"
    if download_from_cloudinary(pub["green_screen_id"], gs_in):
        if apply_green_screen(current, gs_in, gs_out, W, H, dur):
            current = gs_out

    # Outro
    outro_in  = f"/tmp/outro_{name}.mp4"
    final_out = f"/tmp/final_{name}.mp4"
    if download_from_cloudinary(pub["outro_id"], outro_in):
        if add_outro(current, outro_in, final_out, W, H):
            current = final_out

    # رفع وإرسال
    try:
        upload_and_send(current, name)
        success += 1
        print(f"  🎉 {name} ← نُشر بنجاح")
    except Exception as e:
        print(f"  ❌ {name} ← فشل: {e}")

    cleanup_pub(name)

cleanup_global()

print(f"\n{'═'*50}")
print(f"🎉 انتهت المعالجة — {success}/{len(target_pubs)} صفحات نُشرت بنجاح")
