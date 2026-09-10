"""Detect OS UI language and map to edge-tts voices."""

from __future__ import annotations

import locale
import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger("cursor_tts_mcp.locale_voice")

# Primary edge-tts Neural voices by language tag / prefix.
_DEFAULT_VOICE_BY_LANG: dict[str, str] = {
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "zh-hans": "zh-CN-XiaoxiaoNeural",
    "zh-sg": "zh-CN-XiaoxiaoNeural",
    "zh-tw": "zh-TW-HsiaoChenNeural",
    "zh-hk": "zh-HK-HiuMaanNeural",
    "zh-mo": "zh-HK-HiuMaanNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "en-us": "en-US-JennyNeural",
    "en-gb": "en-GB-SoniaNeural",
    "en-au": "en-AU-NatashaNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "pt-br": "pt-BR-FranciscaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "it": "it-IT-ElsaNeural",
}

_SPEAK_HINT: dict[str, str] = {
    "zh": "简体中文短句",
    "en": "short English phrases",
    "ja": "短い日本語",
    "ko": "짧은 한국어",
    "fr": "phrases courtes en français",
    "de": "kurze deutsche Sätze",
    "es": "frases cortas en español",
    "pt": "frases curtas em português",
    "ru": "короткие фразы на русском",
    "it": "frasi brevi in italiano",
}


@dataclass(frozen=True)
class LocaleVoiceResolution:
    locale: str
    language: str
    voice: str
    speak_hint: str
    source: str


def normalize_locale_tag(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().replace("_", "-")
    if not s:
        return None
    # LANG=zh_CN.UTF-8 → zh-CN
    s = s.split(".")[0].split("@")[0]
    if not re.match(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$", s):
        return None
    parts = s.split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def detect_system_locale() -> tuple[str, str]:
    """Return (normalized locale tag, detection source)."""
    force = os.environ.get("CURSOR_TTS_FORCE_LOCALE")
    if force:
        tag = normalize_locale_tag(force)
        if tag:
            return tag, "env:CURSOR_TTS_FORCE_LOCALE"

    if os.name == "nt":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            win_name = locale.windows_locale.get(lang_id)
            tag = normalize_locale_tag(win_name)
            if tag:
                return tag, "windows:GetUserDefaultUILanguage"
        except Exception:
            logger.debug("windows UI language detect failed", exc_info=True)

    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        tag = normalize_locale_tag(os.environ.get(key))
        if tag and tag.lower() not in {"c", "posix"}:
            return tag, f"env:{key}"

    for getter_name, getter in (
        ("getlocale", locale.getlocale),
        ("getdefaultlocale", getattr(locale, "getdefaultlocale", lambda: (None, None))),
    ):
        try:
            loc = getter()[0]
            tag = normalize_locale_tag(loc)
            if tag:
                return tag, f"locale:{getter_name}"
        except Exception:
            logger.debug("%s failed", getter_name, exc_info=True)

    return "en-US", "fallback:en-US"


def language_from_locale(tag: str) -> str:
    return tag.split("-", 1)[0].lower()


def resolve_edge_voice(
    locale_tag: str,
    *,
    voice_map: dict[str, str] | None = None,
) -> str:
    """Pick edge-tts voice for a locale tag using longest-prefix match."""
    merged = dict(_DEFAULT_VOICE_BY_LANG)
    if voice_map:
        for k, v in voice_map.items():
            nk = normalize_locale_tag(k) or str(k).strip().lower()
            if nk:
                merged[nk.lower()] = str(v)

    key = locale_tag.lower()
    if key in merged:
        return merged[key]
    # try progressively shorter prefixes: zh-cn → zh
    parts = key.split("-")
    for i in range(len(parts) - 1, 0, -1):
        prefix = "-".join(parts[:i])
        if prefix in merged:
            return merged[prefix]
    lang = parts[0]
    if lang in merged:
        return merged[lang]
    return merged.get("en", "en-US-JennyNeural")


def speak_hint_for_language(language: str) -> str:
    return _SPEAK_HINT.get(language, _SPEAK_HINT["en"])


def resolve_locale_voice(
    *,
    voice_map: dict[str, str] | None = None,
    forced_locale: str | None = None,
) -> LocaleVoiceResolution:
    if forced_locale:
        tag = normalize_locale_tag(forced_locale) or "en-US"
        source = "forced"
    else:
        tag, source = detect_system_locale()
    language = language_from_locale(tag)
    voice = resolve_edge_voice(tag, voice_map=voice_map)
    return LocaleVoiceResolution(
        locale=tag,
        language=language,
        voice=voice,
        speak_hint=speak_hint_for_language(language),
        source=source,
    )


def is_auto_voice(voice: str | None) -> bool:
    if voice is None:
        return True
    v = str(voice).strip().lower()
    return v in {"", "auto", "system", "locale"}
