import numpy as np
import cv2
import fitz


def get_images_in_block(doc, p_idx, block_xyxy_1024, zoom_val, img_array, sub_elements=None):
    page = doc.load_page(p_idx)
    bx1, by1, bx2, by2 = [c / zoom_val for c in block_xyxy_1024]
    block_rect = fitz.Rect(bx1, by1, bx2, by2)

    intersecting_rects = []
    for img in page.get_image_info(xrefs=True):
        img_rect = fitz.Rect(img["bbox"])
        intersect = block_rect & img_rect
        if not intersect.is_empty:
            img_area = img_rect.get_area()
            if img_area > 0 and (intersect.get_area() / img_area) > 0.1:
                intersecting_rects.append(img_rect)

    threshold = 5.0
    working = [fitz.Rect(r) for r in intersecting_rects]
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(working):
            j = i + 1
            while j < len(working):
                r1_exp = fitz.Rect(
                    working[i].x0 - threshold, working[i].y0 - threshold,
                    working[i].x1 + threshold, working[i].y1 + threshold,
                )
                if not (r1_exp & working[j]).is_empty:
                    working[i] = working[i] | working[j]
                    working.pop(j)
                    changed = True
                else:
                    j += 1
            i += 1

    extracted = []
    for img_rect in working:
        try:
            h, w, _ = img_array.shape
            ix1 = max(0, min(w - 1, int(img_rect.x0 * zoom_val)))
            iy1 = max(0, min(h - 1, int(img_rect.y0 * zoom_val)))
            ix2 = max(0, min(w, int(img_rect.x1 * zoom_val)))
            iy2 = max(0, min(h, int(img_rect.y1 * zoom_val)))
            if (ix2 - ix1) > 10 and (iy2 - iy1) > 10:
                crop = img_array[iy1:iy2, ix1:ix2]
                if crop.size > 0:
                    ok, enc = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
                    if ok:
                        extracted.append(enc.tobytes())
        except Exception:
            pass
    return extracted


def get_reconstructed_block_image(doc, p_idx, block_xyxy_1024, zoom_val, img_array):
    page = doc.load_page(p_idx)
    bx1, by1, bx2, by2 = [c / zoom_val for c in block_xyxy_1024]
    block_rect = fitz.Rect(bx1, by1, bx2, by2)

    bw = int((bx2 - bx1) * zoom_val)
    bh = int((by2 - by1) * zoom_val)
    if bw <= 0 or bh <= 0:
        return None

    canvas = np.ones((bh, bw, 3), dtype=np.uint8) * 255

    for img in page.get_image_info(xrefs=True):
        img_rect = fitz.Rect(img["bbox"])
        intersect = block_rect & img_rect
        if intersect.is_empty:
            continue
        img_area = img_rect.get_area()
        if img_area <= 0 or (intersect.get_area() / img_area) < 0.1:
            continue

        xref = img.get("xref", 0)
        pasted = False

        if xref > 0:
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.colorspace is not None:
                    pix_rgb = fitz.Pixmap(fitz.csRGB, pix) if pix.colorspace.n in (1, 4) else pix
                    h_raw, w_raw = pix_rgb.height, pix_rgb.width
                    img_np = np.frombuffer(pix_rgb.samples, dtype=np.uint8).reshape(h_raw, w_raw, pix_rgb.n).copy()
                    if pix_rgb.n == 4:
                        img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)
                    elif pix_rgb.n == 1:
                        img_np = cv2.cvtColor(img_np, cv2.COLOR_GRAY2RGB)

                    bg = (img_np[:, :, 0] > 220) & (img_np[:, :, 1] > 215) & (img_np[:, :, 2] > 190)
                    img_np[bg] = [255, 255, 255]

                    tw = int((img_rect.x1 - img_rect.x0) * zoom_val)
                    th = int((img_rect.y1 - img_rect.y0) * zoom_val)
                    if tw > 0 and th > 0:
                        resized = cv2.resize(img_np, (tw, th), interpolation=cv2.INTER_AREA)
                        rx1 = int((img_rect.x0 - bx1) * zoom_val)
                        ry1 = int((img_rect.y0 - by1) * zoom_val)
                        cx1 = max(0, min(bw - 1, rx1))
                        cy1 = max(0, min(bh - 1, ry1))
                        cx2 = max(0, min(bw, rx1 + tw))
                        cy2 = max(0, min(bh, ry1 + th))
                        ch, cw = cy2 - cy1, cx2 - cx1
                        if ch > 0 and cw > 0:
                            oy, ox = cy1 - ry1, cx1 - rx1
                            canvas[cy1:cy2, cx1:cx2] = resized[oy:oy+ch, ox:ox+cw]
                            pasted = True
            except Exception:
                pass

        if not pasted:
            try:
                h, w, _ = img_array.shape
                ix1 = max(0, min(w - 1, int(img_rect.x0 * zoom_val)))
                iy1 = max(0, min(h - 1, int(img_rect.y0 * zoom_val)))
                ix2 = max(0, min(w, int(img_rect.x1 * zoom_val)))
                iy2 = max(0, min(h, int(img_rect.y1 * zoom_val)))
                if (ix2 - ix1) > 10 and (iy2 - iy1) > 10:
                    crop = img_array[iy1:iy2, ix1:ix2].copy()
                    bg = (crop[:, :, 0] > 220) & (crop[:, :, 1] > 215) & (crop[:, :, 2] > 190)
                    crop[bg] = [255, 255, 255]
                    rx1 = int((img_rect.x0 - bx1) * zoom_val)
                    ry1 = int((img_rect.y0 - by1) * zoom_val)
                    rx1 = max(0, min(bw - 1, rx1))
                    ry1 = max(0, min(bh - 1, ry1))
                    rx2 = max(0, min(bw, rx1 + (ix2 - ix1)))
                    ry2 = max(0, min(bh, ry1 + (iy2 - iy1)))
                    ch, cw = ry2 - ry1, rx2 - rx1
                    if ch > 0 and cw > 0:
                        canvas[ry1:ry2, rx1:rx2] = crop[0:ch, 0:cw]
            except Exception:
                pass

    return canvas
