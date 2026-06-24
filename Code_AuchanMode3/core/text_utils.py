import re

ALLOWED_PRICE_KEYWORDS = {
    "prix", "payé", "paye", "caisse", "soit", "cagnotte", "déduite", "deduite",
    "dont", "éco", "eco", "participation", "remise", "immédiate", "immediate",
    "ticket", "leclerc", "lot", "carte", "choix", "avantage", "avantages",
    "offert", "offerte", "gratuit", "gratuite", "cagnottée", "cagnottee",
    "contribution", "part", "eco-part", "eco-participation", "eco-contribution",
}

PRICE_STOPWORDS = {
    "remise", "immédiate", "immediate", "cagnotte", "déduite", "deduite",
    "soit", "ticket", "leclerc", "éco", "eco", "participation", "contribution",
    "dont", "prix", "payé", "paye", "en", "caisse",
}

_EXCLUDE_FROM_PRODUCT_INF = ("price", "promo_fidelite", "logo", "price_per_piece")


def strip_boilerplate(text_val, rich_text=None):
    if not text_val:
        return text_val, rich_text

    star_pattern = r'[*✩★☆✪✫✬✭✮✯✰]'
    footnote_pattern = r'(?:\([0-9a-zA-Z]{1,3}\))+'

    text_val = re.sub(star_pattern, '', text_val)
    text_val = re.sub(footnote_pattern, '', text_val)
    text_val = re.sub(r'\s+', ' ', text_val).strip()

    patterns = [
        r'(?i)offre\s+valable\s+sur\s+le\s+moins\s+cher[^\n]*',
        r'(?i)hors\s+promotions?\s+en\s+cours[^\n]*',
        r'(?i)formats\s+promo[^\n]*',
        r'(?i)ff\s+l\s+bl\s+l\s+i\s+h[^\n]*',
    ]
    exact_line_patterns = [
        r'(?i)^(ff|l|bl|i|h)$',
        r'(?i)^(l\s+bl)$',
    ]

    for pat in patterns:
        text_val = re.sub(pat, '', text_val)

    filtered_lines = []
    for line in text_val.split('\n'):
        ls = line.strip()
        if ls and not any(re.match(p, ls) for p in exact_line_patterns):
            filtered_lines.append(ls)
    text_val = "\n".join(filtered_lines)

    if rich_text is not None:
        filtered_rich = []
        current_line = []
        for w in rich_text:
            w_text = w.get("text", "")
            if w_text != "\n":
                w_text = re.sub(star_pattern, '', w_text)
                w_text = re.sub(footnote_pattern, '', w_text)
                if not w_text.strip():
                    continue
                w["text"] = w_text

            if w["text"] == "\n":
                line_str = " ".join(x["text"] for x in current_line)
                is_boiler = (
                    any(re.search(p, line_str, flags=re.IGNORECASE) for p in patterns)
                    or any(re.match(p, line_str.strip()) for p in exact_line_patterns)
                )
                if not is_boiler:
                    filtered_rich.extend(current_line)
                    filtered_rich.append(w)
                current_line = []
            else:
                current_line.append(w)

        if current_line:
            line_str = " ".join(x["text"] for x in current_line)
            if not any(re.search(p, line_str, flags=re.IGNORECASE) for p in patterns):
                filtered_rich.extend(current_line)

        while filtered_rich and filtered_rich[-1]["text"] == "\n":
            filtered_rich.pop()
        rich_text = filtered_rich

    return text_val, rich_text


def strip_price(price_val, text_val):
    if not price_val or not text_val:
        return text_val

    all_price_tokens = re.findall(r'[^\s|]+', price_val)
    if all_price_tokens and len("".join(all_price_tokens)) >= 3:
        full_pattern = r"[\s€]*".join(re.escape(t) for t in all_price_tokens)
        text_lines = []
        for tl in text_val.split('\n'):
            tl = re.sub(r"^[\s€]*" + full_pattern + r"[\s€]*", "", tl, flags=re.IGNORECASE).strip()
            tl = re.sub(r"[\s€]*" + full_pattern + r"[\s€]*$", "", tl, flags=re.IGNORECASE).strip()
            text_lines.append(tl)
        text_val = "\n".join(text_lines).strip()

    price_lines = [l.strip() for l in re.split(r'\s*\|\s*|\n', price_val) if l.strip()]
    text_lines = []
    for tl in text_val.split('\n'):
        for pl in price_lines:
            pl_tokens = re.findall(r'[^\s|]+', pl)
            if not pl_tokens or len("".join(pl_tokens)) < 2:
                continue
            pattern = r"[\s€]*".join(re.escape(t) for t in pl_tokens)
            tl = re.sub(r"^[\s€]*" + pattern + r"[\s€]*", "", tl, flags=re.IGNORECASE).strip()
            tl = re.sub(r"[\s€]*" + pattern + r"[\s€]*$", "", tl, flags=re.IGNORECASE).strip()
        text_lines.append(tl)
    text_val = "\n".join(text_lines).strip()

    return "\n".join(
        l for l in text_val.split('\n') if re.sub(r'[\s€$¢£¥*]+', '', l).strip()
    ).strip()


