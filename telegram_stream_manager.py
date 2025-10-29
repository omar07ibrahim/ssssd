"""Telegram video streaming manager using Pyrogram and PyTgCalls.

This module wraps the standalone tg.py script into a reusable manager that can be
integrated with the camera lifecycle. It waits for a virtual camera to be ready
and then starts streaming into the configured Telegram group call.
"""

import asyncio
import threading
from typing import Optional

from config import logger, CONFIG

# Temporary patch to avoid missing attribute on some Pyrogram versions
import pyrogram.errors


class GroupcallForbidden(Exception):
    """Compatibility wrapper when Pyrogram misses GroupcallForbidden."""


if not hasattr(pyrogram.errors, "GroupcallForbidden"):
    pyrogram.errors.GroupcallForbidden = GroupcallForbidden

from pyrogram import Client
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from pytgcalls import MediaDevices


class TelegramStreamManager:
    """Controls Telegram group call streaming in a background thread."""

    def __init__(self):
        self.enabled = CONFIG.get("telegram_stream_enabled", False)
        self.session_name = CONFIG.get("telegram_stream_session", "stream_bot")
        self.api_id = CONFIG.get("telegram_stream_api_id")
        self.api_hash = CONFIG.get("telegram_stream_api_hash")
        chat_cfg = CONFIG.get("telegram_stream_chat_id")
        if isinstance(chat_cfg, str):
            try:
                chat_cfg = int(chat_cfg)
            except ValueError:
                pass
        self.chat_id = chat_cfg
        self.camera_name = CONFIG.get("telegram_stream_camera_name", "OBS Virtual Camera")
        self.delay_seconds = CONFIG.get("telegram_stream_delay_seconds", 10)
        self.ffmpeg_params = CONFIG.get("telegram_stream_ffmpeg_params")
        self.camera_retry_attempts = CONFIG.get("telegram_stream_camera_retry_attempts", 10)
        self.camera_retry_delay = CONFIG.get("telegram_stream_camera_retry_delay", 2)

        self._app: Optional[Client] = None
        self._pytgcalls: Optional[PyTgCalls] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._running = False
        self._stream_active = False
        self._lock = threading.Lock()
        self._last_error: Optional[Exception] = None
        self._camera_info = None
        self._me = None

        if not self.enabled:
            logger.info("Telegram streaming is disabled in configuration")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_error(self) -> Optional[Exception]:
        return self._last_error

    def start_stream(self, delay: Optional[int] = None) -> bool:
        """
        Launch the Telegram streaming workflow in a dedicated thread.

        Args:
            delay: Optional delay in seconds before attempting to start the stream.
        Returns:
            bool: True if the stream was scheduled to start, False otherwise.
        """
        if not self.enabled:
            return False
        if not self.api_id or not self.api_hash or self.chat_id is None:
            logger.error("Telegram streaming is missing API credentials or chat id")
            return False

        try:
            self.chat_id = int(self.chat_id)
        except (TypeError, ValueError):
            logger.error("Telegram chat id must be an integer, got %s", self.chat_id)
            return False

        with self._lock:
            if self._running:
                logger.info("Telegram stream is already running")
                return True

            self._last_error = None
            self._camera_info = None
            self._running = True
            start_delay = delay if delay is not None else max(int(self.delay_seconds), 0)
            self._thread = threading.Thread(
                target=self._thread_entry,
                args=(start_delay,),
                name="TelegramStreamThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("Telegram stream thread started")
            return True

    def stop_stream(self):
        """Signal the streaming thread to stop and wait for cleanup."""
        with self._lock:
            if not self._running:
                return

            if self._loop and self._stop_event and not self._stop_event.is_set():
                try:
                    self._loop.call_soon_threadsafe(self._stop_event.set)
                except Exception:
                    # Event loop might already be closed
                    pass

            if self._thread:
                self._thread.join(timeout=15)

            # Clean up references
            self._thread = None
            self._loop = None
            if self._stop_event:
                # Make sure the event is set in case of multiple calls
                try:
                    if not self._stop_event.is_set():
                        self._stop_event.set()
                except:
                    pass
            self._stop_event = None
            self._running = False
            self._stream_active = False
            logger.info("Telegram stream stopped")

    def _thread_entry(self, delay: int):
        """Entry point for the background thread running the event loop."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._stop_event = asyncio.Event()
            self._loop.run_until_complete(self._run_stream(delay))
        except Exception as exc:
            self._last_error = exc
            logger.error(f"Telegram stream thread crashed: {exc}")
        finally:
            if self._loop:
                self._loop.close()
                self._loop = None
            self._running = False
            self._stream_active = False

    async def _run_stream(self, delay: int):
        """Main coroutine handling initialization, streaming and cleanup."""
        try:
            await self._initialize_clients()
            await self._prepare_chat()

            if delay > 0:
                print(f"Ожидание {delay} секунд перед запуском стрима...")
                await asyncio.sleep(delay)

            camera = await self._wait_for_camera_device()
            if not camera:
                print("✗ Камеры не найдены")
                print("  Проверьте подключение камеры к компьютеру")
                logger.error("No suitable camera found for Telegram streaming")
                return

            started = await self._start_stream(camera)
            if not started:
                return

            self._stream_active = True
            print("\n⏸️  Для остановки нажмите Ctrl+C")
            logger.info("Telegram stream is now active")

            # Wait until stop is requested
            await self._stop_event.wait()
        except Exception as exc:
            self._last_error = exc
            print(f"\n✗ Критическая ошибка: {exc}")
            logger.error(f"Telegram streaming encountered an error: {exc}")
        finally:
            await self._shutdown()

    async def _initialize_clients(self):
        """Initialize Pyrogram and PyTgCalls clients."""
        print("\nИнициализация клиентов...")
        self._app = Client(
            self.session_name,
            api_id=self.api_id,
            api_hash=self.api_hash,
        )
        self._pytgcalls = PyTgCalls(self._app)

        print("Запуск Pyrogram...")
        await self._app.start()
        print("Запуск PyTgCalls...")
        await self._pytgcalls.start()

        try:
            self._me = await self._app.get_me()
            print(
                "✅ Вход выполнен как: @{} (ID: {})".format(
                    self._me.username if self._me.username else self._me.first_name,
                    self._me.id,
                )
            )
        except Exception:
            print("✅ Клиент подключен")
            self._me = None

    async def _prepare_chat(self):
        """Mirror tg.py logic: preload dialogs to ensure chat is known."""
        if not self._app or self.chat_id is None:
            return

        print("\nЗагрузка информации о чатах...")
        found = False
        try:
            async for dialog in self._app.get_dialogs():
                if dialog.chat.id == self.chat_id:
                    found = True
                    chat_title = getattr(dialog.chat, "title", "Чат")
                    print(f"✅ Чат найден: {chat_title}")
                    if self._me:
                        try:
                            member = await self._app.get_chat_member(self.chat_id, self._me.id)
                            status = str(getattr(member, "status", "")).lower()
                            if any(flag in status for flag in ("owner", "admin", "creator")):
                                print("✅ Бот имеет права администратора")
                        except Exception as exc:
                            logger.debug("Unable to verify admin rights: %s", exc)
                    break

            if not found:
                print(f"⚠️  Чат {self.chat_id} не найден в списке диалогов")
                print("   Возможно бот не добавлен в этот чат")
        except Exception as exc:
            print(f"⚠️  Не удалось загрузить список чатов: {exc}")

        try:
            await self._app.resolve_peer(self.chat_id)
        except Exception as exc:
            logger.warning("Failed to resolve chat peer %s: %s", self.chat_id, exc)

    async def _wait_for_camera_device(self):
        """Wait for the configured camera to become available."""
        print("\nПоиск доступных камер...")
        desired_name = (self.camera_name or "").lower().strip()
        attempts = max(int(self.camera_retry_attempts or 0), 1)
        delay = max(float(self.camera_retry_delay or 1), 0.5)

        for attempt in range(1, attempts + 1):
            try:
                cameras = MediaDevices.camera_devices()
            except Exception as exc:
                logger.error(f"Failed to list camera devices: {exc}")
                cameras = []
            if cameras:
                for camera in cameras:
                    camera_name = getattr(camera, "name", str(camera)) or "Unknown"
                    if not desired_name or desired_name in camera_name.lower():
                        self._camera_info = camera_name
                        print(f"✅ Найдена камера: {camera_name}")
                        return camera
                available = ", ".join(
                    getattr(cam, "name", str(cam)) or "Unknown" for cam in cameras
                )
                logger.warning(
                    "Attempt %d: Virtual camera '%s' not found (available: %s)",
                    attempt,
                    self.camera_name,
                    available,
                )
                print(
                    f"⚠️  Попытка {attempt}: виртуальная камера '{self.camera_name}' не найдена."
                    f" Доступно: {available}"
                )
            else:
                logger.warning(
                    "Attempt %d: No cameras detected while preparing Telegram stream",
                    attempt,
                )
                print(f"⚠️  Попытка {attempt}: камеры не обнаружены")

            await asyncio.sleep(delay)

        return None

    async def _start_stream(self, camera_device):
        """Start streaming the selected camera into the Telegram group call."""
        if not self._pytgcalls:
            raise RuntimeError("PyTgCalls client is not initialized")

        print(f"\n🎬 Запуск стрима в чат {self.chat_id}...")
        print("  Режим: Только видео (без звука)")

        stream_kwargs = {}
        if self.ffmpeg_params:
            stream_kwargs["ffmpeg_parameters"] = self.ffmpeg_params

        try:
            media_stream = MediaStream(camera_device, **stream_kwargs)
            await self._pytgcalls.play(self.chat_id, media_stream)
            print("\n✅ СТРИМ УСПЕШНО ЗАПУЩЕН!")
            print(f"  📹 Камера: {self._camera_info or 'Unknown'}")
            print(f"  💬 Чат: {self.chat_id}")
            if self.ffmpeg_params:
                print("  📊 Качество: 1920x1080 @ 30fps")
            logger.info(
                "Started Telegram streaming into chat %s using camera %s",
                self.chat_id,
                self._camera_info or "unknown",
            )
            return True
        except Exception as primary_exc:
            if self.ffmpeg_params:
                print("Пробуем стандартные настройки...")
                logger.warning(
                    "Custom FFmpeg params failed (%s). Falling back to defaults.",
                    primary_exc,
                )
                try:
                    media_stream = MediaStream(camera_device)
                    await self._pytgcalls.play(self.chat_id, media_stream)
                    print("\n✅ СТРИМ УСПЕШНО ЗАПУЩЕН!")
                    print(f"  📹 Камера: {self._camera_info or 'Unknown'}")
                    print(f"  💬 Чат: {self.chat_id}")
                    print("  📊 Качество: Стандартное")
                    logger.info(
                        "Started Telegram streaming (fallback) into chat %s using camera %s",
                        self.chat_id,
                        self._camera_info or "unknown",
                    )
                    return True
                except Exception as fallback_exc:
                    print(f"\n✗ Ошибка: {fallback_exc}\n")
                    logger.error("Fallback streaming attempt failed: %s", fallback_exc)
                    self._last_error = fallback_exc
                    return False
            self._last_error = primary_exc
            raise

    async def _shutdown(self):
        """Gracefully stop the stream and shutdown clients."""
        print("🧹 Завершение работы...")
        logger.info("Shutting down Telegram streaming")

        if self._pytgcalls:
            try:
                await self._pytgcalls.leave_group_call(self.chat_id)
            except Exception:
                pass

        try:
            if self._pytgcalls:
                await self._pytgcalls.stop()
        except Exception:
            pass
        finally:
            self._pytgcalls = None

        try:
            if self._app:
                await self._app.stop()
        except Exception:
            pass
        finally:
            self._app = None

        logger.info("Telegram streaming shutdown complete")
        print("✅ Программа завершена")
        self._stream_active = False


# Convenience singleton used by modules that do not want to instantiate explicitly
telegram_stream_manager = TelegramStreamManager()
