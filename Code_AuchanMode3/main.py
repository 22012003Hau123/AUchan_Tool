from dotenv import load_dotenv
load_dotenv()  # load .env file before anything else reads env vars

import datetime
import hashlib
import json
import logging
import os
import tempfile
import uuid
import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from ultralytics import RTDETR

try:
    from doclayout_yolo import YOLO as DocYOLO
except ImportError:
    from ultralytics import YOLO as DocYOLO

from ultralytics import YOLO as UltraYOLO

from core.engine import run_comparison

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Auchan Pipeline Comparator")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Model loading ─────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "best_DOCLAYOUT_23_6.pt")
logger.info("Loading model from %s", MODEL_PATH)

if "rt_detr" in MODEL_PATH.lower() or "rtdetr" in MODEL_PATH.lower():
    model = RTDETR(MODEL_PATH)
elif "doclayout" in MODEL_PATH.lower():
    model = DocYOLO(MODEL_PATH, task='detect')
else:
    model = UltraYOLO(MODEL_PATH, task='detect')

logger.info("Model loaded. Classes: %s", getattr(model, 'names', 'N/A'))

# ── Constants ─────────────────────────────────────────────────────────────────

HISTORY_FILE = os.path.join("static", "temp", "history.json")
UPLOAD_FINI_DIR = os.path.join("static", "uploads", "fini")
UPLOAD_ASSEMBLA_DIR = os.path.join("static", "uploads", "assembla")
MAX_UPLOAD_FILES = 10
MAX_HISTORY = 5

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_filename(name: str) -> str:
    """Strip the leading YYYYMMDD_HHMMSS_ timestamp prefix if present."""
    if len(name) > 16 and name[8] == "_" and name[15] == "_":
        return name[16:]
    return name


async def save_uploaded_files(upload_files: list, target_dir: str, max_files: int = MAX_UPLOAD_FILES):
    os.makedirs(target_dir, exist_ok=True)

    for uf in upload_files:
        await uf.seek(0)
        content = await uf.read()

        # Remove any existing file with the same original filename
        for name in os.listdir(target_dir):
            if _clean_filename(name) == uf.filename:
                try:
                    os.remove(os.path.join(target_dir, name))
                except OSError as exc:
                    logger.warning("Could not remove duplicate %s: %s", name, exc)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(target_dir, f"{timestamp}_{uf.filename}")
        with open(dest, "wb") as buf:
            buf.write(content)

        await uf.seek(0)

    # Trim oldest files if over the limit
    try:
        files = sorted(
            [os.path.join(target_dir, f) for f in os.listdir(target_dir)
             if os.path.isfile(os.path.join(target_dir, f))]
        )
        while len(files) > max_files:
            os.remove(files.pop(0))
    except OSError as exc:
        logger.warning("Upload dir cleanup error for %s: %s", target_dir, exc)


def _load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_history(history: list):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)


def _cleanup_orphaned_pdfs(history: list):
    """Remove PDF files in static/temp that are no longer referenced by history."""
    valid = set()
    for rec in history:
        for key in ("raw_fini_url", "raw_assembla_url", "annotated_fini_url", "annotated_assembla_url"):
            url = rec.get("results", {}).get(key)
            if url:
                valid.add(os.path.basename(url))

    temp_dir = os.path.join("static", "temp")
    if os.path.isdir(temp_dir):
        for filename in os.listdir(temp_dir):
            if filename.lower().endswith(".pdf") and filename not in valid:
                try:
                    os.remove(os.path.join(temp_dir, filename))
                except OSError:
                    pass


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/compare")
async def compare_pdfs(
    fini_pdfs: list[UploadFile] = File(...),
    assembla_pdfs: list[UploadFile] = File(...),
    zoom: float = 2.0,
):
    for f in fini_pdfs + assembla_pdfs:
        if not f.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="All uploaded files must be PDFs")

    await save_uploaded_files(fini_pdfs, UPLOAD_FINI_DIR)
    await save_uploaded_files(assembla_pdfs, UPLOAD_ASSEMBLA_DIR)

    temp_dir = os.path.join(tempfile.gettempdir(), f"auchan_api_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)
    path_fini = os.path.join(temp_dir, "fini.pdf")
    path_assembla = os.path.join(temp_dir, "assembla.pdf")

    try:
        # Merge Fini PDFs
        if len(fini_pdfs) == 1:
            with open(path_fini, "wb") as f:
                f.write(await fini_pdfs[0].read())
        else:
            doc = fitz.open()
            for idx, uf in enumerate(fini_pdfs):
                tmp = os.path.join(temp_dir, f"fini_{idx}.pdf")
                with open(tmp, "wb") as f:
                    f.write(await uf.read())
                src = fitz.open(tmp)
                doc.insert_pdf(src)
                src.close()
            doc.save(path_fini)
            doc.close()

        # Merge Assembla PDFs and compute stable hash
        assembla_hashes = []
        if len(assembla_pdfs) == 1:
            content = await assembla_pdfs[0].read()
            with open(path_assembla, "wb") as f:
                f.write(content)
            assembla_hashes.append(hashlib.md5(content).hexdigest())
        else:
            doc = fitz.open()
            for idx, uf in enumerate(assembla_pdfs):
                tmp = os.path.join(temp_dir, f"assembla_{idx}.pdf")
                content = await uf.read()
                with open(tmp, "wb") as f:
                    f.write(content)
                assembla_hashes.append(hashlib.md5(content).hexdigest())
                src = fitz.open(tmp)
                doc.insert_pdf(src)
                src.close()
            doc.save(path_assembla)
            doc.close()

        stable_hash = "-".join(sorted(assembla_hashes))

        results = run_comparison(
            path_fini, path_assembla, model,
            zoom=zoom, conf_thresh=0.25, iou_thresh=0.45,
            assembla_hash=stable_hash,
        )

        # Persist to history
        record = {
            "id": stable_hash[:8] + "_" + datetime.datetime.now().strftime("%H%M%S"),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fini_files": [f.filename for f in fini_pdfs],
            "assembla_files": [f.filename for f in assembla_pdfs],
            "results": results,
        }
        history = _load_history()
        history.insert(0, record)
        history = history[:MAX_HISTORY]
        _save_history(history)
        _cleanup_orphaned_pdfs(history)

        return JSONResponse(content=results)

    except Exception as exc:
        logger.exception("Comparison failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    finally:
        # Remove temporary merge directory
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


@app.get("/api/history")
async def get_history():
    return JSONResponse(content=_load_history())


@app.get("/api/uploaded-files")
async def get_uploaded_files():
    def list_dir(directory: str) -> list:
        if not os.path.isdir(directory):
            return []
        result = []
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if os.path.isfile(full):
                mtime = os.path.getmtime(full)
                result.append({
                    "filename": name,
                    "clean_name": _clean_filename(name),
                    "time": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": mtime,
                })
        result.sort(key=lambda x: x["mtime"], reverse=True)
        return result

    return JSONResponse(content={
        "fini": list_dir(UPLOAD_FINI_DIR),
        "assembla": list_dir(UPLOAD_ASSEMBLA_DIR),
    })