def extract_main_product_name(text) -> str:
    if not text:
        return ""

    connectors = {"de", "d'", "d", "à", "a", "et", "en", "au", "aux", "sans", "avec", "sur", "pour"}
    words = text.split()

    def is_upper_word(w_raw):
        w_clean = re.sub(r'\(\d+\)', '', w_raw).replace('*', '').replace('†', '').strip()
        letters = re.sub(r'[^a-zA-ZÀ-ÿ]', '', w_clean)
        return letters.isupper() and len(letters) >= 2

    kept = []
    for i, w in enumerate(words):
        w_fn = re.sub(r'\(\d+\)', '', w).replace('*', '').replace('†', '').strip()
        if not w_fn:
            continue
        if is_upper_word(w) or any(c.isdigit() for c in w_fn):
            kept.append(w_fn)
        elif w_fn.lower() in connectors:
            if kept and (i + 1) < len(words) and is_upper_word(words[i+1]):
                kept.append(w_fn)

    if kept:
        while kept and kept[-1].lower() in connectors:
            kept.pop()
        return " ".join(kept)

    return " ".join(words[:4])


def compare_price_text_word_by_word(price_a, price_b) -> float:
    if not price_a or not price_b:
        return 0.0

    def price_words(text):
        return set(re.findall(r'[a-zà-ÿ]+', text.lower()))

    wa, wb = price_words(price_a), price_words(price_b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def clean_text_for_matching(text, is_product_inf=False) -> str:
    if not text:
        return ""
    text = extract_main_product_name(text)
    s = text.lower()

    boilerplate = []
    if not is_product_inf:
        boilerplate += [r"sur votre compte wa", r"sur votre compte w", r"sur votre compte"]
    boilerplate += [
        r"d'économie", r"d'economie", r"sur la gamme", r"sur les", r"la gamme",
        r"existe d'autres variétés", r"existe d'autres varietes",
        r"soit le kg\s*:\s*\d+[\s€,.]+\d*", r"soit le kg",
        r"soit le l\s*:\s*\d+[\s€,.]+\d*", r"soit le l", r"soit l'unité",
        r"transformé en france", r"transforme en france",
        r"produit en france", r"origine france", r"prix choc",
        r"le lot de", r"remise immédiate", r"remise immediate",
        r"avec la carte", r"cagnotte déduite", r"cagnotte deduite",
        r"différentes recettes", r"differentes recettes",
        r"différents parfums", r"differents parfums",
        r"différentes variétés", r"differentes varietes", r"au choix",
        r"le 1er produit", r"le 2ème produit", r"le 2eme produit", r"le 2e produit",
        r"soit le 2ème produit", r"soit le 2eme produit", r"soit le 2e produit",
        r"offre valable sur le moins cher",
        r"cagnotte déduite\*", r"cagnotte deduite\*",
        r"les 2\s*:", r"au lieu de",
        r"vendu seul\s*(:\s*)?", r"par \d+\s*(:\s*)?",
        r"sur le \d+(ème|eme|e)?", r"sur le",
    ]
    for pattern in boilerplate:
        s = re.sub(pattern, "", s)

    s = re.sub(r'\d+[\s]*€\s*\d*', ' ', s)
    s = re.sub(r'\b\d+[\s,.]+\d{2}\b', ' ', s)
    s = re.sub(r'\d+%', ' ', s)
    s = re.sub(r'\b[a-z]\b', ' ', s)
    s = re.sub(r'[^\w\s]', ' ', s)

    filler = {
        "de", "la", "le", "les", "du", "des", "en", "et", "au", "aux", "sur",
        "pour", "dans", "avec", "sans", "par", "un", "une", "gamme", "rayon",
        "produit", "produits", "choix", "remise", "offert", "offerts",
        "gratuit", "gratuits", "immédiate", "immediate", "hors", "promotions", "cours",
    }
    s = " ".join(w for w in s.split() if w not in filler)
    return re.sub(r'\s+', ' ', s).strip()
