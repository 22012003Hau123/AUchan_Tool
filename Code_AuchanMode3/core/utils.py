import base64
import io
import re
from difflib import SequenceMatcher

import numpy as np
from PIL import Image


def encode_image_base64(img_array) -> str:
    if img_array is None or img_array.size == 0:
        return ""
    buffered = io.BytesIO()
    Image.fromarray(img_array).save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def similar(a, b) -> float:
    return SequenceMatcher(None, a, b).ratio()


def get_char_trigrams(text) -> set:
    if not text:
        return set()
    clean = re.sub(r'\s+', '', text).lower()
    if len(clean) < 3:
        return {clean}
    return {clean[i:i+3] for i in range(len(clean) - 2)}


def trigram_jaccard_similarity(set_a, set_b) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def is_inside(inner_box, outer_box, padding=10) -> bool:
    ix1, iy1, ix2, iy2 = inner_box
    ox1, oy1, ox2, oy2 = outer_box
    ox1 -= padding; oy1 -= padding
    ox2 += padding; oy2 += padding
    cx = (ix1 + ix2) / 2
    cy = (iy1 + iy2) / 2
    return ox1 <= cx <= ox2 and oy1 <= cy <= oy2


def calculate_iou(box1, box2) -> float:
    x1 = max(box1[0], box2[0]); y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2]); y2 = min(box1[3], box2[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def calculate_ioa(inner_box, outer_box) -> float:
    x1 = max(inner_box[0], outer_box[0]); y1 = max(inner_box[1], outer_box[1])
    x2 = min(inner_box[2], outer_box[2]); y2 = min(inner_box[3], outer_box[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    inner_area = (inner_box[2] - inner_box[0]) * (inner_box[3] - inner_box[1])
    return intersection / inner_area if inner_area > 0 else 0.0
