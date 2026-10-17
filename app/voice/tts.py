# # # import logging
# # # from pathlib import Path
# # # from silero_tts.silero_tts import SileroTTS
# # #
# # # logger = logging.getLogger(__name__)
# # #
# # # class SileroTTSWrapper:
# # #     """Обёртка для Silero TTS с настройками под телефонию (8 кГц)."""
# # #
# # #     def __init__(
# # #         self,
# # #         language: str = "ru",
# # #         model_id: str = "v4_ru",
# # #         speaker: str = "xenia",
# # #         sample_rate: int = 8000,  # Для телефонии
# # #         device: str = "cpu",
# # #     ):
# # #         self.language = language
# # #         self.sample_rate = sample_rate
# # #
# # #         # Инициализация модели (скачается автоматически при первом запуске)
# # #         logger.info(f"Инициализация Silero TTS: {model_id}, speaker={speaker}")
# # #         self.tts = SileroTTS(
# # #             model_id=model_id,
# # #             language=language,
# # #             speaker=speaker,
# # #             sample_rate=sample_rate,
# # #             device=device,
# # #         )
# # #         logger.info("Silero TTS готов к работе")
# # #
# # #     def synthesize(self, text: str, output_path: str | Path) -> Path:
# # #         """
# # #         Синтезирует речь из текста и сохраняет в WAV-файл.
# # #
# # #         Args:
# # #             text: Текст для озвучивания.
# # #             output_path: Путь для сохранения аудио.
# # #
# # #         Returns:
# # #             Path к сохранённому файлу.
# # #         """
# # #         output_path = Path(output_path)
# # #         output_path.parent.mkdir(parents=True, exist_ok=True)
# # #
# # #         try:
# # #             # Синтез и сохранение
# # #             self.tts.tts(text, str(output_path))
# # #             logger.info(f"Аудио сохранено: {output_path}")
# # #
# # #             if not output_path.exists() or output_path.stat().st_size == 0:
# # #                 raise RuntimeError(f"Файл не создан или пуст: {output_path}")
# # #
# # #             return output_path
# # #
# # #         except Exception as e:
# # #             logger.error(f"Ошибка синтеза: {e}")
# # #             raise
# #
# # import logging
# # from pathlib import Path
# # from silero_tts.silero_tts import SileroTTS
# #
# # logger = logging.getLogger(__name__)
# #
# #
# # class SileroTTSWrapper:
# #     """Обёртка для Silero TTS с настройками под телефонию (8 кГц)."""
# #
# #     def __init__(
# #         self,
# #         language: str = "ru",
# #         model_id: str = "v4_ru",
# #         speaker: str = "xenia",
# #         sample_rate: int = 8000,
# #         device: str = "cpu",
# #     ):
# #         self.language = language
# #         self.sample_rate = sample_rate
# #         logger.info(f"Инициализация Silero TTS: {model_id}, speaker={speaker}")
# #         self.tts = SileroTTS(
# #             model_id=model_id,
# #             language=language,
# #             speaker=speaker,
# #             sample_rate=sample_rate,
# #             device=device,
# #         )
# #         logger.info("Silero TTS готов к работе")
# #
# #     def synthesize(self, text: str, output_path: str | Path) -> Path:
# #         output_path = Path(output_path)
# #         output_path.parent.mkdir(parents=True, exist_ok=True)
# #         try:
# #             self.tts.tts(text, str(output_path))
# #             logger.info(f"Аудио сохранено: {output_path}")
# #             if not output_path.exists() or output_path.stat().st_size == 0:
# #                 raise RuntimeError(f"Файл не создан или пуст: {output_path}")
# #             return output_path
# #         except Exception as e:
# #             logger.error(f"Ошибка синтеза: {e}")
# #             raise
#
# """Обёртка над официальным Silero TTS.
#
# Отдаёт WAV в формате, который Asterisk играет без конвертации:
# PCM 16-bit, mono, 8000 Hz.
# """
#
# from __future__ import annotations
#
# import logging
# import re
# from pathlib import Path
#
# import numpy as np
# import soundfile as sf
# import torch
#
# logger = logging.getLogger(__name__)
#
# _SAMPLE_RATE = 8000
# _SPEAKER = "xenia"
# _LANGUAGE = "ru"
# _MODEL_ID = "v4_ru"
#
#
# class SileroTTSWrapper:
#     """Ленивая инициализация Silero TTS, кэш модели в памяти процесса."""
#
#     def __init__(
#         self,
#         language: str = _LANGUAGE,
#         speaker: str = _SPEAKER,
#         sample_rate: int = _SAMPLE_RATE,
#         model_id: str = _MODEL_ID,
#     ) -> None:
#         self.language = language
#         self.speaker = speaker
#         self.sample_rate = sample_rate
#         self.model_id = model_id
#         self._model = None
#
#     def _lazy_init(self) -> None:
#         if self._model is not None:
#             return
#         from silero import silero_tts
#
#         logger.info("Инициализация Silero TTS: %s, speaker=%s", self.model_id, self.speaker)
#         model, _ = silero_tts(language=self.language, speaker=self.model_id)
#         model.to(torch.device("cpu"))
#         self._model = model
#         logger.info("Silero TTS готов")
#
#     def synthesize(self, text: str, output_path: str | Path) -> Path:
#         """Синтезировать текст в WAV 8 кГц mono PCM16."""
#         self._lazy_init()
#         output_path = Path(output_path)
#         output_path.parent.mkdir(parents=True, exist_ok=True)
#
#         clean_text = _speakable(text)
#
#         audio = self._model.apply_tts(
#             text=clean_text,
#             speaker=self.speaker,
#             sample_rate=self.sample_rate,
#         )
#
#         # audio: torch.Tensor [1, N], значения в [-1, 1]
#         if isinstance(audio, torch.Tensor):
#             audio = audio.squeeze().cpu().numpy()
#         audio = np.asarray(audio, dtype=np.float32)
#
#         # В WAV пишем PCM16
#         sf.write(
#             str(output_path),
#             audio,
#             self.sample_rate,
#             subtype="PCM_16",
#         )
#         logger.info("Аудио сохранено: %s", output_path)
#         return output_path
#
#
# # ─── Нормализация текста для TTS ───
#
# _MONTHS = [
#     "", "января", "февраля", "марта", "апреля", "мая", "июня",
#     "июля", "августа", "сентября", "октября", "ноября", "декабря",
# ]
#
#
# def _speakable(text: str) -> str:
#     """Убрать из текста то, что Silero читает плохо: нумерацию, даты, время."""
#     # "1. " в начале строки → "Вариант один. "
#     text = re.sub(r"(?m)^(\d+)\.\s*", r"Вариант \1. ", text)
#     # "20.10.2026" → "20 октября"
#     def _date(m: re.Match) -> str:
#         d, mo = int(m.group(1)), int(m.group(2))
#         if 1 <= mo <= 12 and 1 <= d <= 31:
#             return f"{d} {_MONTHS[mo]}"
#         return m.group(0)
#     text = re.sub(r"\b(\d{1,2})\.(\d{2})\.\d{4}\b", _date, text)
#     # Переносы строк → пробел
#     text = text.replace("\n", " ")
#     # Множественные пробелы
#     text = re.sub(r"\s+", " ", text).strip()
#     return text

