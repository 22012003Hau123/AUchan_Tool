import logging
import re

import cv2
import fitz
import numpy as np

# doclayout_yolo 0.0.4 + PyTorch >= 2.6 returns dict from YOLOv10 head instead of tensor.
# Patch non_max_suppression to handle dict predictions transparently.
try:
    import doclayout_yolo.utils.ops as _dly_ops
    _orig_nms = _dly_ops.non_max_suppression

    def _patched_nms(prediction, *args, **kwargs):
        if isinstance(prediction, dict):
            prediction = prediction.get("one2one", next(iter(prediction.values())))
            if isinstance(prediction, (list, tuple)):
                prediction = prediction[-1]
        return _orig_nms(prediction, *args, **kwargs)

    _dly_ops.non_max_suppression = _patched_nms
except Exception:
    pass

from .pdf_utils import get_images_in_block, get_reconstructed_block_image
from .text_utils import (
    ALLOWED_PRICE_KEYWORDS,
    PRICE_STOPWORDS,
    _EXCLUDE_FROM_PRODUCT_INF,
    strip_boilerplate,
)
from .utils import calculate_iou, encode_image_base64, is_inside

logger = logging.getLogger(__name__)

MAIN_CLASS_NAMES = [
    "Product_block", "logo", "pack", "plus", "price",
    "price_per_piece", "product_inf", "product_origin", "promo_fidelite",
]


def filter_overlapping_blocks(blocks, iou_threshold=0.9, nest_threshold=0.8, priority_map=None):
    if not blocks:
        return []
    if priority_map:
        sorted_blocks = sorted(blocks, key=lambda x: (priority_map.get(x['name'], 0), x['conf']), reverse=True)
    else:
        sorted_blocks = sorted(blocks, key=lambda x: x['conf'], reverse=True)
    kept = []
    for b in sorted_blocks:
        if all(calculate_iou(b['xyxy'], k['xyxy']) <= iou_threshold for k in kept):
            kept.append(b)
    return kept


def parse_results(results, class_names):
    elements = []
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        name = class_names[cls_id] if cls_id < len(class_names) else "Unknown"
        elements.append({"name": name, "conf": float(box.conf[0]), "xyxy": box.xyxy[0].tolist()})
    return elements


def _get_flat_spans(page, rect) -> list:
    return [
        span
        for bd in page.get_text("dict", clip=rect).get("blocks", [])
        for line in bd.get("lines", [])
        for span in line.get("spans", [])
    ]


def _build_exclude_rects(subs, zoom, shrink=5) -> list:
    result = []
    for sub in subs:
        if sub["name"] in _EXCLUDE_FROM_PRODUCT_INF:
            ex1, ey1, ex2, ey2 = sub["xyxy"]
            w_box, h_box = ex2 - ex1, ey2 - ey1
            if w_box > shrink * 2 and h_box > shrink * 2:
                ex1 += shrink; ey1 += shrink; ex2 -= shrink; ey2 -= shrink
            result.append((sub["name"], fitz.Rect(ex1/zoom, ey1/zoom, ex2/zoom, ey2/zoom)))
    return result


def _word_is_excluded(w, flat_spans, exclude_rects, product_block_nos: set) -> bool:
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    w_color = 0
    best_area = float("inf")
    for span in flat_spans:
        sx0, sy0, sx1, sy1 = span["bbox"]
        if sx0 - 2 <= cx <= sx1 + 2 and sy0 - 2 <= cy <= sy1 + 2:
            area = max(1.0, (sx1 - sx0) * (sy1 - sy0))
            if area < best_area:
                best_area = area
                w_color = span.get("color", 0)
    for ex_name, ex_rect in exclude_rects:
        if not (ex_rect.x0 <= cx <= ex_rect.x1 and ex_rect.y0 <= cy <= ex_rect.y1):
            continue
        word_text = w[4].strip()
        is_pure_text = bool(re.match(r'^[A-Za-zÀ-ÿ\-\'\:]+$', word_text))
        if ex_name in ("promo_fidelite", "logo") and w_color < 5_000_000:
            return False
        if ex_name == "price_per_piece":
            # Giữ lại nếu word thuộc cùng text block với product text (MIGNON nằm trong block PORC FILET ENTIER)
            # Exclude nếu thuộc block riêng của price box (Soit la portion environ)
            if w[5] in product_block_nos:
                return False
            return True
        if (ex_name == "price" and is_pure_text
                and (len(word_text) >= 2 or word_text in (":", "-"))
                and not any(word_text.lower() in pw for pw in PRICE_STOPWORDS)):
            return False
        return True
    return False


