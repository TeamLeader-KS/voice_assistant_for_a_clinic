# # """TCP-сервер для AudioSocket от Asterisk.
# #
# # Asterisk шлёт бинарный протокол:
# #     1 байт  — тип сообщения (0x00 UUID, 0x10 аудио, 0xFF завершение)
# #     2 байта — длина (big-endian)
# #     N байт  — данные
# # """
# #
# # import asyncio
# # import logging
# # import struct
# #
# # logger = logging.getLogger(__name__)
# #
# #
# # class AudioServer:
# #     """TCP-сервер для AudioSocket от Asterisk."""
# #
# #     def __init__(self, host: str = "0.0.0.0", port: int = 9092):
# #         self.host = host
# #         self.port = port
# #
# #     async def handle_client(
# #         self,
# #         reader: asyncio.StreamReader,
# #         writer: asyncio.StreamWriter,
# #     ) -> None:
# #         peer = writer.get_extra_info("peername")
# #         logger.info(f"AudioSocket подключение от {peer}")
# #
# #         try:
# #             while True:
# #                 # Заголовок: 1 байт тип + 2 байта длина
# #                 header = await reader.readexactly(3)
# #                 msg_type = header[0]
# #                 length = struct.unpack(">H", header[1:3])[0]
# #                 payload = await reader.readexactly(length) if length else b""
# #
# #                 if msg_type == 0x00:
# #                     logger.info(f"UUID: {payload.hex()}")
# #
# #                 elif msg_type == 0x10:
# #                     logger.info(f"Аудио: {len(payload)} байт")
# #                     # ЭХО для теста — вернуть то же аудио
# #                     await self._send_audio(writer, payload)
# #
# #                 elif msg_type == 0xFF:
# #                     logger.info("Соединение завершено")
# #                     break
# #
# #                 else:
# #                     logger.warning(f"Неизвестный тип: {msg_type:#x}")
# #
# #         except asyncio.IncompleteReadError:
# #             logger.info("Клиент отключился")
# #         except Exception as e:
# #             logger.error(f"Ошибка: {e}", exc_info=True)
# #         finally:
# #             writer.close()
# #             try:
# #                 await writer.wait_closed()
# #             except Exception:
# #                 pass
# #
# #     async def _send_audio(self, writer: asyncio.StreamWriter, pcm: bytes) -> None:
# #         """Отправить аудио обратно в Asterisk."""
# #         header = bytes([0x10]) + struct.pack(">H", len(pcm))
# #         writer.write(header + pcm)
# #         await writer.drain()
# #
# #     async def start(self) -> None:
# #         server = await asyncio.start_server(
# #             self.handle_client, self.host, self.port
# #         )
# #         logger.info(f"AudioSocket TCP-сервер запущен на {self.host}:{self.port}")
# #         async with server:
# #             await server.serve_forever()
#
# """TCP-сервер для AudioSocket от Asterisk.
#
# Asterisk шлёт бинарный протокол:
#     1 байт  — тип сообщения (0x00 UUID, 0x10 аудио, 0xFF завершение)
#     2 байта — длина (big-endian)
#     N байт  — данные
# """
#
# import asyncio
# import logging
# import struct
#
# logger = logging.getLogger(__name__)
#
#
# class AudioServer:
#     """TCP-сервер для AudioSocket от Asterisk."""
#
#     def __init__(self, host: str = "0.0.0.0", port: int = 9092):
#         self.host = host
#         self.port = port
#
#     async def handle_client(
#         self,
#         reader: asyncio.StreamReader,
#         writer: asyncio.StreamWriter,
#     ) -> None:
#         peer = writer.get_extra_info("peername")
#         logger.info(f"AudioSocket подключение от {peer}")
#
#         total_bytes = 0
#         audio_chunks = 0
#
#         try:
#             while True:
#                 # Читаем заголовок (3 байта) с диагностикой
#                 try:
#                     header = await reader.readexactly(3)
#                 except asyncio.IncompleteReadError as e:
#                     logger.info(
#                         f"Клиент закрыл соединение: "
#                         f"пришло {len(e.partial)} байт заголовка, "
#                         f"всего {total_bytes} байт, {audio_chunks} аудио-чанков"
#                     )
#                     break
#
#                 msg_type = header[0]
#                 length = struct.unpack(">H", header[1:3])[0]
#
#                 # Читаем payload
#                 try:
#                     payload = await reader.readexactly(length) if length else b""
#                 except asyncio.IncompleteReadError as e:
#                     logger.info(
#                         f"Обрыв на payload: ожидалось {length} байт, "
#                         f"пришло {len(e.partial)}"
#                     )
#                     break
#
#                 total_bytes += 3 + length
#
#                 if msg_type == 0x00:
#                     logger.info(f"UUID: {payload.hex()}")
#
#                 elif msg_type == 0x01:
#                     audio_chunks += 1
#                     logger.info(f"Аудио #{audio_chunks}: {len(payload)} байт")
#                     # Эхо для проверки
#                     await self._send_audio(writer, payload)
#
#                 elif msg_type == 0x03:
#                     logger.info("Hangup")
#                     break
#
#                 elif msg_type == 0xFF:
#                     logger.info("Соединение завершено (0xFF)")
#                     break
#
#                 else:
#                     logger.warning(f"Неизвестный тип: {msg_type:#x}")
#
#         except Exception as e:
#             logger.error(f"Ошибка: {e}", exc_info=True)
#         finally:
#             writer.close()
#             try:
#                 await writer.wait_closed()
#             except Exception:
#                 pass
#             logger.info(
#                 f"Сессия закрыта: {total_bytes} байт, {audio_chunks} чанков"
#             )
#
#     async def _send_audio(
#         self, writer: asyncio.StreamWriter, pcm: bytes
#     ) -> None:
#         """Отправить аудио обратно в Asterisk."""
#         header = bytes([0x01]) + struct.pack(">H", len(pcm))
#         writer.write(header + pcm)
#         await writer.drain()
#
#     async def start(self) -> None:
#         server = await asyncio.start_server(
#             self.handle_client, self.host, self.port
#         )
#         logger.info(
#             f"AudioSocket TCP-сервер запущен на {self.host}:{self.port}"
#         )
#         async with server:
#             await server.serve_forever()

