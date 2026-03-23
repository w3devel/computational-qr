"""Tests for computational_qr.numberstation.capsule."""

from __future__ import annotations

import pytest

from computational_qr.numberstation.capsule import (
    CapsuleContent,
    CapsuleMeta,
    CapsuleProfile,
    CapsuleV2,
    ContentTokens,
    RepeatPolicy,
    capsule_to_e11_script,
    load_capsule,
    upgrade_e11_v1_to_capsule_v2,
)
from computational_qr.numberstation.e11_script import E11Script


# ---------------------------------------------------------------------------
# Fixtures – representative v1 E11 payload
# ---------------------------------------------------------------------------

V1_PAYLOAD: dict = {
    "v": "1",
    "station": {
        "id": "E11",
        "nickname": "Oblique",
        "family": "ENIGMA",
    },
    "transmission": {
        "role": "message",
        "variant": "E11a",
        "session_id": "042",
        "group_count": 3,
        "datetime_utc": "2026-03-23T12:00:00Z",
        "frequency_khz": 6840.0,
        "format": {
            "group_size": 5,
            "group_type": "numeric",
        },
    },
    "message": {
        "groups": ["12345", "67890", "11111"],
        "attention_token": "ATTENTION",
        "outro_token": "OUT",
        "repetitions": 2,
    },
}

V2_PAYLOAD: dict = {
    "v": "2",
    "profile": {
        "family": "ENIGMA",
        "id": "E11",
        "variant": "E11a",
        "nickname": "Oblique",
    },
    "content": {
        "group_size": 5,
        "groups": ["12345", "67890", "11111"],
        "repeat": {"mode": "repeat-block", "times": 2},
        "tokens": {"attention": "ATTENTION", "outro": "OUT"},
    },
    "meta": {
        "session_id": "042",
        "group_count": 3,
        "datetime_utc": "2026-03-23T12:00:00Z",
        "frequency_khz": 6840.0,
    },
}


# ---------------------------------------------------------------------------
# upgrade_e11_v1_to_capsule_v2
# ---------------------------------------------------------------------------

