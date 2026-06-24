import base64
import concurrent.futures
import io
import json
import logging
import re

import numpy as np
import requests
from PIL import Image
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from .text_utils import clean_text_for_matching, compare_price_text_word_by_word
from .vlm import NVIDIA_API_URL, nvidia_headers

logger = logging.getLogger(__name__)


def match_product_blocks_global(blocks_a, blocks_b):
    if not blocks_a or not blocks_b:
        return [], list(blocks_a), list(blocks_b)

    matched = []
    len_a, len_b = len(blocks_a), len(blocks_b)
    matched_indices_a = set(range(len_a))
    matched_indices_b = set(range(len_b))

    logger.debug("Matching: %d Fini blocks vs %d Assembla blocks", len_a, len_b)

    def has_valid_name(b):
        has_inf = "product_inf" in b.get("sub_classes", [])
        return has_inf and len(clean_text_for_matching(b["text"], is_product_inf=has_inf).strip()) >= 3

    # ── Stage 1: text-based matching ────────────────────────────────────────
    score_matrix = np.zeros((len_a, len_b))
    for r in range(len_a):
        if not has_valid_name(blocks_a[r]):
            continue
        ta = clean_text_for_matching(blocks_a[r]["text"], is_product_inf=True)
        nums_a = set(re.findall(r'\d+', ta))

        for c in range(len_b):
            if not has_valid_name(blocks_b[c]):
                continue
            tb = clean_text_for_matching(blocks_b[c]["text"], is_product_inf=True)
            nums_b = set(re.findall(r'\d+', tb))

            nums_conflict = bool(
                nums_a and nums_b
                and not (nums_a.issubset(nums_b) or nums_b.issubset(nums_a))
            )

            text_sim = (0.85 * fuzz.token_sort_ratio(ta, tb) / 100.0
                        + 0.15 * fuzz.token_set_ratio(ta, tb) / 100.0)

            price_sim = compare_price_text_word_by_word(
                blocks_a[r].get("price", ""), blocks_b[c].get("price", "")
            )
            if price_sim >= 0.7:
                text_sim = max(text_sim, 0.85)

            if text_sim >= 0.85:
                score_matrix[r, c] = text_sim
            elif text_sim >= 0.70 and not nums_conflict:
                score_matrix[r, c] = text_sim

    if np.any(score_matrix > 0):
        row_ind, col_ind = linear_sum_assignment(1.0 - score_matrix)
        for r, c in zip(row_ind, col_ind):
            if score_matrix[r, c] > 0:
                matched.append((blocks_a[r], blocks_b[c],
                                f"Text Logic (product_inf) ({score_matrix[r, c]:.2f})"))
                matched_indices_a.discard(r)
                matched_indices_b.discard(c)

    # ── Stage 2: VLM visual fallback ─────────────────────────────────────────
    rem_a = sorted(matched_indices_a)
    rem_b = sorted(matched_indices_b)

    def has_text(b):
        return "product_inf" in b.get("sub_classes", [])

    pools = [(
        "NO-TEXT",
        [i for i in rem_a if not has_text(blocks_a[i])],
        [i for i in rem_b if not has_text(blocks_b[i])],
    )]

    def encode_for_api(img_array):
        if img_array is None or img_array.size == 0:
            return ""
        try:
            buf = io.BytesIO()
            Image.fromarray(img_array).save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return ""

    if rem_a and rem_b:
        def process_pool(pool_data):
            pool_name, pool_a, pool_b = pool_data
            cur_a = [i for i in pool_a if i in matched_indices_a]
            cur_b = [i for i in pool_b if i in matched_indices_b]
            if not cur_a or not cur_b:
                return []

            content = [{
                "type": "text",
                "text": (
                    "Tôi có 2 danh sách các ảnh chụp sản phẩm từ 2 phiên bản của tờ rơi siêu thị. "
                    "Bạn hãy đóng vai chuyên gia đối soát.\n"
                    "Nhiệm vụ: Phân tích và ghép cặp (match) những bức ảnh ở List A giống với bức ảnh "
                    "ở List B (tức là quảng cáo cho CÙNG MỘT SẢN PHẨM).\n"
                    "Lưu ý quan trọng:\n"
                    "- TUYỆT ĐỐI KHÔNG ghép cặp nếu sản phẩm bên trong ảnh khác nhau.\n"
                    "- Hai ảnh được coi là match khi chúng có cùng sản phẩm chính.\n"
                    "Chỉ trả về ĐÚNG MỘT danh sách JSON: [{\"A\": id_A, \"B\": id_B}]."
                ),
            }]
            content.append({"type": "text", "text": "--- List A ---"})
            for idx in cur_a:
                b64 = encode_for_api(blocks_a[idx].get("crop"))
                if b64:
                    content += [
                        {"type": "text", "text": f"Image A, ID: {idx}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ]
            content.append({"type": "text", "text": "--- List B ---"})
            for idx in cur_b:
                b64 = encode_for_api(blocks_b[idx].get("crop"))
                if b64:
                    content += [
                        {"type": "text", "text": f"Image B, ID: {idx}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ]

            payload = {
                "model": "minimaxai/minimax-m3",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 1024, "temperature": 0.0, "top_p": 0.95, "stream": False,
            }
            try:
                resp = requests.post(NVIDIA_API_URL, headers=nvidia_headers(), json=payload)
                if resp.status_code != 200:
                    logger.error("VLM API error %d: %s", resp.status_code, resp.text[:200])
                    return []
                choices = resp.json().get("choices", [])
                if not choices:
                    return []
                text = choices[0]["message"]["content"].strip()
                text = re.sub(r'^```json|^```|```$', '', text).strip()
                return json.loads(text)
            except Exception as exc:
                logger.error("VLM API exception: %s", exc)
                return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for future in concurrent.futures.as_completed(
                [executor.submit(process_pool, p) for p in pools]
            ):
                for m in future.result():
                    a_id, b_id = m.get("A"), m.get("B")
                    if a_id in matched_indices_a and b_id in matched_indices_b:
                        matched.append((blocks_a[a_id], blocks_b[b_id], "VLM-API-Optimized"))
                        matched_indices_a.discard(a_id)
                        matched_indices_b.discard(b_id)

    return matched, [blocks_a[i] for i in matched_indices_a], [blocks_b[i] for i in matched_indices_b]
