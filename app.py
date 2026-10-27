import logging
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
import webbrowser
from threading import Lock, Timer

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("whisper-app")

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
RETURN_ABSOLUTE_OUTPUT_DIR = False

ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "flac", "webm", "mp4"}
ALLOWED_MODELS = {"tiny", "base", "small", "medium", "turbo", "large"}
ALLOWED_LANGUAGES = {"auto", "zh", "en", "ja", "ko"}
DEFAULT_MODEL = "small"
DEFAULT_LANGUAGE = "zh"
DEFAULT_CHUNK_MINUTES = 10
MIN_CHUNK_MINUTES = 1
MAX_CHUNK_MINUTES = 999
MAX_CONCURRENT_JOBS = 1
MAX_FILENAME_STEM_LEN = 80
JOB_RETENTION_SECONDS = 3600
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ACTIVE_STATES = {"requested", "processing", "cancel_requested"}
CONTEXT_TAIL_CHARS = 180
DEFAULT_ZH_PROMPT = "以下是繁體中文的逐字稿，請使用台灣常見繁體字與全形標點符號。"
HALLUCINATION_PHRASES = {
    "謝謝觀看",
    "感謝觀看",
    "謝謝收看",
    "感謝收看",
    "請訂閱",
    "字幕由",
    "Amara.org",
    "Subtitles by",
}

MODEL_CATALOG = [
    {"id": "tiny", "name": "Tiny", "size": "~75MB", "note": "最快，精度最低", "default": False, "enabled": True},
    {"id": "base", "name": "Base", "size": "~142MB", "note": "速度快，品質中等", "default": False, "enabled": True},
    {"id": "small", "name": "Small", "size": "~466MB", "note": "預設推薦，速度/精度平衡", "default": True, "enabled": True},
    {"id": "medium", "name": "Medium", "size": "~1.5GB", "note": "更高精度，較慢", "default": False, "enabled": True},
    {"id": "turbo", "name": "Turbo (large-v3-turbo)", "size": "~1.5GB", "note": "極高性價比，接近 Large 精度但速度大幅提升", "default": False, "enabled": True},
    {"id": "large", "name": "Large", "size": "~3GB", "note": "最高精度，最慢", "default": False, "enabled": True},
]

_model_cache = {}
_model_lock = Lock()

_opencc_converter = None
_opencc_initialized = False

_jobs = {}
_jobs_lock = Lock()

_active_jobs = 0
_active_jobs_lock = Lock()


def log_event(job_id: str, stage: str, message: str) -> None:
    logger.info("[%s] [job:%s] %s", stage, job_id, message)


