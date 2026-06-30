"""
engine.py — Orchestration layer for the Auchan PDF comparison pipeline.

Split layout:
  utils.py       — geometry + image encoding helpers
  text_utils.py  — text cleaning, price extraction helpers, constants
  pdf_utils.py   — PDF image reconstruction helpers
  blocks.py      — YOLO inference, block extraction, OCR
  vlm.py         — NVIDIA VLM sub-element verification
  matching.py    — two-phase block matching (text + VLM)
  annotation.py  — diff generation and PDF annotation writing
  engine.py      — cache, MD5, cleanup, run_comparison()
"""
import copy
import glob
import hashlib
import logging
import os
import pickle
import shutil
import threading
import time
import uuid

import fitz

from .annotation import annotate_pdf, format_block_for_json, get_fini_annotations
from .blocks import extract_all_blocks
from .matching import match_product_blocks_global

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "assembla_cache.pkl")
CACHE_VERSION = 38  # bumped: use visual bbox height for CTM-scaled text instead of nominal span size

CACHE_LOCK = threading.Lock()


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            logger.warning("Failed to load block cache: %s", exc)
    return {}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(cache, f)
    except Exception as exc:
        logger.warning("Failed to save block cache: %s", exc)


ASSEMBLA_CACHE: dict = _load_cache()


