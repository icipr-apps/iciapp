def render_overlay_chouf2(title, location, date_str, visibility_badge, color_hex, W, H):
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
    info_y   = int(H * 0.038)
    
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
    
    # التاريخ والمكان
    if date_str:
        tw, th = get_tw(draw_perm, date_str, font_i)
        text_cy = info_y + th // 2
        draw_perm.text((margin_x+2, info_y+2), date_str, font=font_i, fill=shadow)
        draw_perm.text((margin_x,   info_y),   date_str, font=font_i, fill=white)
        ic_cx = margin_x + tw + icon_gap + icon_sz
        draw_icon_calendar(draw_perm, ic_cx, text_cy, icon_sz, white)
    
    if location:
        tw2, th2 = get_tw(draw_perm, location, font_i)
        text_cy2 = info_y + th2 // 2
        ic_cx2 = W - margin_x - icon_sz
        loc_tx  = ic_cx2 - icon_gap - tw2
        draw_perm.text((loc_tx+2, info_y+2), location, font=font_i, fill=shadow)
        draw_perm.text((loc_tx,   info_y),   location, font=font_i, fill=white)
        draw_icon_location(draw_perm, ic_cx2, text_cy2, icon_sz, white)
    
    # badge عمودي على اليسار لـ visibility_badge (متداول - @مصدر)
    if visibility_badge:
        badge_sz = max(26, int(W * 0.030))
        font_b   = load_font(badge_sz)
        bw, bh   = get_tw(draw_perm, visibility_badge, font_b)
        margin   = int(badge_sz * 0.35)
        tmp      = Image.new("RGBA", (bw + margin*2, bh + margin*2), (0, 0, 0, 0))
        td       = ImageDraw.Draw(tmp)
        td.text((margin+1, margin+1), visibility_badge, font=font_b, fill=shadow)
        td.text((margin,   margin),   visibility_badge, font=font_b, fill=white)
        rotated  = tmp.rotate(90, expand=True)
        img_perm.paste(rotated, (4, (H - rotated.height) // 2), rotated)
    
    img_perm.save("/tmp/overlay_permanent.png", "PNG")
    print("✅ overlay_permanent.png (chouf2)")
    
    # ── شريط العنوان بخلفية داكنة ─────────────────────────────
    img_title  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_title = ImageDraw.Draw(img_title)
    
    if title:
        font_size  = 40
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
        
        # خلفية داكنة مع شفافية منخفضة
        dark_bg = (0, 0, 0, 200)  # أسود داكن مع شفافية عالية
        draw_title.rectangle([bar_x, bar_y, bar_x+bar_w, bar_y+bar_h], fill=dark_bg)
        
        for i, line in enumerate(lines):
            lw, _ = get_tw(draw_title, line, font_t)
            tx = bar_x + (bar_w - lw) // 2
            ty = bar_y + bar_pad_v + i * line_h
            draw_title.text((tx+2, ty+2), line, font=font_t, fill=(0,0,0,110))
            draw_title.text((tx,   ty),   line, font=font_t, fill=(255,255,255,255))
        
        # ملاحظة: لم نعد نضيف visibility_badge هنا لأنه أصبح في الـ overlay الثابت
        # وإذا أردنا إضافته في مكان آخر يمكن تعديله
    
    if title:
        img_title.save("/tmp/overlay_title.png", "PNG")
        print("✅ overlay_title.png (chouf2)")
    else:
        if os.path.exists("/tmp/overlay_title.png"):
            os.remove("/tmp/overlay_title.png")
        print("ℹ️  لا عنوان → overlay_title.png محذوف (chouf2)")
    return "/tmp/overlay_title.png"
