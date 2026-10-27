import json
import re
from pathlib import Path

from sakuramedia_more_rank_movies import translations

I18N_DIR = Path(__file__).resolve().parents[1] / "i18n"
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _catalog(name: str) -> dict[str, str]:
    return json.loads((I18N_DIR / f"{name}.json").read_text(encoding="utf-8"))


def test_text_helpers_fall_back_when_keys_are_missing(monkeypatch):
    monkeypatch.setattr(
        translations,
        "_CATALOGS",
        {"zh-CN": {"only.zh": "中文"}, "en": {}},
    )

    assert translations.text("only.zh") == "中文"
    assert translations.text("only.zh", locale="en") == "中文"
    assert translations.text("missing", default="fallback") == "fallback"
    assert translations.text("missing") == "missing"
    assert translations.text_map("only.zh") == {"zh-CN": "中文"}
    assert translations.text_map("missing") == {}


def test_load_catalog_returns_empty_for_missing_and_invalid_files(tmp_path):
    assert translations._load_catalog(tmp_path / "missing.json") == {}

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert translations._load_catalog(invalid) == {}

    not_object = tmp_path / "list.json"
    not_object.write_text(json.dumps(["x"]), encoding="utf-8")
    assert translations._load_catalog(not_object) == {}


def test_load_catalog_keeps_only_string_entries(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps({"ok": "text", "bad": 1}),
        encoding="utf-8",
    )

    assert translations._load_catalog(path) == {"ok": "text"}


def test_catalogs_share_key_sets_and_placeholders():
    zh = _catalog("zh-CN")
    en = _catalog("en")

    assert set(zh) == set(en)
    for key, value in zh.items():
        assert set(_PLACEHOLDER.findall(value)) == set(
            _PLACEHOLDER.findall(en[key])
        ), key


def test_catalogs_translate_user_visible_text():
    zh = _catalog("zh-CN")
    en = _catalog("en")

    assert zh["boards.javlibrary_bestrated"] == "JavLibrary 高评价"
    assert en["boards.javlibrary_bestrated"] == "JavLibrary Top Rated"
    assert zh["boards.javlibrary_mostwanted"] == "JavLibrary 最想要"
    assert en["boards.javlibrary_mostwanted"] == "JavLibrary Most Wanted"
    assert zh["manifest.display_name"] == "SakuraMedia 更多影片榜单"
    assert en["manifest.display_name"] == "SakuraMedia More Movie Rankings"
    assert zh["progress.action.aborted"] == "任务中止"
    assert en["progress.action.aborted"] == "Task aborted"


def test_runtime_text_without_translator_keeps_chinese_source():
    assert translations.runtime_text(None, "progress.action.finished") == "已完成"
    assert (
        translations.runtime_text(
            None,
            "javlibrary.page.ranking_page",
            page=3,
        )
        == "榜单第 3 页"
    )


def test_runtime_text_delegates_with_preformatted_default():
    calls = []

    class FakeI18n:
        def t(self, key, default=None, **params):
            calls.append((key, default, params))
            return "translated"

    assert (
        translations.runtime_text(
            FakeI18n(),
            "minnano.error.http_status",
            page="榜单",
            status=503,
        )
        == "translated"
    )
    assert calls == [
        (
            "minnano.error.http_status",
            "Minnano AV 榜单返回 HTTP 503",
            {"page": "榜单", "status": 503},
        )
    ]