def _extract_product_text(page, rect, exclude_subs, zoom):
    exclude_rects = _build_exclude_rects(exclude_subs, zoom)
    flat_spans = _get_flat_spans(page, rect)

    all_words = page.get_text("words", clip=rect)

    # Pass 1: tìm block_nos có ít nhất 1 word NGOÀI tất cả exclude_rects
    # Đây là các "product text block" (block chứa tên sản phẩm như PORC FILET ENTIER)
    def _in_any_exclude(w):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        return any(
            ex_rect.x0 <= cx <= ex_rect.x1 and ex_rect.y0 <= cy <= ex_rect.y1
            for _, ex_rect in exclude_rects
        )

    product_block_nos = {w[5] for w in all_words if not _in_any_exclude(w)}

    # Pass 2: lọc words
    remaining_words = [
        w for w in all_words
        if not _word_is_excluded(w, flat_spans, exclude_rects, product_block_nos)
    ]

    lines_dict: dict = {}
    for w in remaining_words:
        lines_dict.setdefault((w[5], w[6]), []).append(w)

    valid_keys, line_texts = [], []
    for key in sorted(lines_dict.keys()):
        line_str = " ".join(x[4] for x in sorted(lines_dict[key], key=lambda x: x[0]))
        if re.search(r'offre.*valable.*sur.*le.*moins.*cher', line_str, re.IGNORECASE):
            continue
        valid_keys.append(key)
        line_texts.append(line_str)

    text_val = re.sub('￼', '', "\n".join(line_texts)).strip()

    rich_text = []
    for key in valid_keys:
        for w in sorted(lines_dict[key], key=lambda x: x[0]):
            wx, wy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
            w_size, w_bold = 0.0, False
            for span in flat_spans:
                sx0, sy0, sx1, sy1 = span["bbox"]
                if sx0 - 1 <= wx <= sx1 + 1 and sy0 - 1 <= wy <= sy1 + 1:
                    w_size = round(span["size"], 1)
                    flags = span.get("flags", 0)
                    font_name = span.get("font", "").lower()
                    w_bold = bool((flags & 16) or "bold" in font_name or "black" in font_name)
                    break
            rich_text.append({
                "text": w[4], "size": w_size, "bold": w_bold,
                "xyxy": [w[0]*zoom, w[1]*zoom, w[2]*zoom, w[3]*zoom],
            })
        rich_text.append({"text": "\n", "size": 0.0, "bold": False})

    # Replace size outliers: if a token is >2.5× the median, pin it to the median
    # of normal tokens (catches CTM-scaled decorative text with inflated nominal sizes)
    _all_sizes = [r["size"] for r in rich_text if r["size"] > 0]
    if _all_sizes:
        from statistics import median as _median
        _med = _median(_all_sizes)
        _cap = _med * 2.5
        if any(s > _cap for s in _all_sizes):
            _normal = [s for s in _all_sizes if s <= _cap]
            _fill = round(_median(_normal), 1) if _normal else round(_med, 1)
            for r in rich_text:
                if r["size"] > _cap:
                    r["size"] = _fill

    if rich_text and rich_text[-1]["text"] == "\n":
        rich_text.pop()

    sizes = [r["size"] for r in rich_text if r["size"] > 0]
    if sizes:
        from collections import Counter
        font_size = round(Counter(sizes).most_common(1)[0][0], 1)
    else:
        font_size = None
    is_bold = any(r["bold"] for r in rich_text)
    return text_val, rich_text, font_size, is_bold


