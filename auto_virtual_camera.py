import threading
from virtual_camera_manager import VirtualCameraManager
from PIL import Image
import numpy as np


class AutoVirtualCamera:
    """
    Класс-обертка для автоматического запуска виртуальной камеры
    при подключении к реальной камере
    """
    
    def __init__(self, original_class):
        """
        Args:
            original_class: Ваш оригинальный класс камеры
        """
        self.original_class = original_class
        self.virtual_camera = None
        self.is_virtual_camera_started = False
        
        # Сохраняем оригинальный callback
        self._original_frame_callback = None
        
        # Настройки виртуальной камеры
        self.virtual_cam_width = 1280
        self.virtual_cam_height = 720
        self.virtual_cam_fps = 30
        
    def __getattr__(self, name):
        """Проксируем все атрибуты к оригинальному классу"""
        return getattr(self.original_class, name)
        
    def connect_to_camera(self, *args, **kwargs):
        """
        Подключение к камере с автоматическим запуском виртуальной камеры
        """
        print("📷 Подключаемся к реальной камере...")
        
        # Запускаем виртуальную камеру если еще не запущена
        if not self.is_virtual_camera_started:
            self._start_virtual_camera()
            
        # Подключаемся к реальной камере
        result = self.original_class.connect_to_camera(*args, **kwargs)
        
        # Перехватываем callback для копирования кадров
        self._intercept_frame_callback()
        
        return result
        
    def _start_virtual_camera(self):
        """Запуск виртуальной камеры"""
        try:
            print("🚀 Запускаем виртуальную камеру...")
            self.virtual_camera = VirtualCameraManager(
                width=self.virtual_cam_width,
                height=self.virtual_cam_height,
                fps=self.virtual_cam_fps
            )
            self.virtual_camera.start()
            
            if self.virtual_camera.is_initialized:
                self.is_virtual_camera_started = True
                print("✅ Виртуальная камера успешно запущена!")
                print(f"   Разрешение: {self.virtual_cam_width}x{self.virtual_cam_height}")
                print(f"   FPS: {self.virtual_cam_fps}")
                print("   Доступна как: OBS Virtual Camera")
            else:
                print("❌ Не удалось запустить виртуальную камеру")
                
        except Exception as e:
            print(f"❌ Ошибка при запуске виртуальной камеры: {e}")
            self.is_virtual_camera_started = False
            
    def _intercept_frame_callback(self):
        """Перехватываем frame callback для копирования кадров"""
        # Сохраняем оригинальный callback
        if hasattr(self.original_class, 'frame_callback'):
            self._original_frame_callback = self.original_class.frame_callback
            
        # Устанавливаем наш callback-обертку
        if hasattr(self.original_class, '_frame_captured_callback'):
            original_callback = self.original_class._frame_captured_callback
            
            def wrapped_callback(video_capture, frame, custom_object):
                # Вызываем оригинальный callback
                result = original_callback(video_capture, frame, custom_object)
                
                # Если виртуальная камера запущена, отправляем туда копию
                if self.is_virtual_camera_started and self.virtual_camera:
                    try:
                        # Получаем PIL изображение
                        if hasattr(frame, 'GetImage'):
                            pil_image = frame.GetImage()
                        elif isinstance(frame, np.ndarray):
                            pil_image = Image.fromarray(frame)
                        else:
                            pil_image = frame
                            
                        # Создаем копию и отправляем в виртуальную камеру
                        if pil_image:
                            pil_image_copy = pil_image.copy() if hasattr(pil_image, 'copy') else pil_image
                            self.virtual_camera.send_frame(pil_image_copy)
                            
                    except Exception as e:
                        # Не прерываем работу основной камеры при ошибке
                        pass
                        
                return result
                
            # Заменяем callback
            self.original_class._frame_captured_callback = wrapped_callback
            
    def disconnect(self):
        """Отключение от камеры и остановка виртуальной камеры"""
        print("📷 Отключаемся от камеры...")
        
        # Отключаемся от реальной камеры
        if hasattr(self.original_class, 'disconnect'):
            self.original_class.disconnect()
            
        # Останавливаем виртуальную камеру
        if self.is_virtual_camera_started and self.virtual_camera:
            print("🛑 Останавливаем виртуальную камеру...")
            self.virtual_camera.stop()
            self.is_virtual_camera_started = False
            
    def __del__(self):
        """Деструктор для корректной очистки"""
        if self.is_virtual_camera_started and self.virtual_camera:
            self.virtual_camera.stop()


class EnhancedCameraWrapper:
    """
    Альтернативный вариант - полная обертка для вашего класса камеры
    с автоматическим запуском виртуальной камеры
    """
    
    def __init__(self):
        self.engine = None
        self.frame_callback = None
        self.camera_info = {'frames_processed': 0}
        
        # Виртуальная камера
        self.virtual_camera = None
        self.virtual_camera_enabled = True  # Можно включать/выключать
        
    def initialize_camera(self):
        """Инициализация камеры с автозапуском виртуальной камеры"""
        
        # Автоматически запускаем виртуальную камеру
        if self.virtual_camera_enabled and not self.virtual_camera:
            try:
                print("🎬 Инициализируем виртуальную камеру...")
                self.virtual_camera = VirtualCameraManager(
                    width=1280, 
                    height=720, 
                    fps=30
                )
                self.virtual_camera.start()
                
                if self.virtual_camera.is_initialized:
                    print("✅ Виртуальная камера готова к работе!")
                else:
                    print("⚠️ Виртуальная камера не инициализирована")
                    self.virtual_camera = None
                    
            except Exception as e:
                print(f"❌ Ошибка при запуске виртуальной камеры: {e}")
                self.virtual_camera = None
                
    def _frame_captured_callback(self, video_capture, frame, custom_object):
        """
        Callback для обработки кадров с автоматической отправкой в виртуальную камеру
        """
        # Увеличиваем счетчик
        self.camera_info['frames_processed'] += 1
        
        # Отправляем в LPR engine
        if self.engine:
            ret = self.engine.PutFrame(frame, frame.Timestamp())
        
        # Обрабатываем каждый 2-й кадр
        if self.camera_info['frames_processed'] % 2 == 0:
            # Получаем PIL изображение
            pil_image = frame.GetImage()
            
            # Отправляем в оригинальный callback для превью
            if self.frame_callback:
                self.frame_callback(pil_image)
            
            # Автоматически отправляем копию в виртуальную камеру
            if self.virtual_camera and self.virtual_camera.is_initialized:
                try:
                    pil_image_copy = pil_image.copy()
                    self.virtual_camera.send_frame(pil_image_copy)
                except Exception as e:
                    # Не прерываем основной поток при ошибке
                    pass
                    
    def set_virtual_camera_enabled(self, enabled):
        """Включение/выключение виртуальной камеры"""
        self.virtual_camera_enabled = enabled
        
        if enabled and not self.virtual_camera:
            self.initialize_camera()
        elif not enabled and self.virtual_camera:
            self.virtual_camera.stop()
            self.virtual_camera = None
            
    def cleanup(self):
        """Очистка ресурсов"""
        if self.virtual_camera:
            self.virtual_camera.stop()
            self.virtual_camera = None
            
    def __del__(self):
        """Автоматическая очистка при удалении объекта"""
        self.cleanup()