from __future__ import annotations

import sys
import json
import re
import math
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Install with: pip install PyMuPDF")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: PIL not installed. Install with: pip install Pillow")
    sys.exit(1)


# ============ Helpers chung ============

NULL_MARKERS = {"null"}


STYLE_TOKEN_PATTERN = re.compile(
    r"\b(?:bold|regular|italic|italique|italics|gras|non\s+gras|roman|normal)\b",
    re.IGNORECASE,
)
STYLE_PAREN_PATTERN = re.compile(
    r"\((?:bold|regular|italic|italique|italics|gras|non\s+gras|roman|normal)\)",
    re.IGNORECASE,
)
IMAGE_SECTION_PATTERN = re.compile(r"image\s*(\d+)\s*:\s*", re.IGNORECASE)
LAYOUT_NOTE_PATTERN = re.compile(
    r"\s*\((?:same|different|identical|only|just)?[^)]*"
    r"(line\s*break|linebreak|line\s+breaks|line\s+spacing|spacing|layout|formatting)"
    r"[^)]*\)\s*$",
    re.IGNORECASE,
)


def remove_style_descriptors(s: str) -> str:
    if not s:
        return ""
    no_paren = STYLE_PAREN_PATTERN.sub(" ", s)
    no_tokens = STYLE_TOKEN_PATTERN.sub(" ", no_paren)
    return re.sub(r"\s+", " ", no_tokens).strip()


def normalize_text_basic(s: str) -> str:
    """
    Chuẩn hoá để so sánh, bỏ qua khác biệt nhỏ:
    - bỏ bớt khoảng trắng dư
    - lowercase
    - bỏ dấu tiếng Việt/Pháp để tránh coi accent là khác biệt
    - bỏ hoàn toàn dấu chấm, dấu phẩy, dấu hai chấm khi so sánh (chỉ giữ lại để đọc)
    - chuẩn hoá "Réf." vs "Ref" vs "réf"
    """
    if not s:
        return ""
    normalized = s.replace("+", " ")
    # Chuẩn hoá "Réf" variants
    normalized = re.sub(r"\bréf\.?\b", "ref", normalized, flags=re.IGNORECASE)
    # Bỏ tất cả dấu chấm, dấu phẩy, dấu hai chấm, dấu chấm phẩy
    normalized = re.sub(r"[.,:;]", " ", normalized)
    # Chuẩn hoá khoảng trắng
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    # Bỏ dấu tiếng Việt/Pháp
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    # Bỏ khoảng trắng thừa ở đầu/cuối
    return normalized.strip()


def normalize_text_for_diff(s: str) -> str:
    return normalize_text_basic(remove_style_descriptors(s))


def compute_column_overlap(rect: fitz.Rect, col_left: float, col_right: float) -> float:
    if rect is None or col_right <= col_left:
        return 0.0
    overlap_left = max(rect.x0, col_left)
    overlap_right = min(rect.x1, col_right)
    overlap = overlap_right - overlap_left
    if overlap <= 0:
        return 0.0
    rect_width = max(rect.x1 - rect.x0, 1e-3)
    col_width = col_right - col_left
    return overlap / min(rect_width, col_width)


def strip_layout_notes(text: str) -> str:
    if not text:
        return ""
    return LAYOUT_NOTE_PATTERN.sub("", text).strip()


