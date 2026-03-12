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

VIDEO_PUBLISHER  = os.environ.get("VIDEO_PUBLISHER",  "ALL").strip()
VIDEO_URL_INPUT  = os.environ.get("VIDEO_URL",         "").strip()
VIDEO_TITLE_INPUT= os.environ.get("VIDEO_TITLE",       "").strip()
VIDEO_LOCATION   = os.environ.get("VIDEO_LOCATION",    "").strip()
VIDEO_DATE       = os.environ.get("VIDEO_DATE",        "").strip()
VIDEO_VISIBILITY = os.environ.get("VIDEO_VISIBILITY",  "متداول").strip()
VIDEO_SOURCE     = os.environ.get("VIDEO_SOURCE",      "").strip()
print(f"👤 {VIDEO_PUBLISHER} | 📍 {VIDEO_LOCATION or '—'} | 📅 {VIDEO_DATE or '—'} | 🔒 {VIDEO_VISIBILITY}")


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
#   رسم الـ Overlay الكامل — مقسّم إلى ملفين:
#
#   overlay_permanent.png ← مكان + تاريخ + متداول/خاص
#                            يظهر fade-in ويبقى طول الفيديو
#
#   overlay_title.png     ← شريط العنوان فقط
#                            يظهر fade-in ويختفي بعد 12 ثانية
#
#   التصميم:
#   ┌─────────────────────────────────────────────┐
#   │ 📍 تافرطة، بجاية        [أعلى يسار]        │
#   │ 📅 2026-03-11                               │
#   │                                             │
#   │           محتوى الفيديو                     │
#   │                                             │
#   │ متداول ← نص عمودي أقصى اليسار              │
#   │                                             │
#   │ ████████ عنوان الفيديو ████████             │ ← يختفي بعد 12s
#   └─────────────────────────────────────────────┘
# ══════════════════════════════════════════════════════════════