def get_clean_lines_from_rect(page, rect, exclude_rects=None) -> list:
    words = page.get_text("words", clip=rect)
    if not words:
        return []

    remaining_words = []
    for w in words:
        cx = (w[0] + w[2]) / 2
        cy = (w[1] + w[3]) / 2
        if not exclude_rects or not any(
            r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 for r in exclude_rects
        ):
            remaining_words.append(w)

    if not remaining_words:
        return []

    lines_dict: dict = {}
    for w in remaining_words:
        lines_dict.setdefault((w[5], w[6]), []).append(w)

    cleaned_lines = []
    for key in sorted(lines_dict.keys()):
        l = " ".join(x[4] for x in sorted(lines_dict[key], key=lambda x: x[0])).strip()
        if not l:
            continue

        has_digit = any(c.isdigit() for c in l)
        words_in_line = re.findall(r'[a-zA-Zà-ÿ\-]+', l.lower())
        if not (has_digit or any(w in ALLOWED_PRICE_KEYWORDS for w in words_in_line)):
            continue

        cleaned = re.sub(r'\bA\b|(?<=\d)A|(?<=\s)A(?=\s|$)', ' ', l).strip()
        has_long_word = any(len(w) >= 3 and w.isalpha() for w in cleaned.split())
        if not has_long_word:
            cleaned = re.sub(r'\s+[a-zA-Z\*]+$', '', cleaned).strip()
        if not cleaned:
            continue

        parts = cleaned.split()
        if len(parts) > 1 and all(re.match(r'^\d+$|^[^\w\s]$|^€$', p) for p in parts):
            cleaned_lines.extend(parts)
        else:
            cleaned_lines.append(cleaned)

    result = []
    i = 0
    n = len(cleaned_lines)
    while i < n:
        curr = cleaned_lines[i]

        if i + 2 < n:
            l1, l2, l3 = curr, cleaned_lines[i+1], cleaned_lines[i+2]
            if (re.match(r'^\d+$', l1)
                    and (l2 in ('€', ',', '.') or re.match(r'^[^\d\s\w]$', l2))
                    and re.match(r'^\d+$', l3)):
                result.append(f"{l1} {l2} {l3}")
                i += 3
                continue

        if i + 1 < n:
            l1, l2 = curr, cleaned_lines[i+1]
            if re.match(r'^\d+$', l1) and re.match(r'^\d{1,2}$', l2):
                result.append(f"{l1} € {l2}")
                i += 2; continue
            if re.match(r'^\d+$', l1) and re.match(r'^€\d+$', l2):
                result.append(f"{l1} {l2}")
                i += 2; continue
            if re.match(r'^\d+€$', l1) and re.match(r'^\d+$', l2):
                result.append(f"{l1} {l2}")
                i += 2; continue

        result.append(curr)
        i += 1

    return result


def _build_sub_elements(subs, img_array) -> list:
    result = []
    for s in subs:
        sx1, sy1, sx2, sy2 = map(int, s["xyxy"])
        sx1, sy1 = max(0, sx1), max(0, sy1)
        sx2, sy2 = min(img_array.shape[1], sx2), min(img_array.shape[0], sy2)
        c_img = img_array[sy1:sy2, sx1:sx2]
        result.append({
            "name": s["name"],
            "xyxy": s["xyxy"],
            "crop_base64": encode_image_base64(c_img) if c_img.size > 0 else "",
        })
    return result


