from __future__ import annotations

import pytest

from aitopiahub.content_engine.agents.writer import WriterAgent
from aitopiahub.core.constants import ContentAngle, PostFormat


class _FakeLLM:
    def __init__(self):
        self.last_prompt = ""

    async def complete_json(self, prompt: str, **kwargs):
        self.last_prompt = prompt
        return {
            "caption": "Masal",
            "scenes": [{"index": 0, "speaker": "Narrator", "text": "test", "image_prompt": "pixar"}],
            "image_prompt_hint": "pixar",
        }

class _FakeResearchNote:
    def __init__(self):
        self.keyword = "Kırmızı Başlıklı Kız"
        self.main_finding = "Dikkatli olmanın önemi"
        self.supporting_facts = []
        self.source_urls = []
        self.source_credibility = 10
        self.novelty_score = 10.0
        self.suggested_angle = "story"
        self.language_of_sources = "tr"


@pytest.mark.asyncio
async def test_writer_long_episode_fairy_mode_injects_constraints() -> None:
    llm = _FakeLLM()
    writer = WriterAgent(llm, persona="kids_storyteller")
    note = _FakeResearchNote()

    await writer.write(
        note,
        post_format=PostFormat.LONG_EPISODE,
        angle=ContentAngle.INFORMATIVE,
        language="tr",
        content_mode="fairy_tale",
        fairy_style="modern_educational",
        story_profile={
            "id": "red_riding_hood",
            "characters": ["Kırmızı", "Kurt"],
            "blocked_elements": ["şiddet"],
            "moral": "Güvenlik",
        },
    )

    assert "Masal modu aktif" in llm.last_prompt
    assert "Finalde tam 1 ders cümlesi" in llm.last_prompt