def error_response(code: str, message: str, status: int = 400, details: dict | None = None):
    return (
        jsonify(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                },
            }
        ),
        status,
    )


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_chunk_minutes(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("chunk_minutes 必須是整數") from exc
    if value < MIN_CHUNK_MINUTES or value > MAX_CHUNK_MINUTES:
        raise ValueError(f"chunk_minutes 必須介於 {MIN_CHUNK_MINUTES} 到 {MAX_CHUNK_MINUTES}")
    return value


def sanitize_stem(filename: str) -> str:
    stem = secure_filename(Path(filename).stem)[:MAX_FILENAME_STEM_LEN]
    stem = stem.strip("._-")
    return stem or "audio"


def build_job_prefix(filename: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{sanitize_stem(filename)}_{timestamp}"


def fmt_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}m{secs:02d}s"


def count_words(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))
    non_cjk = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", text)
    latin_words = len(re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", non_cjk))
    return cjk_chars + latin_words


def to_traditional_zh(text: str) -> str:
    global _opencc_converter, _opencc_initialized
    if not text:
        return text
    if not _opencc_initialized:
        _opencc_initialized = True
        try:
            from opencc import OpenCC

            _opencc_converter = OpenCC("s2twp")
        except Exception:
            _opencc_converter = None
    if _opencc_converter is not None:
        try:
            return _opencc_converter.convert(text)
        except Exception:
            return text
    return text


def build_effective_prompt(language: str, user_prompt: str, context_tail: str = "") -> str:
    parts = []
    if language == "zh" and not user_prompt:
        parts.append(DEFAULT_ZH_PROMPT)
    elif language == "zh" and user_prompt:
        parts.append(f"{DEFAULT_ZH_PROMPT} {user_prompt}")
    elif user_prompt:
        parts.append(user_prompt)

    if context_tail:
        parts.append(context_tail[-CONTEXT_TAIL_CHARS:])
    return " ".join(p.strip() for p in parts if p and p.strip())


def compute_silence_boundaries(
    audio,
    sample_rate: int,
    chunk_seconds: float,
    search_window_sec: float = 15.0,
    frame_sec: float = 0.25,
) -> list[tuple[int, int]]:
    total_samples = len(audio)
    if total_samples == 0:
        return [(0, 0)]
    target_chunk_samples = int(round(chunk_seconds * sample_rate))
    if target_chunk_samples <= 0 or total_samples <= target_chunk_samples:
        return [(0, total_samples)]

    window_samples = int(round(search_window_sec * sample_rate))
    frame_samples = max(1, int(round(frame_sec * sample_rate)))

    boundaries = [0]
    current = 0
    while current + target_chunk_samples < total_samples:
        ideal = current + target_chunk_samples
        if total_samples - ideal <= window_samples:
            break

        search_start = max(current + frame_samples, ideal - window_samples)
        search_end = min(total_samples - frame_samples, ideal + window_samples)

        if search_end <= search_start + frame_samples:
            best_idx = ideal
        else:
            best_idx = ideal
            best_energy = float("inf")
            for pos in range(search_start, search_end, frame_samples):
                segment = audio[pos : pos + frame_samples]
                if len(segment) == 0:
                    continue
                try:
                    energy = float((segment * segment).mean())
                except AttributeError:
                    energy = sum(float(x) * float(x) for x in segment) / len(segment)
                if energy < best_energy:
                    best_energy = energy
                    best_idx = pos + len(segment) // 2

        boundaries.append(best_idx)
        current = best_idx

    boundaries.append(total_samples)
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def is_hallucination_or_duplicate(text: str, prev_text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return True
    if prev_text and cleaned == prev_text.strip():
        return True
    if len(cleaned) <= 14 and any(phrase in cleaned for phrase in HALLUCINATION_PHRASES):
        return True
    return False


def filter_and_normalize_segments(
    raw_segments: list[dict],
    chunk_start_sec: float,
    language: str,
) -> list[dict]:
    normalized_list = []
    prev_text = ""
    convert_zh = language == "zh"

    for seg in raw_segments:
        text = (seg.get("text") or "").strip()
        if convert_zh and text:
            text = to_traditional_zh(text)
        if is_hallucination_or_duplicate(text, prev_text):
            continue
        prev_text = text
        rel_start = float(seg.get("start", 0.0))
        rel_end = float(seg.get("end", rel_start))
        normalized_list.append(
            {
                "start": round(chunk_start_sec + rel_start, 2),
                "end": round(chunk_start_sec + rel_end, 2),
                "text": text,
            }
        )
    return normalized_list


def save_chunk_txt(output_dir: Path, job_prefix: str, chunk_index: int, start_sec: float, end_sec: float, segments: list[dict]) -> str:
    start_label = fmt_time(start_sec)
    end_label = fmt_time(end_sec)
    filename = f"{job_prefix}_第{chunk_index:02d}段_{start_label}-{end_label}.txt"
    filepath = output_dir / filename

    lines = [f"=== 第{chunk_index}段 {start_label} ~ {end_label} ===", ""]
    for seg in segments:
        if seg["text"]:
            lines.append(seg["text"])
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filename


def output_dir_for_response(output_dir: Path) -> str:
    if RETURN_ABSOLUTE_OUTPUT_DIR:
        return str(output_dir)
    try:
        return str(output_dir.relative_to(BASE_DIR))
    except ValueError:
        return output_dir.name


def create_or_reset_job(job_id: str, *, model: str, language: str, filename: str) -> None:
    with _jobs_lock:
        _jobs[job_id] = {
            "state": "requested",
            "cancel_requested": False,
            "model": model,
            "language": language,
            "filename": filename,
            "created_at": time.time(),
            "updated_at": time.time(),
        }


def update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["updated_at"] = time.time()
            _jobs[job_id].update(fields)


def set_cancel(job_id: str, cancelled: bool) -> bool:
    with _jobs_lock:
        if job_id not in _jobs:
            return False
        _jobs[job_id]["cancel_requested"] = cancelled
        if cancelled and _jobs[job_id].get("state") in {"requested", "processing"}:
            _jobs[job_id]["state"] = "cancel_requested"
        return True


def is_cancelled(job_id: str) -> bool:
    with _jobs_lock:
        return bool(_jobs.get(job_id, {}).get("cancel_requested", False))


def clear_job(job_id: str) -> None:
    with _jobs_lock:
        _jobs.pop(job_id, None)


def cleanup_old_jobs() -> None:
    now = time.time()
    with _jobs_lock:
        expired = [
            job_id
            for job_id, job in _jobs.items()
            if now - float(job.get("updated_at", job.get("created_at", now))) > JOB_RETENTION_SECONDS
        ]
        for job_id in expired:
            _jobs.pop(job_id, None)


def get_job_snapshot(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return dict(job)


def try_acquire_job_slot() -> bool:
    global _active_jobs
    with _active_jobs_lock:
        if _active_jobs >= MAX_CONCURRENT_JOBS:
            return False
        _active_jobs += 1
        return True


def release_job_slot() -> None:
    global _active_jobs
    with _active_jobs_lock:
        _active_jobs = max(0, _active_jobs - 1)


def has_cuda_device() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def use_fp16() -> bool:
    return has_cuda_device()


def job_is_active(job_id: str) -> bool:
    with _jobs_lock:
        return _jobs.get(job_id, {}).get("state") in ACTIVE_STATES


def load_audio_16k(path: str):
    """Loads audio at 16kHz mono float32 using faster_whisper (PyAV) or whisper.audio (ffmpeg)."""
    try:
        from faster_whisper.audio import decode_audio

        return decode_audio(path, sampling_rate=16000)
    except ImportError:
        pass
    try:
        import whisper.audio

        return whisper.audio.load_audio(path)
    except ImportError as exc:
        raise ImportError("無法載入音訊解碼器，請執行 start.bat / start.sh 安裝 faster-whisper") from exc


class FasterWhisperAdapter:
    """Wraps faster_whisper.WhisperModel to provide a consistent .transcribe() interface
    with per-segment cancellation check and built-in Silero VAD filtering."""

    is_faster_whisper = True

    def __init__(self, fw_model):
        self._model = fw_model

    def transcribe(self, audio_chunk, **kwargs):
        job_id = kwargs.get("_job_id", "")
        language = kwargs.get("language")
        initial_prompt = kwargs.get("initial_prompt")
        condition_on_prev = kwargs.get("condition_on_previous_text", False)
        no_speech_threshold = kwargs.get("no_speech_threshold", 0.6)
        log_prob_threshold = kwargs.get("logprob_threshold", -1.0)
        compression_ratio_threshold = kwargs.get("compression_ratio_threshold", 2.4)

        try:
            import numpy as np

            if not isinstance(audio_chunk, np.ndarray):
                audio_chunk = np.asarray(audio_chunk, dtype=np.float32)
        except Exception:
            pass

        segments_gen, info = self._model.transcribe(
            audio_chunk,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=condition_on_prev,
            no_speech_threshold=no_speech_threshold,
            log_prob_threshold=log_prob_threshold,
            compression_ratio_threshold=compression_ratio_threshold,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        collected = []
        for seg in segments_gen:
            if job_id and is_cancelled(job_id):
                break
            collected.append(
                {
                    "start": float(getattr(seg, "start", 0.0)),
                    "end": float(getattr(seg, "end", 0.0)),
                    "text": getattr(seg, "text", ""),
                }
            )

        detected_lang = getattr(info, "language", None) or language or "unknown"
        return {"language": detected_lang, "segments": collected}


def get_model(model_size: str = DEFAULT_MODEL):
    with _model_lock:
        if model_size in _model_cache:
            return _model_cache[model_size]

        has_cuda = has_cuda_device()

        try:
            from faster_whisper import WhisperModel

            device = "cuda" if has_cuda else "cpu"
            compute_type = "float16" if has_cuda else "int8"
            fw_model_name = "large-v3-turbo" if model_size == "turbo" else model_size
            logger.info("載入 faster-whisper 模型: %s (device=%s, compute_type=%s) ...", fw_model_name, device, compute_type)
            fw_model = WhisperModel(fw_model_name, device=device, compute_type=compute_type)
            adapter = FasterWhisperAdapter(fw_model)
            _model_cache[model_size] = adapter
            logger.info("faster-whisper 模型載入完成: %s", fw_model_name)
            return adapter
        except ImportError:
            pass
        except Exception as exc:
            raise RuntimeError(f"模型載入失敗: {model_size}") from exc

        try:
            import whisper
        except ImportError as exc:
            raise RuntimeError("找不到 faster-whisper 或 whisper，請執行 start.bat / start.sh") from exc

        try:
            logger.info("載入 Whisper 模型: %s ...", model_size)
            model = whisper.load_model(model_size)
        except Exception as exc:
            raise RuntimeError(f"模型載入失敗: {model_size}") from exc

        _model_cache[model_size] = model
        logger.info("模型載入完成: %s", model_size)
        return model


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/cancel", methods=["POST"])
def cancel():
    cleanup_old_jobs()
    payload = request.get_json(silent=True) or {}
    job_id = (payload.get("job_id") or request.form.get("job_id") or "").strip()
    if not job_id:
        return error_response("MISSING_JOB_ID", "缺少 job_id", 400)

    if not set_cancel(job_id, True):
        return error_response("JOB_NOT_FOUND", "找不到對應的 job_id", 404, {"job_id": job_id})

    log_event(job_id, "cancel", "cancel requested")
    return jsonify({"ok": True, "job": {"id": job_id, "cancel_requested": True}})


@app.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    cleanup_old_jobs()
    snapshot = get_job_snapshot(job_id)
    if not snapshot:
        return error_response("JOB_NOT_FOUND", "找不到對應的 job_id", 404, {"job_id": job_id})

    total_chunks = int(snapshot.get("total_chunks") or 0)
    processed_chunks = int(snapshot.get("processed_chunks") or 0)
    progress_percent = 0.0
    if total_chunks > 0:
        progress_percent = round(min(100.0, (processed_chunks / total_chunks) * 100), 1)

    started_at = snapshot.get("started_at")
    state = snapshot.get("state", "requested")
    if started_at and state in ACTIVE_STATES:
        elapsed = round(max(0.0, time.time() - float(started_at)), 1)
    else:
        elapsed = round(float(snapshot.get("elapsed_seconds") or 0), 1)

    return jsonify(
        {
            "ok": True,
            "job": {
                "id": job_id,
                "state": state,
                "cancel_requested": bool(snapshot.get("cancel_requested", False)),
                "model": snapshot.get("model"),
                "language": snapshot.get("language"),
                "filename": snapshot.get("filename"),
                "job_prefix": snapshot.get("job_prefix"),
                "processed_chunks": processed_chunks,
                "total_chunks": total_chunks,
                "progress_percent": progress_percent,
                "elapsed_seconds": elapsed,
                "word_count": int(snapshot.get("word_count") or 0),
            },
        }
    )


@app.route("/transcribe", methods=["POST"])
def transcribe():
    tmp_path = None
    job_id = ""
    cleanup_old_jobs()

    if "audio" not in request.files:
        return error_response("MISSING_AUDIO", "缺少音訊檔欄位 audio", 400)

    file = request.files["audio"]
    if not file.filename:
        return error_response("EMPTY_FILENAME", "未選擇檔案", 400)
    if not allowed_file(file.filename):
        return error_response("UNSUPPORTED_FILE_TYPE", "不支援的檔案格式", 400)

    model_size = request.form.get("model", DEFAULT_MODEL).strip().lower()
    language = request.form.get("language", DEFAULT_LANGUAGE).strip().lower()
    initial_prompt = request.form.get("initial_prompt", "").strip()
    job_id = (request.form.get("job_id", "") or "").strip() or str(uuid.uuid4())
    if not JOB_ID_PATTERN.match(job_id):
        return error_response("INVALID_JOB_ID", "job_id 只允許英數、底線、連字號，最長 64 字", 400)
    if job_is_active(job_id):
        return error_response("JOB_ID_IN_USE", "job_id 已有進行中的任務", 409, {"job_id": job_id})

    if model_size not in ALLOWED_MODELS:
        return error_response("INVALID_MODEL", "model 不在允許清單", 400, {"allowed": sorted(ALLOWED_MODELS)})
    if language not in ALLOWED_LANGUAGES:
        return error_response("INVALID_LANGUAGE", "language 不在允許清單", 400, {"allowed": sorted(ALLOWED_LANGUAGES)})

    raw_chunk_minutes = request.form.get("chunk_minutes", str(DEFAULT_CHUNK_MINUTES))
    try:
        chunk_minutes = parse_chunk_minutes(raw_chunk_minutes)
    except ValueError as exc:
        return error_response("INVALID_CHUNK_MINUTES", str(exc), 400)

    if not try_acquire_job_slot():
        return error_response("BUSY", "目前有進行中的轉錄工作，請稍後再試", 429, {"max_concurrent_jobs": MAX_CONCURRENT_JOBS})

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir_view = output_dir_for_response(output_dir)
    suffix = Path(file.filename).suffix.lower()
    job_prefix = build_job_prefix(file.filename)

    create_or_reset_job(job_id, model=model_size, language=language, filename=file.filename)
    update_job(
        job_id,
        state="processing",
        chunk_minutes=chunk_minutes,
        processed_chunks=0,
        total_chunks=0,
        word_count=0,
        elapsed_seconds=0.0,
        job_prefix=job_prefix,
    )
    log_event(job_id, "upload-start", f"file={file.filename}, model={model_size}, language={language}, chunk_minutes={chunk_minutes}")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            audio = load_audio_16k(tmp_path)
        except ImportError:
            update_job(job_id, state="failed", error_code="TRANSCRIBER_UNAVAILABLE")
            return error_response("TRANSCRIBER_UNAVAILABLE", "音訊解碼器無法載入，請重新安裝依賴", 500)

        try:
            model = get_model(model_size)
        except RuntimeError as exc:
            update_job(job_id, state="failed", error_code="MODEL_LOAD_FAILED")
            log_event(job_id, "model-load-fail", str(exc))
            return error_response("MODEL_LOAD_FAILED", "模型載入失敗，請查看伺服器日誌", 500)

        options = {
            "fp16": use_fp16(),
            "verbose": False,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "logprob_threshold": -1.0,
            "compression_ratio_threshold": 2.4,
        }
        if language != "auto":
            options["language"] = language

        start_time = time.time()
        sample_rate = 16000
        total_seconds = len(audio) / sample_rate

        write_chunk_files = chunk_minutes < MAX_CHUNK_MINUTES
        chunk_seconds = (chunk_minutes * 60) if write_chunk_files else total_seconds
        chunk_seconds = max(float(chunk_seconds), 1.0)

        if write_chunk_files:
            chunk_ranges = compute_silence_boundaries(audio, sample_rate, chunk_seconds)
        else:
            chunk_ranges = [(0, len(audio))]
        total_chunks = max(1, len(chunk_ranges))

        log_event(job_id, "processing-start", f"audio_seconds={round(total_seconds, 1)}, total_chunks={total_chunks}")
        update_job(job_id, total_chunks=total_chunks, audio_seconds=round(total_seconds, 1), started_at=start_time)

        all_segments = []
        transcript_parts = []
        saved_files = []
        detected_language = "unknown"
        cancelled = False
        processed_chunks = 0
        word_count = 0
        context_tail = ""

        for chunk_index, (start_idx, end_idx) in enumerate(chunk_ranges):
            if is_cancelled(job_id):
                cancelled = True
                update_job(job_id, state="cancelled")
                log_event(job_id, "cancelled", f"cancelled before chunk {chunk_index + 1}")
                break

            chunk_start_sec = start_idx / sample_rate
            chunk_end_sec = end_idx / sample_rate
            chunk_audio = audio[start_idx:end_idx]
            if len(chunk_audio) == 0:
                continue

            log_event(job_id, "chunk-start", f"{chunk_index + 1}/{total_chunks} {fmt_time(chunk_start_sec)}-{fmt_time(chunk_end_sec)}")
            chunk_options = dict(options)
            effective_prompt = build_effective_prompt(language, initial_prompt, context_tail)
            if effective_prompt:
                chunk_options["initial_prompt"] = effective_prompt
            if getattr(model, "is_faster_whisper", False):
                chunk_options["_job_id"] = job_id

            chunk_result = model.transcribe(chunk_audio, **chunk_options)
            log_event(job_id, "chunk-end", f"{chunk_index + 1}/{total_chunks}")

            if detected_language == "unknown":
                detected_language = chunk_result.get("language", "unknown")

            effective_lang = detected_language if detected_language != "unknown" else language
            chunk_segments = filter_and_normalize_segments(
                raw_segments=chunk_result.get("segments", []),
                chunk_start_sec=chunk_start_sec,
                language=effective_lang,
            )

            for normalized in chunk_segments:
                all_segments.append(normalized)
                text = normalized["text"]
                if text:
                    transcript_parts.append(text)
                    word_count += count_words(text)

            processed_chunks += 1
            update_job(job_id, processed_chunks=processed_chunks, elapsed_seconds=round(time.time() - start_time, 1), word_count=word_count)

            if write_chunk_files and (chunk_segments or not is_cancelled(job_id)):
                chunk_filename = save_chunk_txt(
                    output_dir=output_dir,
                    job_prefix=job_prefix,
                    chunk_index=chunk_index + 1,
                    start_sec=chunk_start_sec,
                    end_sec=chunk_end_sec,
                    segments=chunk_segments,
                )
                saved_files.append(chunk_filename)
                log_event(job_id, "save", f"chunk_file={chunk_filename}")

            if chunk_segments:
                context_tail = " ".join(s["text"] for s in chunk_segments if s["text"])[-CONTEXT_TAIL_CHARS:]

            if is_cancelled(job_id):
                cancelled = True
                update_job(job_id, state="cancelled")
                log_event(job_id, "cancelled", f"cancelled during chunk {chunk_index + 1}")
                break

        full_transcript = " ".join(transcript_parts).strip()
        elapsed = round(time.time() - start_time, 1)

        if cancelled:
            full_filename = f"{job_prefix}_已停止_部分逐字稿.txt"
        else:
            full_filename = f"{job_prefix}_完整逐字稿.txt"
        full_path = output_dir / full_filename
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(full_transcript)
        saved_files.append(full_filename)
        log_event(job_id, "save", f"full_file={full_filename}")

        final_state = "cancelled" if cancelled else "done"
        update_job(job_id, state=final_state, processed_chunks=processed_chunks, word_count=word_count, elapsed_seconds=elapsed)
        log_event(job_id, "done", f"state={final_state}, elapsed={elapsed}s, words={word_count}")

        return jsonify(
            {
                "ok": True,
                "job": {
                    "id": job_id,
                    "cancelled": cancelled,
                    "state": final_state,
                    "model": model_size,
                    "language": detected_language if detected_language != "unknown" else language,
                    "job_prefix": job_prefix,
                    "processed_chunks": processed_chunks,
                    "total_chunks": total_chunks,
                },
                "metrics": {
                    "elapsed_seconds": elapsed,
                    "audio_seconds": round(total_seconds, 1),
                    "word_count": word_count,
                },
                "result": {
                    "transcript": full_transcript,
                    "segments": all_segments,
                },
                "artifacts": {
                    "output_dir": output_dir_view,
                    "saved_files": saved_files,
                },
            }
        )

    except Exception as exc:
        update_job(job_id, state="failed", error_code="INTERNAL_ERROR")
        log_event(job_id or "-", "fail", f"{type(exc).__name__}: {exc}")
        return error_response("INTERNAL_ERROR", "轉錄失敗，請查看伺服器日誌", 500)
    finally:
        release_job_slot()
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/outputs/<path:filename>", methods=["GET"])
def download_output_file(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".txt"):
        return error_response("INVALID_FILENAME", "不合法的檔案名稱", 400)
    target = (OUTPUT_DIR / filename).resolve()
    try:
        target.relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return error_response("INVALID_FILENAME", "不合法的檔案路徑", 400)
    if not target.is_file():
        return error_response("FILE_NOT_FOUND", "找不到指定的輸出檔案", 404)
    return send_from_directory(str(OUTPUT_DIR.resolve()), filename, as_attachment=True)


@app.route("/models", methods=["GET"])
def list_models():
    return jsonify({"ok": True, "models": MODEL_CATALOG})


if __name__ == "__main__":
    host = os.environ.get("WHISPER_HOST", "127.0.0.1")
    port = int(os.environ.get("WHISPER_PORT", "5000"))
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"

    print("=" * 52)
    print("  Whisper Transcription System (faster-whisper)")
    print("=" * 52)
    print(f"  URL: {url}")
    print("  Press Ctrl+C to stop")
    print("=" * 52)

    if host != "127.0.0.1":
        logger.warning("服務綁定在 %s，區網內其他裝置可存取", host)

    if os.environ.get("WHISPER_NO_BROWSER", "").strip() not in {"1", "true", "yes"}:
        Timer(1.2, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False, threaded=True)
