"""
Camera handling module for LPR Counter-Surveillance System
Manages video capture and frame processing
"""

import time
from threading import Lock, Thread
from PIL import Image, ImageTk
from DTKLPR5 import LPREngine, LPRParams, DTKLPRLibrary, LicensePlate
from DTKVID import VideoCapture, VideoFrame, DTKVIDLibrary
from config import logger, CONFIG, ERROR_MESSAGES, lib_path
from virtual_camera_manager import VirtualCameraManager
from telegram_stream_manager import telegram_stream_manager

class CameraHandler:
    """Manages camera operations and video processing"""
    
    def __init__(self, frame_callback=None, error_callback=None, plate_callback=None):
        self.frame_callback = frame_callback
        self.error_callback = error_callback
        self.plate_callback = plate_callback

        # Camera state
        self.video_capture = None
        self.engine = None
        self.is_connected = False
        self.is_paused = False

        # Frame processing control
        self.display_enabled = True  # Toggle GUI display
        self.display_skip_rate = CONFIG.get('display_skip_rate', 2)  # Every Nth frame for GUI
        self.virtual_camera_skip_rate = CONFIG.get('virtual_camera_skip_rate', 2)  # Every Nth frame for virtual camera
        
        # Statistics
        self.camera_info_lock = Lock()
        self.camera_info = {
            "status": "Disconnected",
            "fps": 0,
            "frames_processed": 0,
            "plates_detected": 0,
            "last_frame_time": time.time(),
            "processing_fps": 0
        }
        
        # Virtual camera
        self.virtual_camera = None
        self.telegram_stream = telegram_stream_manager

        # Initialize LPR engine
        self.initialize_lpr_engine()

    def initialize_lpr_engine(self):
        """Initialize LPR engine with parameters"""
        try:
            # Create DTK library
            dtk_library = DTKLPRLibrary(lib_path)
            
            # Create parameters
            params = LPRParams(dtk_library)
            params.MinPlateWidth = CONFIG['min_plate_width']
            params.MaxPlateWidth = CONFIG['max_plate_width']
            params.Countries = CONFIG['countries']
            params.FormatPlateText = True
            params.RotateAngle = 0
            params.FPSLimit = CONFIG['fps_limit']
            params.DuplicateResultsDelay = CONFIG['duplicate_delay']
            params.ResultConfirmationsCount = CONFIG['confirmation_count']

            # Set NumThreads = CPU cores for maximum performance
            import os
            cpu_cores = os.cpu_count() or 4  # Fallback to 4
            params.NumThreads = cpu_cores
            logger.info(f"⚡ DTK LPR Engine using {cpu_cores} CPU threads")

            params.RecognitionOnMotion = True
            
            # Create engine with callback
            self.engine = LPREngine(params, True, self._license_plate_detected_callback)
            
            # Check license
            if self.engine.IsLicensed() != 0:
                logger.warning("LPR License is invalid or not activated")
                self.update_status("License Invalid", "warning")
            else:
                logger.info("LPR Engine initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize LPR engine: {e}")
            self.engine = None
            raise
    
    def update_engine_params(self):
        """Update LPR engine parameters from config"""
        if not self.engine:
            return
            
        try:
            self.engine.params.MinPlateWidth = CONFIG['min_plate_width']
            self.engine.params.MaxPlateWidth = CONFIG['max_plate_width']
            self.engine.params.Countries = CONFIG['countries']
            self.engine.params.FPSLimit = CONFIG['fps_limit']
            self.engine.params.DuplicateResultsDelay = CONFIG['duplicate_delay']
            self.engine.params.ResultConfirmationsCount = CONFIG['confirmation_count']
            self.engine.params.NumThreads = CONFIG['num_threads']
            
            logger.info("LPR engine parameters updated")
        except Exception as e:
            logger.error(f"Error updating engine parameters: {e}")
    
    def connect_camera(self, device_index=None, width=None, height=None):
        """Connect to camera device"""
        if self.is_connected:
            self.disconnect_camera()
        
        device_index = device_index or CONFIG['camera_index']
        width = width or CONFIG['camera_width']
        height = height or CONFIG['camera_height']
        
        try:
            # Create video capture
            dtk_vid_library = DTKVIDLibrary(lib_path)
            self.video_capture = VideoCapture(
                self._frame_captured_callback,
                self._capture_error_callback,
                self.engine
            )
            
            self.update_status(f"Connecting to camera {device_index}...", "info")
            
            # Start capture
            ret = self.video_capture.StartCaptureFromDevice(device_index, width, height)
            
            if ret == 0:
                self.is_connected = True
                with self.camera_info_lock:
                    self.camera_info['status'] = "Connected"
                    self.camera_info['fps'] = self.video_capture.GetVideoFPS()
                
                self.update_status("Camera connected successfully", "success")
                logger.info(f"Camera {device_index} connected: {width}x{height}")
                
                # Start virtual camera AFTER successful connection
                self._start_virtual_camera(width, height)
                self._maybe_start_telegram_stream()

                return True
            else:
                self.update_status(f"Failed to connect to camera (error code: {ret})", "error")
                logger.error(f"Camera connection failed with code: {ret}")
                return False
                
        except Exception as e:
            self.update_status(f"Camera connection error: {str(e)}", "error")
            logger.error(f"Camera connection error: {e}")
            return False
    
    def connect_file(self, file_path, repeat=0):
        """Connect to video file"""
        if self.is_connected:
            self.disconnect_camera()
        
        try:
            self.video_capture = VideoCapture(
                self._frame_captured_callback,
                self._capture_error_callback,
                self.engine,
                DTKVIDLibrary(lib_path)
            )
            
            self.update_status(f"Opening video file: {file_path}", "info")
            
            ret = self.video_capture.StartCaptureFromFile(file_path, repeat)
            
            if ret == 0:
                self.is_connected = True
                with self.camera_info_lock:
                    self.camera_info['status'] = "File Connected"
                    self.camera_info['fps'] = self.video_capture.GetVideoFPS()
                
                self.update_status("Video file opened successfully", "success")
                logger.info(f"Video file opened: {file_path}")
                return True
            else:
                self.update_status(f"Failed to open video file (error code: {ret})", "error")
                logger.error(f"Video file open failed with code: {ret}")
                return False
                
        except Exception as e:
            self.update_status(f"Video file error: {str(e)}", "error")
            logger.error(f"Video file error: {e}")
            return False
    
    def connect_ip_camera(self, url):
        """Connect to IP camera stream"""
        if self.is_connected:
            self.disconnect_camera()
        
        try:
            # Create video capture
            dtk_vid_library = DTKVIDLibrary(lib_path)
            self.video_capture = VideoCapture(
                self._frame_captured_callback,
                self._capture_error_callback,
                self.engine
            )
            
            self.update_status(f"Connecting to IP camera...", "info")
            
            ret = self.video_capture.StartCaptureFromIPCamera(url)
            
            if ret == 0:
                self.is_connected = True
                with self.camera_info_lock:
                    self.camera_info['status'] = "IP Camera Connected"
                    self.camera_info['fps'] = self.video_capture.GetVideoFPS()
                
                self.update_status("IP camera connected successfully", "success")
                logger.info(f"IP camera connected: {url}")
                return True
            else:
                self.update_status(f"Failed to connect to IP camera (error code: {ret})", "error")
                logger.error(f"IP camera connection failed with code: {ret}")
                return False
                
        except Exception as e:
            self.update_status(f"IP camera error: {str(e)}", "error")
            logger.error(f"IP camera error: {e}")
            return False
    
    def _start_virtual_camera(self, width, height):
        """Start virtual camera when connecting to real camera"""
        try:
            if not self.virtual_camera:
                logger.info(f"Starting virtual camera with resolution {width}x{height}...")
                self.virtual_camera = VirtualCameraManager(
                    width=width,
                    height=height,
                    fps=30
                )
                self.virtual_camera.start()

                if self.virtual_camera.is_initialized:
                    logger.info("✅ Virtual camera started successfully!")
                    logger.info(f"✅ Available as: OBS Virtual Camera ({width}x{height} @ 30fps)")
                else:
                    logger.warning("⚠️ Virtual camera failed to initialize - check if OBS is installed")
                    self.virtual_camera = None
        except Exception as e:
            logger.error(f"❌ Error starting virtual camera: {e}")
            logger.info("Make sure OBS Studio is installed: https://obsproject.com/")
            self.virtual_camera = None

    def _maybe_start_telegram_stream(self):
        """Start Telegram streaming once the virtual camera is ready."""
        if not self.telegram_stream:
            return

        if not getattr(self.telegram_stream, "enabled", True):
            return

        if not self.virtual_camera or not getattr(self.virtual_camera, "is_initialized", False):
            logger.warning("Telegram streaming not started because virtual camera is unavailable")
            return

        try:
            if self.telegram_stream.is_running:
                return

            started = self.telegram_stream.start_stream()
            if started:
                logger.info("Telegram streaming start requested")
        except Exception as e:
            logger.error(f"Failed to start Telegram streaming: {e}")

    def _stop_telegram_stream(self):
        """Stop Telegram streaming if it is running."""
        if not self.telegram_stream:
            return

        try:
            if getattr(self.telegram_stream, "is_running", False):
                self.telegram_stream.stop_stream()
        except Exception as e:
            logger.error(f"Failed to stop Telegram streaming: {e}")

    def disconnect_camera(self):
        """Disconnect from camera"""
        if self.video_capture:
            try:
                self.video_capture.StopCapture()
                logger.info("Camera disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting camera: {e}")
            finally:
                self.video_capture = None
                self.is_connected = False
                with self.camera_info_lock:
                    self.camera_info['status'] = "Disconnected"
                
        # Stop virtual camera
        if self.virtual_camera:
            try:
                self.virtual_camera.stop()
                self.virtual_camera = None
                logger.info("Virtual camera stopped")
            except Exception as e:
                logger.error(f"Error stopping virtual camera: {e}")

        # Stop Telegram stream
        self._stop_telegram_stream()

        self.update_status("Camera disconnected", "info")
    
    def pause(self):
        """Pause processing"""
        self.is_paused = True
        logger.info("Camera processing paused")
        
    def resume(self):
        """Resume processing"""
        self.is_paused = False
        logger.info("Camera processing resumed")
        
    def toggle_pause(self):
        """Toggle pause state"""
        self.is_paused = not self.is_paused
        logger.info(f"Camera processing {'paused' if self.is_paused else 'resumed'}")
        return self.is_paused
    
    def _frame_captured_callback(self, video_capture: VideoCapture, frame: VideoFrame, custom_object):
        """
        Callback for captured frames with optimized processing pipeline:
        1. ALL frames → DTK LPR Engine (100% - NO SKIPPING)
        2. Throttled frames → GUI Display (configurable skip rate)
        3. Throttled frames → Virtual Camera (configurable skip rate)
        """
        if self.is_paused or not frame or frame.GetHeight() <= 0 or frame.GetWidth() <= 0:
            return

        # Update statistics
        with self.camera_info_lock:
            current_time = time.time()
            elapsed = current_time - self.camera_info['last_frame_time']
            self.camera_info['last_frame_time'] = current_time

            if elapsed > 0:
                # Calculate FPS with exponential moving average
                instant_fps = 1 / elapsed
                self.camera_info['fps'] = 0.9 * self.camera_info['fps'] + 0.1 * instant_fps

            self.camera_info['frames_processed'] += 1
            frames_count = self.camera_info['frames_processed']

        # === PRIORITY 1: LPR ENGINE - EVERY FRAME (100%) ===
        if self.engine:
            try:
                ret = self.engine.PutFrame(frame, frame.Timestamp())
                if ret != 0:
                    logger.warning(f"LPR engine returned code: {ret}")
            except Exception as e:
                logger.error(f"LPR engine error: {e}")

        # === PRIORITY 2: GUI DISPLAY - THROTTLED ===
        if self.display_enabled and self.frame_callback:
            if frames_count % self.display_skip_rate == 0:
                self._send_to_gui_display(frame)

        # === PRIORITY 3: VIRTUAL CAMERA - THROTTLED ===
        if self.virtual_camera and self.virtual_camera.is_initialized:
            if frames_count % self.virtual_camera_skip_rate == 0:
                self._send_to_virtual_camera(frame)
    
    def _capture_error_callback(self, video_capture: VideoCapture, error_code: int, custom_object):
        """Callback for capture errors"""
        error_msg = ERROR_MESSAGES.get(error_code, f"Unknown error: {error_code}")
        
        with self.camera_info_lock:
            self.camera_info['status'] = f"Error: {error_msg}"
        
        logger.error(f"Camera error: {error_msg}")
        
        if self.error_callback:
            self.error_callback(error_code, error_msg)
        
        # Handle end of video file
        if error_code == 3:  # End of video file
            self.is_connected = False
    
    def _license_plate_detected_callback(self, engine: LPREngine, plate: LicensePlate):
        """Callback for detected license plates"""
        if self.is_paused:
            return 0

        with self.camera_info_lock:
            self.camera_info['plates_detected'] += 1

        if self.plate_callback:
            try:
                self.plate_callback(plate)
            except Exception as e:
                logger.error(f"Error in plate callback: {e}")

        return 0

    def _send_to_gui_display(self, frame):
        """Send frame to GUI display (called with throttling)"""
        pil_image = None
        try:
            pil_image = frame.GetImage()
            if pil_image and self.frame_callback:
                self.frame_callback(pil_image)
        except Exception as e:
            logger.error(f"GUI display error: {e}")
        finally:
            if pil_image:
                try:
                    pil_image.close()
                except:
                    pass

    def _send_to_virtual_camera(self, frame):
        """Send frame to virtual camera (called with throttling)"""
        pil_image = None
        pil_copy = None
        try:
            pil_image = frame.GetImage()
            if pil_image:
                pil_copy = pil_image.copy()
                self.virtual_camera.send_frame(pil_copy)
        except Exception:
            # Silently ignore errors to avoid spam
            pass
        finally:
            if pil_image:
                try:
                    pil_image.close()
                except:
                    pass
            if pil_copy:
                try:
                    pil_copy.close()
                except:
                    pass

    def toggle_display(self, enabled):
        """Enable/disable GUI display updates"""
        self.display_enabled = enabled
        logger.info(f"GUI display {'enabled' if enabled else 'disabled'}")

    def set_display_skip_rate(self, rate):
        """Set GUI display frame skip rate (1=every frame, 2=every 2nd, etc)"""
        self.display_skip_rate = max(1, rate)
        logger.info(f"Display skip rate set to {self.display_skip_rate}")

    def set_virtual_camera_skip_rate(self, rate):
        """Set virtual camera frame skip rate"""
        self.virtual_camera_skip_rate = max(1, rate)
        logger.info(f"Virtual camera skip rate set to {self.virtual_camera_skip_rate}")

    def get_statistics(self):
        """Get camera statistics"""
        with self.camera_info_lock:
            stats = self.camera_info.copy()
            
            # Add LPR engine statistics if available
            if self.engine:
                try:
                    stats['processing_fps'] = self.engine.GetProcessingFPS()
                    stats['queue_empty'] = self.engine.IsQueueEmpty()
                except:
                    pass
            
            return stats
    
    def get_status(self):
        """Get current camera status"""
        with self.camera_info_lock:
            return self.camera_info['status']
    
    def update_status(self, status, status_type="info"):
        """Update camera status"""
        with self.camera_info_lock:
            self.camera_info['status'] = status
        
        # Log based on type
        if status_type == "error":
            logger.error(status)
        elif status_type == "warning":
            logger.warning(status)
        else:
            logger.info(status)
    
    def reset_statistics(self):
        """Reset camera statistics"""
        with self.camera_info_lock:
            self.camera_info['frames_processed'] = 0
            self.camera_info['plates_detected'] = 0
            self.camera_info['fps'] = 0
            self.camera_info['processing_fps'] = 0
        logger.info("Camera statistics reset")
    
    def capture_snapshot(self, filepath=None):
        """Capture current frame as snapshot"""
        # TODO: Implement snapshot capture
        pass
    
    def start_recording(self, filepath):
        """Start recording video"""
        # TODO: Implement video recording
        pass
    
    def stop_recording(self):
        """Stop recording video"""
        # TODO: Implement stop recording
        pass
    
    def set_resolution(self, width, height):
        """Change camera resolution"""
        if self.is_connected:
            # Reconnect with new resolution
            device_index = CONFIG['camera_index']
            self.disconnect_camera()
            return self.connect_camera(device_index, width, height)
        else:
            # Just update config
            CONFIG['camera_width'] = width
            CONFIG['camera_height'] = height
            return True
    
    def cleanup(self):
        """Cleanup resources"""
        if self.is_connected:
            self.disconnect_camera()
        
        # Stop virtual camera
        if self.virtual_camera:
            try:
                self.virtual_camera.stop()
                self.virtual_camera = None
                logger.info("Virtual camera stopped in cleanup")
            except Exception as e:
                logger.error(f"Error stopping virtual camera in cleanup: {e}")

        # Ensure Telegram stream is stopped
        self._stop_telegram_stream()
        
        if self.engine:
            try:
                # Properly delete the engine to free up resources
                self.engine = None
            except:
                pass
        
        logger.info("Camera handler cleaned up")
