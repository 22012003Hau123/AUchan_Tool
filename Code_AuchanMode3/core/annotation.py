import copy
import io
import logging
import re
import textwrap
from collections import defaultdict
from difflib import SequenceMatcher

import base64
import fitz
import numpy as np
from PIL import Image

from .text_utils import clean_text_for_matching
from .utils import encode_image_base64
from .vlm import _VLM_VERIFY_CLASSES, verify_missing_elements_via_vlm

logger = logging.getLogger(__name__)


def text_diff_label(text_a, text_b) -> str:
    def flatten(t):
        return re.sub(r'\s+', ' ', t).strip()[:60] or "(trống)"
    return f"{flatten(text_a)} → {flatten(text_b)}"


def get_word_diff(ta, tb) -> str:
    ta_c = re.sub(r'\s+', ' ', ta).strip()
    tb_c = re.sub(r'\s+', ' ', tb).strip()
    words_a, words_b = ta_c.split(), tb_c.split()
    matcher = SequenceMatcher(None, words_a, words_b)

    sai, thieu = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            sai.append(" ".join(words_a[i1:i2]))
            thieu.append(" ".join(words_b[j1:j2]))
        elif tag == 'delete':
            sai.append(" ".join(words_a[i1:i2]))
        elif tag == 'insert':
            thieu.append(" ".join(words_b[j1:j2]))

    def colorize(items):
        return [f'<span style="color:#e74c3c;font-weight:bold;">{x}</span>' for x in items]

    parts = [
        f"Fini: {', '.join(colorize(sai)) if sai else '(trống)'}",
        f"Assembla: {', '.join(colorize(thieu)) if thieu else '(trống)'}",
    ]
    res = " | ".join(parts)
    if not sai and not thieu and ta_c != tb_c:
        return (f'Fini: <span style="color:#e74c3c;font-weight:bold;">{ta_c}</span>'
                f' | Assembla: <span style="color:#e74c3c;font-weight:bold;">{tb_c}</span>')
    return res


def format_block_for_json(block):
    return {
        "page_idx": block["page_idx"],
        "xyxy": block["xyxy"],
        "text": block["text"] if block["text"] else block["block_full_text"],
        "rich_text": block.get("rich_text", []),
        "promo_text": block.get("promo_text", ""),
        "price": block["price"],
        "pdv_code": block["pdv_code"],
        "sub_classes": block["sub_classes"],
        "sub_elements": block.get("sub_elements", []),
        "font_size": block["font_size"],
        "is_bold": block["is_bold"],
        "image_base64": encode_image_base64(block["crop"]),
    }