"""AudioSocket-мост: Asterisk ⇄ VAD ⇄ STT ⇄ DialogEngine ⇄ TTS."""

import asyncio
import logging
import struct
import uuid as uuidlib
from collections import deque

import webrtcvad

from app.api.demo import _engine          # общий движок диалога
from app.voice.stt import transcribe_pcm8k
from app.voice.tts import SileroTTSWrapper

logger = logging.getLogger(__name__)

KIND_HANGUP, KIND_UUID, KIND_DTMF, KIND_AUDIO, KIND_ERROR = 0x00, 0x01, 0x03, 0x10, 0xFF
FRAME = 320                 # 20 мс при 8 кГц, 16 бит
FRAME_SEC = 0.02
END_SILENCE_FRAMES = 40     # 0,8 с тишины = конец реплики
MAX_UTTERANCE_FRAMES = 500  # не дольше 10 с
NO_SPEECH_FRAMES = 750      # 15 с молчания

TRANSFERS: set[str] = set()  # звонки, которые нужно перевести на оператора


class AudioServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9092):
        self.host, self.port = host, port
        self._tts = SileroTTSWrapper()

    # ── протокол ──
    @staticmethod
    async def _read_msg(reader):
        header = await reader.readexactly(3)
        length = struct.unpack(">H", header[1:3])[0]
        payload = await reader.readexactly(length) if length else b""
        return header[0], payload

    async def _pump(self, reader, q: asyncio.Queue, closed: asyncio.Event):
        """Читает сокет всё время, чтобы он не переполнялся, пока мы говорим."""
        try:
            while True:
                kind, payload = await self._read_msg(reader)
                if kind == KIND_AUDIO:
                    q.put_nowait(payload)
                elif kind in (KIND_HANGUP, KIND_ERROR):
                    break
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            closed.set()

    async def _say(self, writer, text: str, closed: asyncio.Event):
        loop = asyncio.get_running_loop()
        pcm = await loop.run_in_executor(None, self._tts.synthesize_pcm, text)
        for i in range(0, len(pcm), FRAME):
            if closed.is_set():
                return
            chunk = pcm[i:i + FRAME]
            writer.write(bytes([KIND_AUDIO]) + struct.pack(">H", len(chunk)) + chunk)
            await writer.drain()
            await asyncio.sleep(FRAME_SEC)   # отдаём в реальном времени

    async def _listen(self, q: asyncio.Queue, closed: asyncio.Event) -> bytes | None:
        """Ждёт реплику пациента. None — звонок завершён, b'' — молчание."""
        while not q.empty():                 # выбросить то, что накопилось, пока говорили мы
            q.get_nowait()
        vad = webrtcvad.Vad(2)
        ring: deque = deque(maxlen=10)       # предзапись 200 мс, чтобы не резать начало слова
        speech, started, silence, waited = bytearray(), False, 0, 0
        while True:
            try:
                frame = await asyncio.wait_for(q.get(), 0.1)
            except asyncio.TimeoutError:
                if closed.is_set():
                    return None
                continue
            if len(frame) != FRAME:
                continue
            is_sp = vad.is_speech(frame, 8000)
            if not started:
                ring.append((frame, is_sp))
                waited += 1
                if sum(s for _, s in ring) >= 6:
                    started = True
                    speech = bytearray(b"".join(f for f, _ in ring))
                elif waited > NO_SPEECH_FRAMES:
                    return b""
            else:
                speech += frame
                silence = 0 if is_sp else silence + 1
                if silence >= END_SILENCE_FRAMES or len(speech) > MAX_UTTERANCE_FRAMES * FRAME:
                    return bytes(speech)

    # ── сценарий звонка ──
    async def _session(self, call_id, q, closed, writer):
        loop = asyncio.get_running_loop()
        r = await _engine.handle(call_id, "алло")        # приветствие движка
        await self._say(writer, r.reply, closed)
        empty = 0
        while not closed.is_set():
            pcm = await self._listen(q, closed)
            if pcm is None:
                return
            text = await loop.run_in_executor(None, transcribe_pcm8k, pcm) if pcm else ""
            logger.info("[%s] пациент: %r", call_id, text)
            if not text:
                empty += 1
                if empty >= 3:
                    await self._say(writer, "Не слышу вас. Перезвоните, пожалуйста.", closed)
                    return
                await self._say(writer, "Извините, не расслышала. Повторите, пожалуйста.", closed)
                continue
            empty = 0
            r = await _engine.handle(call_id, text)
            logger.info("[%s] ассистент: %r (step=%s)", call_id, r.reply, r.step)
            await self._say(writer, r.reply, closed)
            if getattr(r, "transfer", False):
                TRANSFERS.add(call_id)
                return
            if r.booked:
                return

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        closed, q, pump, call_id = asyncio.Event(), asyncio.Queue(), None, "unknown"
        try:
            kind, payload = await self._read_msg(reader)
            if kind == KIND_UUID and len(payload) == 16:
                call_id = str(uuidlib.UUID(bytes=payload))
            logger.info("Звонок %s от %s", call_id, peer)
            pump = asyncio.create_task(self._pump(reader, q, closed))
            await self._session(call_id, q, closed, writer)
            await asyncio.sleep(0.7)         # дать доиграть последнюю фразу
        except (asyncio.IncompleteReadError, ConnectionError):
            logger.info("Звонок %s: соединение закрыто", call_id)
        except Exception:
            logger.exception("Звонок %s: ошибка", call_id)
        finally:
            if pump:
                pump.cancel()
            _engine._states.pop(call_id, None)   # noqa: SLF001
            writer.close()

    def _warmup(self):
        """Прогреть модели, иначе первый звонок ждёт десятки секунд."""
        try:
            transcribe_pcm8k(b"\x00\x00" * 8000)
            self._tts.synthesize_pcm("Проверка")
            logger.info("Модели STT и TTS прогреты")
        except Exception:
            logger.exception("Прогрев моделей не удался")

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logger.info("AudioSocket TCP-сервер запущен на %s:%s", self.host, self.port)
        asyncio.get_running_loop().run_in_executor(None, self._warmup)
        async with server:
            await server.serve_forever()