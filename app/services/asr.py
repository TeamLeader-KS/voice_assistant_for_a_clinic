import os
import sys
import numpy as np
import sounddevice as sd
import gigastt_uniffi as g

# --- Настройки ---
MODEL_DIR = os.path.expanduser("~/.gigastt/models")
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.4  # 400 мс
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

# --- Инициализация движка и потока ---
print("Загрузка модели...")
engine = g.Engine(MODEL_DIR)
stream = g.Stream(engine)
print("Модель загружена. Говорите... (Ctrl+C для выхода)\n")


def audio_callback(indata, frames, time, status):
    """Callback для захвата аудио с микрофона."""
    if status:
        print(f"[audio] {status}", file=sys.stderr)

    # float32 → PCM16 mono (little-endian)
    pcm16 = (indata[:, 0] * 32767).astype(np.int16).tobytes()

    # Обработка чанка
    segments = stream.process_chunk(pcm16, SAMPLE_RATE)

    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if seg.is_final:
            # Финальный результат — выводим на новой строке
            print(f"\r{text}")
        else:
            # Промежуточный результат — перезаписываем строку
            print(f"\r... {text}", end="", flush=True)


# --- Запуск захвата ---
try:
    with sd.InputStream(
        callback=audio_callback,
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=CHUNK_SAMPLES,
        dtype="float32",
    ):
        # Бесконечное ожидание до Ctrl+C
        while True:
            sd.sleep(1000)
except KeyboardInterrupt:
    print("\n\nОстановка...")

# --- Финальная обработка остатка буфера ---
final_segments = stream.flush()
for seg in final_segments:
    text = seg.text.strip()
    if text and seg.is_final:
        print(text)