def get_fini_annotations(ba, bb, match_method):
    raw_name_log = (ba.get("text") or ba.get("block_full_text") or "?")[:50]
    logger.info("[ANNOT-ENTRY] product='%s' | match_method='%s'", raw_name_log, match_method)

    annotations = []
    subs_a = ba.get("sub_elements", [])
    subs_b = bb.get("sub_elements", [])

    dict_a: dict = defaultdict(list)
    dict_b: dict = defaultdict(list)
    for s in subs_a:
        dict_a[s["name"]].append(s)
    for s in subs_b:
        dict_b[s["name"]].append(s)

    def _load_b64(b64_str):
        if not b64_str:
            return None
        try:
            return Image.open(io.BytesIO(base64.b64decode(b64_str))).convert('RGB')
        except Exception:
            return None

    def _ncc(img1, img2) -> float:
        if img1 is None or img2 is None:
            return 0.0
        try:
            a1 = np.array(img1.resize((32, 32)).convert('L'), dtype=np.float32)
            a2 = np.array(img2.resize((32, 32)).convert('L'), dtype=np.float32)
            a1 -= np.mean(a1); a2 -= np.mean(a2)
            s1, s2 = np.std(a1), np.std(a2)
            if s1 < 1e-5 or s2 < 1e-5:
                return 1.0 - abs(np.mean(a1) - np.mean(a2)) / 255.0 if s1 < 1e-5 and s2 < 1e-5 else 0.0
            return float(np.mean((a1 / s1) * (a2 / s2)))
        except Exception as exc:
            logger.debug("NCC exception: %s", exc)
            return 0.0

    def _align(list_a, list_b):
        if not list_a or not list_b:
            return list_a, list_b
        imgs_a = [_load_b64(x.get("crop_base64")) for x in list_a]
        imgs_b = [_load_b64(x.get("crop_base64")) for x in list_b]
        sim = [[abs(_ncc(ia, ib)) for ib in imgs_b] for ia in imgs_a]
        used_a, used_b = set(), set()
        pairs = sorted(
            [(sim[i][j], i, j) for i in range(len(list_a)) for j in range(len(list_b))],
            reverse=True,
        )
        matched_pairs = []
        for score, i, j in pairs:
            if i not in used_a and j not in used_b:
                matched_pairs.append((i, j))
                used_a.add(i); used_b.add(j)
        al_a = ([list_a[i] for i, _ in matched_pairs]
                + [list_a[i] for i in range(len(list_a)) if i not in used_a])
        al_b = ([list_b[j] for _, j in matched_pairs]
                + [list_b[j] for j in range(len(list_b)) if j not in used_b])
        return al_a, al_b

    raw_name = ba.get("text") or ba.get("block_full_text") or "?"
    clean_name = clean_text_for_matching(raw_name, is_product_inf="product_inf" in ba.get("sub_classes", []))
    product_name = (clean_name or raw_name)[:40]
    all_classes = set(dict_a) | set(dict_b)
    diff_count = 0

    for cls_name in all_classes:
        al_a, al_b = _align(dict_a.get(cls_name, []), dict_b.get(cls_name, []))
        dict_a[cls_name], dict_b[cls_name] = al_a, al_b
        cnt_a, cnt_b = len(al_a), len(al_b)

        if cnt_a == cnt_b:
            continue

        diff_count += 1
        direction = "THỪA" if cnt_a > cnt_b else "THIẾU"
        action = "→ gọi VLM" if cls_name in _VLM_VERIFY_CLASSES else "→ ghi annotation (không qua VLM)"
        logger.info(
            "[SUB-DIFF] product='%s' | class='%s' | Fini=%d Assembla=%d | Fini %s %s",
            product_name, cls_name, cnt_a, cnt_b, direction, action,
        )

        if cls_name in _VLM_VERIFY_CLASSES:
            # Gọi VLM từng element riêng — crop của bên NHIỀU + full block của bên ÍT
            if cnt_a > cnt_b:
                for el in al_a[cnt_b:]:
                    vlm_result = verify_missing_elements_via_vlm(el, bb, cls_name)
                    if vlm_result is False:
                        logger.info("[SUB-CHECK] class='%s' → lệch thực → annotation đỏ", cls_name)
                        annotations.append({"type": "delete", "xyxy": el["xyxy"],
                                             "label": "del", "color": "#c0392b"})
                    elif vlm_result is True:
                        logger.info("[SUB-CHECK] class='%s' → YOLO miss → cân bằng Assembla", cls_name)
                        al_b.append(copy.deepcopy(el))
                    else:
                        logger.info("[SUB-CHECK] class='%s' → API fail → bỏ qua", cls_name)
                dict_a[cls_name], dict_b[cls_name] = al_a, al_b
            else:
                x1_b, y1_b, x2_b, y2_b = ba["xyxy"]
                indicator_y = y2_b - 5
                insert_idx = 0
                for el in al_b[cnt_a:]:
                    vlm_result = verify_missing_elements_via_vlm(el, ba, cls_name)
                    if vlm_result is False:
                        logger.info("[SUB-CHECK] class='%s' → lệch thực → annotation cam", cls_name)
                        annotations.append({
                            "type": "insert",
                            "xyxy": [x1_b + insert_idx*50, indicator_y,
                                     x1_b + 40 + insert_idx*50, indicator_y + 15],
                            "label": f"miss: {cls_name}", "color": "#f39c12",
                        })
                        insert_idx += 1
                    elif vlm_result is True:
                        logger.info("[SUB-CHECK] class='%s' → YOLO miss → cân bằng Fini", cls_name)
                        al_a.append(copy.deepcopy(el))
                    else:
                        logger.info("[SUB-CHECK] class='%s' → API fail → bỏ qua", cls_name)
                dict_a[cls_name], dict_b[cls_name] = al_a, al_b
            continue

        # Class không qua VLM → annotate thẳng
        if cnt_a > cnt_b:
            logger.info("[ANNOTATION] class='%s' | Fini DƯ %d → đỏ", cls_name, cnt_a - cnt_b)
            for el in al_a[cnt_b:]:
                annotations.append({"type": "delete", "xyxy": el["xyxy"],
                                     "label": "del", "color": "#c0392b"})
        elif cnt_b > cnt_a:
            logger.info("[ANNOTATION] class='%s' | Fini THIẾU %d → cam", cls_name, cnt_b - cnt_a)
            x1_b, y1_b, x2_b, y2_b = ba["xyxy"]
            indicator_y = y2_b - 5
            for i in range(cnt_b - cnt_a):
                annotations.append({
                    "type": "insert",
                    "xyxy": [x1_b + i*50, indicator_y, x1_b + 40 + i*50, indicator_y + 15],
                    "label": f"miss: {cls_name}", "color": "#f39c12",
                })

    logger.info(
        "[SUB-SUMMARY] product='%s' | classes checked=%d | diffs=%d | annotations=%d",
        product_name, len(all_classes), diff_count, len(annotations),
    )

    new_subs_a, new_subs_b = [], []
    for cls_name in sorted(all_classes):
        new_subs_a.extend(dict_a[cls_name])
        new_subs_b.extend(dict_b[cls_name])
    ba["sub_elements"] = new_subs_a
    bb["sub_elements"] = new_subs_b
    ba["sub_classes"] = [s["name"] for s in new_subs_a]
    bb["sub_classes"] = [s["name"] for s in new_subs_b]

    return annotations


