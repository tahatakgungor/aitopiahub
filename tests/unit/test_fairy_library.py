from __future__ import annotations

from pathlib import Path

from aitopiahub.content_engine.fairy_library import FairyLibrary


def test_fairy_library_load_and_pick(tmp_path: Path) -> None:
    p = tmp_path / "fairy.yaml"
    p.write_text(
        """
stories:
  - id: red
    title: Red
    theme: safety
  - id: rap
    title: Rap
    theme: hope
""",
        encoding="utf-8",
    )

    lib = FairyLibrary(p)
    assert len(lib.stories) == 2

    picked = lib.get_story_for_today({"red": 5.0, "rap": 0.2})
    assert picked is not None
    assert picked["id"] in {"red", "rap"}


def test_build_internal_candidates_contains_mode_labels(tmp_path: Path) -> None:
    p = tmp_path / "fairy.yaml"
    p.write_text(
        """
stories:
  - id: red
    title: Red
    theme: safety
""",
        encoding="utf-8",
    )
    lib = FairyLibrary(p)
    items = lib.build_internal_candidates([{"keyword": "uzay"}])
    assert any(i["mode"] == "fairy_tale" for i in items)
    assert any(i["mode"] == "demand_driven" for i in items)
