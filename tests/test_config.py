"""Settings file and portable mode."""

import json

from slidecatch import config


def test_defaults():
    s = config.Settings()
    assert s.interval == 1 and s.language == "en" and s.sensitivity == "medium"
    assert s.ignore_live and s.hotkeys and not s.terms_accepted


def test_clamp_repairs_bad_values():
    s = config.Settings(interval=0, sensitivity="extreme", language="de", theme="pink",
                        export_format="docx", mode="tab", area_mode="magic").clamp()
    assert (s.interval, s.sensitivity, s.language, s.theme) == (1, "medium", "en", "light")
    assert (s.export_format, s.mode, s.area_mode) == ("pptx", "window", "auto")
    assert config.Settings(interval=600).clamp().interval == 60


def test_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDECATCH_HOME", str(tmp_path))
    s = config.Settings(language="ar", interval=3, region=[10, 20, 300, 200], area=[0.1, 0.1, 0.5, 0.5])
    config.save(s)
    loaded = config.load()
    assert (loaded.language, loaded.interval, loaded.region, loaded.area) == \
        ("ar", 3, [10, 20, 300, 200], [0.1, 0.1, 0.5, 0.5])
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]   # no temporary file left


def test_damaged_or_old_file_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDECATCH_HOME", str(tmp_path))
    (tmp_path / "settings.json").write_text("{ broken", encoding="utf-8")
    assert config.load() == config.Settings()
    (tmp_path / "settings.json").write_text(json.dumps({"interval": 0, "unknown_key": 1}),
                                            encoding="utf-8")
    assert config.load().interval == 1                  # unknown keys ignored, values clamped


def test_portable_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("SLIDECATCH_HOME", raising=False)
    monkeypatch.setattr(config, "program_dir", lambda: str(tmp_path))
    assert not config.is_portable()
    (tmp_path / config.PORTABLE_MARKER).write_text("", encoding="utf-8")
    assert config.is_portable()
    assert config.config_dir() == str(tmp_path / "settings")
    assert config.default_sessions_dir() == str(tmp_path / "sessions")
    assert config.default_export_dir() == str(tmp_path / "exports")
