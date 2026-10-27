import io
import re
import sys
import types

import pytest

import app as whisper_app


def install_fake_whisper(monkeypatch, *, seconds=12.0, language="zh", segments=None, fail_transcribe=False, capture_kwargs=None):
    if segments is None:
        segments = [{"start": 0.0, "end": 1.0, "text": "測試文字"}]

    whisper_module = types.ModuleType("whisper")
    audio_module = types.ModuleType("whisper.audio")

    sample_rate = 16000
    fake_audio = [0.0] * int(seconds * sample_rate)

    def load_audio(_path):
        return fake_audio

    class FakeModel:
        def transcribe(self, _audio_chunk, **kwargs):
            if capture_kwargs is not None:
                capture_kwargs.append(kwargs)
            if fail_transcribe:
                raise RuntimeError("secret backend detail")
            return {"language": language, "segments": segments}

    def load_model(_name):
        return FakeModel()

    audio_module.load_audio = load_audio
    whisper_module.load_model = load_model
    whisper_module.audio = audio_module

    monkeypatch.setitem(sys.modules, "whisper", whisper_module)
    monkeypatch.setitem(sys.modules, "whisper.audio", audio_module)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(whisper_app, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(whisper_app, "RETURN_ABSOLUTE_OUTPUT_DIR", False)

    whisper_app._model_cache.clear()
    whisper_app._jobs.clear()
    whisper_app._active_jobs = 0

    with whisper_app.app.test_client() as test_client:
        yield test_client


def make_upload_data(**overrides):
    data = {
        "audio": (io.BytesIO(b"dummy"), "meeting.mp3"),
        "model": "small",
        "language": "zh",
        "chunk_minutes": "999",
        "job_id": "job-test-001",
    }
    data.update(overrides)
    return data


def test_allowed_file():
    assert whisper_app.allowed_file("a.mp3")
    assert whisper_app.allowed_file("a.MP4")
    assert not whisper_app.allowed_file("a.txt")
    assert not whisper_app.allowed_file("noext")


def test_count_words_mixed_cjk_and_english():
    assert whisper_app.count_words("測試文字") == 4
    assert whisper_app.count_words("Hello world") == 2
    assert whisper_app.count_words("今天開會討論 AI agent 架構") == 9


def test_build_job_prefix_format():
    prefix = whisper_app.build_job_prefix("../中文 檔案!!.mp3")
    assert re.match(r"^[A-Za-z0-9_-]+_\d{8}_\d{6}$", prefix)


def test_parse_chunk_minutes_bounds():
    assert whisper_app.parse_chunk_minutes("1") == 1
    assert whisper_app.parse_chunk_minutes("999") == 999
    with pytest.raises(ValueError):
        whisper_app.parse_chunk_minutes("0")
    with pytest.raises(ValueError):
        whisper_app.parse_chunk_minutes("1000")
    with pytest.raises(ValueError):
        whisper_app.parse_chunk_minutes("abc")


def test_transcribe_success_schema(client, monkeypatch):
    install_fake_whisper(monkeypatch, seconds=8.0)
    res = client.post("/transcribe", data=make_upload_data(), content_type="multipart/form-data")
    assert res.status_code == 200

    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["job"]["id"] == "job-test-001"
    assert payload["job"]["model"] == "small"
    assert isinstance(payload["metrics"]["elapsed_seconds"], float)
    assert payload["result"]["transcript"] != ""
    assert payload["artifacts"]["output_dir"] == "output"
    assert payload["artifacts"]["saved_files"]
    assert any(re.search(r"_\d{8}_\d{6}_", name) for name in payload["artifacts"]["saved_files"])


def test_transcribe_context_carryover(client, monkeypatch):
    captured = []
    install_fake_whisper(monkeypatch, seconds=130.0, capture_kwargs=captured)
    res = client.post(
        "/transcribe",
        data=make_upload_data(chunk_minutes="1", initial_prompt="專有名詞"),
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    assert len(captured) == 3
    assert captured[0]["initial_prompt"] == "專有名詞"
    assert "測試文字" in captured[1]["initial_prompt"]


def test_transcribe_validation_errors(client):
    res = client.post("/transcribe", data={}, content_type="multipart/form-data")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "MISSING_AUDIO"

    bad_model = client.post("/transcribe", data=make_upload_data(model="xlarge"), content_type="multipart/form-data")
    assert bad_model.status_code == 400
    assert bad_model.get_json()["error"]["code"] == "INVALID_MODEL"

    bad_language = client.post("/transcribe", data=make_upload_data(language="fr"), content_type="multipart/form-data")
    assert bad_language.status_code == 400
    assert bad_language.get_json()["error"]["code"] == "INVALID_LANGUAGE"

    bad_chunk = client.post("/transcribe", data=make_upload_data(chunk_minutes="0"), content_type="multipart/form-data")
    assert bad_chunk.status_code == 400
    assert bad_chunk.get_json()["error"]["code"] == "INVALID_CHUNK_MINUTES"

    bad_job_id = client.post("/transcribe", data=make_upload_data(job_id="bad/job..id"), content_type="multipart/form-data")
    assert bad_job_id.status_code == 400
    assert bad_job_id.get_json()["error"]["code"] == "INVALID_JOB_ID"


def test_transcribe_rejects_duplicate_active_job_id(client):
    whisper_app.create_or_reset_job("dup-job", model="small", language="zh", filename="a.mp3")
    whisper_app.update_job("dup-job", state="processing")

    res = client.post("/transcribe", data=make_upload_data(job_id="dup-job"), content_type="multipart/form-data")
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "JOB_ID_IN_USE"


def test_download_output_file(client, monkeypatch):
    install_fake_whisper(monkeypatch, seconds=8.0)
    res = client.post("/transcribe", data=make_upload_data(), content_type="multipart/form-data")
    saved = res.get_json()["artifacts"]["saved_files"][0]

    dl = client.get(f"/outputs/{saved}")
    assert dl.status_code == 200
    assert "測試文字" in dl.get_data(as_text=True)

    bad = client.get("/outputs/..%2Fapp.py")
    assert bad.status_code == 400


def test_cancel_endpoint(client):
    missing = client.post("/cancel", json={})
    assert missing.status_code == 400
    assert missing.get_json()["error"]["code"] == "MISSING_JOB_ID"

    not_found = client.post("/cancel", json={"job_id": "not-found"})
    assert not_found.status_code == 404
    assert not_found.get_json()["error"]["code"] == "JOB_NOT_FOUND"

    whisper_app.create_or_reset_job("job-to-cancel", model="small", language="zh", filename="a.mp3")
    ok = client.post("/cancel", json={"job_id": "job-to-cancel"})
    assert ok.status_code == 200
    assert ok.get_json()["ok"] is True
    assert ok.get_json()["job"]["cancel_requested"] is True


def test_get_job_status_not_found(client):
    res = client.get("/jobs/missing-job")
    assert res.status_code == 404
    payload = res.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "JOB_NOT_FOUND"


def test_get_job_status_progress(client):
    whisper_app.create_or_reset_job("job-progress", model="small", language="zh", filename="meeting.mp3")
    whisper_app.update_job("job-progress", state="processing", processed_chunks=2, total_chunks=5, word_count=88, elapsed_seconds=12.4)

    res = client.get("/jobs/job-progress")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["job"]["id"] == "job-progress"
    assert payload["job"]["state"] == "processing"
    assert payload["job"]["processed_chunks"] == 2
    assert payload["job"]["total_chunks"] == 5
    assert payload["job"]["progress_percent"] == 40.0


def test_transcribe_cancelled_state(client, monkeypatch):
    install_fake_whisper(monkeypatch, seconds=8.0)
    monkeypatch.setattr(whisper_app, "is_cancelled", lambda _job_id: True)

    res = client.post("/transcribe", data=make_upload_data(job_id="job-cancelled"), content_type="multipart/form-data")
    assert res.status_code == 200
    payload = res.get_json()
    assert payload["ok"] is True
    assert payload["job"]["cancelled"] is True
    assert payload["job"]["state"] == "cancelled"


def test_transcribe_model_load_failed(client, monkeypatch):
    install_fake_whisper(monkeypatch, seconds=8.0)
    monkeypatch.setattr(whisper_app, "get_model", lambda _model: (_ for _ in ()).throw(RuntimeError("boom")))

    res = client.post("/transcribe", data=make_upload_data(), content_type="multipart/form-data")
    assert res.status_code == 500
    payload = res.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MODEL_LOAD_FAILED"


def test_transcribe_internal_error_no_detail_leak(client, monkeypatch):
    install_fake_whisper(monkeypatch, fail_transcribe=True)
    res = client.post("/transcribe", data=make_upload_data(), content_type="multipart/form-data")
    assert res.status_code == 500
    payload = res.get_json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "secret backend detail" not in payload["error"]["message"]