class TestUpgradeV1ToV2:
    def test_returns_capsule_v2(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert isinstance(capsule, CapsuleV2)

    def test_version_is_two(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.v == "2"

    def test_profile_id_from_station(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.profile is not None
        assert capsule.profile.id == "E11"

    def test_profile_family_from_station(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.profile.family == "ENIGMA"

    def test_profile_variant_from_transmission(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.profile.variant == "E11a"

    def test_profile_nickname_preserved(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.profile.nickname == "Oblique"

    def test_meta_session_id(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.meta is not None
        assert capsule.meta.session_id == "042"

    def test_meta_group_count(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.meta.group_count == 3

    def test_meta_datetime_utc(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.meta.datetime_utc == "2026-03-23T12:00:00Z"

    def test_meta_frequency_khz(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.meta.frequency_khz == 6840.0

    def test_content_groups_preserved(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.groups == ["12345", "67890", "11111"]

    def test_content_group_size(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.group_size == 5

    def test_content_repeat_mode(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.repeat is not None
        assert capsule.content.repeat.mode == "repeat-block"

    def test_content_repeat_times_from_repetitions(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.repeat.times == 2

    def test_content_tokens_attention(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.tokens is not None
        assert capsule.content.tokens.attention == "ATTENTION"

    def test_content_tokens_outro(self):
        capsule = upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)
        assert capsule.content.tokens.outro == "OUT"

    def test_default_repeat_times_when_missing(self):
        """Payload without explicit repetitions should default to 2."""
        payload = {
            "v": "1",
            "station": {"id": "E11"},
            "transmission": {
                "role": "message",
                "variant": "E11",
                "session_id": "001",
                "group_count": 1,
            },
            "message": {"groups": ["99999"]},
        }
        capsule = upgrade_e11_v1_to_capsule_v2(payload)
        assert capsule.content.repeat.times == 2

    def test_default_group_size_five_when_format_absent(self):
        payload = {
            "v": "1",
            "station": {"id": "E11"},
            "transmission": {
                "role": "message",
                "variant": "E11",
                "session_id": "001",
                "group_count": 1,
            },
            "message": {"groups": ["99999"]},
        }
        capsule = upgrade_e11_v1_to_capsule_v2(payload)
        assert capsule.content.group_size == 5

    def test_integrity_copied_when_present(self):
        payload = dict(V1_PAYLOAD)
        payload["integrity"] = {"encoding": "utf-8", "checksum": {"alg": "sha256", "value": "abc"}}
        capsule = upgrade_e11_v1_to_capsule_v2(payload)
        assert capsule.integrity is not None
        assert capsule.integrity.encoding == "utf-8"
        assert capsule.integrity.checksum == {"alg": "sha256", "value": "abc"}

    def test_preamble_copied_when_present(self):
        payload = dict(V1_PAYLOAD)
        payload = {**V1_PAYLOAD, "message": {**V1_PAYLOAD["message"], "preamble": ["042", "/", "3"]}}
        capsule = upgrade_e11_v1_to_capsule_v2(payload)
        assert capsule.content.preamble == ["042", "/", "3"]


# ---------------------------------------------------------------------------
# load_capsule – version routing
# ---------------------------------------------------------------------------

class TestLoadCapsule:
    def test_v2_payload_returns_capsule_v2(self):
        capsule = load_capsule(V2_PAYLOAD)
        assert isinstance(capsule, CapsuleV2)
        assert capsule.v == "2"

    def test_v1_payload_is_upgraded(self):
        capsule = load_capsule(V1_PAYLOAD)
        assert isinstance(capsule, CapsuleV2)
        assert capsule.v == "2"

    def test_v2_content_groups(self):
        capsule = load_capsule(V2_PAYLOAD)
        assert capsule.content.groups == ["12345", "67890", "11111"]

    def test_v2_profile_id(self):
        capsule = load_capsule(V2_PAYLOAD)
        assert capsule.profile is not None
        assert capsule.profile.id == "E11"

    def test_v2_meta_session_id(self):
        capsule = load_capsule(V2_PAYLOAD)
        assert capsule.meta is not None
        assert capsule.meta.session_id == "042"

    def test_v2_repeat_mode(self):
        capsule = load_capsule(V2_PAYLOAD)
        assert capsule.content.repeat is not None
        assert capsule.content.repeat.mode == "repeat-block"

    def test_v2_render_audio_preferred(self):
        payload = {**V2_PAYLOAD, "render": {"audio": {"preferred": "samples", "samples": {"voice_pack_id": "pack-001"}}}}
        capsule = load_capsule(payload)
        assert capsule.render is not None
        assert capsule.render.audio is not None
        assert capsule.render.audio.preferred == "samples"
        assert capsule.render.audio.samples is not None
        assert capsule.render.audio.samples.voice_pack_id == "pack-001"

    def test_v2_render_tts(self):
        payload = {**V2_PAYLOAD, "render": {"audio": {"preferred": "tts", "tts": {"language_tag": "en-GB", "voice_id": "carol"}}}}
        capsule = load_capsule(payload)
        assert capsule.render.audio.tts is not None
        assert capsule.render.audio.tts.language_tag == "en-GB"
        assert capsule.render.audio.tts.voice_id == "carol"


# ---------------------------------------------------------------------------
# capsule_to_e11_script
# ---------------------------------------------------------------------------

class TestCapsuleToE11Script:
    def _capsule_from_v1(self) -> CapsuleV2:
        return upgrade_e11_v1_to_capsule_v2(V1_PAYLOAD)

    def test_returns_e11_script(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        assert isinstance(script, E11Script)

    def test_station_id_from_session_id(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        assert script.station_id == 42  # "042" → 42

    def test_group_count_from_meta(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        assert script.group_count == 3

    def test_groups_converted_to_ints(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        assert script.groups == [12345, 67890, 11111]

    def test_four_line_format(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        text = script.to_text()
        lines = text.rstrip("\n").split("\n")
        assert len(lines) == 4

    def test_first_line_is_E11(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        assert script.to_text().split("\n")[0] == "E11"

    def test_station_id_line_three_digits(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        id_line = script.to_text().split("\n")[1]
        assert id_line == "042"

    def test_group_count_line(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        count_line = script.to_text().split("\n")[2]
        assert int(count_line) == 3

    def test_groups_line_content(self):
        script = capsule_to_e11_script(self._capsule_from_v1())
        groups_line = script.to_text().split("\n")[3]
        assert groups_line == "12345 67890 11111"

    def test_raises_when_group_size_not_five(self):
        capsule = CapsuleV2(
            v="2",
            profile=CapsuleProfile(id="E11"),
            content=CapsuleContent(group_size=4, groups=["1234"]),
            meta=CapsuleMeta(session_id="001"),
        )
        with pytest.raises(ValueError, match="group_size"):
            capsule_to_e11_script(capsule)

    def test_raises_when_no_session_id(self):
        capsule = CapsuleV2(
            v="2",
            profile=CapsuleProfile(id="E11"),
            content=CapsuleContent(group_size=5, groups=["12345"]),
            meta=CapsuleMeta(session_id=None),
        )
        with pytest.raises(ValueError, match="session_id"):
            capsule_to_e11_script(capsule)

    def test_group_count_falls_back_to_len_groups(self):
        """When meta.group_count is absent, derive it from len(groups)."""
        capsule = CapsuleV2(
            v="2",
            profile=CapsuleProfile(id="E11"),
            content=CapsuleContent(group_size=5, groups=["12345", "67890"]),
            meta=CapsuleMeta(session_id="007"),
        )
        script = capsule_to_e11_script(capsule)
        assert script.group_count == 2

    def test_roundtrip_via_v2_payload(self):
        """Full round-trip: v2 dict → load → capsule_to_e11_script → to_text."""
        capsule = load_capsule(V2_PAYLOAD)
        script = capsule_to_e11_script(capsule)
        text = script.to_text()
        assert text.startswith("E11\n")
        assert "042" in text
        assert "12345" in text


# ---------------------------------------------------------------------------
# CapsuleV2.to_dict round-trip
# ---------------------------------------------------------------------------

class TestCapsuleToDict:
    def test_v2_roundtrip(self):
        capsule = load_capsule(V2_PAYLOAD)
        d = capsule.to_dict()
        assert d["v"] == "2"
        assert d["content"]["groups"] == ["12345", "67890", "11111"]
        assert d["profile"]["id"] == "E11"
        assert d["meta"]["session_id"] == "042"