def html_to_pdf_popup(label, color) -> str:
    color_titles = {
        '#e74c3c': '❌ ', '#9b59b6': '💲 ',
        '#e67e22': '🏷 ', '#f39c12': '📦 ',
    }
    prefix = color_titles.get(color, '🔍 DIFF')

    text = re.sub(r'<span[^>]*>(.*?)</span>', r'【\1】', label, flags=re.DOTALL)
    text = re.sub(r'<em>(.*?)</em>', r'【\1】', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'\1', text, flags=re.DOTALL)
    text = (text.replace('&amp;', '&').replace('&lt;', '<')
                .replace('&gt;', '>').replace('&nbsp;', ' '))

    text = re.sub(r'(?i)\b(assembla:?)', r'\n\1', text)
    text = re.sub(r'(?i)\b(fini:?)', r'\n\1', text)
    text = re.sub(r'<[^>]+>', '\n', text)

    raw_lines = [l.strip() for l in text.split('\n') if l.strip()]
    fini_parts, assembla_parts = [], []
    current_target = None

    for line in raw_lines:
        ll = line.lower()
        if 'fini:' in ll or ll.rstrip(':') == 'fini':
            current_target = 'fini'
            content = re.sub(r'(?i)^fini:?\s*', '', line).strip()
            if content:
                fini_parts.append(content)
        elif 'assembla:' in ll or ll.rstrip(':') == 'assembla':
            current_target = 'assembla'
            content = re.sub(r'(?i)^assembla:?\s*', '', line).strip()
            if content:
                assembla_parts.append(content)
        elif line in ('→', '➔', '->', '|'):
            continue
        else:
            cleaned = re.sub(r'^\|\s*|\s*\|$', '', line).strip()
            if cleaned:
                if current_target == 'fini':
                    fini_parts.append(cleaned)
                elif current_target == 'assembla':
                    assembla_parts.append(cleaned)
                else:
                    fini_parts.append(cleaned)

    def clean_parts(parts):
        return [
            re.sub(r'^\|\s*|\s*\|$', '', p.replace('【】', '').replace('【 】', '')).strip()
            for p in parts
            if re.sub(r'^\|\s*|\s*\|$', '', p.replace('【】', '').replace('【 】', '')).strip() not in ('', '|')
        ]

    fini_parts = clean_parts(fini_parts)
    assembla_parts = clean_parts(assembla_parts)

    body_lines = []
    if fini_parts:
        body_lines.append("fi:")
        for part in fini_parts:
            body_lines.extend(f"  {l}" for l in textwrap.wrap(part, width=50))
    if assembla_parts:
        body_lines.append("as:")
        for part in assembla_parts:
            body_lines.extend(f"  {l}" for l in textwrap.wrap(part, width=50))
    if not body_lines:
        body_lines.append("\n".join(textwrap.wrap(
            " ".join(raw_lines).replace('【】', '').replace('【 】', '').strip(), width=50
        )))

    return f"{prefix.strip()}\n" + "\n".join(body_lines)