def _extract_prices(page, price_subs, promo_subs, zoom) -> tuple:
    price_subs = sorted(price_subs, key=lambda s: s["xyxy"][1])
    price_xyxy = price_subs[0]["xyxy"] if price_subs else None
    prices = []
    promo_exclude = [
        fitz.Rect(s["xyxy"][0]/zoom, s["xyxy"][1]/zoom,
                  s["xyxy"][2]/zoom, s["xyxy"][3]/zoom)
        for s in promo_subs
    ]
    for sub in price_subs:
        sx1, sy1, sx2, sy2 = sub["xyxy"]
        rect = fitz.Rect(sx1/zoom, sy1/zoom, sx2/zoom, sy2/zoom)
        lines = get_clean_lines_from_rect(page, rect, exclude_rects=promo_exclude)
        px = re.sub(r'\s+', ' ', "\n".join(lines)).strip()
        if px:
            prices.append(px)
    return " | ".join(prices), price_xyxy


def _finalise_block_text(page, block_rect, text_val, promo_text, rich_text, block_full_text_raw):
    block_full_text = re.sub('￼', '',
                              page.get_text("text", clip=block_rect)).strip()

    if not text_val:
        text_val = block_full_text

    if promo_text:
        for pl in [l.strip() for l in promo_text.split('\n') if l.strip()]:
            if len(pl) >= 2:
                pat = r'\s+'.join(re.escape(w) for w in pl.split())
                text_val = re.sub(pat, "", text_val, flags=re.IGNORECASE).strip()

    text_val = re.sub(r'\s+', ' ', re.sub(r'\b\d{5}\b', '', text_val)).strip()
    if rich_text:
        rich_text = [w for w in rich_text if not re.search(r'\b\d{5}\b', w.get("text", ""))]

    text_val, rich_text = strip_boilerplate(text_val, rich_text)
    block_full_text = re.sub(r'\s+', ' ', re.sub(r'\b\d{5}\b', '', block_full_text)).strip()
    block_full_text, _ = strip_boilerplate(block_full_text, None)

    return text_val, rich_text, block_full_text


def _process_single_block(page, doc, p_idx, b, candidate_subs, crop, img_array,
                           block_rect, pdv_code, zoom):
    bx1, by1, bx2, by2 = b["xyxy"]

    text_val, rich_text, font_size, is_bold = "", [], None, False
    product_inf_xyxy = None
    promo_text, promo_xyxy = "", None

    for sub in candidate_subs:
        if sub["name"] == "product_inf":
            product_inf_xyxy = sub["xyxy"]
            sx1, sy1, sx2, sy2 = sub["xyxy"]
            ex_x1 = max(bx1, sx1 - 30)
            ex_x2 = min(bx2, sx2 + 30)
            rect = fitz.Rect(ex_x1/zoom, sy1/zoom, ex_x2/zoom, sy2/zoom)
            exclude_subs = [s for s in candidate_subs if s["name"] in _EXCLUDE_FROM_PRODUCT_INF]
            text_val, rich_text, font_size, is_bold = _extract_product_text(
                page, rect, exclude_subs, zoom
            )

        if sub["name"] == "promo_fidelite":
            promo_xyxy = sub["xyxy"]
            sx1, sy1, sx2, sy2 = sub["xyxy"]
            raw = page.get_text("text", clip=fitz.Rect(sx1/zoom, sy1/zoom, sx2/zoom, sy2/zoom)).strip()
            promo_text = re.sub('￼', '', raw).strip()

    price_subs = [s for s in candidate_subs if s["name"] == "price"]
    promo_subs = [s for s in candidate_subs if s["name"] == "promo_fidelite"]
    price_val, price_xyxy = _extract_prices(page, price_subs, promo_subs, zoom)

    if price_val:
        logger.debug("Page %d extracted price: %.100s", p_idx, price_val)

    text_val, rich_text, block_full_text = _finalise_block_text(
        page, block_rect, text_val, promo_text, rich_text, None
    )

    if not candidate_subs and not text_val.strip():
        return None

    return {
        "page_idx": p_idx,
        "img_w": img_array.shape[1], "img_h": img_array.shape[0],
        "xyxy": b["xyxy"],
        "text": text_val, "rich_text": rich_text,
        "price": price_val, "block_full_text": block_full_text,
        "pdv_code": pdv_code, "crop": crop,
        "sub_classes": [s["name"] for s in candidate_subs],
        "sub_elements": _build_sub_elements(candidate_subs, img_array),
        "price_xyxy": price_xyxy, "product_inf_xyxy": product_inf_xyxy,
        "promo_text": promo_text, "promo_xyxy": promo_xyxy,
        "font_size": font_size, "is_bold": is_bold,
        "embedded_images": get_images_in_block(doc, p_idx, b["xyxy"], zoom, img_array),
        "raw_words": [
            {"text": w[4], "rect": [c * zoom for c in w[:4]]}
            for w in sorted(page.get_text("words", clip=block_rect), key=lambda x: (x[5], x[6], x[7]))
        ],
    }


