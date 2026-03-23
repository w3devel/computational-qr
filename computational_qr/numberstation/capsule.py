"""Number-station QR capsule v2 – data model and migration helpers.

This module defines profile-agnostic dataclasses for the v2 capsule schema
(see ``computational_qr/schemas/numberstations-capsule.v2.schema.json``) and
provides helpers for:

- Parsing raw dicts into typed objects (:func:`load_capsule`).
- Upgrading legacy v1 E11 payloads to v2 (:func:`upgrade_e11_v1_to_capsule_v2`).
- Converting a v2 capsule back to an :class:`~.e11_script.E11Script`
  (:func:`capsule_to_e11_script`).

No external dependencies beyond the standard library are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CapsuleProfile:
    """Optional descriptor for the station style (e.g. ENIGMA E11)."""

    family: Optional[str] = None
    id: Optional[str] = None
    variant: Optional[str] = None
    nickname: Optional[str] = None
    voice: Optional[str] = None
    mode: Optional[str] = None
    location_hint: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RepeatPolicy:
    """Repetition policy for the groups block."""

    mode: str = "none"
    times: Optional[int] = None

    def to_dict(self) -> dict:
        d: dict = {"mode": self.mode}
        if self.times is not None:
            d["times"] = self.times
        return d


@dataclass
class ContentTokens:
    """Optional callup/closing tokens."""

    attention: Optional[str] = None
    outro: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class CapsuleContent:
    """The canonical groups payload (required in a v2 capsule)."""

    group_size: int
    groups: list[str]
    repeat: Optional[RepeatPolicy] = None
    tokens: Optional[ContentTokens] = None
    preamble: Optional[list[str]] = None
    count_announce: Optional[bool] = None

    def to_dict(self) -> dict:
        d: dict = {
            "group_size": self.group_size,
            "groups": list(self.groups),
        }
        if self.repeat is not None:
            d["repeat"] = self.repeat.to_dict()
        if self.tokens is not None:
            tok = self.tokens.to_dict()
            if tok:
                d["tokens"] = tok
        if self.preamble is not None:
            d["preamble"] = list(self.preamble)
        if self.count_announce is not None:
            d["count_announce"] = self.count_announce
        return d


@dataclass
class CapsuleMeta:
    """Optional transmission metadata."""

    datetime_utc: Optional[str] = None
    frequency_khz: Optional[float] = None
    session_id: Optional[str] = None
    group_count: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RenderText:
    """Text rendering hints."""

    separator: str = " "
    line_break_every: Optional[int] = None

    def to_dict(self) -> dict:
        d: dict = {"separator": self.separator}
        if self.line_break_every is not None:
            d["line_break_every"] = self.line_break_every
        return d


@dataclass
class RenderAudioTTS:
    """Text-to-speech rendering preferences (reference only, no binary data)."""

    language_tag: str = "en-US"
    voice_id: Optional[str] = None
    rate: Optional[float] = None
    pitch: Optional[float] = None
    engine: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RenderAudioSamples:
    """Pre-recorded sample-pack rendering preferences (reference only, no binary data)."""

    voice_pack_id: str = ""
    digit_set_id: Optional[str] = None
    asset_base_uri: Optional[str] = None
    silence_ms_between_digits: Optional[int] = None
    silence_ms_between_groups: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class RenderAudio:
    """Audio rendering preferences."""

    preferred: str = "tts"
    tts: Optional[RenderAudioTTS] = None
    samples: Optional[RenderAudioSamples] = None

    def to_dict(self) -> dict:
        d: dict = {"preferred": self.preferred}
        if self.tts is not None:
            d["tts"] = self.tts.to_dict()
        if self.samples is not None:
            d["samples"] = self.samples.to_dict()
        return d


@dataclass
class CapsuleRender:
    """Optional rendering hints for text and audio output."""

    text: Optional[RenderText] = None
    audio: Optional[RenderAudio] = None

    def to_dict(self) -> dict:
        d: dict = {}
        if self.text is not None:
            d["text"] = self.text.to_dict()
        if self.audio is not None:
            d["audio"] = self.audio.to_dict()
        return d


@dataclass
class CapsuleIntegrity:
    """Optional integrity/checksum information."""

    encoding: Optional[str] = None
    checksum: Optional[dict] = None

    def to_dict(self) -> dict:
        d: dict = {}
        if self.encoding is not None:
            d["encoding"] = self.encoding
        if self.checksum is not None:
            d["checksum"] = dict(self.checksum)
        return d


@dataclass
class CapsuleV2:
    """A v2 number-station QR capsule.

    The top-level object mirrors ``numberstations-capsule.v2.schema.json``.
    """

    v: str
    content: CapsuleContent
    profile: Optional[CapsuleProfile] = None
    meta: Optional[CapsuleMeta] = None
    render: Optional[CapsuleRender] = None
    integrity: Optional[CapsuleIntegrity] = None

    def to_dict(self) -> dict:
        """Serialise back to a plain ``dict`` suitable for JSON encoding."""
        d: dict = {
            "v": self.v,
            "content": self.content.to_dict(),
        }
        if self.profile is not None:
            prof = self.profile.to_dict()
            if prof:
                d["profile"] = prof
        if self.meta is not None:
            m = self.meta.to_dict()
            if m:
                d["meta"] = m
        if self.render is not None:
            r = self.render.to_dict()
            if r:
                d["render"] = r
        if self.integrity is not None:
            i = self.integrity.to_dict()
            if i:
                d["integrity"] = i
        return d


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_profile(obj: dict) -> CapsuleProfile:
    return CapsuleProfile(
        family=obj.get("family"),
        id=obj.get("id"),
        variant=obj.get("variant"),
        nickname=obj.get("nickname"),
        voice=obj.get("voice"),
        mode=obj.get("mode"),
        location_hint=obj.get("location_hint"),
    )


def _parse_content(obj: dict) -> CapsuleContent:
    repeat_raw = obj.get("repeat")
    repeat = (
        RepeatPolicy(
            mode=repeat_raw.get("mode", "none"),
            times=repeat_raw.get("times"),
        )
        if repeat_raw is not None
        else None
    )
    tokens_raw = obj.get("tokens")
    tokens = (
        ContentTokens(
            attention=tokens_raw.get("attention"),
            outro=tokens_raw.get("outro"),
        )
        if tokens_raw is not None
        else None
    )
    return CapsuleContent(
        group_size=obj["group_size"],
        groups=list(obj["groups"]),
        repeat=repeat,
        tokens=tokens,
        preamble=list(obj["preamble"]) if "preamble" in obj else None,
        count_announce=obj.get("count_announce"),
    )


def _parse_meta(obj: dict) -> CapsuleMeta:
    return CapsuleMeta(
        datetime_utc=obj.get("datetime_utc"),
        frequency_khz=obj.get("frequency_khz"),
        session_id=obj.get("session_id"),
        group_count=obj.get("group_count"),
    )


def _parse_render_audio(obj: dict) -> RenderAudio:
    tts_raw = obj.get("tts")
    tts = (
        RenderAudioTTS(
            language_tag=tts_raw.get("language_tag", "en-US"),
            voice_id=tts_raw.get("voice_id"),
            rate=tts_raw.get("rate"),
            pitch=tts_raw.get("pitch"),
            engine=tts_raw.get("engine"),
        )
        if tts_raw is not None
        else None
    )
    samples_raw = obj.get("samples")
    samples = (
        RenderAudioSamples(
            voice_pack_id=samples_raw["voice_pack_id"],
            digit_set_id=samples_raw.get("digit_set_id"),
            asset_base_uri=samples_raw.get("asset_base_uri"),
            silence_ms_between_digits=samples_raw.get("silence_ms_between_digits"),
            silence_ms_between_groups=samples_raw.get("silence_ms_between_groups"),
        )
        if samples_raw is not None
        else None
    )
    return RenderAudio(
        preferred=obj.get("preferred", "tts"),
        tts=tts,
        samples=samples,
    )


def _parse_render(obj: dict) -> CapsuleRender:
    text_raw = obj.get("text")
    text = (
        RenderText(
            separator=text_raw.get("separator", " "),
            line_break_every=text_raw.get("line_break_every"),
        )
        if text_raw is not None
        else None
    )
    audio_raw = obj.get("audio")
    audio = _parse_render_audio(audio_raw) if audio_raw is not None else None
    return CapsuleRender(text=text, audio=audio)


def _parse_integrity(obj: dict) -> CapsuleIntegrity:
    return CapsuleIntegrity(
        encoding=obj.get("encoding"),
        checksum=dict(obj["checksum"]) if "checksum" in obj else None,
    )


def _parse_v2(obj: dict) -> CapsuleV2:
    """Parse a raw dict that already carries ``v == "2"``."""
    profile = _parse_profile(obj["profile"]) if "profile" in obj else None
    content = _parse_content(obj["content"])
    meta = _parse_meta(obj["meta"]) if "meta" in obj else None
    render = _parse_render(obj["render"]) if "render" in obj else None
    integrity = _parse_integrity(obj["integrity"]) if "integrity" in obj else None
    return CapsuleV2(
        v="2",
        profile=profile,
        content=content,
        meta=meta,
        render=render,
        integrity=integrity,
    )


# ---------------------------------------------------------------------------
# Migration: v1 E11 → v2 capsule
# ---------------------------------------------------------------------------

def upgrade_e11_v1_to_capsule_v2(obj: dict) -> CapsuleV2:
    """Upgrade a legacy v1 E11 QR payload to a :class:`CapsuleV2` object.

    The mapping rules are deterministic:

    * ``profile`` is derived from ``station`` + ``transmission.variant``.
    * ``meta`` is derived from ``transmission`` fields
      (``datetime_utc``, ``frequency_khz``, ``session_id``, ``group_count``).
    * ``content`` is derived from ``message.groups`` and
      ``transmission.format``.  ``group_size`` defaults to 5 (the E11 norm).
    * ``content.repeat`` uses ``message.repetitions`` (default 2) with mode
      ``"repeat-block"``.
    * ``content.tokens`` uses ``message.attention_token`` (default
      ``"ATTENTION"``) and ``message.outro_token`` (default ``"OUT"``).
    * ``content.preamble`` is copied from ``message.preamble`` when present.
    * ``integrity`` is copied verbatim when present.

    Parameters
    ----------
    obj:
        A plain dict representing a v1 E11 QR payload.

    Returns
    -------
    CapsuleV2
    """
    station = obj.get("station", {})
    transmission = obj.get("transmission", {})
    message = obj.get("message", {})
    fmt = transmission.get("format", {})

    # ------------------------------------------------------------------
    # profile
    # ------------------------------------------------------------------
    profile = CapsuleProfile(
        family=station.get("family", "ENIGMA"),
        id=station.get("id", "E11"),
        variant=transmission.get("variant"),
        nickname=station.get("nickname"),
        voice=station.get("voice"),
        mode=station.get("mode"),
        location_hint=station.get("location_hint"),
    )

    # ------------------------------------------------------------------
    # meta
    # ------------------------------------------------------------------
    meta = CapsuleMeta(
        datetime_utc=transmission.get("datetime_utc"),
        frequency_khz=transmission.get("frequency_khz"),
        session_id=transmission.get("session_id"),
        group_count=transmission.get("group_count"),
    )

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------
    group_size: int = fmt.get("group_size", 5)

    raw_groups: list[str] = message.get("groups", [])
    # Normalise: ensure each group is a zero-padded string of the right length.
    groups = [g.zfill(group_size) if isinstance(g, str) else f"{g:0{group_size}d}" for g in raw_groups]

    repetitions: int = message.get("repetitions", 2)
    repeat = RepeatPolicy(
        mode="repeat-block",
        times=repetitions,
    )

    tokens = ContentTokens(
        attention=message.get("attention_token", "ATTENTION"),
        outro=message.get("outro_token", "OUT"),
    )

    preamble: list[str] | None = (
        list(message["preamble"]) if "preamble" in message else None
    )

    content = CapsuleContent(
        group_size=group_size,
        groups=groups,
        repeat=repeat,
        tokens=tokens,
        preamble=preamble,
        count_announce=None,
    )

    # ------------------------------------------------------------------
    # integrity (copy verbatim)
    # ------------------------------------------------------------------
    integrity_raw = obj.get("integrity")
    integrity = _parse_integrity(integrity_raw) if integrity_raw is not None else None

    return CapsuleV2(
        v="2",
        profile=profile,
        content=content,
        meta=meta,
        integrity=integrity,
    )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_capsule(obj: dict) -> CapsuleV2:
    """Load a capsule from a raw dict, handling both v1 and v2 formats.

    * If ``obj["v"] == "2"`` the object is parsed directly as a v2 capsule.
    * Otherwise it is treated as a legacy v1 E11 payload and upgraded via
      :func:`upgrade_e11_v1_to_capsule_v2`.

    Parameters
    ----------
    obj:
        A plain dict (e.g. decoded from QR JSON).

    Returns
    -------
    CapsuleV2
    """
    version = obj.get("v")
    if version == "2":
        return _parse_v2(obj)
    # Treat anything else as a legacy v1 E11 payload.
    return upgrade_e11_v1_to_capsule_v2(obj)


# ---------------------------------------------------------------------------
# Capsule → E11Script
# ---------------------------------------------------------------------------

def capsule_to_e11_script(capsule: CapsuleV2):  # -> E11Script
    """Convert a v2 capsule to an :class:`~.e11_script.E11Script`.

    Conditions for E11-style output (at least one must hold):
    * ``capsule.profile.id == "E11"``
    * ``capsule.content.group_size == 5`` **and** ``capsule.meta.session_id``
      is present.

    The ``station_id`` is taken from ``meta.session_id`` (parsed as ``int``).
    The ``group_count`` is taken from ``meta.group_count`` when provided,
    otherwise derived from ``len(content.groups)``.

    Parameters
    ----------
    capsule:
        A :class:`CapsuleV2` instance.

    Returns
    -------
    E11Script

    Raises
    ------
    ValueError
        When the capsule cannot be represented as an E11 script (wrong
        group size, missing session_id, etc.).
    """
    from .e11_script import E11Script  # local import to avoid circular deps

    profile_id = capsule.profile.id if capsule.profile else None
    session_id = capsule.meta.session_id if capsule.meta else None
    group_size = capsule.content.group_size

    is_e11 = profile_id == "E11" or (group_size == 5 and session_id is not None)

    if not is_e11:
        raise ValueError(
            "Cannot convert capsule to E11Script: profile.id must be 'E11' or "
            "(content.group_size == 5 and meta.session_id must be set)."
        )

    if group_size != 5:
        raise ValueError(
            f"E11 scripts require group_size == 5, got {group_size}."
        )

    if session_id is None:
        raise ValueError(
            "E11 scripts require meta.session_id to be set."
        )

    station_id = int(session_id)

    # Convert string groups to ints, preserving leading-zero semantics.
    groups_int: list[int] = [int(g) for g in capsule.content.groups]

    group_count: int = (
        capsule.meta.group_count
        if (capsule.meta and capsule.meta.group_count is not None)
        else len(groups_int)
    )

    return E11Script(
        station_id=station_id,
        group_count=group_count,
        groups=groups_int,
    )