def annotate_pdf(doc, page_annotations, zoom):
    for p_idx, annots in page_annotations.items():
        if p_idx >= len(doc):
            continue
        page = doc[p_idx]
        for ann in annots:
            color = ann.get("color", "#e74c3c")
            r_val = int(color[1:3], 16) / 255.0
            g_val = int(color[3:5], 16) / 255.0
            b_val = int(color[5:7], 16) / 255.0
            ann_type = ann.get("type", "replace")

            if ann_type in ("replace", "delete"):
                for rect_coords in ann.get("rects", []):
                    x1, y1, x2, y2 = rect_coords
                    pad = 2
                    pdf_rect = fitz.Rect(x1/zoom - pad, y1/zoom - pad, x2/zoom + pad, y2/zoom + pad)
                    annot = page.add_rect_annot(pdf_rect)
                    if ann_type == "replace":
                        annot.set_colors(stroke=(0.4, 0.4, 0.9), fill=(0.4, 0.4, 0.9))
                        annot.set_info(title="Diff", content=f"Thay vì: {ann['label']}")
                    else:
                        annot.set_colors(stroke=(0.9, 0.2, 0.2), fill=(0.9, 0.2, 0.2))
                        annot.set_info(title="Diff", content="Dư từ này")
                    annot.set_opacity(0.3)
                    annot.set_border(width=1.5)
                    annot.update()

            elif ann_type == "insert":
                x1, y1, x2, y2 = ann["xyxy"]
                pdf_rect = fitz.Rect(x1/zoom, y1/zoom, x1/zoom + 40, y2/zoom)
                annot = page.add_rect_annot(pdf_rect)
                annot.set_colors(stroke=(0.9, 0.5, 0.0), fill=(0.9, 0.5, 0.0))
                annot.set_opacity(0.5)
                annot.set_border(width=2.0, dashes=[3])
                annot.set_info(title="Diff", content=ann["label"])
                annot.update()

            else:
                x1, y1, x2, y2 = ann.get("xyxy", [0, 0, 0, 0])
                pdf_rect = fitz.Rect(x1/zoom, y1/zoom, x2/zoom, y2/zoom)
                pdf_annot = page.add_rect_annot(pdf_rect)
                pdf_annot.set_colors(stroke=(r_val, g_val, b_val))
                pdf_annot.set_border(width=1.0, dashes=[2])
                pdf_annot.set_info(title="", content=html_to_pdf_popup(ann["label"], color))
                pdf_annot.update()