def _process_multi_block(page, doc, p_idx, b, candidate_subs, distinct_product_infs,
                          img_array, pdv_code, zoom):
    bx1, by1, bx2, by2 = b["xyxy"]

    sub_groups = {id(p): [] for p in distinct_product_infs}
    for sub in candidate_subs:
        if sub["name"] == "product_inf":
            continue
        scx = (sub["xyxy"][0] + sub["xyxy"][2]) / 2
        scy = (sub["xyxy"][1] + sub["xyxy"][3]) / 2
        best_p = min(
            distinct_product_infs,
            key=lambda p: ((scx - (p["xyxy"][0] + p["xyxy"][2]) / 2) ** 2
                           + (scy - (p["xyxy"][1] + p["xyxy"][3]) / 2) ** 2)
        )
        sub_groups[id(best_p)].append(sub)

    records = []
    for p in distinct_product_infs:
        group_subs = sub_groups[id(p)]
        all_subs = [p] + group_subs

        p_xyxy = list(p["xyxy"])
        for sub in group_subs:
            p_xyxy[0] = min(p_xyxy[0], sub["xyxy"][0])
            p_xyxy[1] = min(p_xyxy[1], sub["xyxy"][1])
            p_xyxy[2] = max(p_xyxy[2], sub["xyxy"][2])
            p_xyxy[3] = max(p_xyxy[3], sub["xyxy"][3])

        vbx1 = max(0, int(p_xyxy[0]))
        vby1 = max(0, int(p_xyxy[1]))
        vbx2 = min(img_array.shape[1], int(p_xyxy[2]))
        vby2 = min(img_array.shape[0], int(p_xyxy[3]))
        v_crop = img_array[vby1:vby2, vbx1:vbx2]
        v_block_rect = fitz.Rect(vbx1/zoom, vby1/zoom, vbx2/zoom, vby2/zoom)

        sx1, sy1, sx2, sy2 = p["xyxy"]
        ex_x1 = max(vbx1, sx1 - 30)
        ex_x2 = min(vbx2, sx2 + 30)
        v_rect = fitz.Rect(ex_x1/zoom, sy1/zoom, ex_x2/zoom, sy2/zoom)
        exclude_subs = [s for s in group_subs if s["name"] in _EXCLUDE_FROM_PRODUCT_INF]
        text_val, rich_text, font_size, is_bold = _extract_product_text(page, v_rect, exclude_subs, zoom)

        promo_text, promo_xyxy = "", None
        for s in group_subs:
            if s["name"] == "promo_fidelite":
                promo_xyxy = s["xyxy"]
                raw = page.get_text("text", clip=fitz.Rect(
                    s["xyxy"][0]/zoom, s["xyxy"][1]/zoom,
                    s["xyxy"][2]/zoom, s["xyxy"][3]/zoom
                )).strip()
                promo_text = re.sub('￼', '', raw).strip()

        price_subs = [s for s in group_subs if s["name"] == "price"]
        promo_subs = [s for s in group_subs if s["name"] == "promo_fidelite"]
        price_val, price_xyxy = _extract_prices(page, price_subs, promo_subs, zoom)

        text_val, rich_text, block_full_text = _finalise_block_text(
            page, v_block_rect, text_val, promo_text, rich_text, None
        )

        records.append({
            "page_idx": p_idx,
            "img_w": img_array.shape[1], "img_h": img_array.shape[0],
            "xyxy": p_xyxy,
            "text": text_val, "rich_text": rich_text,
            "price": price_val, "block_full_text": block_full_text,
            "pdv_code": pdv_code, "crop": v_crop,
            "sub_classes": [s["name"] for s in all_subs],
            "sub_elements": _build_sub_elements(all_subs, img_array),
            "price_xyxy": price_xyxy, "product_inf_xyxy": p["xyxy"],
            "promo_text": promo_text, "promo_xyxy": promo_xyxy,
            "font_size": font_size, "is_bold": is_bold,
            "embedded_images": get_images_in_block(doc, p_idx, p_xyxy, zoom, img_array),
            "raw_words": [
                {"text": w[4], "rect": [c * zoom for c in w[:4]]}
                for w in sorted(page.get_text("words", clip=v_block_rect), key=lambda x: (x[5], x[6], x[7]))
            ],
        })
    return records