def preprocess_diff_value(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    cleaned = strip_layout_notes(cleaned)
    return cleaned.strip()


def coerce_text_list(value, *, preserve_null: bool = False) -> list[str | None]:
    """
    Chuẩn hoá dữ liệu differences sang list[string].
    Hỗ trợ:
    - list[str]
    - string đơn
    - string biểu diễn JSON array
    """
    texts: list[str | None] = []

    if value is None:
        return texts

    if isinstance(value, list):
        raw_list = value
    else:
        raw = preprocess_diff_value(value)
        if not raw:
            return texts
        raw_list = [raw]
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    raw_list = parsed
            except Exception:
                raw_list = [raw]

    for item in raw_list:
        if item is None and preserve_null:
            texts.append(None)
            continue
        if isinstance(item, str):
            text = preprocess_diff_value(item)
        else:
            text = preprocess_diff_value(str(item))
        texts.append(text)

    return texts


def is_null_marker(value: str | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULL_MARKERS:
        return True
    return False


def split_multiline_pair(ann: str, highlight: str) -> tuple[list[tuple[str, str]], bool] | None:
    if "\n" not in highlight:
        return None

    lines = [line.strip() for line in highlight.splitlines() if line.strip()]
    if len(lines) <= 1:
        return None

    norm_ann = normalize_text_for_diff(ann)
    matched_idx: int | None = None
    if norm_ann:
        for idx, line in enumerate(lines):
            if normalize_text_for_diff(line) == norm_ann:
                matched_idx = idx
                break

    if matched_idx is None and ann.strip():
        # Không có line nào trùng với annotation → không tách
        return None

    segments: list[tuple[str, str]] = []
    consume_ann = False

    for idx, line in enumerate(lines):
        if matched_idx is not None and idx == matched_idx:
            segments.append((ann, line))
            consume_ann = True
        else:
            segments.append(("", line))

    if not segments:
        return None

    return segments, consume_ann


def build_pairs_from_lists(list_a: list[str], list_b: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    idx_a = 0
    idx_b = 0
    len_a = len(list_a)
    len_b = len(list_b)

    if len_a == 0 and len_b == 0:
        return pairs

    while idx_a < len_a or idx_b < len_b:
        ann = list_a[idx_a] if idx_a < len_a else ""
        highlight = list_b[idx_b] if idx_b < len_b else ""

        # Xử lý case multiline trong highlight
        split_result = split_multiline_pair(ann, highlight)
        if split_result is not None:
            segments, consume_ann = split_result
            for seg_ann, seg_highlight in segments:
                if not seg_highlight and not seg_ann:
                    continue
                if normalize_text_for_diff(seg_ann) == normalize_text_for_diff(seg_highlight):
                    continue
                pairs.append((seg_ann, seg_highlight))

            if idx_a < len_a:
                idx_a += 1
            if idx_b < len_b:
                idx_b += 1
            continue

        if not highlight and not ann:
            if idx_a < len_a:
                idx_a += 1
            if idx_b < len_b:
                idx_b += 1
            continue

        # Nếu annotation rỗng nhưng highlight có text khác với mọi phần còn lại, chỉ highlight
        if not ann:
            ann_to_use = ""
        else:
            ann_to_use = ann

        if ann_to_use and highlight and normalize_text_for_diff(ann_to_use) == normalize_text_for_diff(highlight):
            if idx_a < len_a:
                idx_a += 1
            if idx_b < len_b:
                idx_b += 1
            continue

        pairs.append((ann_to_use, highlight))

        if idx_a < len_a:
            idx_a += 1
        if idx_b < len_b:
            idx_b += 1

    return pairs


def split_image_sections(text: str) -> dict[int, str]:
    if not text:
        return {}

    sections: dict[int, str] = {}
    last_idx = None
    last_pos = 0

    for match in IMAGE_SECTION_PATTERN.finditer(text):
        if last_idx is not None:
            sections[last_idx] = text[last_pos : match.start()].strip()
        last_idx = int(match.group(1))
        last_pos = match.end()

    if last_idx is not None:
        sections[last_idx] = text[last_pos:].strip()

    return sections


def extract_actual_text_from_description(description: str, field_name: str = "") -> str | None:
    """
    Extract text thực tế từ mô tả GPT.
    
    Ví dụ:
    - "Image 2 contains the additional text 'Existe aussi :'..." → "Existe aussi :"
    - "Image 2 contains the text 'DÈS 5 ANS'..." → "DÈS 5 ANS"
    - "In Image 1, the product name is bold..." → None (formatting description)
    
    Nếu không extract được, có thể dùng field_name nếu nó trông giống text thực tế.
    """
    if not description:
        return None
    
    # Pattern 1: Extract text trong single quotes
    single_quote_match = re.search(r"'([^']+)'", description)
    if single_quote_match:
        extracted = single_quote_match.group(1).strip()
        if len(extracted) <= 100 and not extracted.lower().startswith(("image", "in image")):
            return extracted
    
    # Pattern 2: Extract text trong double quotes
    double_quote_match = re.search(r'"([^"]+)"', description)
    if double_quote_match:
        extracted = double_quote_match.group(1).strip()
        if len(extracted) <= 100 and not extracted.lower().startswith(("image", "in image")):
            return extracted
    
    # Pattern 3: Nếu description là formatting description (bắt đầu "In Image", "Image 2 contains", etc.)
    if re.match(r"^(?:In\s+Image|Image\s+\d+\s+contains|Image\s+\d+\s+only)", description, re.IGNORECASE):
        # Thử dùng field_name nếu nó trông giống text thực tế
        if field_name and len(field_name) <= 50 and not re.match(r"^(?:In\s+Image|Image|Product|Spacing|Brand)", field_name, re.IGNORECASE):
            return field_name
        return None
    
    # Pattern 4: Nếu description ngắn và không phải formatting → có thể là text thực tế
    if len(description) <= 50 and not re.match(r"^(?:In\s+Image|Image\s+\d+)", description, re.IGNORECASE):
        return description.strip()
    
    return None


def extract_keyword_snippet(description: str) -> str | None:
    if not description:
        return None

    keyword_patterns = [
        re.compile(r"(Existe\s+aussi\s*:?)", re.IGNORECASE),
    ]

    for pattern in keyword_patterns:
        match = pattern.search(description)
        if match:
            snippet = match.group(1).strip()
            snippet = re.sub(r"\s+", " ", snippet)
            if not snippet.endswith(":"):
                snippet = snippet.rstrip(".") + " :"
            return snippet

    return None


def is_formatting_description(text: str) -> bool:
    """Kiểm tra xem text có phải là mô tả formatting không."""
    if not text:
        return False
    text_lower = text.lower()
    
    # Pattern 1: Bắt đầu bằng "In Image", "Image X", "Present in Image"
    if re.match(r"^(?:In\s+Image|Image\s+\d+|Present\s+in\s+Image)", text_lower):
        return True
    
    # Pattern 2: Chứa "Present in Image X, not in Image Y" hoặc tương tự
    if re.search(r"present\s+in\s+image\s+\d+.*not\s+in\s+image", text_lower):
        return True
    
    # Pattern 3: Chứa formatting keywords và mention Image
    formatting_keywords = [
        "bold", "regular", "italic", "separate line", "follows immediately",
        "more spacing", "condensed", "formatting", "visible", "display",
        "on separate lines", "combined", "does not display", "separate lines",
        "immediately after", "bottom right", "bottom left", "top right", "top left"
    ]
    has_formatting_keyword = any(keyword in text_lower for keyword in formatting_keywords)
    mentions_image = "image 1" in text_lower or "image 2" in text_lower
    
    if has_formatting_keyword and mentions_image:
        return True
    
    # Pattern 4: Mô tả về vị trí, layout, line-break
    layout_keywords = ["corner", "position", "placement", "layout", "arrangement"]
    if any(keyword in text_lower for keyword in layout_keywords) and mentions_image:
        return True

    line_break_keywords = [
        "line break", "line-break", "line breaks", "line-breaks",
        "split onto two lines", "split on two lines",
        "split across two lines", "split across lines",
        "different line", "new line", "breaks the line"
    ]
    if any(keyword in text_lower for keyword in line_break_keywords):
        return True
    
    return False


def is_formatting_field_name(field_name: str) -> bool:
    """Kiểm tra xem field_name có phải là tên field về formatting không."""
    if not field_name:
        return False
    field_lower = field_name.lower()
    formatting_field_names = [
        "formatting", "spacing", "brand logo", "logo", "position",
        "layout", "arrangement", "placement", "product description formatting",
        "line_break", "line_breaks", "line breaks", "line-breaks", "linebreaks", "line breaks info"
    ]
    return any(keyword in field_lower for keyword in formatting_field_names)


def merge_vertically_close_rects(
    rects: list[fitz.Rect],
    *,
    max_vertical_gap: float = 18.0,
    max_horizontal_shift: float = 25.0,
) -> list[fitz.Rect]:
    """
    Một số text nhiều dòng (ví dụ 'Existe\\naussi :') sẽ được PyMuPDF trả về
    nhiều rect riêng rẽ cho từng dòng. Hàm này gộp các rect gần nhau theo phương Y.
    """
    if not rects or len(rects) == 1:
        return rects

    rects_sorted = sorted(rects, key=lambda r: (r.y0, r.x0))
    merged: list[fitz.Rect] = []
    current = rects_sorted[0]

    for rect in rects_sorted[1:]:
        same_column = abs(rect.x0 - current.x0) <= max_horizontal_shift
        vertically_close = rect.y0 - current.y1 <= max_vertical_gap
        overlap_x = not (rect.x1 < current.x0 or rect.x0 > current.x1)

        if same_column and vertically_close and overlap_x:
            current = fitz.Rect(
                min(current.x0, rect.x0),
                min(current.y0, rect.y0),
                max(current.x1, rect.x1),
                max(current.y1, rect.y1),
            )
        else:
            merged.append(current)
            current = rect

    merged.append(current)
    return merged


def get_line_rects_for_pattern(
    page: fitz.Page,
    pattern: str,
    anchor_rect: fitz.Rect,
    *,
    padding: float = 3.0,
) -> list[fitz.Rect]:
    """
    Lấy tất cả rect thuộc text pattern trùng với vùng anchor (để highlight đủ nhiều dòng).
    Cải thiện: Tìm các dòng liên tiếp trong cùng cột.
    """
    try:
        raw_rects = page.search_for(pattern, flags=fitz.TEXT_DEHYPHENATE)
    except Exception:
        raw_rects = []

    if not raw_rects:
        return [anchor_rect]

    # Tìm các rect gần anchor_rect (trong cùng cột và gần nhau theo chiều dọc)
    # Chỉ merge các dòng liên tiếp gần nhau, không merge các text quá xa
    column_tolerance = 50.0  # Khoảng cách ngang cho phép
    vertical_tolerance = 25.0  # Khoảng cách dọc cho phép giữa các dòng (giảm từ 30.0)
    max_vertical_gap = 40.0  # Giới hạn tối đa khoảng cách dọc để merge (giảm từ 150pt)
    
    filtered = []
    for r in raw_rects:
        # Kiểm tra xem có cùng cột không
        horizontal_overlap = min(r.x1, anchor_rect.x1) - max(r.x0, anchor_rect.x0)
        if horizontal_overlap > 0:
            # Kiểm tra khoảng cách dọc - chỉ merge nếu rất gần nhau
            vertical_gap = abs((r.y0 + r.y1) / 2 - (anchor_rect.y0 + anchor_rect.y1) / 2)
            if vertical_gap <= max_vertical_gap:  # Giảm từ vertical_tolerance * 5 xuống max_vertical_gap
                filtered.append(r)
    
    # Nếu không tìm thấy, dùng logic cũ
    if not filtered:
        tol_rect = fitz.Rect(
            anchor_rect.x0 - padding,
            anchor_rect.y0 - padding,
            anchor_rect.x1 + padding,
            anchor_rect.y1 + padding,
        )
        filtered = [r for r in raw_rects if r.intersects(tol_rect)]
    
    # Sắp xếp theo vị trí dọc để highlight đúng thứ tự
    filtered.sort(key=lambda r: (r.y0, r.x0))
    
    return filtered if filtered else [anchor_rect]


def load_comparison_data(comparison_str: str) -> dict:
    if not comparison_str:
        return {}

    raw = comparison_str.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except Exception as e:
        print(f"    WARNING: parse_comparison_json error (json.loads): {e}")
        print(f"    Raw (first 200 chars): {comparison_str[:200]!r}")
        return {}


def parse_comparison_json(comparison_str: str) -> list[tuple[str, str]]:
    """
    Parse JSON từ field `comparison` của step6.

    Format mới (ví dụ):
      {
        "differ_product": [
          {
            "aspect": "product size",
            "image1": "200 x 200 cm",
            "image2": "400 x 200 cm"
          },
          ...
        ],
        "differences": {
          "price": {
            "image1": "25€ 99",
            "image2": "55€ 99"
          },
          "product_title": {
            "image1": "...",
            "image2": "..."
          }
        }
      }

    Returns:
      List of tuples: [(annotation_text, text_to_highlight), ...]
      - annotation_text = image1 value (A)
      - text_to_highlight = image2 value (B)
    """
    data = load_comparison_data(comparison_str)
    if not data:
        return []

    # ----- FORMAT MỚI: có differ_product / differences -----
    result: list[tuple[str, str]] = []

    # 1) differ_product: list[{aspect, image1, image2}]
    differ_product = data.get("differ_product") or []
    if isinstance(differ_product, list):
        for item in differ_product:
            if not isinstance(item, dict):
                continue
            img1 = preprocess_diff_value(item.get("image1"))
            img2 = preprocess_diff_value(item.get("image2"))
            if not img2:
                continue
            # bỏ qua nếu thực tế không khác nhau (sau normalize nhẹ)
            if normalize_text_for_diff(img1) == normalize_text_for_diff(img2):
                continue
            result.append((img1, img2))

    # 2) differences: dict[field_name] = {image1, image2}
    differences = data.get("differences") or {}
    if isinstance(differences, dict):
        lower_keys = {str(k).strip().lower() for k in differences.keys()}
        simple_diff = lower_keys and lower_keys.issubset({"image1", "image 1", "image2", "image 2"})
        if simple_diff:
            img1_list = coerce_text_list(differences.get("image1") or differences.get("image 1"))
            img2_list = coerce_text_list(differences.get("image2") or differences.get("image 2"))
            result.extend(build_pairs_from_lists(img1_list, img2_list))
        else:
            for field_name, field_data in differences.items():
                # Bỏ qua các field về formatting ngay từ đầu
                if is_formatting_field_name(field_name):
                    continue
                
                img1 = ""
                img2 = ""

                if isinstance(field_data, dict):
                    img1 = preprocess_diff_value(field_data.get("image1"))
                    img2 = preprocess_diff_value(field_data.get("image2"))
                elif isinstance(field_data, str):
                    img2_raw = field_data.strip()
                    
                    # Pattern: "<text1> vs <text2>" → tách trực tiếp
                    vs_match = re.match(r"^(?P<img1>.+?)\s+vs\s+(?P<img2>.+)$", img2_raw, re.IGNORECASE)
                    if vs_match:
                        img1_candidate = vs_match.group("img1").strip(" \"'")
                        img2_candidate = vs_match.group("img2").strip(" \"'")
                        if normalize_text_for_diff(img1_candidate) != normalize_text_for_diff(img2_candidate):
                            img1 = preprocess_diff_value(img1_candidate)
                            img2 = preprocess_diff_value(img2_candidate)
                        else:
                            continue
                        # Đã xử lý xong pattern 'vs'
                        if img2:
                            if normalize_text_for_diff(img1) == normalize_text_for_diff(img2):
                                continue
                            result.append((img1, img2))
                            continue
                    
                    # Kiểm tra xem có phải formatting description không
                    if is_formatting_description(img2_raw):
                        # Bỏ qua formatting descriptions
                        continue
                    
                    # Thử extract text thực tế từ description
                    extracted_text = extract_actual_text_from_description(img2_raw, field_name)
                    if extracted_text:
                        img2 = preprocess_diff_value(extracted_text)
                    else:
                        keyword_snippet = extract_keyword_snippet(img2_raw)
                        if keyword_snippet:
                            img2 = preprocess_diff_value(keyword_snippet)
                        else:
                            # Fallback: thử split image sections
                            sections = split_image_sections(img2_raw)
                            if 1 in sections and 2 in sections:
                                img1_candidate = sections.get(1, "")
                                img2_candidate = sections.get(2, "")
                                if normalize_text_for_diff(img1_candidate) == normalize_text_for_diff(img2_candidate):
                                    continue    
                                img1 = preprocess_diff_value(img1_candidate)
                                img2 = preprocess_diff_value(img2_candidate)
                            else:
                                # Nếu field_name trông giống text thực tế (ngắn, không phải tên sản phẩm dài), dùng nó
                                # Nhưng chỉ khi description là formatting description
                                if is_formatting_description(img2_raw):
                                    # Nếu description là formatting, bỏ qua hoàn toàn
                                    continue
                                # Nếu không phải formatting và field_name hợp lý, có thể dùng
                                if field_name and len(field_name) <= 30 and not is_formatting_description(field_name):
                                    img2 = preprocess_diff_value(field_name)
                                else:
                                    # Nếu không extract được và không phải formatting, bỏ qua để tránh highlight sai
                                    continue
                elif isinstance(field_data, list):
                    img1_candidates: list[str] = []
                    img2_candidates: list[str] = []
                    fallback_entries: list[str] = []

                    for item in field_data:
                        candidate_img1 = ""
                        candidate_img2 = ""

                        if isinstance(item, dict):
                            candidate_img1 = preprocess_diff_value(item.get("image1"))
                            candidate_img2 = preprocess_diff_value(item.get("image2"))
                        elif isinstance(item, str):
                            raw_text = item.strip()
                            if not raw_text:
                                continue

                            sections = split_image_sections(raw_text)
                            if 1 in sections or 2 in sections:
                                candidate_img1 = preprocess_diff_value(sections.get(1))
                                candidate_img2 = preprocess_diff_value(sections.get(2))
                            else:
                                label_match = re.match(
                                    r"^\s*(?:image|img)\s*([12])\s*[:\-]\s*(.+)$",
                                    raw_text,
                                    re.IGNORECASE,
                                )
                                if label_match:
                                    idx = label_match.group(1)
                                    value = preprocess_diff_value(label_match.group(2))
                                    if idx == "1":
                                        candidate_img1 = value
                                    else:
                                        candidate_img2 = value
                                else:
                                    fallback_entries.append(preprocess_diff_value(raw_text))
                                    continue
                        else:
                            continue

                        if candidate_img1:
                            img1_candidates.append(candidate_img1)
                        if candidate_img2:
                            img2_candidates.append(candidate_img2)

                    if not img1_candidates and fallback_entries:
                        first = fallback_entries[0]
                        if first:
                            img1_candidates.append(first)
                    if not img2_candidates and len(fallback_entries) >= 2:
                        second = fallback_entries[1]
                        if second:
                            img2_candidates.append(second)

                    if img1_candidates and img2_candidates:
                        img1 = img1_candidates[0]
                        img2 = img2_candidates[0]
                    else:
                        continue
                else:
                    continue

                if not img2:
                    continue
                if normalize_text_for_diff(img1) == normalize_text_for_diff(img2):
                    continue
                result.append((img1, img2))

    if result:
        return result

    # ----- FALLBACK: format cũ (image_a + different) -----
    try:
        image_a = data.get("image_a", "") or ""
        different = data.get("different", "") or ""
        if different:
            # Tách theo |
            different_parts = [p.strip() for p in different.split("|") if p.strip()]
            image_a_parts = [p.strip() for p in image_a.split("|") if p.strip()]
            pairs = []
            for i, diff_part in enumerate(different_parts):
                ann_text = image_a_parts[i] if i < len(image_a_parts) else image_a
                pairs.append((ann_text, diff_part))
            return pairs
    except Exception:
        pass

    return []


def normalize_color(color: str) -> str:
    """
    Normalize màu để coi các màu tương tự là giống nhau.
    White, beige, cream, ivory, off-white, light gray được coi là giống nhau.
    """
    if not color:
        return ""
    
    color_lower = color.lower().strip()
    
    # Nhóm các mô tả "transparent"/"no background"
    transparent_variants = [
        "transparent",
        "no background",
        "no backdrop",
        "without background",
        "without backdrop",
        "no logo background",
        "none",
        "transparent around logo",
    ]
    if any(variant in color_lower for variant in transparent_variants):
        return "transparent"

    # Nhóm các màu trắng/beige/cream/ivory thành "white"
    white_variants = ["white", "beige", "cream", "ivory", "off-white", "off white", "light gray", "light grey"]
    if any(variant in color_lower for variant in white_variants):
        return "white"
    
    # Trả về màu gốc (đã lowercase)
    return color_lower


def parse_background_differences(comparison_str: str) -> list[tuple[str, str]]:
    data = load_comparison_data(comparison_str)
    if not data:
        return []

    bg = data.get("background_differences")
    if isinstance(bg, dict):
        img1 = str(bg.get("image1") or "").strip()
        img2 = str(bg.get("image2") or "").strip()
        if img1 or img2:
            # Normalize màu để coi white/beige/cream là giống nhau
            img1_normalized = normalize_color(img1)
            img2_normalized = normalize_color(img2)
            
            # Bỏ qua nếu cả hai giống nhau sau khi normalize
            if img1_normalized == img2_normalized:
                return []
            return [(img1, img2)]
    return []


def parse_missing_elements(comparison_str: str) -> dict | None:
    """
    Parse missing_elements từ comparison JSON.
    
    Returns:
        Dict với keys: image1, image2, missing
        Hoặc None nếu không có missing elements hoặc GPT báo sai (Image 2 có thêm thay vì thiếu)
    """
    data = load_comparison_data(comparison_str)
    if not data:
        return None

    missing = data.get("missing_elements")
    if isinstance(missing, dict):
        # Chỉ highlight nếu missing = true
        if missing.get("missing") is True:
            # Validation: Kiểm tra xem GPT có báo sai không (Image 2 có thêm thay vì thiếu)
            img2_desc = str(missing.get("image2") or "").lower()
            # Nếu description có từ "additional", "more", "contains an" → GPT báo sai, bỏ qua
            invalid_keywords = ["additional", "more", "contains an", "has an", "includes an", "added"]
            if any(keyword in img2_desc for keyword in invalid_keywords):
                # GPT đang báo Image 2 có thêm, không phải thiếu → bỏ qua
                return None
            return missing
    return None


def extract_additional_text_from_missing_elements(comparison_str: str) -> list[tuple[str, str]]:
    """
    Extract additional text từ missing_elements khi GPT báo sai (Image 2 có thêm thay vì thiếu).
    Trả về list of (annotation_text, highlight_text) để highlight như text differences.
    """
    data = load_comparison_data(comparison_str)
    if not data:
        return []

    missing = data.get("missing_elements")
    if not isinstance(missing, dict) or missing.get("missing") is not True:
        return []

    img2_desc = str(missing.get("image2") or "").lower()
    # Nếu description có từ "additional" → GPT báo Image 2 có thêm text
    if "additional" in img2_desc or "contains an" in img2_desc:
        # Thử extract text từ description (ví dụ: "Existe aussi :")
        full_desc = str(missing.get("image2") or "")
        extracted = extract_actual_text_from_description(full_desc, "")
        if extracted:
            # Trả về như text difference (image1 empty, image2 = extracted text)
            return [("", extracted)]
    
    return []


def get_color_rgb(color_name: str) -> tuple[float, float, float]:
    color_map = {
        "Green": (0.0, 1.0, 0.0),
        "Yellow": (1.0, 1.0, 0.0),
        "Red": (1.0, 0.0, 0.0),
        "Blue": (0.0, 0.0, 1.0),
        "Orange": (1.0, 0.65, 0.0),
        "Pink": (1.0, 0.75, 0.8),
    }
    return color_map.get(color_name, (0.0, 1.0, 0.0))  # default: Green


def split_parts(text: str) -> list[str]:
    """
    (Giữ lại để fallback format cũ nếu cần)
    Tách text theo '|' & loại bỏ label vô nghĩa.
    Ví dụ:
      "Image B|55€99|10€ DE REMISE..."
      -> ["55€99", "10€ DE REMISE..."]
    """
    skip_labels = {"image b", "id hình b", "hình b", "b", ""}
    parts = []
    for p in text.split("|"):
        p_clean = p.strip()
        if not p_clean:
            continue
        if p_clean.lower() in skip_labels:
            continue
        parts.append(p_clean)
    return parts


def align_a_b_parts(image_a_text: str, different_text: str) -> list[tuple[str, str]]:
    """
    (Không còn dùng cho format mới, nhưng giữ lại để khỏi vỡ code cũ nếu bạn dùng)
    Căn hàng A/B theo kiểu:
      A_parts = image_a.split('|')
      B_parts = different.split('|')
    """
    a_parts = split_parts(image_a_text)
    b_parts = split_parts(different_text)

    if not b_parts:
        return []

    if len(a_parts) == 0:
        a_parts = [image_a_text.strip()] * len(b_parts)

    if len(a_parts) > len(b_parts):
        if re.match(r"^\d{3,}$", a_parts[0]):
            a_parts = a_parts[1:]
        if len(a_parts) > len(b_parts):
            a_parts = a_parts[: len(b_parts)]
    elif len(a_parts) < len(b_parts):
        a_parts = a_parts + [a_parts[-1]] * (len(b_parts) - len(a_parts))

    return list(zip(a_parts, b_parts))


def build_annotation(a_part: str, b_part: str, max_len: int = 220) -> str:
    """
    Annotation gọn: chỉ lấy context từ Image 1 (A) để mô tả chênh lệch.
    Tự động xuống dòng theo câu để dễ đọc.
    Nếu image1 rỗng, dùng image2 làm annotation.
    """

    text = (a_part or "").strip()
    if not text:
        return "Brief:"

    sentence_pattern = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ0-9])")
    segments = sentence_pattern.split(text)
    segments = [seg.strip() for seg in segments if seg.strip()]

    if segments:
        formatted = "\n".join(segments)
    else:
        formatted = text

    formatted = formatted.strip()
    if len(formatted) > max_len:
        formatted = formatted[: max_len] + "…"

    if "\n" in formatted:
        return f"Brief:\n{formatted}"
    return f"Brief: {formatted}"


# ============ Helpers cho GIÁ (55€99, 10€99, ...) ============

def parse_price_value(text: str) -> float | None:
    """
    Parse giá từ string rất linh hoạt:
      "55€99", "55 € 99", "55,99 €", "55.99€" -> 55.99
      "24€" -> 24.0
    """
    nums = re.findall(r"\d+", text)
    if not nums:
        return None

    # dạng có € và >= 2 nhóm số: euros + cents
    if "€" in text and len(nums) >= 2:
        try:
            euros = int(nums[0])
            cents = int(nums[1][:2])
            return euros + cents / 100.0
        except ValueError:
            pass

    # dạng 55,99 hoặc 55.99
    m = re.search(r"(\d+[,.]\d+)", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass

    # fallback: chỉ euros
    try:
        return float(nums[0])
    except ValueError:
        return None


def is_price_like(text: str) -> bool:
    """Chuỗi có vẻ là giá?"""
    return ("€" in text) or bool(re.search(r"\d+\s*[€$£]", text))


def pattern_rank(pattern: str) -> tuple[int, int]:
    """
    Tính điểm ưu tiên cho pattern khi chọn rect tốt nhất.
    - Ưu tiên pattern chứa chữ cái (rank 0)
    - Sau đó mới đến pattern chỉ số (rank 1+)
    - Ưu tiên thêm pattern dài hơn (length_rank = -len)
    """
    cleaned = (pattern or "").strip()
    if not cleaned:
        return (2, 0)

    has_alpha = bool(re.search(r"[A-Za-zÀ-ÿ]", cleaned))
    rank = 0 if has_alpha else 1
    length_rank = -len(cleaned)
    return (rank, length_rank)


def tokenize_for_diff(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"[A-Za-zÀ-ÿ0-9%€]+|[^\s]", text)


def extract_diff_snippets(text_a: str, text_b: str, *, max_snippets: int = 3) -> list[str]:
    """
    Lấy ra các đoạn text khác nhau giữa A và B (word-level) để ưu tiên
    tìm chính xác phần thay đổi, ví dụ "+ 3 taies".
    """
    if not text_b:
        return []

    snippets: list[str] = []

    tokens_a = tokenize_for_diff(text_a or "")
    tokens_b = tokenize_for_diff(text_b)

    try:
        matcher = SequenceMatcher(None, tokens_a, tokens_b)
        for tag, a0, a1, b0, b1 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                start = max(b0 - 2, 0)
                end = min(b1 + 2, len(tokens_b))
                snippet_tokens = tokens_b[start:end]
                snippet = " ".join(snippet_tokens)
                snippet = re.sub(r"\s+", " ", snippet).strip()
                if len(snippet) >= 3:
                    snippets.append(snippet[:150])
            if len(snippets) >= max_snippets:
                break
    except Exception:
        snippets = []

    if snippets:
        return snippets

    # Fallback: character-level diff (ít khi cần)
    try:
        matcher = SequenceMatcher(None, text_a or "", text_b)
        for tag, a0, a1, b0, b1 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                snippet = text_b[b0:b1]
                snippet = re.sub(r"\s+", " ", snippet).strip()
                if len(snippet) >= 3:
                    snippets.append(snippet[:150])
            if len(snippets) >= max_snippets:
                break
    except Exception:
        return []

    return snippets


def should_use_price_mode(text: str) -> bool:
    """
    Chỉ kích hoạt price-mode cho chuỗi ngắn chủ yếu là giá.
    Các mô tả dài (dù có ký tự €) sẽ dùng logic text-search chuẩn,
    tránh trường hợp highlight sai vị trí.
    """
    if not text or not is_price_like(text):
        return False

    text = text.strip()
    if len(text) > 60:
        return False

    word_count = len(text.split())
    if word_count > 10:
        return False

    return True


def normalize_token(token: str) -> str:
    if not token:
        return ""
    return re.sub(r"[^A-Za-zÀ-ÿ0-9%]", "", token).lower()


def find_rects_by_word_sequence(page, snippet: str, *, max_results: int = 3) -> list[fitz.Rect]:
    """
    Tìm rect dựa trên chuỗi ngắn gồm nhiều token (ví dụ '3 taies 60%').
    Dùng word-level nên chịu được dấu '+' hoặc xuống dòng.
    """
    if not snippet:
        return []

    tokens = [normalize_token(t) for t in re.findall(r"[A-Za-zÀ-ÿ0-9%]+", snippet)]
    tokens = [t for t in tokens if t]
    if len(tokens) < 2:
        return []

    words = page.get_text("words")
    max_window = min(len(tokens), 5)

    for window in range(max_window, 1, -1):
        for start in range(0, len(tokens) - window + 1):
            target_tokens = tokens[start : start + window]
            rects: list[fitz.Rect] = []

            for i in range(len(words)):
                matched_words = []
                token_idx = 0
                j = i
                while j < len(words) and token_idx < len(target_tokens):
                    word_token = normalize_token(words[j][4])
                    if not word_token:
                        j += 1
                        continue
                    advance = 0
                    combined = target_tokens[token_idx]
                    if word_token == combined:
                        advance = 1
                    else:
                        k = token_idx + 1
                        while k < len(target_tokens):
                            combined += target_tokens[k]
                            if word_token == combined:
                                advance = k - token_idx + 1
                                break
                            k += 1
                    if advance > 0:
                        matched_words.append(words[j])
                        token_idx += advance
                    else:
                        break
                    j += 1

                if token_idx == len(target_tokens) and matched_words:
                    x0 = min(w[0] for w in matched_words)
                    y0 = min(w[1] for w in matched_words)
                    x1 = max(w[2] for w in matched_words)
                    y1 = max(w[3] for w in matched_words)
                    rects.append(fitz.Rect(x0, y0, x1, y1))
                    if len(rects) >= max_results:
                        return rects

            if rects:
                return rects

    return []


def is_rect_closer_to_current_id(rect: fitz.Rect, id_rect: fitz.Rect, neighbors: dict, id_text: str, *, strict: bool = True, search_region: fitz.Rect = None) -> bool:
    """
    Kiểm tra xem rect có gần ID hiện tại hơn các ID lân cận không.
    Trả về True nếu rect gần ID hiện tại hơn, False nếu gần ID lân cận hơn.
    
    Args:
        strict: Nếu True, kiểm tra chặt chẽ. Nếu False, chỉ kiểm tra khi ID lân cận rất gần (< 100pt).
        search_region: Vùng tìm kiếm của ID hiện tại. Nếu có, kiểm tra xem rect có nằm trong vùng này không.
    """
    rect_cx = (rect.x0 + rect.x1) / 2
    rect_cy = (rect.y0 + rect.y1) / 2
    id_cx = (id_rect.x0 + id_rect.x1) / 2
    id_cy = (id_rect.y0 + id_rect.y1) / 2
    dist_to_current = math.hypot(rect_cx - id_cx, rect_cy - id_cy)
    
    # Nếu có search_region, kiểm tra xem rect có nằm trong vùng này không
    # Nếu rect nằm trong search_region, ưu tiên chấp nhận (có thể bỏ qua một số kiểm tra)
    if search_region is not None:
        # Cho phép một chút ngoài search region (padding 50pt)
        expanded_region = fitz.Rect(
            search_region.x0 - 50,
            search_region.y0 - 50,
            search_region.x1 + 50,
            search_region.y1 + 50,
        )
        
        # Nếu rect nằm trong search_region (không cần padding), ưu tiên chấp nhận
        if search_region.contains(rect):
            # Rect nằm trong search_region → có thể là text đúng
            # Chỉ kiểm tra nếu ID lân cận rất gần và text gần ID lân cận hơn đáng kể
            for neighbor_id, neighbor_rect in neighbors.items():
                if neighbor_id == id_text:
                    continue
                neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
                neighbor_cy = (neighbor_rect.y0 + neighbor_rect.y1) / 2
                dist_to_neighbor = math.hypot(rect_cx - neighbor_cx, rect_cy - neighbor_cy)
                id_to_neighbor_dist = math.hypot(id_cx - neighbor_cx, id_cy - neighbor_cy)
                
                # Chỉ bỏ qua nếu ID lân cận rất gần (< 150pt) VÀ text gần ID lân cận hơn đáng kể (0.6x)
                if id_to_neighbor_dist < 150 and dist_to_neighbor < dist_to_current * 0.6:
                    return False
            # Nếu không có ID lân cận quá gần, chấp nhận
            return True
        elif not expanded_region.contains(rect):
            # Rect nằm ngoài search region (kể cả với padding) → có thể thuộc ID lân cận
            # Kiểm tra xem có gần ID lân cận nào không
            for neighbor_id, neighbor_rect in neighbors.items():
                if neighbor_id == id_text:
                    continue
                neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
                neighbor_cy = (neighbor_rect.y0 + neighbor_rect.y1) / 2
                dist_to_neighbor = math.hypot(rect_cx - neighbor_cx, rect_cy - neighbor_cy)
                # Nếu rect gần ID lân cận hơn ID hiện tại, bỏ qua
                if dist_to_neighbor < dist_to_current:
                    return False
    
    # Kiểm tra với tất cả ID lân cận
    for neighbor_id, neighbor_rect in neighbors.items():
        if neighbor_id == id_text:
            continue
        neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
        neighbor_cy = (neighbor_rect.y0 + neighbor_rect.y1) / 2
        dist_to_neighbor = math.hypot(rect_cx - neighbor_cx, rect_cy - neighbor_cy)
        
        # Tính khoảng cách giữa 2 ID
        id_to_neighbor_dist = math.hypot(id_cx - neighbor_cx, id_cy - neighbor_cy)
        
        # Kiểm tra xem ID lân cận có cùng hàng không (cùng y)
        same_row = abs(neighbor_cy - id_cy) < 50  # Cùng hàng nếu chênh lệch y < 50pt
        
        if strict:
            # Chế độ chặt: 
            # 1. Nếu text gần ID lân cận hơn ID hiện tại, bỏ qua
            # 2. Nếu ID lân cận cùng hàng và text nằm về phía ID lân cận, bỏ qua (nhưng chỉ khi chênh lệch đáng kể)
            if dist_to_neighbor < dist_to_current * 0.9:  # Cho phép một chút linh hoạt (0.9)
                return False
            
            # Kiểm tra vị trí ngang: nếu ID lân cận cùng hàng và text nằm về phía ID lân cận
            # Nhưng chỉ bỏ qua nếu text nằm rõ ràng về phía ID lân cận (chênh lệch > 100pt)
            if same_row:
                if neighbor_cx < id_cx and rect_cx < id_cx - 100:  # ID lân cận bên trái, text cũng bên trái ID hiện tại (rõ ràng)
                    return False
                if neighbor_cx > id_cx and rect_cx > id_cx + 100:  # ID lân cận bên phải, text cũng bên phải ID hiện tại (rõ ràng)
                    return False
        else:
            # Chế độ lỏng: Chỉ kiểm tra khi ID lân cận rất gần (< 100pt) VÀ text gần ID lân cận hơn đáng kể
            if id_to_neighbor_dist < 100 and dist_to_neighbor < dist_to_current * 0.7:
                return False
    
    return True


def find_price_rects_by_words(page, id_rect, target_text: str):
    """
    Tìm vùng giá trong PDF bằng word-level để xử lý case "55 € 99".

    - target_text: chuỗi diff bên B, ví dụ "55€99".
    - Duyệt tất cả cụm 1–3 word chứa chữ số + '€'.
    - Parse thành giá float, chọn cụm:
        + giá gần target nhất
        + khoảng cách gần ID
    """
    target_val = parse_price_value(target_text)
    id_x = id_rect.x0
    id_y = id_rect.y1  # Dùng bottom của ID để chỉ tìm dưới ID
    words = page.get_text("words")  # [x0, y0, x1, y1, "word", block, line, wordno]

    candidates = []

    for n in (1, 2, 3):
        for i in range(0, len(words) - n + 1):
            chunk = words[i: i + n]
            text = " ".join(w[4] for w in chunk)

            # phải có số & '€'
            if not any(ch.isdigit() for ch in text):
                continue
            if "€" not in text:
                continue

            val = parse_price_value(text)
            if val is None:
                continue

            x0 = min(w[0] for w in chunk)
            y0 = min(w[1] for w in chunk)
            x1 = max(w[2] for w in chunk)
            y1 = max(w[3] for w in chunk)

            # Chỉ tìm giá trong phạm vi gần ID: dưới ID và không quá xa
            # Giới hạn chặt: chỉ tìm trong vòng 200pt dưới ID và 150pt ngang
            if y0 < id_y - 20 or y0 > id_y + 200:
                continue

            rect = fitz.Rect(x0, y0, x1, y1)
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            dist = math.hypot(cx - id_x, cy - id_y)
            
            # Giới hạn khoảng cách ngang: không quá 150pt sang trái/phải
            horizontal_dist = abs(cx - id_x)
            if horizontal_dist > 150:
                continue
            
            delta = abs(val - target_val) if target_val is not None else 0.0

            candidates.append((rect, dist, val, delta, text))

    if not candidates:
        return []

    # Ưu tiên: giá gần target nhất, sau đó gần ID nhất
    candidates.sort(key=lambda x: (x[3], x[1]))

    # Debug nhỏ:
    best = candidates[0]
    print(
        f"    [price-word] best='{best[4]}' val={best[2]} "
        f"delta={best[3]:.2f} dist={best[1]:.1f}"
    )

    # Trả tối đa 2 rect (thường 1 là đủ)
    return [c[0] for c in candidates[:2]]


# ============ STEP 7 MAIN ============

def step7_highlight_pdf_b(
    pdf_b_path: Path,
    step6_results_file: Path,
    output_path: Path,
    *,
    markup_color: str = "Green",
) -> dict:
    """
    Bước 7:
    - Đọc step6_results.json
    - Mỗi ID:
      + Đọc differ_product + differences (format mới)
      + Với từng phần → tìm trong PDF B & highlight
      + Annotation = image1 (A) vs image2 (B)
      + Riêng giá (có €) → dùng word-level để bắt dạng "55 € 99"
    """
    print("=" * 60)
    print("BƯỚC 7: HIGHLIGHT PDF B (PyMuPDF)")
    print("=" * 60)
    print(f"PDF B: {pdf_b_path}")
    print(f"Step6 results: {step6_results_file}")
    print(f"Output: {output_path}")
    print()

    stats = {"total": 0, "highlighted": 0, "skipped": 0, "errors": 0}

    # Đọc step6_results.json
    if not step6_results_file.exists():
        print(f"ERROR: Step6 results file not found: {step6_results_file}")
        return stats

    with open(step6_results_file, "r", encoding="utf-8") as f:
        step6_data = json.load(f)

    results = step6_data.get("results", [])
    stats["total"] = len(results)
    print(f"Found {len(results)} comparison results\n")

    # Mở PDF B
    try:
        doc = fitz.open(str(pdf_b_path))
        print(f"PDF loaded: {len(doc)} pages")
    except Exception as e:
        print(f"ERROR: Failed to load PDF B: {e}")
        stats["errors"] = 1
        return stats

    highlight_color = get_color_rgb(markup_color)
    id_position_cache: dict[str, tuple[int, fitz.Rect]] = {}
    page_id_map: dict[int, dict[str, fitz.Rect]] = defaultdict(dict)

    def locate_id(id_text: str) -> tuple[int | None, fitz.Rect | None]:
        if not id_text:
            return None, None
        cached = id_position_cache.get(id_text)
        if cached:
            return cached
        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                matches = page.search_for(id_text, flags=fitz.TEXT_DEHYPHENATE)
            except Exception:
                continue
            if matches:
                rect = matches[0]
                id_position_cache[id_text] = (page_num, rect)
                page_id_map[page_num][id_text] = rect
                return page_num, rect
        return None, None

    # Pre-cache tất cả vị trí ID để biết hàng/cột lân cận
    for entry in results:
        locate_id(entry.get("id", ""))

    for idx, entry in enumerate(results, 1):
        id_text = entry.get("id", "N/A")
        comparison_raw = entry.get("comparison", "")

        # Parse format mới: trả về list of (annotation_text, highlight_text)
        pairs = parse_comparison_json(comparison_raw)
        background_entries = parse_background_differences(comparison_raw)
        missing_elements_data = parse_missing_elements(comparison_raw)
        additional_text_pairs = extract_additional_text_from_missing_elements(comparison_raw)
        
        # Thêm additional text từ missing_elements vào pairs nếu có
        if additional_text_pairs:
            pairs.extend(additional_text_pairs)

        if not pairs and not background_entries and not missing_elements_data:
            print(f"[{idx}/{len(results)}] ID {id_text}: No differences found → skip")
            stats["skipped"] += 1
            continue

        print(f"[{idx}/{len(results)}] ID {id_text}")
        print(f"  Parts to process: {len(pairs)}")

        # 1) Tìm ID trong PDF B để giới hạn vùng tìm kiếm
        print(f"  Step 1: Finding ID '{id_text}' in PDF...")
        id_page, id_rect = locate_id(id_text)

        if id_page is None or id_rect is None:
            print(f"  ⚠️  ID '{id_text}' not found in PDF → skip")
            stats["skipped"] += 1
            continue

        print(
            f"  ✅ Found ID on page {id_page + 1} "
            f"at ({id_rect.x0:.1f}, {id_rect.y0:.1f})"
        )

        page = doc[id_page]
        page_rect = page.rect
        # Dùng bottom của ID (id_rect.y1) để đảm bảo chỉ highlight ở DƯỚI ID
        id_x = (id_rect.x0 + id_rect.x1) / 2
        id_y = id_rect.y1  # Dùng bottom của ID để delta_y > 0 nghĩa là thực sự ở dưới ID
        
        # BƯỚC 1: Đọc size ảnh từ pdf_b trong compare_temp/pdf_b
        image_b_path = entry.get("image_b")
        search_region = None
        if image_b_path:
            try:
                # Resolve đường dẫn (có thể là absolute hoặc relative)
                image_b_file = Path(image_b_path)
                if not image_b_file.is_absolute():
                    # Nếu là relative path, thử resolve từ step6_results_file
                    step6_dir = step6_results_file.parent
                    image_b_file = step6_dir / "pdf_b" / image_b_file.name
                
                if image_b_file.exists():
                    with Image.open(image_b_file) as img:
                        img_width, img_height = img.size
                        
                        # Ảnh trong pdf_b được copy từ bbox (step5), và bbox được tạo từ step1
                        # step1 convert PDF sang ảnh ở DPI 300, sau đó cắt bbox từ ảnh đó
                        # Vậy nên ảnh trong pdf_b có kích thước pixel từ ảnh gốc (DPI 300)
                        # Scale từ pixel (DPI 300) sang PDF point
                        # PDF point = pixel * (72 / 300) = pixel * 0.24
                        scale_factor = 72.0 / 300.0
                        pdf_width = img_width * scale_factor
                        pdf_height = img_height * scale_factor
                        
                        print(f"  📐 Reading image: {image_b_file.name}")
                        print(f"  📐 Image size: {img_width}x{img_height}px (DPI 300)")
                        print(f"  📐 Scale factor: {scale_factor:.4f} (72/300)")
                        print(f"  📐 PDF size: {pdf_width:.1f}x{pdf_height:.1f}pt")
                        
                        # BƯỚC 2: Tạo khung tìm kiếm chính xác dựa trên size ảnh THEO ID
                        # Ảnh pdf_b được cắt từ PDF B dựa trên ID, nên khung phải chứa ID và có kích thước bằng ảnh
                        page_rect = page.rect
                        
                        # Lấy vị trí các ID lân cận để tránh highlight nhầm
                        neighbors = page_id_map.get(id_page, {})
                        neighbor_ids = [other_id for other_id, other_rect in neighbors.items() if other_id != id_text]
                        
                        # Tìm tất cả text trong pairs, nhưng CHỈ lấy text gần ID hiện tại và KHÔNG gần ID lân cận
                        all_text_rects = []
                        for ann, highlight in pairs:
                            if highlight and highlight.strip() and highlight.strip().lower() != "null":
                                try:
                                    # Tìm text này trong PDF
                                    search_text = " ".join(highlight.split()[:5])  # Lấy 5 từ đầu
                                    matches = page.search_for(search_text, flags=fitz.TEXT_DEHYPHENATE)
                                    if matches:
                                        for match_rect in matches[:3]:  # Kiểm tra tối đa 3 matches
                                            # Tính khoảng cách đến ID hiện tại
                                            match_cx = (match_rect.x0 + match_rect.x1) / 2
                                            match_cy = (match_rect.y0 + match_rect.y1) / 2
                                            id_cx = (id_rect.x0 + id_rect.x1) / 2
                                            id_cy = (id_rect.y0 + id_rect.y1) / 2
                                            dist_to_current_id = math.hypot(match_cx - id_cx, match_cy - id_cy)
                                            
                                            # Kiểm tra xem có gần ID lân cận không
                                            too_close_to_neighbor = False
                                            for neighbor_id in neighbor_ids:
                                                neighbor_rect = neighbors[neighbor_id]
                                                neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
                                                neighbor_cy = (neighbor_rect.y0 + neighbor_rect.y1) / 2
                                                dist_to_neighbor = math.hypot(match_cx - neighbor_cx, match_cy - neighbor_cy)
                                                # Nếu text gần ID lân cận hơn ID hiện tại, bỏ qua
                                                if dist_to_neighbor < dist_to_current_id:
                                                    too_close_to_neighbor = True
                                                    break
                                            
                                            # Chỉ thêm nếu gần ID hiện tại và không gần ID lân cận
                                            if not too_close_to_neighbor and dist_to_current_id < 1000:
                                                all_text_rects.append(match_rect)
                                                break  # Chỉ lấy match đầu tiên thỏa mãn
                                except Exception:
                                    pass
                        
                        # Nếu tìm được text, dùng vùng text đó để xác định khung
                        if all_text_rects:
                            # Tìm bounding box của tất cả text (chỉ text của ID hiện tại)
                            min_x = min(r.x0 for r in all_text_rects)
                            min_y = min(r.y0 for r in all_text_rects)
                            max_x = max(r.x1 for r in all_text_rects)
                            max_y = max(r.y1 for r in all_text_rects)
                            
                            # Tạo khung bao quanh text, nhưng đảm bảo chứa ID và có kích thước tối thiểu bằng size ảnh
                            # Đảm bảo khung bắt đầu từ ID hoặc text (lấy min), nhưng không mở rộng quá về bên trái nếu có ID lân cận
                            bbox_x0_base = min(id_rect.x0, min_x) - 20  # Padding nhỏ
                            bbox_y0 = min(id_rect.y0, min_y) - 20
                            
                            # Khung phải có kích thước tối thiểu bằng size ảnh
                            text_bbox_width = max_x - min_x
                            text_bbox_height = max_y - min_y
                            
                            # Đảm bảo khung có kích thước ít nhất bằng size ảnh
                            final_width = max(pdf_width, text_bbox_width + 40)
                            final_height = max(pdf_height, text_bbox_height + 40)
                            
                            # Nếu có ID lân cận, điều chỉnh nhẹ để tránh chồng lấn, nhưng không giới hạn quá chặt
                            if neighbor_ids:
                                id_cx = (id_rect.x0 + id_rect.x1) / 2
                                
                                # Chỉ điều chỉnh nếu ID lân cận rất gần (trong vòng 100pt)
                                for neighbor_id in neighbor_ids:
                                    neighbor_rect = neighbors[neighbor_id]
                                    neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
                                    neighbor_dist = abs(neighbor_cx - id_cx)
                                    
                                    # Chỉ điều chỉnh nếu ID lân cận rất gần
                                    if neighbor_dist < 100:
                                        # ID lân cận bên trái - chỉ điều chỉnh nếu quá gần
                                        if neighbor_cx < id_cx and neighbor_rect.x1 > bbox_x0_base:
                                            bbox_x0_base = max(bbox_x0_base, neighbor_rect.x1 + 5)
                                        
                                        # ID lân cận bên phải - chỉ điều chỉnh nếu quá gần
                                        if neighbor_cx > id_cx and neighbor_rect.x0 < bbox_x0_base + final_width:
                                            # Chỉ giảm width nếu không làm width nhỏ hơn image size
                                            new_width = neighbor_rect.x0 - bbox_x0_base - 5
                                            if new_width >= pdf_width:
                                                final_width = new_width
                                
                                bbox_x0 = bbox_x0_base
                                bbox_x1 = bbox_x0 + final_width
                                
                                # Đảm bảo khung vẫn có kích thước tối thiểu bằng image size (KHÔNG phải 50%)
                                if bbox_x1 - bbox_x0 < pdf_width:
                                    # Mở rộng về bên phải nếu có thể
                                    if bbox_x1 + (pdf_width - (bbox_x1 - bbox_x0)) <= page_rect.x1:
                                        bbox_x1 = bbox_x0 + pdf_width
                                    # Hoặc mở rộng về bên trái
                                    elif bbox_x0 - (pdf_width - (bbox_x1 - bbox_x0)) >= page_rect.x0:
                                        bbox_x0 = bbox_x1 - pdf_width
                                    # Nếu không thể mở rộng, ít nhất đảm bảo width >= 70% image size
                                    else:
                                        min_width = pdf_width * 0.7
                                        if bbox_x1 - bbox_x0 < min_width:
                                            if bbox_x1 + (min_width - (bbox_x1 - bbox_x0)) <= page_rect.x1:
                                                bbox_x1 = bbox_x0 + min_width
                                            elif bbox_x0 - (min_width - (bbox_x1 - bbox_x0)) >= page_rect.x0:
                                                bbox_x0 = bbox_x1 - min_width
                            else:
                                bbox_x0 = bbox_x0_base
                                bbox_x1 = bbox_x0 + final_width
                            
                            bbox_y1 = bbox_y0 + final_height
                            
                            print(f"  🎯 Text bbox: ({min_x:.1f}, {min_y:.1f}, {max_x:.1f}, {max_y:.1f})")
                            print(f"  📏 Final bbox: ({bbox_x0:.1f}, {bbox_y0:.1f}, {bbox_x1:.1f}, {bbox_y1:.1f})")
                        else:
                            # Fallback: dùng vị trí ID và size ảnh
                            # Bắt đầu từ ID, mở rộng theo size ảnh
                            bbox_x0 = id_rect.x0
                            bbox_y0 = id_rect.y0
                            bbox_x1 = bbox_x0 + pdf_width
                            bbox_y1 = bbox_y0 + pdf_height
                            
                            # Nếu có ID lân cận, điều chỉnh nhẹ để tránh chồng lấn, nhưng không giới hạn quá chặt
                            if neighbor_ids:
                                id_cx = (id_rect.x0 + id_rect.x1) / 2
                                
                                # Chỉ điều chỉnh nếu ID lân cận rất gần (trong vòng 50pt)
                                for neighbor_id in neighbor_ids:
                                    neighbor_rect = neighbors[neighbor_id]
                                    neighbor_cx = (neighbor_rect.x0 + neighbor_rect.x1) / 2
                                    neighbor_dist = abs(neighbor_cx - id_cx)
                                    
                                    # Chỉ điều chỉnh nếu ID lân cận rất gần
                                    if neighbor_dist < 50:
                                        # ID lân cận bên trái - chỉ điều chỉnh nếu quá gần
                                        if neighbor_cx < id_cx and neighbor_rect.x1 > bbox_x0:
                                            new_x0 = max(bbox_x0, neighbor_rect.x1 + 5)
                                            # Chỉ điều chỉnh nếu không làm width nhỏ hơn image size
                                            if bbox_x1 - new_x0 >= pdf_width:
                                                bbox_x0 = new_x0
                                        
                                        # ID lân cận bên phải - chỉ điều chỉnh nếu quá gần
                                        if neighbor_cx > id_cx and neighbor_rect.x0 < bbox_x1:
                                            new_x1 = min(bbox_x1, neighbor_rect.x0 - 5)
                                            # Chỉ điều chỉnh nếu không làm width nhỏ hơn image size
                                            if new_x1 - bbox_x0 >= pdf_width:
                                                bbox_x1 = new_x1
                                
                                # Đảm bảo khung vẫn có kích thước tối thiểu bằng image size
                                if bbox_x1 - bbox_x0 < pdf_width:
                                    # Mở rộng về bên phải nếu có thể
                                    if bbox_x1 + (pdf_width - (bbox_x1 - bbox_x0)) <= page_rect.x1:
                                        bbox_x1 = bbox_x0 + pdf_width
                                    # Hoặc mở rộng về bên trái
                                    elif bbox_x0 - (pdf_width - (bbox_x1 - bbox_x0)) >= page_rect.x0:
                                        bbox_x0 = bbox_x1 - pdf_width
                                    # Nếu không thể mở rộng, ít nhất đảm bảo width >= 70% image size
                                    else:
                                        min_width = pdf_width * 0.7
                                        if bbox_x1 - bbox_x0 < min_width:
                                            if bbox_x1 + (min_width - (bbox_x1 - bbox_x0)) <= page_rect.x1:
                                                bbox_x1 = bbox_x0 + min_width
                                            elif bbox_x0 - (min_width - (bbox_x1 - bbox_x0)) >= page_rect.x0:
                                                bbox_x0 = bbox_x1 - min_width
                        
                        # Đảm bảo khung nằm trong trang và có kích thước hợp lệ
                        # NHƯNG đảm bảo width và height ít nhất bằng image size
                        search_region = fitz.Rect(
                            max(page_rect.x0, bbox_x0),
                            max(page_rect.y0, bbox_y0),
                            min(page_rect.x1, bbox_x1),
                            min(page_rect.y1, bbox_y1),
                        )
                        
                        # Đảm bảo search_region có kích thước tối thiểu bằng image size
                        # Nếu bị clip bởi page boundary, mở rộng về phía ngược lại
                        if search_region.width < pdf_width:
                            # Nếu bị clip bên phải, mở rộng về bên trái
                            if search_region.x1 >= page_rect.x1 - 1:
                                search_region.x0 = max(page_rect.x0, search_region.x1 - pdf_width)
                            # Nếu bị clip bên trái, mở rộng về bên phải
                            elif search_region.x0 <= page_rect.x0 + 1:
                                search_region.x1 = min(page_rect.x1, search_region.x0 + pdf_width)
                            # Nếu không bị clip, mở rộng từ center
                            else:
                                center_x = (search_region.x0 + search_region.x1) / 2
                                search_region.x0 = max(page_rect.x0, center_x - pdf_width / 2)
                                search_region.x1 = min(page_rect.x1, center_x + pdf_width / 2)
                                # Nếu vẫn chưa đủ, mở rộng về một phía
                                if search_region.width < pdf_width:
                                    if search_region.x0 <= page_rect.x0 + 1:
                                        search_region.x1 = min(page_rect.x1, search_region.x0 + pdf_width)
                                    else:
                                        search_region.x0 = max(page_rect.x0, search_region.x1 - pdf_width)
                        
                        if search_region.height < pdf_height:
                            # Nếu bị clip bên dưới, mở rộng lên trên
                            if search_region.y1 >= page_rect.y1 - 1:
                                search_region.y0 = max(page_rect.y0, search_region.y1 - pdf_height)
                            # Nếu bị clip bên trên, mở rộng xuống dưới
                            elif search_region.y0 <= page_rect.y0 + 1:
                                search_region.y1 = min(page_rect.y1, search_region.y0 + pdf_height)
                            # Nếu không bị clip, mở rộng từ center
                            else:
                                center_y = (search_region.y0 + search_region.y1) / 2
                                search_region.y0 = max(page_rect.y0, center_y - pdf_height / 2)
                                search_region.y1 = min(page_rect.y1, center_y + pdf_height / 2)
                                # Nếu vẫn chưa đủ, mở rộng về một phía
                                if search_region.height < pdf_height:
                                    if search_region.y0 <= page_rect.y0 + 1:
                                        search_region.y1 = min(page_rect.y1, search_region.y0 + pdf_height)
                                    else:
                                        search_region.y0 = max(page_rect.y0, search_region.y1 - pdf_height)
                        
                        # Đảm bảo search_region có kích thước hợp lệ (width và height > 0)
                        if search_region.width <= 0 or search_region.height <= 0:
                            print(f"  ⚠️  Invalid search region (width={search_region.width:.1f}, height={search_region.height:.1f}), using fallback")
                            search_region = None
                        else:
                            print(f"  📦 Search region (based on image size): ({search_region.x0:.1f}, {search_region.y0:.1f}, {search_region.x1:.1f}, {search_region.y1:.1f})")
                            print(f"  📏 Region size: {search_region.width:.1f}x{search_region.height:.1f}pt (image: {pdf_width:.1f}x{pdf_height:.1f}pt)")
            except Exception as e:
                print(f"  ⚠️  Failed to read image size: {e}")
        
        # Nếu không có search_region từ ảnh, dùng vùng tìm kiếm mặc định
        if search_region is None:
            base_max_distance = 1000  # Mở rộng bán kính để tìm được text ở xa hơn (panel bên phải)
            fallback_max_distance = 2000  # Fallback toàn trang (mở rộng để tìm được text ở panel bên phải)
            vertical_above_limit = 100
            vertical_below_limit = 1000  # Mở rộng để tìm được text ở dưới xa hơn

            # Tạo vùng tìm kiếm theo ID (tránh highlight ID lân cận)
            # Mở rộng về phía phải để tìm được text ở panel bên phải
            region_expand_left = 80
            region_expand_right = 1000  # Mở rộng lớn để tìm được text ở panel bên phải
            region_expand_top = 120
            region_expand_bottom = 1000  # Mở rộng lớn để tìm được text ở dưới
            page_rect = page.rect
            search_region = fitz.Rect(
                max(page_rect.x0, id_rect.x0 - region_expand_left),
                max(page_rect.y0, id_rect.y0 - region_expand_top),
                min(page_rect.x1, id_rect.x1 + region_expand_right),
                min(page_rect.y1, id_rect.y1 + region_expand_bottom),
            )
        else:
            # BƯỚC 3: Tìm kiếm và highlight TRONG khung đó
            # Tính toán các giá trị dựa trên search_region từ size ảnh
            base_max_distance = max(search_region.width, search_region.height) * 1.2
            fallback_max_distance = max(search_region.width, search_region.height) * 1.5
            vertical_above_limit = 100
            vertical_below_limit = search_region.height * 1.5
            print(f"  🔍 Search limits: base={base_max_distance:.1f}, fallback={fallback_max_distance:.1f}, vertical={vertical_below_limit:.1f}")
        column_left = search_region.x0
        column_right = search_region.x1

        neighbors = page_id_map.get(id_page, {})
        if neighbors:
            same_row_tolerance = 120.0
            left_boundary = page_rect.x0
            right_boundary = page_rect.x1
            top_boundary = page_rect.y0
            bottom_boundary = page_rect.y1

            for other_id, other_rect in neighbors.items():
                if other_id == id_text:
                    continue
                # Horizontal neighbors (same row) → update column window
                if abs(other_rect.y0 - id_rect.y0) <= same_row_tolerance:
                    if other_rect.x1 <= id_rect.x0:
                        # ID lân cận bên trái - giới hạn search region không mở rộng về trái quá nhiều
                        midpoint = (other_rect.x1 + id_rect.x0) / 2
                        left_boundary = max(left_boundary, midpoint)
                    elif other_rect.x0 >= id_rect.x1:
                        # ID lân cận bên phải - giới hạn search region không mở rộng về phải quá nhiều
                        midpoint = (id_rect.x1 + other_rect.x0) / 2
                        right_boundary = min(right_boundary, midpoint)

                # Vertical neighbors (same column / overlapping horizontally) → update row window
                horizontal_overlap = min(id_rect.x1, other_rect.x1) - max(id_rect.x0, other_rect.x0)
                if horizontal_overlap > 0:
                    if other_rect.y1 <= id_rect.y0:
                        midpoint = (other_rect.y1 + id_rect.y0) / 2
                        top_boundary = max(top_boundary, midpoint)
                    elif other_rect.y0 >= id_rect.y1:
                        midpoint = (id_rect.y1 + other_rect.y0) / 2
                        bottom_boundary = min(bottom_boundary, midpoint)

            # Điều chỉnh search_region nhưng đảm bảo không quá nhỏ
            original_width = search_region.width
            original_height = search_region.height

            if right_boundary - left_boundary > 20:
                new_x0 = max(search_region.x0, left_boundary)
                new_x1 = min(search_region.x1, right_boundary)
                # Chỉ điều chỉnh nếu không làm search region quá nhỏ (ít nhất 70% kích thước ban đầu)
                if new_x1 - new_x0 >= original_width * 0.7:
                    search_region.x0 = new_x0
                    search_region.x1 = new_x1
                column_left = search_region.x0
                column_right = search_region.x1

            if bottom_boundary - top_boundary > 20:
                new_y0 = max(search_region.y0, top_boundary)
                new_y1 = min(search_region.y1, bottom_boundary)
                # Chỉ điều chỉnh nếu không làm search region quá nhỏ (ít nhất 70% kích thước ban đầu)
                if new_y1 - new_y0 >= original_height * 0.7:
                    search_region.y0 = new_y0
                    search_region.y1 = new_y1

        # KHÔNG mở rộng search_region nữa vì đã được tính toán chính xác từ size ảnh và ID lân cận
        # Giữ nguyên search_region đã được tính toán
        column_left = search_region.x0
        column_right = search_region.x1

        total_found_for_id = 0
        background_highlighted = 0
        missing_highlighted = 0

        # 2) Gộp các pairs có cùng highlight_text và tổng hợp annotation
        merged_pairs: dict[str, list[str]] = {}
        for ann, highlight in pairs:
            highlight_norm = normalize_text_for_diff(highlight)
            if highlight_norm not in merged_pairs:
                merged_pairs[highlight_norm] = []
            if ann and ann.strip():
                merged_pairs[highlight_norm].append(ann.strip())
        
        # Tạo lại pairs list với annotation đã gộp (có đánh số thứ tự)
        merged_pairs_list: list[tuple[str, str]] = []
        seen_highlights: set[str] = set()
        for ann, highlight in pairs:
            highlight_norm = normalize_text_for_diff(highlight)
            if highlight_norm in seen_highlights:
                continue
            seen_highlights.add(highlight_norm)
            # Gộp tất cả annotation tương ứng với highlight này, thêm số thứ tự
            ann_parts = merged_pairs.get(highlight_norm, [])
            if len(ann_parts) > 1:
                # Nếu có nhiều phần, đánh số thứ tự
                numbered_parts = [f"{idx + 1}. {part}" for idx, part in enumerate(ann_parts)]
                merged_ann = "\n".join(numbered_parts)
            elif ann_parts:
                # Chỉ có 1 phần, không cần đánh số
                merged_ann = ann_parts[0]
            else:
                merged_ann = ann if ann else ""
            merged_pairs_list.append((merged_ann, highlight))
        
        pairs = merged_pairs_list
        
        # 3) Xử lý từng phần diff
        for part_idx, (annotation_text_raw, highlight_text) in enumerate(pairs, 1):
            highlight_text = highlight_text.strip()
            if not highlight_text:
                continue

            # Validation: Bỏ qua các description không hợp lệ (không phải text thực tế trong PDF)
            # Ví dụ: "Present in Image 2, not in Image 1", "Image 2 contains...", etc.
            if is_formatting_description(highlight_text):
                print(f"  Processing part {part_idx}/{len(pairs)}:")
                print(f"    Annotation (image1): {annotation_text_raw[:80] if annotation_text_raw else '(empty)'}...")
                print(f"    Highlight (image2): {highlight_text[:80]}...")
                print(f"    ⚠️  Skipping: description is not actual text in PDF")
                continue

            print(f"  Processing part {part_idx}/{len(pairs)}:")
            print(f"    Annotation (image1): {annotation_text_raw[:80] if annotation_text_raw else '(empty)'}...")
            print(f"    Highlight (image2): {highlight_text[:80]}...")

            # Build annotation text: Gốc (A) vs B (PDF)
            annotation_text = build_annotation(annotation_text_raw, highlight_text)
            # Chuẩn hóa text để tìm kiếm:
            #  - Gộp xuống dòng thành khoảng trắng đơn
            #  - Bỏ ký tự bullet / dấu "+" ở đầu (nếu có)
            highlight_text_normalized = " ".join(highlight_text.split())
            highlight_text_normalized = re.sub(r"^[+\-•]+\s*", "", highlight_text_normalized)
            # Nếu text chứa newline thì thay bằng space để tránh mismatch khi PDF flatten
            if "\n" in highlight_text:
                highlight_text_normalized = highlight_text_normalized.replace("\n", " ").strip()
            
            # Tạo nhiều biến thể của text để tìm kiếm linh hoạt hơn
            # 1. Text gốc đã normalize
            # 2. Text không có dấu chấm cuối
            # 3. Text không có khoảng trắng dư
            search_variants = [highlight_text_normalized.strip()]
            if highlight_text_normalized.endswith('.'):
                search_variants.append(highlight_text_normalized.rstrip('.').strip())
            if '  ' in highlight_text_normalized:
                search_variants.append(re.sub(r'\s+', ' ', highlight_text_normalized).strip())
            
            part_is_price = should_use_price_mode(highlight_text_normalized)

            found_rects: list[dict] = []

            # ---- Mode 0: ưu tiên tìm full text TRƯỚC (không cắt nhỏ) ----
            # Thử tìm với tất cả các biến thể của text
            for variant_text in search_variants:
                if len(variant_text) < 2:
                    continue
                print(f"    [mode] exact text search: '{variant_text[:50]}...'")
                try:
                    exact_matches_raw = page.search_for(
                        variant_text,
                        flags=fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE,
                    )
                except Exception:
                    exact_matches_raw = []
                if exact_matches_raw:
                    exact_matches = merge_vertically_close_rects(exact_matches_raw)
                    exact_text = variant_text  # Dùng variant đã tìm thấy
                    break
            else:
                # Không tìm thấy với bất kỳ variant nào
                exact_matches = []
                exact_text = highlight_text_normalized.strip()
            
            if exact_matches:
                for rect in exact_matches:
                    cx = (rect.x0 + rect.x1) / 2
                    cy = (rect.y0 + rect.y1) / 2
                    dist = math.hypot(cx - id_x, cy - id_y)
                    delta_y = cy - id_y
                    # Ưu tiên rect ở DƯỚI ID, nhưng cho phép một chút trên ID nếu không tìm thấy ở dưới
                    # Chỉ loại bỏ rect quá xa phía trên ID (> 50px)
                    if delta_y < -50:
                        continue
                    rank, len_rank = pattern_rank(exact_text)
                    col_overlap = compute_column_overlap(rect, column_left, column_right)
                    if col_overlap <= 0:
                        continue
                    # CHỈ tìm kiếm trong search_region (khung từ size ảnh)
                    # Nhưng cho phép một chút ngoài search region nếu cần (padding 20pt)
                    if not search_region.contains(rect):
                        # Kiểm tra xem có gần search region không (trong vòng 20pt)
                        expanded_region = fitz.Rect(
                            search_region.x0 - 20,
                            search_region.y0 - 20,
                            search_region.x1 + 20,
                            search_region.y1 + 20,
                        )
                        if not expanded_region.contains(rect):
                            continue
                    
                    # Kiểm tra xem text có gần ID hiện tại hơn ID lân cận không
                    # Nếu nằm trong search_region, dùng chế độ lỏng, nếu không dùng chế độ chặt
                    in_search_region = search_region.contains(rect) or expanded_region.contains(rect)
                    if not is_rect_closer_to_current_id(rect, id_rect, neighbors, id_text, strict=not in_search_region, search_region=search_region):
                        continue
                    
                    # Kiểm tra khoảng cách và vị trí dọc
                    if not (
                        dist <= base_max_distance
                        and delta_y <= vertical_below_limit
                    ):
                        continue
                    found_rects.append(
                        {
                            "rect": rect,
                            "dist": dist,
                            "pattern": exact_text,
                            "is_price": False,
                            "delta_y": delta_y,
                            "rank": rank,
                            "len_rank": len_rank,
                            "is_focus": False,
                            "is_exact_match": True,  # Đánh dấu exact match
                            "column_overlap": col_overlap,
                        }
                    )

            # ---- Mode 1: GIÁ → dùng word-level ----
            if part_is_price and not found_rects:
                print("    [mode] price-like → using word-level search")
                price_rects = find_price_rects_by_words(page, id_rect, highlight_text_normalized)
                for r in price_rects:
                    cy = (r.y0 + r.y1) / 2
                    cx = (r.x0 + r.x1) / 2
                    id_cx = (id_rect.x0 + id_rect.x1) / 2
                    delta_y = cy - id_y
                    delta_x = abs(cx - id_cx)
                    
                    # Với giá: chỉ chấp nhận nếu ở DƯỚI ID và không quá xa
                    # Giới hạn chặt: delta_y > 0 (dưới ID), và không quá 200pt dưới, không quá 150pt ngang
                    if delta_y <= 0 or delta_y > 200:
                        continue
                    if delta_x > 150:
                        continue
                    
                    rank, len_rank = pattern_rank(highlight_text_normalized)
                    col_overlap = compute_column_overlap(r, column_left, column_right)
                    
                    # Kiểm tra chặt chẽ với ID lân cận
                    if not is_rect_closer_to_current_id(r, id_rect, neighbors, id_text, strict=True, search_region=search_region):
                        continue
                    
                    # Phải nằm trong search_region hoặc gần search_region
                    if not search_region.contains(r):
                        # Kiểm tra xem có gần search region không (trong vòng 30pt)
                        expanded_region = fitz.Rect(
                            search_region.x0 - 30,
                            search_region.y0 - 30,
                            search_region.x1 + 30,
                            search_region.y1 + 30,
                        )
                        if not expanded_region.contains(r):
                            continue
                    
                    found_rects.append(
                        {
                            "rect": r,
                            "dist": 0.0,
                            "pattern": highlight_text_normalized,
                            "is_price": True,
                            "delta_y": delta_y,
                            "rank": rank,
                            "len_rank": len_rank,
                            "is_focus": False,
                            "column_overlap": col_overlap if col_overlap > 0 else 0.5,  # Đảm bảo có giá trị
                        }
                    )

            # ---- Mode 2: Text thường hoặc price-word không tìm được → search_for ----
            if not found_rects:
                print("    [mode] text search via page.search_for (fragments)")

                diff_snippets = extract_diff_snippets(annotation_text_raw or "", highlight_text)

                # Thử match trực tiếp bằng word sequence cho snippet ngắn
                for snippet in diff_snippets:
                    if len(snippet) > 80:
                        continue
                    seq_rects = find_rects_by_word_sequence(page, snippet)
                    for rect in seq_rects:
                        cx = (rect.x0 + rect.x1) / 2
                        cy = (rect.y0 + rect.y1) / 2
                        dist = math.hypot(cx - id_x, cy - id_y)
                        delta_y = cy - id_y
                        # CHỈ chấp nhận rect ở DƯỚI ID (delta_y > 0)
                        if delta_y <= 0:
                            continue
                        # CHỈ tìm kiếm trong search_region (khung từ size ảnh)
                        # Nhưng cho phép một chút ngoài search region nếu cần (padding 20pt)
                        if not search_region.contains(rect):
                            # Kiểm tra xem có gần search region không (trong vòng 20pt)
                            expanded_region = fitz.Rect(
                                search_region.x0 - 20,
                                search_region.y0 - 20,
                                search_region.x1 + 20,
                                search_region.y1 + 20,
                            )
                            if not expanded_region.contains(rect):
                                continue
                        
                        # Kiểm tra xem text có gần ID hiện tại hơn ID lân cận không
                        # Nếu nằm trong search_region, dùng chế độ lỏng, nếu không dùng chế độ chặt
                        in_search_region = search_region.contains(rect) or expanded_region.contains(rect)
                        if not is_rect_closer_to_current_id(rect, id_rect, neighbors, id_text, strict=not in_search_region, search_region=search_region):
                            continue
                        
                        if (
                            dist <= base_max_distance
                            and delta_y <= vertical_below_limit
                        ):
                            rank, len_rank = pattern_rank(snippet)
                            col_overlap = compute_column_overlap(rect, column_left, column_right)
                            if col_overlap <= 0:
                                continue
                            found_rects.append(
                                {
                                    "rect": rect,
                                    "dist": dist,
                                    "pattern": snippet,
                                    "is_price": False,
                                    "delta_y": delta_y,
                                    "rank": rank,
                                    "len_rank": len_rank,
                                    "is_focus": True,
                                    "column_overlap": col_overlap,
                                }
                            )

                if not found_rects:
                    search_texts_raw: list[tuple[str, bool]] = []

                    for snippet in diff_snippets:
                        search_texts_raw.append((snippet, True))

                    # text full
                    search_texts_raw.append((highlight_text_normalized, False))

                    # nếu dài → thêm head/tail
                    if len(highlight_text_normalized) > 90:
                        search_texts_raw.append((highlight_text_normalized[:90], False))
                        search_texts_raw.append((highlight_text_normalized[-90:], False))

                    # số tiền
                    money_patterns = re.findall(r"\d+\s*[€$£]", highlight_text_normalized)
                    for p in money_patterns[:3]:
                        search_texts_raw.append((p, False))

                    # số (réf, kích thước, giá lẻ)
                    pure_nums = re.findall(r"\d+", highlight_text_normalized)
                    for n in pure_nums[:3]:
                        if len(n) >= 2:
                            search_texts_raw.append((n, False))

                    # từ khóa đầu viết hoa (PARURE, ACTUEL, NASTY,...)
                    words_cap = re.findall(r"\b[A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-Za-zÀ-ÿ]{2,}\b", highlight_text_normalized)
                    for w in words_cap[:5]:  # Tăng từ 3 lên 5 để tìm được nhiều từ hơn
                        search_texts_raw.append((w, False))
                    
                    # Nếu text ngắn (như "PARURE NASTY"), thêm cả cụm từ viết hoa
                    if len(highlight_text_normalized.strip()) <= 30 and len(words_cap) >= 2:
                        # Thêm cụm 2 từ đầu viết hoa
                        cap_phrase = " ".join(words_cap[:2])
                        if cap_phrase:
                            search_texts_raw.insert(0, (cap_phrase, True))  # Ưu tiên cao

                    # Từ đơn (chỉ khi text dài, không tách text ngắn thành từng từ)
                    # Tránh trường hợp "Existe aussi :" bị tách thành "Existe" và match nhầm "Existe en noir"
                    if len(highlight_text_normalized) > 30:  # Chỉ tách từng từ khi text dài
                        words_all = re.findall(r"\b\w+\b", highlight_text_normalized)
                        for word in words_all:
                            if len(word) >= 3:  # Tối thiểu 3 ký tự để tránh match nhầm
                                search_texts_raw.append((word, False))

                    # unique & tối thiểu 2 ký tự, giữ ưu tiên focus
                    search_texts: list[tuple[str, bool]] = []
                    seen: dict[str, int] = {}
                    for text, is_focus in search_texts_raw:
                        if text is None:
                            continue
                        trimmed = text.strip()
                        if len(trimmed) < 2:
                            continue
                        idx = seen.get(trimmed)
                        if idx is not None:
                            if is_focus and not search_texts[idx][1]:
                                search_texts[idx] = (trimmed, True)
                            continue
                        search_texts.append((trimmed, is_focus))
                        seen[trimmed] = len(search_texts) - 1

                    # Nếu text quá ngắn (< 3 ký tự), vẫn thử tìm chính nó (ví dụ 'à')
                    if 1 <= len(highlight_text_normalized.strip()) < 3:
                        search_texts.insert(0, (highlight_text_normalized.strip(), True))  # Ưu tiên text gốc

                    debug_patterns = [p for p, _ in search_texts[:5]]
                    print(f"    Search patterns: {debug_patterns}{'...' if len(search_texts) > 5 else ''}")

                    for s_text, is_focus in search_texts:
                        try:
                            matches_raw = page.search_for(s_text, flags=fitz.TEXT_DEHYPHENATE)
                        except Exception:
                            continue

                        matches = merge_vertically_close_rects(matches_raw)

                        for rect in matches:
                            cx = (rect.x0 + rect.x1) / 2
                            cy = (rect.y0 + rect.y1) / 2
                            dist = math.hypot(cx - id_x, cy - id_y)
                            delta_y = cy - id_y

                            # CHỈ chấp nhận rect ở DƯỚI ID (delta_y > 0)
                            if delta_y <= 0:
                                continue

                            # CHỈ tìm kiếm trong search_region (khung từ size ảnh)
                            # Nhưng cho phép một chút ngoài search region nếu cần (padding 50pt)
                            expanded_region = fitz.Rect(
                                search_region.x0 - 50,
                                search_region.y0 - 50,
                                search_region.x1 + 50,
                                search_region.y1 + 50,
                            )
                            in_search_region = search_region.contains(rect)
                            in_expanded_region = expanded_region.contains(rect)
                            
                            if not in_expanded_region:
                                continue
                            
                            # Kiểm tra xem text có gần ID hiện tại hơn ID lân cận không
                            # Nếu nằm trong search_region, dùng chế độ lỏng, nếu không dùng chế độ chặt
                            if not is_rect_closer_to_current_id(rect, id_rect, neighbors, id_text, strict=not in_search_region, search_region=search_region):
                                continue
                            
                            # chỉ lấy vùng trong bán kính và trong cửa sổ theo chiều dọc (chỉ dưới ID)
                            if (
                                dist <= base_max_distance
                                and delta_y <= vertical_below_limit
                            ):
                                rank, len_rank = pattern_rank(s_text)
                                col_overlap = compute_column_overlap(rect, column_left, column_right)
                                if col_overlap <= 0:
                                    continue
                                found_rects.append(
                                    {
                                        "rect": rect,
                                        "dist": dist,
                                        "pattern": s_text,
                                        "is_price": False,
                                        "delta_y": delta_y,
                                        "rank": rank,
                                        "len_rank": len_rank,
                                        "is_focus": is_focus,
                                        "column_overlap": col_overlap,
                                    }
                                )

            if not found_rects:
                # Thử tìm với text gốc (không có điều kiện độ dài) nếu chưa tìm thấy
                if len(highlight_text.strip()) >= 1:
                    try:
                        matches_raw = page.search_for(highlight_text_normalized.strip(), flags=fitz.TEXT_DEHYPHENATE)
                        matches = merge_vertically_close_rects(matches_raw)
                        for rect in matches:
                            cx = (rect.x0 + rect.x1) / 2
                            cy = (rect.y0 + rect.y1) / 2
                            dist = math.hypot(cx - id_x, cy - id_y)
                            delta_y = cy - id_y
                            
                            # CHỈ chấp nhận rect ở DƯỚI ID (delta_y > 0)
                            if delta_y <= 0:
                                continue
                            
                            # CHỈ tìm kiếm trong search_region (khung từ size ảnh)
                            # Nhưng cho phép một chút ngoài search region nếu cần (padding 50pt)
                            expanded_region = fitz.Rect(
                                search_region.x0 - 50,
                                search_region.y0 - 50,
                                search_region.x1 + 50,
                                search_region.y1 + 50,
                            )
                            in_search_region = search_region.contains(rect)
                            in_expanded_region = expanded_region.contains(rect)
                            
                            if not in_expanded_region:
                                continue
                            
                            # Kiểm tra xem text có gần ID hiện tại hơn ID lân cận không
                            # Nếu nằm trong search_region, dùng chế độ lỏng, nếu không dùng chế độ chặt
                            if not is_rect_closer_to_current_id(rect, id_rect, neighbors, id_text, strict=not in_search_region, search_region=search_region):
                                continue
                            
                            if (
                                dist <= base_max_distance
                                and delta_y <= vertical_below_limit
                            ):
                                rank, len_rank = pattern_rank(highlight_text.strip())
                                col_overlap = compute_column_overlap(rect, column_left, column_right)
                                if col_overlap <= 0:
                                    continue
                                found_rects.append(
                                    {
                                        "rect": rect,
                                        "dist": dist,
                                        "pattern": highlight_text.strip(),
                                        "is_price": False,
                                        "delta_y": delta_y,
                                        "rank": rank,
                                        "len_rank": len_rank,
                                        "is_focus": False,
                                        "column_overlap": col_overlap,
                                    }
                                )
                    except Exception:
                        pass

                if not found_rects:
                    print("    [mode] fallback: search entire page (no radius limit)")
                    # Thử tìm với tất cả các biến thể của text
                    for variant_text in search_variants:
                        if len(variant_text) < 2:
                            continue
                        try:
                            global_matches_raw = page.search_for(
                                variant_text, flags=fitz.TEXT_DEHYPHENATE
                            )
                        except Exception:
                            global_matches_raw = []

                        if global_matches_raw:
                            global_matches = merge_vertically_close_rects(global_matches_raw)
                            break
                    else:
                        # Nếu không tìm thấy với variant nào, thử text gốc
                        try:
                            global_matches_raw = page.search_for(
                                highlight_text_normalized.strip(), flags=fitz.TEXT_DEHYPHENATE
                            )
                        except Exception:
                            global_matches_raw = []
                        global_matches = merge_vertically_close_rects(global_matches_raw) if global_matches_raw else []

                    for rect in global_matches:
                        cx = (rect.x0 + rect.x1) / 2
                        cy = (rect.y0 + rect.y1) / 2
                        dist = math.hypot(cx - id_x, cy - id_y)
                        delta_y = cy - id_y
                        
                        # Ưu tiên rect ở DƯỚI ID, nhưng cho phép một chút trên ID nếu không tìm thấy ở dưới
                        # Chỉ loại bỏ rect quá xa phía trên ID (> 50px)
                        if delta_y < -50:
                            continue
                        
                        # Mở rộng vùng tìm kiếm: không giới hạn search_region quá chặt trong fallback
                        # Chỉ kiểm tra khoảng cách, không kiểm tra search_region.contains() trong fallback
                        # NHƯNG vẫn phải kiểm tra text gần ID hiện tại hơn ID lân cận (chế độ lỏng trong fallback)
                        if not is_rect_closer_to_current_id(rect, id_rect, neighbors, id_text, strict=False, search_region=search_region):
                            continue
                        
                        if dist <= fallback_max_distance:
                            rank, len_rank = pattern_rank(highlight_text.strip())
                            # Trong fallback, vẫn ưu tiên rect trong cùng cột nhưng không bắt buộc
                            col_overlap = compute_column_overlap(rect, column_left, column_right)
                            # Cho phép col_overlap = 0 trong fallback để tìm được text ở panel bên phải
                            if col_overlap < 0:
                                continue
                            found_rects.append(
                                {
                                    "rect": rect,
                                    "dist": dist,
                                    "pattern": highlight_text.strip(),
                                    "is_price": False,
                                    "delta_y": delta_y,
                                    "rank": rank,
                                    "len_rank": len_rank,
                                    "is_focus": False,
                                    "column_overlap": col_overlap,
                                }
                            )

                if not found_rects:
                    print(f"    ⚠️  Part {part_idx}: not found in page. Using fallback highlight (search_region).")
                    found_rects.append(
                        {
                            "rect": search_region,
                            "dist": 0.0,
                            "pattern": "[FALLBACK] " + highlight_text.strip(),
                            "is_price": False,
                            "delta_y": 0.0,
                            "rank": 9,
                            "len_rank": 0,
                            "is_focus": False,
                            "column_overlap": 1.0,
                        }
                    )

            # Chọn rect tốt nhất: ưu tiên rect ở DƯỚI ID (delta_y > 0), rồi pattern chứa toàn bộ text, rồi mode price, rồi khoảng cách
            # Kiểm tra xem pattern có chứa toàn bộ text cần tìm không (ưu tiên pattern đầy đủ hơn)
            highlight_words = set(re.findall(r"\b\w+\b", highlight_text_normalized.lower()))
            for item in found_rects:
                pattern_words = set(re.findall(r"\b\w+\b", item["pattern"].lower()))
                # Pattern chứa càng nhiều từ của highlight_text thì càng tốt
                item["match_ratio"] = len(pattern_words & highlight_words) / max(len(highlight_words), 1) if highlight_words else 0
            
            found_rects.sort(
                key=lambda item: (
                    -item.get("column_overlap", 0.0),  # Ưu tiên nằm trong cùng cột
                    item.get("delta_y", 0) <= 0,  # Ưu tiên TUYỆT ĐỐI rect ở DƯỚI ID (delta_y > 0) - False (0) được ưu tiên trước True (1)
                    not item.get("is_exact_match", False),  # Ưu tiên exact match cao nhất
                    not item.get("is_focus", False),
                    -item.get("match_ratio", 0),  # Ưu tiên pattern chứa nhiều từ hơn
                    item.get("delta_y", 999999.0) if item.get("delta_y", 0) > 0 else 999999.0,  # Trong các rect ở dưới ID, ưu tiên gần ID hơn
                    item["rank"],
                    item["len_rank"],
                    not item["is_price"],
                    item["dist"],  # Cuối cùng mới xét khoảng cách
                )
            )
            best = found_rects[0]
            best_rect = best["rect"]
            best_dist = best["dist"]
            best_pattern = best["pattern"]
            is_priority = best["is_price"]
            best_overlap = best.get("column_overlap", 0.0)

            # Validation: Nếu khoảng cách quá xa (> 500) VÀ rect ở trên ID, có thể đang highlight nhầm
            # Nhưng nếu rect ở dưới ID, cho phép khoảng cách xa hơn (có thể text ở xa nhưng vẫn đúng)
            if best_dist > 500 and best.get("delta_y", 0) <= 0 and not is_priority:
                print(f"    ⚠️  Skipping: distance too far ({best_dist:.1f}) and above ID - might be wrong ID")
                continue
            if best_dist > 800 and not is_priority:
                print(f"    ⚠️  Skipping: distance too far ({best_dist:.1f}) - might be wrong ID")
                continue

            try:
                # Với giá (price), chỉ highlight đúng rect tìm được, không merge nhiều dòng
                if is_priority:
                    # Giá: dùng đúng rect tìm được, padding nhỏ
                    highlight_rect = fitz.Rect(
                        best_rect.x0 - 1.0,
                        best_rect.y0 - 1.0,
                        best_rect.x1 + 1.0,
                        best_rect.y1 + 1.0,
                    )
                else:
                    # Text thường: merge các dòng liên tiếp (chỉ merge các dòng gần nhau)
                    line_rects = get_line_rects_for_pattern(page, best_pattern, best_rect, padding=4.0)
                    
                    # Chỉ merge các rect gần nhau, không merge các rect quá xa
                    # Sắp xếp theo khoảng cách từ anchor_rect
                    line_rects_with_dist = []
                    anchor_cy = (best_rect.y0 + best_rect.y1) / 2
                    for r in line_rects:
                        r_cy = (r.y0 + r.y1) / 2
                        dist = abs(r_cy - anchor_cy)
                        line_rects_with_dist.append((r, dist))
                    
                    # Sắp xếp theo khoảng cách
                    line_rects_with_dist.sort(key=lambda x: x[1])
                    
                    # Chỉ merge các rect trong vòng 50pt từ anchor_rect
                    merged_rects = []
                    for r, dist in line_rects_with_dist:
                        if dist <= 50.0:  # Chỉ merge nếu trong vòng 50pt
                            merged_rects.append(r)
                        else:
                            break  # Dừng khi gặp rect quá xa
                    
                    # Nếu không có rect nào gần, chỉ dùng anchor_rect
                    if not merged_rects:
                        merged_rects = [best_rect]
                    
                    highlight_rect = fitz.Rect(merged_rects[0])
                    for r in merged_rects[1:]:
                        highlight_rect = fitz.Rect(
                            min(highlight_rect.x0, r.x0),
                            min(highlight_rect.y0, r.y0),
                            max(highlight_rect.x1, r.x1),
                            max(highlight_rect.y1, r.y1),
                        )
                annot = page.add_highlight_annot(highlight_rect)

                annot.set_colors(stroke=highlight_color)
                annot.set_info(title=f"ID {id_text}", content=annotation_text)
                annot.update()
                total_found_for_id += 1

                mode_str = "price-word" if is_priority else "text-search"
                print(
                    f"    ✅ Highlighted ({mode_str}, pattern='{best_pattern[:40]}...', "
                    f"distance={best_dist:.1f}, overlap={best_overlap:.2f})"
                )
            except Exception as e:
                print(f"    ⚠️  Failed to highlight: {e}")

        # Highlight background/missing với CHUNG annotation nếu cần
        if background_entries or missing_elements_data:
            try:
                combined_title_suffix: list[str] = []
                combined_lines: list[str] = []

                missing_rect: fitz.Rect | None = None
                bg_rect: fitz.Rect | None = None

                if missing_elements_data:
                    missing_highlighted = 1
                    missing_padding = 2.0
                    missing_rect = fitz.Rect(
                        max(page_rect.x0, id_rect.x0 - missing_padding),
                        max(page_rect.y0, id_rect.y0 - missing_padding),
                        min(page_rect.x1, id_rect.x1 + missing_padding),
                        min(page_rect.y1, id_rect.y1 + missing_padding),
                    )
                    combined_title_suffix.append("missing")
                    combined_lines.append("Missing Element")
                    img1_desc = str(missing_elements_data.get("image1") or "").strip()
                    img2_desc = str(missing_elements_data.get("image2") or "").strip()
                    combined_lines.append(f"brief: {img1_desc or '(empty)'}")
                    combined_lines.append(f"produ fini: {img2_desc or '(empty)'}")

                if background_entries:
                    background_highlighted = len(background_entries)
                    bg_padding = 4.0
                    bg_rect = fitz.Rect(
                        max(page_rect.x0, id_rect.x0 - bg_padding),
                        max(page_rect.y0, id_rect.y0 - bg_padding),
                        min(page_rect.x1, id_rect.x1 + bg_padding),
                        min(page_rect.y1, id_rect.y1 + bg_padding),
                    )
                    if combined_lines:
                        combined_lines.append("")
                    combined_title_suffix.append("background")
                    combined_lines.append("Background differences:")
                    for bg_idx, (bg_a, bg_b) in enumerate(background_entries, 1):
                        prefix = "" if len(background_entries) == 1 else f"{bg_idx}. "
                        combined_lines.append(f"{prefix}brief: {bg_a or '(empty)'}")
                        combined_lines.append(f"{prefix}produ fini: {bg_b or '(empty)'}")
                        if bg_idx != len(background_entries):
                            combined_lines.append("")

                combined_highlight_rect = bg_rect or missing_rect or id_rect
                combined_highlight_color = (
                    get_color_rgb("Yellow")
                    if background_entries
                    else get_color_rgb("Red")
                )

                # Dọn dẹp dòng trống cuối
                while combined_lines and combined_lines[-1] == "":
                    combined_lines.pop()

                content_text = (
                    "\n".join(combined_lines)
                    if combined_lines
                    else "Missing/background details"
                )
                title = f"ID {id_text}"
                if combined_title_suffix:
                    title += " (" + ", ".join(combined_title_suffix) + ")"

                annot = page.add_highlight_annot(combined_highlight_rect)
                annot.set_colors(stroke=combined_highlight_color)
                annot.set_info(title=title, content=content_text)
                annot.update()

                # Nếu cần nhấn mạnh missing riêng (khi highlight chính dùng màu background)
                if background_entries and missing_rect is not None:
                    try:
                        missing_overlay = page.add_rect_annot(missing_rect)
                        missing_overlay.set_colors(stroke=get_color_rgb("Red"))
                        missing_overlay.set_border(width=1.0)
                        missing_overlay.set_info(
                            title=f"ID {id_text} (missing area)",
                            content="Missing Element region",
                        )
                        missing_overlay.update()
                    except Exception as overlay_err:
                        print(f"  ⚠️  Failed to add missing overlay: {overlay_err}")

                if missing_elements_data:
                    print(f"  ✅ Missing element highlighted for ID {id_text}")
                if background_entries:
                    print(f"  ✅ Background difference highlighted for ID {id_text}")
            except Exception as e:
                print(f"  ⚠️  Failed to highlight missing/background: {e}")

        if total_found_for_id > 0 or background_highlighted > 0 or missing_highlighted > 0:
            stats["highlighted"] += 1
            parts_msgs = []
            if total_found_for_id > 0:
                parts_msgs.append(f"{total_found_for_id}/{len(pairs)} parts")
            if background_highlighted > 0:
                parts_msgs.append("background")
            if missing_highlighted > 0:
                parts_msgs.append("missing")
            highlighted_parts_msg = ", ".join(parts_msgs) if parts_msgs else "background only"
            print(f"  ✅ ID {id_text}: highlighted {highlighted_parts_msg}")
        else:
            stats["skipped"] += 1
            print(f"  ⚠️  ID {id_text}: no parts highlighted")

    # Lưu PDF
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print("\nSaving highlighted PDF...")
    doc.save(str(output_path))
    doc.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total results: {stats['total']}")
    print(f"Highlighted IDs: {stats['highlighted']}")
    print(f"Skipped IDs: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"Output: {output_path}")
    print("\nDone!")
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Step 7: Highlight PDF B using step6 results (PyMuPDF)"
    )
    parser.add_argument("pdf_b_path", type=str, help="Đường dẫn đến PDF B")
    parser.add_argument(
        "--step6-results",
        type=str,
        default=None,
        help="File JSON step6_results (default: ./compare_temp/step6_results.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Đường dẫn output PDF (default: ./output/pdf_b_highlighted_pymupdf.pdf)",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="Green",
        choices=["Green", "Yellow", "Red", "Blue", "Orange", "Pink"],
        help="Màu highlight",
    )

    args = parser.parse_args()

    pdf_b_path = Path(args.pdf_b_path)
    if pdf_b_path.suffix.lower() != ".pdf":
        print(f"ERROR: pdf_b_path must be PDF, got: {pdf_b_path}")
        return 1

    if args.step6_results:
        step6_results_file = Path(args.step6_results)
    else:
        step6_results_file = Path(__file__).resolve().parent / "compare_temp" / "step6_results.json"

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(__file__).resolve().parent / "output" / "pdf_b_highlighted_pymupdf.pdf"

    stats = step7_highlight_pdf_b(
        pdf_b_path=pdf_b_path,
        step6_results_file=step6_results_file,
        output_path=output_path,
        markup_color=args.color,
    )

    return 0 if stats["highlighted"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
