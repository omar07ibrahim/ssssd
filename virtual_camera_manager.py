import threading
import queue
import numpy as np
from PIL import Image
import pyvirtualcam
import time
import cv2


class VirtualCameraManager:
    def __init__(self, width=1280, height=720, fps=30, camera_name="10dirham Virtual Camera"):
        """
        Инициализация менеджера виртуальной камеры
        
        Args:
            width: ширина видео
            height: высота видео
            fps: частота кадров
            camera_name: имя виртуальной камеры
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.camera_name = camera_name
        
        self.virtual_cam = None
        self.frame_queue = queue.Queue(maxsize=30)
        self.is_running = False
        self.thread = None
        
        # Флаг для обозначения что камера инициализирована
        self.is_initialized = False
        
    def start(self):
        """Запуск виртуальной камеры"""
        if self.is_running:
            print("Виртуальная камера уже запущена")
            return
            
        try:
            # Для Windows используем OBS Virtual Camera backend
            self.virtual_cam = pyvirtualcam.Camera(
                width=self.width, 
                height=self.height, 
                fps=self.fps,
                backend='obs'  # OBS Virtual Camera для Windows
            )
            
            print(f'Виртуальная камера запущена: {self.virtual_cam.device}')
            print(f'Разрешение: {self.width}x{self.height}, FPS: {self.fps}')
            
            self.is_running = True
            self.is_initialized = True
            
            # Запуск потока для обработки кадров
            self.thread = threading.Thread(target=self._process_frames)
            self.thread.daemon = True
            self.thread.start()
            
        except Exception as e:
            print(f"Ошибка при запуске виртуальной камеры: {e}")
            print("Убедитесь, что OBS Virtual Camera установлена!")
            print("Скачать можно с: https://obsproject.com/forum/resources/obs-virtualcam.539/")
            self.is_initialized = False
            
    def stop(self):
        """Остановка виртуальной камеры"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        # Очищаем очередь кадров
        self.cleanup_queue()
        
        # Ждем завершения потока
        if self.thread:
            self.thread.join(timeout=3)  # Увеличенный таймаут
            
        # Закрываем виртуальную камеру
        if self.virtual_cam:
            try:
                self.virtual_cam.close()
            except Exception as e:
                print(f"Error closing virtual camera: {e}")
            self.virtual_cam = None
            
        self.is_initialized = False
        print("Виртуальная камера остановлена")
        
    def send_frame(self, pil_image):
        """
        Отправка кадра в виртуальную камеру
        
        Args:
            pil_image: PIL Image объект или numpy array
        """
        if not self.is_initialized:
            return
            
        try:
            # Проверяем тип входных данных
            if isinstance(pil_image, np.ndarray):
                # Если это уже numpy array
                frame = pil_image
                
                # Проверяем формат
                if len(frame.shape) == 2:  # Grayscale
                    frame = np.stack([frame] * 3, axis=-1)
                elif frame.shape[2] == 4:  # RGBA
                    frame = frame[:, :, :3]
                    
                # Изменяем размер если нужно
                if frame.shape[:2] != (self.height, self.width):
                    import cv2
                    frame = cv2.resize(frame, (self.width, self.height))
                    
            else:
                # Это PIL Image
                # Изменяем размер если необходимо
                if pil_image.size != (self.width, self.height):
                    pil_image = pil_image.resize((self.width, self.height), Image.LANCZOS)
                
                # Конвертируем в RGB если необходимо
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                
                # Конвертируем в numpy array
                frame = np.array(pil_image)
            
            # Убеждаемся что формат правильный (uint8)
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)
                
            # Добавляем кадр в очередь (если очередь полная, удаляем старый кадр)
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
                    
            self.frame_queue.put(frame)
            
        except Exception as e:
            print(f"Ошибка при отправке кадра: {e}")
            import traceback
            traceback.print_exc()
            
    def _process_frames(self):
        """Поток для обработки и отправки кадров в виртуальную камеру"""
        last_frame = None
        frame_interval = 1.0 / self.fps
        last_frame_time = time.time()
        
        while self.is_running:
            try:
                # Пытаемся получить новый кадр из очереди
                try:
                    frame = self.frame_queue.get(timeout=0.1)
                    last_frame = frame
                except queue.Empty:
                    frame = last_frame
                    
                # Если есть кадр, отправляем его
                if frame is not None and self.virtual_cam:
                    # Контролируем FPS
                    current_time = time.time()
                    elapsed = current_time - last_frame_time
                    
                    if elapsed < frame_interval:
                        time.sleep(frame_interval - elapsed)
                        
                    # Отправляем кадр в виртуальную камеру
                    self.virtual_cam.send(frame)
                    last_frame_time = time.time()
                    
                else:
                    # Если нет кадров, создаем черный кадр
                    if self.virtual_cam:
                        black_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                        self.virtual_cam.send(black_frame)
                    time.sleep(frame_interval)
                    
            except Exception as e:
                print(f"Ошибка в потоке обработки кадров: {e}")
                time.sleep(0.1)
                
    def __del__(self):
        """Деструктор для корректного закрытия камеры"""
        self.stop()
        
    def cleanup_queue(self):
        """Clear all frames from queue to free memory"""
        try:
            while True:
                self.frame_queue.get_nowait()
        except queue.Empty:
            pass


# Модифицированный callback для интеграции с вашим кодом
class CameraWithVirtualOutput:
    def __init__(self):
        self.virtual_camera = VirtualCameraManager(width=1280, height=720, fps=30)
        self.engine = None
        self.frame_callback = None
        self.camera_info = {'frames_processed': 0}
        
        # Запускаем виртуальную камеру
        self.virtual_camera.start()
        
    def _frame_captured_callback(self, video_capture, frame, custom_object):
        # Увеличиваем счетчик кадров
        self.camera_info['frames_processed'] += 1
        
        # Кадр отправляется в LPR engine для распознавания
        if self.engine:
            ret = self.engine.PutFrame(frame, frame.Timestamp())
        
        # Тот же кадр отправляется на превью (с прореживанием)
        if self.frame_callback and self.camera_info['frames_processed'] % 2 == 0:
            pil_image = frame.GetImage()
            
            # Отправляем кадр в оригинальный callback
            self.frame_callback(pil_image)
            
            # Создаем копию и отправляем в виртуальную камеру
            pil_image_copy = pil_image.copy()
            self.virtual_camera.send_frame(pil_image_copy)
            
    def stop(self):
        """Остановка камеры и виртуального вывода"""
        if self.virtual_camera:
            self.virtual_camera.stop()