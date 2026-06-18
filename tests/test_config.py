import pytest

from clipper.config import Config


def test_default_workdir_under_output():
    cfg = Config(output_dir="out")
    assert cfg.work_dir == "out/work"


def test_validate_ok():
    Config().validate()  # ne lève pas


def test_validate_rejects_bad_durations():
    with pytest.raises(ValueError):
        Config(min_duration=200, target_duration=120).validate()
    with pytest.raises(ValueError):
        Config(target_duration=200, max_duration=140).validate()


def test_validate_rejects_bad_clip_count():
    with pytest.raises(ValueError):
        Config(num_clips=0).validate()


def test_validate_rejects_bad_crop():
    with pytest.raises(ValueError):
        Config(crop_mode="diagonal").validate()


def test_to_dict_hides_api_key():
    cfg = Config(api_key="secret")
    assert "api_key" not in cfg.to_dict()


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    cfg = Config.from_env(num_clips=3)
    assert cfg.num_clips == 3
    assert cfg.api_key == "k"