def get_file_md5(file_path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def cleanup_temp_files():
    temp_dir = "static/temp"
    if not os.path.exists(temp_dir):
        return
    cutoff = time.time() - 3600
    for f in glob.glob(os.path.join(temp_dir, "*.pdf")):
        try:
            if os.stat(f).st_mtime < cutoff:
                os.remove(f)
        except Exception as exc:
            logger.debug("Temp cleanup error: %s", exc)


def run_comparison(path_a, path_b, model, zoom=2.0, conf_thresh=0.25, iou_thresh=0.45,
                   assembla_hash=None):
    doc_a = fitz.open(path_a)
    doc_b = fitz.open(path_b)

    blocks_a, _, _ = extract_all_blocks(doc_a, model, zoom, conf_thresh, iou_thresh)

    cache_key = None
    try:
        b_hash = assembla_hash or get_file_md5(path_b)
        model_id = (getattr(model, "ckpt_path", "") or getattr(model, "pt_path", "")
                    or model.__class__.__name__)
        cache_key = (b_hash, model_id, zoom, conf_thresh, iou_thresh, CACHE_VERSION)
    except Exception as exc:
        logger.warning("Could not build Assembla cache key: %s", exc)

    blocks_b = None
    if cache_key:
        with CACHE_LOCK:
            cached = ASSEMBLA_CACHE.get(cache_key)
            if cached is not None:
                if cached and "rich_text" not in cached[0]:
                    logger.warning("Cache invalid (missing 'rich_text') for %s — rebuilding.", b_hash)
                    del ASSEMBLA_CACHE[cache_key]
                else:
                    logger.info("Cache hit for Assembla PDF %s", b_hash)
                    blocks_b = copy.deepcopy(cached)

    if blocks_b is None:
        logger.info("Cache miss — running inference on Assembla PDF…")
        blocks_b, _, _ = extract_all_blocks(doc_b, model, zoom, conf_thresh, iou_thresh)
        if cache_key and doc_b.page_count > 10:
            with CACHE_LOCK:
                ASSEMBLA_CACHE[cache_key] = copy.deepcopy(blocks_b)
                while len(ASSEMBLA_CACHE) > 50:
                    del ASSEMBLA_CACHE[next(iter(ASSEMBLA_CACHE))]
                _save_cache(ASSEMBLA_CACHE)

    footers_a = [b for b in blocks_a if b.get("is_footer")]
    footers_b = [b for b in blocks_b if b.get("is_footer")]
    blocks_a = [b for b in blocks_a if not b.get("is_footer")]
    blocks_b = [b for b in blocks_b if not b.get("is_footer")]

    matched, un_a, un_b = match_product_blocks_global(blocks_a, blocks_b)

    page_mapping: dict = {}
    for ba, bb, method in matched:
        pa = ba["page_idx"]
        pb = bb["page_idx"]
        bb_cx = (bb["xyxy"][0] + bb["xyxy"][2]) / 2
        b_side = "full"
        if bb["img_w"] > bb["img_h"] * 1.1:
            b_side = "left" if bb_cx < bb["img_w"] / 2 else "right"
        page_mapping.setdefault(pa, {}).setdefault((pb, b_side), 0)
        page_mapping[pa][(pb, b_side)] += 1

    resolved = {pa: max(targets, key=targets.get) for pa, targets in page_mapping.items()}

    for fa in footers_a:
        pa = fa["page_idx"]
        matched_fb = None
        if pa in resolved:
            target_pb, target_side = resolved[pa]
            matched_fb = next(
                (fb for fb in footers_b
                 if fb["page_idx"] == target_pb
                 and fb.get("footer_side") == target_side
                 and not fb.get("matched")),
                None,
            )
        if matched_fb:
            matched_fb["matched"] = True
            matched.append((fa, matched_fb, "footer"))
        else:
            un_a.append(fa)

    for fb in footers_b:
        if not fb.get("matched"):
            un_b.append(fb)

    fini_pdv_pages = sorted({b["page_idx"] + 1 for b in blocks_a if b.get("pdv_code")})

    page_annotations_a: dict = {}
    page_annotations_b: dict = {}

    formatted_matched = []
    for ba, bb, method in matched:
        if method == "footer":
            continue

        annotations = get_fini_annotations(ba, bb, method)
        has_diff = bool(annotations)

        for ann in annotations:
            page_annotations_a.setdefault(ba["page_idx"], []).append(ann)

        formatted_matched.append({
            "method": method, "has_diff": has_diff,
            "fini": format_block_for_json(ba),
            "assembla": format_block_for_json(bb),
            "differences": [
                {"label": a["label"], "html": a.get("html", False), "color": a["color"]}
                for a in annotations
            ],
        })

    formatted_un_a = []
    for ba in un_a:
        formatted_un_a.append(format_block_for_json(ba))
        page_annotations_a.setdefault(ba["page_idx"], []).append({
            "xyxy": ba["xyxy"],
            "label": (f"Fini: {ba['text'] or ba['block_full_text'] or '(Không có text)'}"
                      f"<br>➔ Không tìm thấy block tương ứng bên Assembla (Unmatched Fini)"),
            "html": True, "color": "#e74c3c",
        })

    cleanup_temp_files()
    os.makedirs("static/temp", exist_ok=True)
    unique_id = uuid.uuid4().hex

    annotate_pdf(doc_a, page_annotations_a, zoom)
    annotate_pdf(doc_b, page_annotations_b, zoom)

    out_a = f"static/temp/annotated_fini_{unique_id}.pdf"
    out_b = f"static/temp/annotated_assembla_{unique_id}.pdf"
    raw_a = f"static/temp/raw_fini_{unique_id}.pdf"
    raw_b = f"static/temp/raw_assembla_{unique_id}.pdf"

    doc_a.save(out_a)
    doc_b.save(out_b)
    shutil.copy(path_a, raw_a)
    shutil.copy(path_b, raw_b)
    doc_a.close()
    doc_b.close()

    return {
        "global_pdv_check": {
            "has_error": bool(fini_pdv_pages),
            "sample_pages": fini_pdv_pages[:3],
            "total_pages_with_error": len(fini_pdv_pages),
        },
        "matched": formatted_matched,
        "unmatched_fini": formatted_un_a,
        "unmatched_assembla": [],
        "annotated_fini_url": f"/static/temp/annotated_fini_{unique_id}.pdf",
        "annotated_assembla_url": f"/static/temp/annotated_assembla_{unique_id}.pdf",
        "raw_fini_url": f"/static/temp/raw_fini_{unique_id}.pdf",
        "raw_assembla_url": f"/static/temp/raw_assembla_{unique_id}.pdf",
        "full_pages": [],
        "engine_zoom": zoom,
        "stats": {
            "total_matched": len(matched),
            "total_unmatched_fini": len(un_a),
            "total_unmatched_assembla": len(un_b),
        },
        "debug_info": {},
    }