def extract_all_blocks(doc, model, zoom=2.0, conf_thresh=0.25, iou_thresh=0.45, pages=None):
    all_processed_blocks = []

    PRIORITY_MAP = {"promo_fidelite": 10, "product_inf": 8, "price": 8, "logo": 1}
    min_px = 113.38 * zoom

    page_range = pages if pages is not None else range(len(doc))
    for p_idx in page_range:
        page = doc.load_page(p_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

        res = model.predict(source=img_array, conf=conf_thresh, iou=iou_thresh, imgsz=1024, verbose=False)
        elements = parse_results(res, MAIN_CLASS_NAMES)

        blocks = [
            e for e in elements
            if e["name"] == "Product_block"
            and (e["xyxy"][2] - e["xyxy"][0]) > min_px
            and (e["xyxy"][3] - e["xyxy"][1]) > min_px
        ]
        subs = [e for e in elements if e["name"] != "Product_block"]

        blocks = filter_overlapping_blocks(blocks, iou_threshold=0.9, priority_map=PRIORITY_MAP)
        subs = filter_overlapping_blocks(subs, iou_threshold=0.9, priority_map=PRIORITY_MAP)

        for b in blocks:
            bx1, by1, bx2, by2 = map(int, b["xyxy"])
            crop = img_array[max(0, by1):max(0, by2), max(0, bx1):max(0, bx2)]
            block_rect = fitz.Rect(bx1/zoom, by1/zoom, bx2/zoom, by2/zoom)

            pdv_codes = [
                code
                for bd in page.get_text("dict", clip=block_rect).get("blocks", [])
                for line in bd.get("lines", [])
                for span in line.get("spans", [])
                if span.get("color", 0) > 15_000_000
                for code in re.findall(r'\b\d{5}\b', span.get("text", "").strip())
            ]
            pdv_code = pdv_codes[0] if pdv_codes else None

            candidate_subs = [s for s in subs if is_inside(s["xyxy"], b["xyxy"])]

            raw_infs = [s for s in candidate_subs if s["name"] == "product_inf"]
            distinct_infs = []
            for p in sorted(raw_infs, key=lambda x: x["conf"], reverse=True):
                x1_A, y1_A, x2_A, y2_A = p["xyxy"]
                w_A = x2_A - x1_A
                duplicate = False
                for dp in distinct_infs:
                    x1_B, _, x2_B, _ = dp["xyxy"]
                    w_B = x2_B - x1_B
                    overlap_x = max(0, min(x2_A, x2_B) - max(x1_A, x1_B))
                    if (overlap_x / min(w_A, w_B) > 0.5 if min(w_A, w_B) > 0 else False) \
                            or calculate_iou(p["xyxy"], dp["xyxy"]) > 0.3:
                        duplicate = True
                        break
                if not duplicate:
                    distinct_infs.append(p)

            if len(distinct_infs) <= 1:
                record = _process_single_block(
                    page, doc, p_idx, b, candidate_subs, crop, img_array,
                    block_rect, pdv_code, zoom
                )
                if record is not None:
                    all_processed_blocks.append(record)
            else:
                all_processed_blocks.extend(
                    _process_multi_block(
                        page, doc, p_idx, b, candidate_subs, distinct_infs,
                        img_array, pdv_code, zoom
                    )
                )

        # ── Footer extraction ──────────────────────────────────────────────
        f_y0 = page.rect.height * 0.92
        is_spread = page.rect.width > page.rect.height * 1.1
        footer_rects = (
            [(fitz.Rect(0, f_y0, page.rect.width / 2, page.rect.height), "left"),
             (fitz.Rect(page.rect.width / 2, f_y0, page.rect.width, page.rect.height), "right")]
            if is_spread
            else [(fitz.Rect(0, f_y0, page.rect.width, page.rect.height), "full")]
        )

        for f_rect, f_side in footer_rects:
            f_words = page.get_text("words", clip=f_rect)
            if not f_words:
                continue
            f_text_val = re.sub('￼', '',
                                page.get_text("text", clip=f_rect)).strip()
            if not f_text_val:
                continue

            f_lines_dict: dict = {}
            for w in f_words:
                if w[4].strip():
                    f_lines_dict.setdefault((w[5], w[6]), []).append(w)

            f_flat_spans = _get_flat_spans(page, f_rect)
            f_rich_text = []
            for key in sorted(f_lines_dict.keys()):
                for w in sorted(f_lines_dict[key], key=lambda x: x[0]):
                    wx, wy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
                    w_size, w_bold = 0.0, False
                    for span in f_flat_spans:
                        sx0, sy0, sx1, sy1 = span["bbox"]
                        if sx0 - 1 <= wx <= sx1 + 1 and sy0 - 1 <= wy <= sy1 + 1:
                            w_size = round(span["size"], 1)
                            flags = span.get("flags", 0)
                            font_name = span.get("font", "").lower()
                            w_bold = bool((flags & 16) or "bold" in font_name or "black" in font_name)
                            break
                    f_rich_text.append({
                        "text": w[4], "size": w_size, "bold": w_bold,
                        "xyxy": [w[0]*zoom, w[1]*zoom, w[2]*zoom, w[3]*zoom],
                    })
                f_rich_text.append({"text": "\n", "size": 0.0, "bold": False})
            if f_rich_text and f_rich_text[-1]["text"] == "\n":
                f_rich_text.pop()

            f_crop_img = None
            try:
                f_crop_img = get_reconstructed_block_image(
                    doc, p_idx,
                    [f_rect.x0*zoom, f_rect.y0*zoom, f_rect.x1*zoom, f_rect.y1*zoom],
                    zoom, img_array,
                )
            except Exception:
                pass
            if f_crop_img is None:
                pix2 = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=f_rect)
                f_crop_img = np.frombuffer(pix2.samples, dtype=np.uint8).reshape(pix2.h, pix2.w, pix2.n)
                if pix2.n == 4:
                    f_crop_img = cv2.cvtColor(f_crop_img, cv2.COLOR_RGBA2RGB)

            f_sizes = [r["size"] for r in f_rich_text if r["size"] > 0]
            all_processed_blocks.append({
                "is_footer": True, "footer_side": f_side,
                "page_idx": p_idx,
                "img_w": img_array.shape[1], "img_h": img_array.shape[0],
                "xyxy": [f_rect.x0*zoom, f_rect.y0*zoom, f_rect.x1*zoom, f_rect.y1*zoom],
                "text": f_text_val, "rich_text": f_rich_text,
                "price": "", "block_full_text": f_text_val,
                "pdv_code": "", "crop": f_crop_img,
                "sub_classes": [], "sub_elements": [],
                "price_xyxy": [], "product_inf_xyxy": [],
                "promo_text": "", "promo_xyxy": [],
                "font_size": round(max(f_sizes), 1) if f_sizes else 0,
                "is_bold": any(r["bold"] for r in f_rich_text),
                "embedded_images": [], "raw_words": [],
            })

    return all_processed_blocks, {}, []