def render_overlay(title, location, date_str, visibility, color_hex, W, H):
    from PIL import Image, ImageDraw
    white   = (255, 255, 255, 255)
    shadow  = (0, 0, 0, 160)
    pad     = int(W * 0.04)

    hex_str  = color_hex.replace("0x","").replace("#","")
    title_bg = (int(hex_str[0:2],16), int(hex_str[2:4],16), int(hex_str[4:6],16), 217)

    # ── Overlay 1: دائم (مكان + تاريخ + متداول) ───────────────
    img_perm  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_perm = ImageDraw.Draw(img_perm)

    info_sz = max(30, int(W * 0.034))
    font_i  = load_font(info_sz)

    # ── أيقونات outline نحيفة بـ PIL (بدون emoji) ──────────────
    import math

    def draw_icon_location(d, cx, cy, R, color):
        """دبوس موقع outline — مثل هسبريس"""
        lw      = max(3, int(R * 0.18))
        head_r  = R * 0.62
        head_cy = cy - R * 0.28
        # الشكل الخارجي كـ polygon بنقاط كثيرة
        pts = []
        steps = 40
        for i in range(steps + 1):
            angle = math.pi + (math.pi * i / steps)
            pts.append((cx + head_r * math.cos(angle),
                        head_cy + head_r * math.sin(angle)))
        tip_y  = cy + R * 0.95
        base_y = head_cy + head_r * 0.85
        hw     = head_r * 0.55
        pts.append((cx + hw, base_y))
        pts.append((cx,      tip_y))
        pts.append((cx - hw, base_y))
        d.polygon(pts, outline=color, width=lw)
        # الدائرة الداخلية
        ir = max(3, int(head_r * 0.38))
        d.ellipse([cx-ir, head_cy-ir, cx+ir, head_cy+ir],
                  outline=color, width=lw)

    def draw_icon_calendar(d, cx, cy, R, color):
        """تقويم outline — مثل هسبريس"""
        lw  = max(3, int(R * 0.17))
        x0  = cx - R;   x1 = cx + R
        y0  = cy - int(R * 0.80); y1 = cy + int(R * 0.90)
        rad = max(3, int(R * 0.18))
        hh  = int((y1 - y0) * 0.28)
        # الإطار الخارجي
        d.rounded_rectangle([x0,y0,x1,y1], radius=rad, outline=color, width=lw)
        # خط الهيدر الفاصل
        d.line([(x0+1, y0+hh), (x1-1, y0+hh)], fill=color, width=lw)
        # ربطتان أعلى
        pk_h = int(R * 0.35); pk_w = max(2, int(R * 0.11))
        for px in [cx - int(R*0.38), cx + int(R*0.38)]:
            d.rounded_rectangle(
                [px-pk_w, y0-pk_h, px+pk_w, y0+int(pk_h*0.4)],
                radius=pk_w, outline=color, width=lw)
        # 6 نقاط مملوءة (3×2)
        dot_r = max(2, int(R * 0.09))
        gx0   = x0 + int((x1-x0) * 0.16)
        gy0   = y0 + hh + int((y1-y0-hh) * 0.22)
        csp   = int((x1-x0) * 0.62 / 2)
        rsp   = int((y1-y0-hh) * 0.48)
        for row in range(2):
            for col in range(3):
                gx = gx0 + col * csp
                gy = gy0 + row * rsp
                d.ellipse([gx-dot_r,gy-dot_r,gx+dot_r,gy+dot_r], fill=color)

    # ── أيقونة يمين + نص يمتد لليسار (align right مثل هسبريس) ──
    info_items = []
    if location: info_items.append(("location", location))
    if date_str: info_items.append(("date",     date_str))

    icon_sz   = int(info_sz * 0.46)
    icon_gap  = int(info_sz * 0.28)
    y = int(H * 0.13)

    # نحسب أوسع سطر لتحديد نقطة الارتساء اليمنى الثابتة
    max_tw = max((get_tw(draw_perm, t, font_i)[0] for _, t in info_items), default=0)
    right_anchor = pad + max_tw + icon_gap + icon_sz * 2  # نقطة يمين ثابتة

    for kind, text in info_items:
        tw, th = get_tw(draw_perm, text, font_i)

        # الأيقونة عند نقطة الارتساء اليمنى
        icon_cx = right_anchor - icon_sz
        icon_cy = y + th // 2 + int(icon_sz * 0.15)

        # النص يبدأ من اليسار وينتهي عند الأيقونة (align right)
        text_x  = icon_cx - icon_sz - icon_gap - tw

        draw_perm.text((text_x+2, y+2), text, font=font_i, fill=shadow)
        draw_perm.text((text_x,   y),   text, font=font_i, fill=white)

        if kind == "location":
            draw_icon_location(draw_perm, icon_cx, icon_cy, icon_sz, (255,255,255,240))
        else:
            draw_icon_calendar(draw_perm, icon_cx, icon_cy + int(icon_sz * 0.18), icon_sz, (255,255,255,240))

        y += th + int(info_sz * 0.55)

    # متداول / خاص عمودي أقصى اليسار
    if visibility:
        badge_sz = max(26, int(W * 0.030))
        font_b   = load_font(badge_sz)
        bw, bh   = get_tw(draw_perm, visibility, font_b)
        margin   = int(badge_sz * 0.35)
        tmp      = Image.new("RGBA", (bw + margin*2, bh + margin*2), (0, 0, 0, 0))
        td       = ImageDraw.Draw(tmp)
        td.text((margin+1, margin+1), visibility, font=font_b, fill=shadow)
        td.text((margin,   margin),   visibility, font=font_b, fill=white)
        rotated  = tmp.rotate(90, expand=True)
        img_perm.paste(rotated, (4, (H - rotated.height) // 2), rotated)

    img_perm.save("/tmp/overlay_permanent.png", "PNG")
    print("✅ overlay_permanent.png")

    # ── Overlay 2: شريط العنوان فقط ───────────────────────────
    img_title  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_title = ImageDraw.Draw(img_title)

    if title:
        font_size = max(20, int(W * 0.042))
        font_t    = load_font(font_size)
        pad_h     = int(W * 0.05)
        pad_v     = int(H * 0.018)
        bar_w     = W - int(W * 0.25)
        usable    = bar_w - 2 * pad_h

        lines  = wrap_text(draw_title, title, font_t, usable)
        line_h = int(font_size * 1.5)
        bar_h  = len(lines) * line_h + 2 * pad_v
        bar_x  = (W - bar_w) // 2
        bar_y  = H - bar_h - int(H * 0.22)

        draw_title.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=title_bg)
        for i, line in enumerate(lines):
            lw, _ = get_tw(draw_title, line, font_t)
            tx = bar_x + (bar_w - lw) // 2
            ty = bar_y + pad_v + i * line_h
            draw_title.text((tx+2, ty+2), line, font=font_t, fill=(0,0,0,110))
            draw_title.text((tx,   ty),   line, font=font_t, fill=white)

    img_title.save("/tmp/overlay_title.png", "PNG")
    print("✅ overlay_title.png")
    return "/tmp/overlay_title.png"


# ══════════════════════════════════════════════════════════════
#   Overlay مميز لـ chouf2
#
#   [تاريخ][🗓]  يسار    |    [مكان][📍]  يمين  — بدون خلفية
#   كلاهما في نفس المستوى الأفقي مع شعار الـ frame
#   شريط عنوان أضيق بلون البابليشر
#   [مسافة] badge خاص/متداول بلون البابليشر
# ══════════════════════════════════════════════════════════════

def render_overlay_chouf2(title, location, date_str, visibility, color_hex, W, H):
    from PIL import Image, ImageDraw
    import math
    white  = (255, 255, 255, 255)
    shadow = (0, 0, 0, 160)

    hex_str   = color_hex.replace("0x","").replace("#","")
    pub_color = (int(hex_str[0:2],16), int(hex_str[2:4],16), int(hex_str[4:6],16), 220)

    font_sz  = max(28, int(W * 0.037))
    font_i   = load_font(font_sz)
    icon_sz  = int(font_sz * 0.42)
    icon_gap = int(font_sz * 0.55)
    margin_x = int(W * 0.037)

    # info_y: يتوافق مع مستوى شعار الـ frame (أعلى الفيديو)
    info_y   = int(H * 0.038)

    # ── Overlay 1: دائم (تاريخ يسار + مكان يمين، بدون خلفية) ──
    img_perm  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_perm = ImageDraw.Draw(img_perm)

    def draw_icon_location(d, cx, cy, R, color):
        lw = max(3, int(R*0.18))
        head_r = R*0.62; head_cy = cy - R*0.28
        pts = []
        for i in range(41):
            angle = math.pi + (math.pi*i/40)
            pts.append((cx + head_r*math.cos(angle), head_cy + head_r*math.sin(angle)))
        tip_y = cy+R*0.95; base_y = head_cy+head_r*0.85; hw = head_r*0.55
        pts += [(cx+hw,base_y),(cx,tip_y),(cx-hw,base_y)]
        d.polygon(pts, outline=color, width=lw)
        ir = max(3, int(head_r*0.38))
        d.ellipse([cx-ir,head_cy-ir,cx+ir,head_cy+ir], outline=color, width=lw)

    def draw_icon_calendar(d, cx, cy, R, color):
        lw = max(3, int(R*0.17))
        x0=cx-R; x1=cx+R; y0=cy-int(R*0.80); y1=cy+int(R*0.90)
        rad = max(3, int(R*0.18)); hh = int((y1-y0)*0.28)
        d.rounded_rectangle([x0,y0,x1,y1], radius=rad, outline=color, width=lw)
        d.line([(x0+1,y0+hh),(x1-1,y0+hh)], fill=color, width=lw)
        pk_h=int(R*0.35); pk_w=max(2,int(R*0.11))
        for px in [cx-int(R*0.38), cx+int(R*0.38)]:
            d.rounded_rectangle([px-pk_w,y0-pk_h,px+pk_w,y0+int(pk_h*0.4)],
                                 radius=pk_w, outline=color, width=lw)
        dot_r=max(2,int(R*0.09))
        gx0=x0+int((x1-x0)*0.16); gy0=y0+hh+int((y1-y0-hh)*0.22)
        csp=int((x1-x0)*0.62/2); rsp=int((y1-y0-hh)*0.48)
        for row in range(2):
            for col in range(3):
                gx=gx0+col*csp; gy=gy0+row*rsp
                d.ellipse([gx-dot_r,gy-dot_r,gx+dot_r,gy+dot_r], fill=color)

    # التاريخ يسار: [نص]  [أيقونة🗓]
    if date_str:
        tw, th = get_tw(draw_perm, date_str, font_i)
        text_cy = info_y + th // 2   # المركز الرأسي الحقيقي للنص
        draw_perm.text((margin_x+2, info_y+2), date_str, font=font_i, fill=shadow)
        draw_perm.text((margin_x,   info_y),   date_str, font=font_i, fill=white)
        ic_cx = margin_x + tw + icon_gap + icon_sz
        draw_icon_calendar(draw_perm, ic_cx, text_cy, icon_sz, white)

    # المكان يمين: [نص]  [أيقونة📍]
    if location:
        tw2, th2 = get_tw(draw_perm, location, font_i)
        text_cy2 = info_y + th2 // 2   # المركز الرأسي الحقيقي للنص
        ic_cx2 = W - margin_x - icon_sz
        loc_tx  = ic_cx2 - icon_gap - tw2
        draw_perm.text((loc_tx+2, info_y+2), location, font=font_i, fill=shadow)
        draw_perm.text((loc_tx,   info_y),   location, font=font_i, fill=white)
        draw_icon_location(draw_perm, ic_cx2, text_cy2, icon_sz, white)

    img_perm.save("/tmp/overlay_permanent.png", "PNG")
    print("✅ overlay_permanent.png (chouf2)")

    # ── Overlay 2: شريط العنوان أضيق + badge بلون البابليشر ──
    img_title  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_title = ImageDraw.Draw(img_title)

    if title:
        font_size  = max(20, int(W * 0.048))
        font_t     = load_font(font_size)
        bar_pad_h  = int(W * 0.045)
        bar_pad_v  = int(H * 0.016)
        bar_w      = int(W * 0.78)
        usable     = bar_w - 2 * bar_pad_h
        lines      = wrap_text(draw_title, title, font_t, usable)
        line_h     = int(font_size * 1.55)
        bar_h      = len(lines) * line_h + 2 * bar_pad_v
        bar_x      = (W - bar_w) // 2
        bar_y      = H - bar_h - int(H * 0.22)

        draw_title.rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], fill=pub_color)
        for i, line in enumerate(lines):
            lw, _ = get_tw(draw_title, line, font_t)
            tx = bar_x + (bar_w - lw) // 2
            ty = bar_y + bar_pad_v + i * line_h
            draw_title.text((tx+2, ty+2), line, font=font_t, fill=(0,0,0,110))
            draw_title.text((tx,   ty),   line, font=font_t, fill=white)

        if visibility:
            font_bdg  = load_font(max(28, int(W * 0.036)))
            bw, bh    = get_tw(draw_title, visibility, font_bdg)
            bdg_pad_h = int(W * 0.045)
            bdg_pad_v = int(H * 0.010)
            bdg_w     = bw + bdg_pad_h * 2
            bdg_h     = bh + bdg_pad_v * 2
            bdg_x     = bar_x + (bar_w - bdg_w) // 2
            bdg_gap   = int(H * 0.013)
            bdg_y     = bar_y + bar_h + bdg_gap
            draw_title.rectangle([bdg_x, bdg_y, bdg_x+bdg_w, bdg_y+bdg_h], fill=pub_color)
            draw_title.text((bdg_x+bdg_pad_h+2, bdg_y+bdg_pad_v+2),
                            visibility, font=font_bdg, fill=(0,0,0,130))
            draw_title.text((bdg_x+bdg_pad_h,   bdg_y+bdg_pad_v),
                            visibility, font=font_bdg, fill=white)

    img_title.save("/tmp/overlay_title.png", "PNG")
    print("✅ overlay_title.png (chouf2)")
    return "/tmp/overlay_title.png"



