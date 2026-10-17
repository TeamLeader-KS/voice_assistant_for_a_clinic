# """AudioSocket-мост: Asterisk ⇄ VAD ⇄ ASR ⇄ DialogEngine ⇄ TTS."""
#
# from __future__ import annotations
#
# import asyncio
# import logging
# import os
# import struct
# import uuid as uuidlib
# from collections import deque
#
# import webrtcvad
#
# from app.voice.stt import transcribe_pcm8k, warmup as stt_warmup
# from app.voice.tts import get_tts
#
# logger = logging.getLogger(__name__)
#
# # ── Константы протокола AudioSocket (строго по спецификации Asterisk) ──
# KIND_HANGUP = 0x00
# KIND_UUID = 0x01
# KIND_DTMF = 0x03
# KIND_AUDIO = 0x10
# KIND_ERROR = 0xFF
#
# FRAME = 320  # 20 мс при 8 кГц, 16 бит
# FRAME_SEC = 0.02
# VAD_MODE = int(os.getenv("VAD_MODE", "2"))
# END_SILENCE_FRAMES = int(os.getenv("END_SILENCE_FRAMES", "35"))
# MIN_VOICED_FRAMES = 12
# MAX_UTTERANCE_FRAMES = 600
# NO_SPEECH_FRAMES = 500
# MAX_CALL_SEC = 600
#
# TRANSFERS: set[str] = set()
#
#
# def _is_transfer(resp) -> bool:
#     return bool(getattr(resp, "escalated", False) or getattr(resp, "transfer", False))
#
#
# class AudioServer:
#     def __init__(self, host: str = "0.0.0.0", port: int = 9092, engine=None):
#         self.host, self.port = host, port
#         if engine is None:
#             from app.api.demo import _engine
#             engine = _engine
#         self.engine = engine
#
#     def _forget(self, call_id: str) -> None:
#         end_call = getattr(self.engine, "end_call", None)
#         if end_call:
#             end_call(call_id)
#         else:
#             self.engine._states.pop(call_id, None)  # noqa: SLF001
#
#     # ── ФУНКЦИЯ ЧТЕНИЯ ПАКЕТА (её не хватало!) ──
#     @staticmethod
#     async def _read_msg(reader):
#         """Читает ровно 3 байта заголовка и payload согласно AudioSocket."""
#         header = await reader.readexactly(3)
#         kind = header[0]
#         length = struct.unpack(">H", header[1:3])[0]
#         payload = await reader.readexactly(length) if length else b""
#
#         # Лог для отладки: покажет, что реально приходит
#         logger.debug(f"RX kind=0x{kind:02x} len={length} head={payload[:8].hex()}")
#         return kind, payload
#
#     async def _pump(self, reader, q: asyncio.Queue, closed: asyncio.Event):
#         buf = bytearray()
#         try:
#             while True:
#                 kind, payload = await self._read_msg(reader)
#                 if kind == KIND_AUDIO:
#                     buf += payload
#                     while len(buf) >= FRAME:
#                         q.put_nowait(bytes(buf[:FRAME]))
#                         del buf[:FRAME]
#                 elif kind == KIND_UUID:
#                     # UUID приходит первым, мы его уже прочитали в handle_client.
#                     # Если пришёл ещё раз — просто игнорируем.
#                     logger.info(f"Второй UUID: {payload.hex()}")
#                 elif kind in (KIND_HANGUP, KIND_ERROR):
#                     logger.info("Пациент положил трубку (hangup/error)")
#                     break
#         except (asyncio.IncompleteReadError, ConnectionError):
#             logger.info("Соединение с Asterisk закрыто")
#         finally:
#             closed.set()
#
#     # async def _say(self, writer, text: str, closed: asyncio.Event):
#     #     loop = asyncio.get_running_loop()
#     #     pcm = await asyncio.to_thread(get_tts().synthesize_pcm, text)
#     #     t0 = loop.time()
#     #     for n, i in enumerate(range(0, len(pcm), FRAME)):
#     #         if closed.is_set():
#     #             return
#     #         chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")
#     #         packet = struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk
#     #         writer.write(packet)
#     #         await writer.drain()
#     #         delay = t0 + (n + 1) * FRAME_SEC - loop.time()
#     #         if delay > 0:
#     #             await asyncio.sleep(delay)
#
#     # async def _say(self, writer, text: str, closed: asyncio.Event):
#     #     loop = asyncio.get_running_loop()
#     #     pcm = await asyncio.to_thread(get_tts().synthesize_pcm, text)
#     #
#     #     t0 = loop.time()
#     #     for n, i in enumerate(range(0, len(pcm), FRAME)):
#     #         if closed.is_set():
#     #             return
#     #         chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")
#     #
#     #         # Отправляем: 0x10 (Audio) + длина (big-endian) + аудио
#     #         writer.write(struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk)
#     #         await writer.drain()
#     #
#     #         # Ждем в реальном времени, чтобы не переполнить буфер
#     #         delay = t0 + (n + 1) * FRAME_SEC - loop.time()
#     #         if delay > 0:
#     #             await asyncio.sleep(delay)
#
#     async def _say(self, writer, text: str, closed: asyncio.Event):
#         loop = asyncio.get_running_loop()
#         pcm = await asyncio.to_thread(get_tts().synthesize_pcm, text)
#
#         t0 = loop.time()
#         for n, i in enumerate(range(0, len(pcm), FRAME)):
#             if closed.is_set():
#                 return
#             chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")
#
#             writer.write(struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk)
#             await writer.drain()
#
#             delay = t0 + (n + 1) * FRAME_SEC - loop.time()
#             if delay > 0:
#                 await asyncio.sleep(delay)
#
#     async def _listen(self, q: asyncio.Queue, closed: asyncio.Event) -> bytes | None:
#         while not q.empty():
#             q.get_nowait()
#         vad = webrtcvad.Vad(VAD_MODE)
#         ring: deque = deque(maxlen=10)
#         speech, started, silence, voiced, waited = bytearray(), False, 0, 0, 0
#         while True:
#             try:
#                 frame = await asyncio.wait_for(q.get(), 0.1)
#             except asyncio.TimeoutError:
#                 if closed.is_set():
#                     return None
#                 continue
#             is_sp = vad.is_speech(frame, 8000)
#             if not started:
#                 ring.append((frame, is_sp))
#                 waited += 1
#                 if sum(s for _, s in ring) >= 6:
#                     started, silence = True, 0
#                     speech = bytearray(b"".join(f for f, _ in ring))
#                     voiced = sum(s for _, s in ring)
#                 elif waited > NO_SPEECH_FRAMES:
#                     return b""
#                 continue
#             speech += frame
#             voiced += is_sp
#             silence = 0 if is_sp else silence + 1
#             too_long = len(speech) > MAX_UTTERANCE_FRAMES * FRAME
#             if silence >= END_SILENCE_FRAMES or too_long:
#                 if voiced >= MIN_VOICED_FRAMES:
#                     return bytes(speech)
#                 ring.clear()
#                 speech, started, silence, voiced = bytearray(), False, 0, 0
#
#     async def _session(self, call_id: str, q, closed, writer):
#         # ==========================================
#         # ВРЕМЕННЫЙ ТЕСТ ЗВУКА (потом удалим)
#         # ==========================================
#         logger.info("[%s] Отправляем тестовый звук...", call_id)
#         keepalive = asyncio.create_task(self._keepalive(writer, closed))
#
#         await self._say(writer, "Здравствуйте! Это тестовая фраза. Если вы её слышите, значит звук работает.", closed)
#
#         logger.info("[%s] Тестовый звук отправлен. Ждём 5 секунд...", call_id)
#         await asyncio.sleep(5.0)
#
#         keepalive.cancel()
#         return
#         # ==========================================
#         # КОНЕЦ ТЕСТА. ДАЛЬШЕ ИДЕТ ВАШ ОБЫЧНЫЙ КОД
#         # ==========================================
#
#         # (этот код пока не выполнится из-за return, но он должен остаться здесь)
#         r = await self.engine.handle(call_id, "алло")
#         await self._say(writer, r.reply, closed)
#
#         empty = 0
#         while not closed.is_set():
#             pcm = await self._listen(q, closed)
#             if pcm is None:
#                 return
#             if pcm:
#                 logger.info("[%s] речь %.1f с, распознаю...", call_id, len(pcm) / 16000)
#             text = await asyncio.to_thread(transcribe_pcm8k, pcm) if pcm else ""
#             logger.info("[%s] пациент: %r", call_id, text)
#
#             if not text:
#                 empty += 1
#                 if empty >= 3:
#                     await self._say(writer, "Я вас не слышу. Соединяю с регистратором.", closed)
#                     TRANSFERS.add(call_id)
#                     return
#                 await self._say(writer, "Извините, не расслышала. Повторите, пожалуйста.", closed)
#                 continue
#             empty = 0
#
#             r = await self.engine.handle(call_id, text)
#             logger.info("[%s] ассистент: %r (step=%s)", call_id, r.reply, r.step)
#             await self._say(writer, r.reply, closed)
#
#             if _is_transfer(r):
#                 TRANSFERS.add(call_id)
#                 return
#             if getattr(r, "booked", False):
#                 return
#
#     async def handle_client(self, reader, writer):
#         peer = writer.get_extra_info("peername")
#         closed, q, pump, call_id = asyncio.Event(), asyncio.Queue(), None, "unknown"
#         try:
#             # ── Читаем ПЕРВЫЙ пакет (ожидаем UUID) ──
#             kind, payload = await asyncio.wait_for(self._read_msg(reader), 5)
#
#             if kind == KIND_UUID and len(payload) == 16:
#                 call_id = str(uuidlib.UUID(bytes=payload))
#                 logger.info("UUID получен: %s от %s", call_id, peer)
#             else:
#                 logger.warning("Первый пакет не UUID: kind=0x%02x len=%d", kind, len(payload))
#                 # Если пришёл не UUID — всё равно продолжаем, call_id = "unknown"
#
#             pump = asyncio.create_task(self._pump(reader, q, closed))
#             await asyncio.wait_for(self._session(call_id, q, closed, writer), MAX_CALL_SEC)
#             await asyncio.sleep(0.8)
#         except (asyncio.IncompleteReadError, ConnectionError):
#             logger.info("Звонок %s: соединение закрыто", call_id)
#         except Exception:
#             logger.exception("Звонок %s: ошибка. Переводим на регистратора", call_id)
#             TRANSFERS.add(call_id)
#         finally:
#             if pump:
#                 pump.cancel()
#             self._forget(call_id)
#             writer.close()
#             try:
#                 await writer.wait_closed()
#             except Exception:  # noqa: BLE001
#                 pass
#
#     async def _session(self, call_id: str, q, closed, writer):
#         # ВРЕМЕННЫЙ ТЕСТ
#         logger.info("[%s] === НАЧАЛО ТЕСТА ЗВУКА ===", call_id)
#
#         # 1. Генерируем тон 800 Гц (синусоиду), чтобы не зависеть от TTS
#         import math
#         import struct
#         sample_rate = 8000
#         duration = 3.0
#         num_samples = int(sample_rate * duration)
#
#         logger.info("[%s] Генерируем тон...", call_id)
#         for i in range(0, num_samples, 160):  # чанки по 160 сэмплов = 320 байт
#             chunk = bytearray()
#             for j in range(160):
#                 val = int(32767 * 0.5 * math.sin(2 * math.pi * 800 * (i + j) / sample_rate))
#                 chunk.extend(struct.pack("<h", val))
#
#             # Отправляем в Asterisk: тип 0x10 + длина 320 + данные
#             writer.write(struct.pack("!BH", 0x10, len(chunk)) + chunk)
#             await writer.drain()
#             await asyncio.sleep(0.02)  # 20 мс
#
#         logger.info("[%s] === ТОН ОТПРАВЛЕН ===", call_id)
#         await asyncio.sleep(2)
#         return
#
#     async def _keepalive(self, writer, closed: asyncio.Event):
#         """Шлёт тишину в Asterisk, чтобы он не закрыл соединение по таймауту."""
#         try:
#             while not closed.is_set():
#                 chunk = b"\x00" * FRAME
#                 # Отправляем 0x10 (Audio) + 320 байт тишины
#                 writer.write(struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk)
#                 await writer.drain()
#                 await asyncio.sleep(FRAME_SEC)
#         except (ConnectionError, asyncio.CancelledError):
#             pass
#
#     async def _session(self, call_id: str, q, closed, writer):
#         logger.info("[%s] === СТАРТ ДИАЛОГА ===", call_id)
#
#         # Запускаем keepalive (тишину), чтобы Asterisk не отвалился, пока думает GigaChat
#         keepalive = asyncio.create_task(self._keepalive(writer, closed))
#
#         try:
#             # 1. Приветствие от бота
#             r = await self.engine.handle(call_id, "алло")
#             await self._say(writer, r.reply, closed)
#
#             empty = 0
#             while not closed.is_set():
#                 # 2. Ждем, пока пациент скажет что-то (VAD)
#                 pcm = await self._listen(q, closed)
#                 if pcm is None:
#                     break
#
#                 if pcm:
#                     logger.info("[%s] речь %.1f с, распознаю...", call_id, len(pcm) / 16000)
#
#                 # 3. Распознаем речь (Whisper)
#                 text = await asyncio.to_thread(transcribe_pcm8k, pcm) if pcm else ""
#                 logger.info("[%s] пациент: %r", call_id, text)
#
#                 if not text:
#                     empty += 1
#                     if empty >= 3:
#                         await self._say(writer, "Я вас не слышу. Соединяю с регистратором.", closed)
#                         TRANSFERS.add(call_id)
#                         break
#                     await self._say(writer, "Извините, не расслышала. Повторите, пожалуйста.", closed)
#                     continue
#                 empty = 0
#
#                 # 4. Отвечаем через GigaChat и логику
#                 r = await self.engine.handle(call_id, text)
#                 logger.info("[%s] ассистент: %r (step=%s)", call_id, r.reply, r.step)
#
#                 # 5. Озвучиваем ответ
#                 await self._say(writer, r.reply, closed)
#
#                 # 6. Выходим, если записали или перевели
#                 if _is_transfer(r):
#                     TRANSFERS.add(call_id)
#                     break
#                 if getattr(r, "booked", False):
#                     break
#         finally:
#             keepalive.cancel()
#
#     async def handle_client(self, reader, writer):
#         peer = writer.get_extra_info("peername")
#         closed, q, pump, keepalive_task, call_id = asyncio.Event(), asyncio.Queue(), None, None, "unknown"
#
#         try:
#             # 1. Читаем ПЕРВЫЙ пакет (ожидаем UUID)
#             kind, payload = await asyncio.wait_for(self._read_msg(reader), 5)
#
#             if kind == KIND_UUID and len(payload) == 16:
#                 call_id = str(uuidlib.UUID(bytes=payload))
#                 logger.info("UUID получен: %s от %s", call_id, peer)
#             else:
#                 logger.warning("Первый пакет не UUID: kind=0x%02x len=%d", kind, len(payload))
#
#             # 2. СРАЗУ запускаем тишину, чтобы Asterisk не отвалился,
#             # пока мы думаем (GigaChat, TTS и т.д.)
#             keepalive_task = asyncio.create_task(self._keepalive(writer, closed))
#
#             # 3. Запускаем чтение аудио из сокета
#             pump = asyncio.create_task(self._pump(reader, q, closed))
#
#             # 4. Запускаем сессию диалога
#             await asyncio.wait_for(self._session(call_id, q, closed, writer), MAX_CALL_SEC)
#
#             # Даем время доиграть последнюю фразу
#             await asyncio.sleep(0.8)
#
#         except (asyncio.IncompleteReadError, ConnectionError):
#             logger.info("Звонок %s: соединение закрыто", call_id)
#         except Exception:
#             logger.exception("Звонок %s: ошибка. Переводим на регистратора", call_id)
#             TRANSFERS.add(call_id)
#         finally:
#             # Останавливаем всё
#             closed.set()
#             if pump:
#                 pump.cancel()
#             if keepalive_task:
#                 keepalive_task.cancel()
#
#             self._forget(call_id)
#             writer.close()
#             try:
#                 await writer.wait_closed()
#             except Exception:
#                 pass
#
#     def _warmup(self):
#         try:
#             stt_warmup()
#             get_tts().synthesize_pcm("Проверка")
#             logger.info("Модели ASR и TTS прогреты")
#         except Exception:
#             logger.exception("Прогрев моделей не удался")
#
#     async def start(self) -> None:
#         server = await asyncio.start_server(self.handle_client, self.host, self.port)
#         logger.info("AudioSocket сервер запущен на %s:%s", self.host, self.port)
#         self._warm_task = asyncio.create_task(asyncio.to_thread(self._warmup))
#         async with server:
#             await server.serve_forever()

class AudioServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9092, engine=None):
        self.host, self.port = host, port
        if engine is None:
            from app.api.demo import _engine
            engine = _engine
        self.engine = engine

    def _forget(self, call_id: str) -> None:
        end_call = getattr(self.engine, "end_call", None)
        if end_call:
            end_call(call_id)
        else:
            self.engine._states.pop(call_id, None)

    @staticmethod
    async def _read_msg(reader):
        header = await reader.readexactly(3)
        kind = header[0]
        length = struct.unpack(">H", header[1:3])[0]
        payload = await reader.readexactly(length) if length else b""
        logger.debug(f"RX kind=0x{kind:02x} len={length} head={payload[:8].hex()}")
        return kind, payload

    async def _pump(self, reader, q: asyncio.Queue, closed: asyncio.Event):
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
                    logger.info("Пациент положил трубку (hangup/error)")
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("Соединение с Asterisk закрыто")
        finally:
            closed.set()

    async def _keepalive(self, writer, closed: asyncio.Event):
        """Шлёт тишину в Asterisk, чтобы он не закрыл соединение по таймауту."""
        try:
            while not closed.is_set():
                chunk = b"\x00" * FRAME
                writer.write(struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk)
                await writer.drain()
                await asyncio.sleep(FRAME_SEC)
        except (ConnectionError, asyncio.CancelledError):
            pass

    async def _say(self, writer, text: str, closed: asyncio.Event):
        loop = asyncio.get_running_loop()
        pcm = await asyncio.to_thread(get_tts().synthesize_pcm, text)

        t0 = loop.time()
        for n, i in enumerate(range(0, len(pcm), FRAME)):
            if closed.is_set():
                return
            chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")

            writer.write(struct.pack("!BH", KIND_AUDIO, len(chunk)) + chunk)
            await writer.drain()

            delay = t0 + (n + 1) * FRAME_SEC - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

    async def _listen(self, q: asyncio.Queue, closed: asyncio.Event) -> bytes | None:
        while not q.empty():
            q.get_nowait()
        vad = webrtcvad.Vad(VAD_MODE)
        ring: deque = deque(maxlen=10)
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
                ring.clear()
                speech, started, silence, voiced = bytearray(), False, 0, 0

    async def _session(self, call_id: str, q, closed, writer):
        logger.info("[%s] === СТАРТ ДИАЛОГА ===", call_id)
        keepalive = asyncio.create_task(self._keepalive(writer, closed))

        try:
            r = await self.engine.handle(call_id, "алло")
            await self._say(writer, r.reply, closed)

            empty = 0
            while not closed.is_set():
                pcm = await self._listen(q, closed)
                if pcm is None:
                    break

                if pcm:
                    logger.info("[%s] речь %.1f с, распознаю...", call_id, len(pcm) / 16000)

                text = await asyncio.to_thread(transcribe_pcm8k, pcm) if pcm else ""
                logger.info("[%s] пациент: %r", call_id, text)

                if not text:
                    empty += 1
                    if empty >= 3:
                        await self._say(writer, "Я вас не слышу. Завершаю звонок.", closed)
                        break
                    await self._say(writer, "Извините, не расслышала. Повторите, пожалуйста.", closed)
                    continue
                empty = 0

                r = await self.engine.handle(call_id, text)
                logger.info("[%s] ассистент: %r (step=%s)", call_id, r.reply, r.step)
                await self._say(writer, r.reply, closed)

                if getattr(r, "booked", False):
                    break
        finally:
            keepalive.cancel()

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        closed, q, pump, keepalive_task, call_id = asyncio.Event(), asyncio.Queue(), None, None, "unknown"
        try:
            kind, payload = await asyncio.wait_for(self._read_msg(reader), 5)
            if kind == KIND_UUID and len(payload) == 16:
                call_id = str(uuidlib.UUID(bytes=payload))
                logger.info("UUID получен: %s от %s", call_id, peer)

            keepalive_task = asyncio.create_task(self._keepalive(writer, closed))
            pump = asyncio.create_task(self._pump(reader, q, closed))

            await asyncio.wait_for(self._session(call_id, q, closed, writer), MAX_CALL_SEC)
            await asyncio.sleep(0.8)
        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("Звонок %s: соединение закрыто", call_id)
        except Exception:
            logger.exception("Звонок %s: ошибка.", call_id)
        finally:
            closed.set()
            if pump:
                pump.cancel()
            if keepalive_task:
                keepalive_task.cancel()
            self._forget(call_id)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _warmup(self):
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