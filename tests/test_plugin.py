import json
import tempfile
from pathlib import Path

from sakuramedia_more_rank_movies.plugin import PLUGIN_ID, register

from src.plugins import (
    HOST_API_VERSION,
    METADATA_SOURCE_EXTENSION_KEY,
    RANKING_SOURCE_EXTENSION_KEY,
    PluginContext,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_declares_current_host_api_and_only_ranking_sources():
    manifest = json.loads((PLUGIN_ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["host_api_version"] == HOST_API_VERSION

    with tempfile.TemporaryDirectory() as tmp:
        registration = register(
            PluginContext(
                plugin_id=PLUGIN_ID,
                settings={},
                data_dir=Path(tmp) / "data",
                plugin_root=PLUGIN_ROOT,
            )
        )

    assert registration.version == manifest["version"]
    assert registration.host_api_version == HOST_API_VERSION
    assert registration.extensions
    assert all(
        extension.key == RANKING_SOURCE_EXTENSION_KEY
        for extension in registration.extensions
    )
    assert all(
        extension.key != METADATA_SOURCE_EXTENSION_KEY
        for extension in registration.extensions
    )