# ══════════════════════════════════════════════════════════════
#   تطبيق PNG Frame الشفاف (إطار خاص بكل publisher)
# ══════════════════════════════════════════════════════════════

def apply_png_frame(main, frame_png, out, W, H):
    print("🖼️  PNG Frame...")
    fc = f"[1:v]scale={W}:{H}[frm];[0:v][frm]overlay=0:0[v]"
    for maps in [["-map","[v]","-map","0:a"], ["-map","[v]"]]:
        subprocess.run(
            ["ffmpeg", "-y", "-threads", "2", "-i", main, "-i", frame_png,
             "-filter_complex", fc,
             *maps, "-c:v","libx264","-c:a","copy","-preset","ultrafast", out],
            capture_output=True, text=True, timeout=600
        )
        if os.path.exists(out) and os.path.getsize(out) > 1000:
            print("  ✅"); return True
        if os.path.exists(out): os.remove(out)
    print("  ❌"); return False


# ══════════════════════════════════════════════════════════════
#   تطبيق الـ Overlay — ملفان:
#   permanent: يظهر fade-in ويبقى حتى النهاية
#   title:     يظهر fade-in ثم يختفي بعد 12 ثانية
# ══════════════════════════════════════════════════════════════

def apply_overlay(main, out, dur):
    print("✍️  تطبيق الـ Overlay...")
    perm_png  = "/tmp/overlay_permanent.png"
    title_png = "/tmp/overlay_title.png"
    loop_dur  = dur + 2
    show_start = 1.2
    fade_in    = 0.8
    title_hide = 12.0
    fade_out   = 0.6

    has_perm  = os.path.exists(perm_png)
    has_title = os.path.exists(title_png)

    if has_perm and has_title:
        fc = (
            f"[1:v]format=yuva420p,"
            f"fade=t=in:st={show_start}:d={fade_in}:alpha=1[perm];"
            f"[2:v]format=yuva420p,"
            f"fade=t=in:st={show_start}:d={fade_in}:alpha=1,"
            f"fade=t=out:st={title_hide}:d={fade_out}:alpha=1[ttl];"
            f"[0:v][perm]overlay=0:0[tmp];"
            f"[tmp][ttl]overlay=0:0[v]"
        )
        for maps in [["-map","[v]","-map","0:a"], ["-map","[v]"]]:
            subprocess.run(
                ["ffmpeg", "-y", "-threads", "2",
                 "-i", main,
                 "-loop","1","-t",str(loop_dur),"-i", perm_png,
                 "-loop","1","-t",str(loop_dur),"-i", title_png,
                 "-filter_complex", fc,
                 *maps, "-c:v","libx264","-c:a","copy","-preset","ultrafast","-shortest", out],
                capture_output=True, text=True, timeout=600
            )
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                print("  ✅ (split overlay)"); return True
            if os.path.exists(out): os.remove(out)

    # Fallback: title فقط
    if has_title:
        fc2 = (
            f"[1:v]format=yuva420p,"
            f"fade=t=in:st={show_start}:d={fade_in}:alpha=1,"
            f"fade=t=out:st={title_hide}:d={fade_out}:alpha=1[ttl];"
            f"[0:v][ttl]overlay=0:0[v]"
        )
        for maps in [["-map","[v]","-map","0:a"], ["-map","[v]"]]:
            subprocess.run(
                ["ffmpeg", "-y", "-threads", "2",
                 "-i", main,
                 "-loop","1","-t",str(loop_dur),"-i", title_png,
                 "-filter_complex", fc2,
                 *maps, "-c:v","libx264","-c:a","copy","-preset","ultrafast","-shortest", out],
                capture_output=True, text=True, timeout=600
            )
            if os.path.exists(out) and os.path.getsize(out) > 1000:
                print("  ✅ (title only)"); return True
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
        ["ffmpeg", "-y", "-threads", "2", "-i", src,
         "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out],
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
        ["ffmpeg","-y","-threads","2","-i",main,"-i",outro,"-filter_complex",fc,
         *maps,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out],
        capture_output=True, text=True, timeout=600
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        print("  ✅"); return True

    with open("/tmp/concat.txt","w") as f:
        f.write(f"file '{main}'\nfile '{outro}'\n")
    subprocess.run(
        ["ffmpeg","-y","-threads","2","-f","concat","-safe","0","-i","/tmp/concat.txt",
         "-vf",f"scale={W}:{H},setsar=1","-c:v","libx264","-c:a","aac","-preset","ultrafast",out],
        capture_output=True, text=True, timeout=600
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("  ✅ (concat)" if ok else "  ❌"); return ok


def compress_for_upload(src, out, max_mb=95):
    """ضغط خفيف فقط إذا تجاوز الحجم الحد المسموح"""
    size_mb = os.path.getsize(src) / 1024 / 1024
    if size_mb <= max_mb:
        return src
    print(f"  📦 ضغط ({size_mb:.1f}MB > {max_mb}MB)...")
    subprocess.run(
        ["ffmpeg", "-y", "-threads", "2", "-i", src,
         "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
         "-c:a", "aac", "-b:a", "128k", out],
        capture_output=True, text=True, timeout=300
    )
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        new_mb = os.path.getsize(out) / 1024 / 1024
        print(f"  ✅ مضغوط: {new_mb:.1f}MB")
        return out
    return src

def upload_and_send(video_path, pub_name, title, source_url):
    """رفع الفيديو بالجودة الأصلية بدون ضغط"""
    video_path = compress_for_upload(video_path, video_path.replace(".mp4", "_cmp.mp4"))
    mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"  📤 رفع — {mb:.1f}MB")

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

    time.sleep(300)
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
              "/tmp/overlay_permanent.png", "/tmp/overlay_title.png",
              "/tmp/concat.txt"]:
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
    video_title = VIDEO_TITLE_INPUT or "بدون عنوان"
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

    # ── رسم وتطبيق الـ Overlay الكامل (عنوان + مكان + تاريخ + متداول) ──
    if name == "chouf2":
        render_overlay_chouf2(video_title, VIDEO_LOCATION, VIDEO_DATE, VIDEO_VISIBILITY, color, W, H)
    else:
        render_overlay(video_title, VIDEO_LOCATION, VIDEO_DATE, VIDEO_VISIBILITY, color, W, H)
    titled_out = f"/tmp/titled_{name}.mp4"
    if apply_overlay(current, titled_out, dur):
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
