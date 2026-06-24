import logging
import os

import requests

from .utils import encode_image_base64

logger = logging.getLogger(__name__)

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

_VLM_VERIFY_CLASSES = ("pack", "logo", "product_origin", "price_per_piece", "promo_fidelite")

_CLS_DESCRIPTIONS = {
    "logo":            "logo or badge visible in the product block (ex: 'MON JOUR W!', brand logo, loyalty badge, promotional sticker)",
    "pack":            "pack/lot badge (ex: '2x', 'lot de 3', pack indicator)",
    "product_origin":  "origin label (ex: drapeau France, 'Produit en France')",
    "price_per_piece": "unit price box (ex: 'Soit X€', 'la portion de X g', 'soit X€/kg', 'soit X€/L', 'soit X€/pièce')",
    "promo_fidelite":  "loyalty promo badge (ex: pastille carte fidélité, cagnotte)",
}


def nvidia_headers() -> dict:
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        logger.warning("NVIDIA_API_KEY env var is not set — VLM API calls will fail.")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def verify_missing_elements_via_vlm(element, target_block, cls_name):
    """
    Gửi crop của 1 element + full block của bên còn thiếu.
    Hỏi VLM: "Element này có xuất hiện trong block không?"
    YES → YOLO miss → True (skip annotation)
    NO  → lệch thực → False (ghi annotation)
    Lỗi → None (skip annotation)
    """
    cls_desc = _CLS_DESCRIPTIONS.get(cls_name, cls_name)

    prompt = (
        f"Tu es un expert en contrôle qualité de tracts publicitaires supermarché.\n\n"
        f"Ci-dessous tu vois 1 élément de type « {cls_desc} » détecté dans un bloc produit.\n\n"
        f"Question : Est-ce que cet élément est présent dans l'image du bloc ci-dessous ? "
        f"Il peut se trouver à une position différente ou chevaucher la photo produit.\n\n"
        f"Réponds UNIQUEMENT par YES (présent) ou NO (absent)."
    )

    content = [{"type": "text", "text": prompt}]

    b64 = element.get("crop_base64")
    if b64:
        content += [
            {"type": "text", "text": "Élément détecté :"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]

    b64_target = encode_image_base64(target_block.get("crop"))
    if b64_target:
        content += [
            {"type": "text", "text": "Image du bloc à vérifier :"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_target}"}},
        ]

    payload = {
        "model": "minimaxai/minimax-m3",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 10,
        "temperature": 0.0,
    }

    logger.info("[VLM-VERIFY] class='%s' | 1 crop + 1 full block", cls_name)

    try:
        resp = requests.post(NVIDIA_API_URL, headers=nvidia_headers(), json=payload, timeout=45)
        if resp.status_code == 200:
            raw_ans = resp.json()["choices"][0]["message"]["content"].strip()
            verdict = "YES" in raw_ans.upper()
            logger.info(
                "[VLM-VERIFY] class='%s' → '%s' → %s",
                cls_name, raw_ans[:40],
                "YOLO miss → bỏ qua" if verdict else "lệch thực → annotation",
            )
            return verdict
        logger.warning("[VLM-VERIFY] API error %d → skip: %s", resp.status_code, resp.text[:200])
        return None
    except Exception as exc:
        logger.warning("[VLM-VERIFY] Exception → skip: %s", exc)
        return None
