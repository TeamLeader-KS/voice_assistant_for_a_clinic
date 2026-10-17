"""AudioSocket-мост: Asterisk ⇄ VAD ⇄ ASR ⇄ DialogEngine ⇄ TTS.

Протокол AudioSocket (кадр = 1 байт тип + 2 байта длина BE + данные):
    0x00 hangup · 0x01 UUID · 0x03 DTMF · 0x10 аудио (slin 8 кГц, 16 бит) · 0xFF ошибка

Перевод на оператора: если движок вернул escalated=True (красный флаг, жалоба и т.д.)
или что-то сломалось, call_id кладётся в TRANSFERS. Диалплан после выхода из
AudioSocket спрашивает GET /voice/transfer/{uuid} и при «1» звонит регистратору.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
import uuid as uuidlib
from collections import deque

import webrtcvad

from app.voice.stt import transcribe_pcm8k, warmup as stt_warmup
from app.voice.tts import get_tts

logger = logging.getLogger(__name__)

KIND_HANGUP, KIND_UUID, KIND_DTMF, KIND_AUDIO, KIND_ERROR = 0x00, 0x01, 0x03, 0x10, 0xFF

FRAME = 320                     # 20 мс при 8 кГц, 16 бит
FRAME_SEC = 0.02
VAD_MODE = int(os.getenv("VAD_MODE", "2"))            # 0..3, выше = строже к шуму
END_SILENCE_FRAMES = int(os.getenv("END_SILENCE_FRAMES", "35"))  # 0,7 с тишины = конец реплики
MIN_VOICED_FRAMES = 12          # меньше 240 мс речи — считаем шумом
MAX_UTTERANCE_FRAMES = 600      # не дольше 12 с
NO_SPEECH_FRAMES = 500          # 10 с молчания = «пусто»
MAX_CALL_SEC = 600              # страховка от зависшего звонка

TRANSFERS: set[str] = set()     # звонки, которые нужно перевести на оператора


def _is_transfer(resp) -> bool:
    return bool(getattr(resp, "escalated", False) or getattr(resp, "transfer", False))


class AudioServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9092, engine=None):
        self.host, self.port = host, port
        if engine is None:
            from app.api.demo import _engine  # общий движок по умолчанию

            engine = _engine
        self.engine = engine  # можно подставить свой (тесты, другой сценарий)

    def _forget(self, call_id: str) -> None:
        """Забыть состояние звонка в движке."""
        end_call = getattr(self.engine, "end_call", None)
        if end_call:
            end_call(call_id)
        else:
            self.engine._states.pop(call_id, None)  # noqa: SLF001

    # ── протокол ──

    @staticmethod
    async def _read_msg(reader):
        header = await reader.readexactly(3)
        length = struct.unpack(">H", header[1:3])[0]
        payload = await reader.readexactly(length) if length else b""
        return header[0], payload

    async def _pump(self, reader, q: asyncio.Queue, closed: asyncio.Event):
        """Всё время читает сокет (даже пока мы говорим) и режет звук на кадры по 20 мс."""
        buf = bytearray()
        try:
            while True:
                kind, payload = await self._read_msg(reader)
                if kind == KIND_AUDIO:
                    buf += payload
                    while len(buf) >= FRAME:
                        q.put_nowait(bytes(buf[:FRAME]))
                        del buf[:FRAME]
                elif kind in (KIND_HANGUP, KIND_ERROR):
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            closed.set()

    async def _say(self, writer, text: str, closed: asyncio.Event):
        """Синтезировать и отдать в Asterisk в реальном времени (по часам, без дрейфа)."""
        loop = asyncio.get_running_loop()
        pcm = await asyncio.to_thread(get_tts().synthesize_pcm, text)
        t0 = loop.time()
        for n, i in enumerate(range(0, len(pcm), FRAME)):
            if closed.is_set():
                return
            chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")
            writer.write(bytes([KIND_AUDIO]) + struct.pack(">H", len(chunk)) + chunk)
            await writer.drain()
            delay = t0 + (n + 1) * FRAME_SEC - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

    async def _listen(self, q: asyncio.Queue, closed: asyncio.Event) -> bytes | None:
        """Ждёт реплику пациента (VAD). None — звонок завершён, b'' — долгое молчание."""
        while not q.empty():            # выбросить то, что накопилось, пока говорили мы
            q.get_nowait()
        vad = webrtcvad.Vad(VAD_MODE)
        ring: deque = deque(maxlen=10)  # предзапись 200 мс, чтобы не резать начало слова
        speech, started, silence, voiced, waited = bytearray(), False, 0, 0, 0
        while True:
            try:
                frame = await asyncio.wait_for(q.get(), 0.1)
            except asyncio.TimeoutError:
                if closed.is_set():
                    return None
                continue
            is_sp = vad.is_speech(frame, 8000)
            if not started:
                ring.append((frame, is_sp))
                waited += 1
                if sum(s for _, s in ring) >= 6:
                    started, silence = True, 0
                    speech = bytearray(b"".join(f for f, _ in ring))
                    voiced = sum(s for _, s in ring)
                elif waited > NO_SPEECH_FRAMES:
                    return b""
                continue
            speech += frame
            voiced += is_sp
            silence = 0 if is_sp else silence + 1
            too_long = len(speech) > MAX_UTTERANCE_FRAMES * FRAME
            if silence >= END_SILENCE_FRAMES or too_long:
                if voiced >= MIN_VOICED_FRAMES:
                    return bytes(speech)
                # короткий щелчок или шум — слушаем дальше
                ring.clear()
                speech, started, silence, voiced = bytearray(), False, 0, 0

    # ── сценарий звонка ──

    async def _session(self, call_id: str, q, closed, writer):
        r = await self.engine.handle(call_id, "алло")        # приветствие движка
        await self._say(writer, r.reply, closed)

        empty = 0
        while not closed.is_set():
            pcm = await self._listen(q, closed)
            if pcm is None:
                return
            if pcm:
                logger.info("[%s] речь %.1f с, распознаю...", call_id, len(pcm) / 16000)
            text = await asyncio.to_thread(transcribe_pcm8k, pcm) if pcm else ""
            logger.info("[%s] пациент: %r", call_id, text)

            if not text:
                empty += 1
                if empty >= 3:
                    await self._say(writer, "Я вас не слышу. Соединяю с регистратором.", closed)
                    TRANSFERS.add(call_id)               # человек всегда доступен
                    return
                await self._say(writer, "Извините, не расслышала. Повторите, пожалуйста.", closed)
                continue
            empty = 0

            r = await self.engine.handle(call_id, text)
            logger.info("[%s] ассистент: %r (step=%s)", call_id, r.reply, r.step)
            await self._say(writer, r.reply, closed)

            if _is_transfer(r):
                TRANSFERS.add(call_id)
                return
            if getattr(r, "booked", False):
                return

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        closed, q, pump, call_id = asyncio.Event(), asyncio.Queue(), None, "unknown"
        try:
            kind, payload = await asyncio.wait_for(self._read_msg(reader), 5)
            if kind == KIND_UUID and len(payload) == 16:
                call_id = str(uuidlib.UUID(bytes=payload))
            logger.info("Звонок %s от %s", call_id, peer)
            pump = asyncio.create_task(self._pump(reader, q, closed))
            await asyncio.wait_for(self._session(call_id, q, closed, writer), MAX_CALL_SEC)
            await asyncio.sleep(0.8)                     # дать доиграть последнюю фразу
        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("Звонок %s: соединение закрыто", call_id)
        except Exception:
            logger.exception("Звонок %s: ошибка. Переводим на регистратора", call_id)
            TRANSFERS.add(call_id)
        finally:
            if pump:
                pump.cancel()
            self._forget(call_id)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    def _warmup(self):
        """Прогреть модели, иначе первый звонок ждёт десятки секунд."""
        try:
            stt_warmup()
            get_tts().synthesize_pcm("Проверка")
            logger.info("Модели ASR и TTS прогреты")
        except Exception:
            logger.exception("Прогрев моделей не удался")

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info("AudioSocket сервер запущен на %s:%s", self.host, self.port)
        self._warm_task = asyncio.create_task(asyncio.to_thread(self._warmup))
        async with server:
            await server.serve_forever()
                