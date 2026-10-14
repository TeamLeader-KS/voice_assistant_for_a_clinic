import logging
from pathlib import Path
from silero_tts.silero_tts import SileroTTS

logger = logging.getLogger(__name__)

class SileroTTSWrapper:
    """Обёртка для Silero TTS с настройками под телефонию (8 кГц)."""

    def __init__(
        self,
        language: str = "ru",
        model_id: str = "v4_ru",
        speaker: str = "xenia",
        sample_rate: int = 8000,  # Для телефонии
        device: str = "cpu",
    ):
        self.language = language
        self.sample_rate = sample_rate

        # Инициализация модели (скачается автоматически при первом запуске)
        logger.info(f"Инициализация Silero TTS: {model_id}, speaker={speaker}")
        self.tts = SileroTTS(
            model_id=model_id,
            language=language,
            speaker=speaker,
            sample_rate=sample_rate,
            device=device,
        )
        logger.info("Silero TTS готов к работе")

    def synthesize(self, text: str, output_path: str | Path) -> Path:
        """
        Синтезирует речь из текста и сохраняет в WAV-файл.

        Args:
            text: Текст для озвучивания.
            output_path: Путь для сохранения аудио.

        Returns:
            Path к сохранённому файлу.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Синтез и сохранение
            self.tts.tts(text, str(output_path))
            logger.info(f"Аудио сохранено: {output_path}")

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError(f"Файл не создан или пуст: {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Ошибка синтеза: {e}")
            raise