"""Обёртка над официальным Silero TTS.

Отдаёт WAV в формате, который Asterisk играет без конвертации:
PCM 16-bit, mono, 8000 Hz.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 8000
_SPEAKER = "xenia"
_LANGUAGE = "ru"
_MODEL_ID = "v4_ru"


class SileroTTSWrapper:
    """Ленивая инициализация Silero TTS, кэш модели в памяти процесса."""

    def synthesize_pcm(self, text: str) -> bytes:
        """Текст → сырой PCM16 mono 8 кГц (то, что ждёт AudioSocket)."""
        self._lazy_init()
        audio = self._model.apply_tts(
            text=_speakable(text), speaker=self.speaker, sample_rate=self.sample_rate
        )
        a = audio.squeeze().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio)
        return (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()

    def __init__(
        self,
        language: str = _LANGUAGE,
        speaker: str = _SPEAKER,
        sample_rate: int = _SAMPLE_RATE,
        model_id: str = _MODEL_ID,
    ) -> None:
        self.language = language
        self.speaker = speaker
        self.sample_rate = sample_rate
        self.model_id = model_id
        self._model = None

    def _lazy_init(self) -> None:
        if self._model is not None:
            return
        from silero import silero_tts

        logger.info("Инициализация Silero TTS: %s, speaker=%s", self.model_id, self.speaker)
        model, _ = silero_tts(language=self.language, speaker=self.model_id)
        model.to(torch.device("cpu"))
        self._model = model
        logger.info("Silero TTS готов")

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """Синтезировать текст в WAV 8 кГц mono PCM16."""
        self._lazy_init()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        clean_text = _speakable(text)

        audio = self._model.apply_tts(
            text=clean_text,
            speaker=self.speaker,
            sample_rate=self.sample_rate,
        )

        # audio: torch.Tensor [1, N], значения в [-1, 1]
        if isinstance(audio, torch.Tensor):
            audio = audio.squeeze().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)

        # В WAV пишем PCM16
        sf.write(
            str(output_path),
            audio,
            self.sample_rate,
            subtype="PCM_16",
        )
        logger.info("Аудио сохранено: %s", output_path)
        return output_path


# ─── Нормализация текста для TTS ───

_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _speakable(text: str) -> str:
    """Убрать из текста то, что Silero читает плохо: нумерацию, даты, время."""
    # "1. " в начале строки → "Вариант один. "
    text = re.sub(r"(?m)^(\d+)\.\s*", r"Вариант \1. ", text)
    # "20.10.2026" → "20 октября"
    def _date(m: re.Match) -> str:
        d, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{d} {_MONTHS[mo]}"
        return m.group(0)
    text = re.sub(r"\b(\d{1,2})\.(\d{2})\.\d{4}\b", _date, text)
    # Переносы строк → пробел
    text = text.replace("\n", " ")
    # Множественные пробелы
    text = re.sub(r"\s+", " ", text).strip()
    return text