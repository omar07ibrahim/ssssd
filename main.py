"""
LPR Counter-Surveillance System v2.0
Main application controller
"""

import tkinter as tk
from PIL import ImageTk
from datetime import datetime
from threading import Lock, Event
import sys
import os
import signal
import atexit

# Import all modules
from config import logger, CONFIG, DISPLAY_CONFIG
from database import DatabaseManager
from telegram_notifier import TelegramNotifier
from plate_processor import PlateProcessor
from camera_handler import CameraHandler
from workers import WorkerManager
from gui import LPRMainWindow
from utils import (
    format_duration, 
    create_directory_structure,
    validate_config,
    get_system_info
)

class LPRApplication:
    """Main application controller"""

    def __init__(self, root):
        self.root = root
        self.shutdown_event = Event()
        self.shutdown_in_progress = False

        # Set high process priority for maximum performance
        self._set_process_priority()

        # Initialize components
        print("Initializing LPR Counter-Surveillance System v2.0")
        print(f"System info: {get_system_info()}")
        
        # Create directory structure
        create_directory_structure()
        
        # Validate configuration
        config_errors = validate_config()
        if config_errors:
            logger.warning(f"Configuration warnings: {config_errors}")
        
        # Initialize database
        self.db = DatabaseManager(CONFIG.get('database_path', 'lpr_surveillance.db'))
        
        # Initialize Telegram notifier
        self.telegram = TelegramNotifier()
        
        # Initialize plate processor
        self.processor = PlateProcessor(self.db, self.telegram)
        
        # Initialize camera handler
        self.camera = None
        self.init_camera()
        
        # Initialize worker manager
        self.workers = WorkerManager(self)
        
        # Initialize GUI
        self.gui = LPRMainWindow(root, self)
        
        # State management
        self.is_paused = False
        self.update_requested = False
        self.update_lock = Lock()
        
        # Start workers
        self.workers.start_all_workers()
        
        # Schedule periodic updates
        self.schedule_updates()
        
        # Load existing results from database
        self.root.after(500, lambda: self.update_results())

        # Auto-connect camera if enabled
        if CONFIG.get('auto_connect_camera', False):
            logger.info("⚡ Auto-connect enabled, connecting to camera...")
            self.root.after(1000, self._auto_connect_camera)

        print("Application initialized successfully")

    def _auto_connect_camera(self):
        """Auto-connect to camera on startup"""
        try:
            success = self.connect_camera()
            if success:
                logger.info("✅ Auto-connect successful")
            else:
                logger.warning("⚠ Auto-connect failed")
        except Exception as e:
            logger.error(f"❌ Auto-connect error: {e}")

    def _set_process_priority(self):
        """Set high process priority for maximum performance"""
        try:
            import psutil
            p = psutil.Process()

            if sys.platform == 'win32':
                # Windows: HIGH_PRIORITY_CLASS
                p.nice(psutil.HIGH_PRIORITY_CLASS)
                logger.info("⚡ Process priority set to HIGH (Windows)")
            else:
                # Linux: nice -10
                p.nice(-10)
                logger.info("⚡ Process priority set to -10 (Linux)")

        except ImportError:
            logger.warning("⚠ psutil not installed, cannot set process priority")
        except Exception as e:
            logger.warning(f"⚠ Could not set process priority: {e}")

    def init_camera(self):
        """Initialize camera handler with callbacks"""
        self.camera = CameraHandler(
            frame_callback=self.on_frame_received,
            error_callback=self.on_camera_error,
            plate_callback=self.on_plate_detected
        )
    
    def on_frame_received(self, pil_image):
        """Handle received camera frame"""
        try:
            # Resize for display
            display_size = DISPLAY_CONFIG['video_display_size']
            pil_image.thumbnail(display_size)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(pil_image)
            
            # Update GUI in main thread
            self.root.after_idle(self.gui.update_video_display, photo)
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
    
    def on_camera_error(self, error_code, error_message):
        """Handle camera error"""
        logger.error(f"Camera error {error_code}: {error_message}")
        self.gui.update_status(error_message, "error")
        
        # Show error dialog
        self.root.after(0, lambda: tk.messagebox.showerror("Camera Error", error_message))
    
    def on_plate_detected(self, plate):
        """Handle detected license plate"""
        # Add to processing queue
        if not self.workers.add_plate_to_queue(plate):
            logger.warning("Failed to add plate to processing queue")
    
    def connect_camera(self):
        """Connect to camera"""
        if self.camera.is_connected:
            # Disconnect
            self.camera.disconnect_camera()
            self.gui.set_connection_state(False)
        else:
            # Connect
            success = self.camera.connect_camera()
            self.gui.set_connection_state(success)
    
    def toggle_pause(self):
        """Toggle pause state"""
        self.is_paused = self.camera.toggle_pause()
        self.gui.set_pause_state(self.is_paused)
        
        status = "PAUSED" if self.is_paused else "ACTIVE"
        logger.info(f"System status: {status}")
    
    def search_plates(self, search_term):
        """Search for plates"""
        self.update_results(search_term)
    
    def update_results(self, search_term=""):
        """Update results display"""
        try:
            # Get data from database
            rows = self.db.search_plates(search_term, limit=DISPLAY_CONFIG['max_results_display'])
            
            # Format results for display
            results = []
            for row in rows:
                plate, count, last_ts, first_ts, suspicious, blacklisted, confidence = row
                
                # Calculate duration
                try:
                    first_dt = datetime.fromisoformat(first_ts)
                    last_dt = datetime.fromisoformat(last_ts)
                    duration = last_dt - first_dt
                    duration_str = format_duration(duration.total_seconds())
                except:
                    duration_str = "N/A"
                
                # Format last seen
                try:
                    last_seen = datetime.fromisoformat(last_ts).strftime('%H:%M:%S')
                except:
                    last_seen = "N/A"
                
                # Determine status
                status = []
                if blacklisted:
                    status.append("BLACKLIST")
                if suspicious:
                    status.append("SUSPICIOUS")
                status_str = ", ".join(status) if status else "Normal"
                
                # Format confidence
                confidence_str = f"{confidence:.0f}%" if confidence else "N/A"
                
                results.append((
                    plate, count, last_seen, duration_str, confidence_str, status_str
                ))
            
            # Update GUI
            self.gui.update_results(results)
            
        except Exception as e:
            logger.error(f"Error updating results: {e}")
    
    def update_camera_stats(self, stats):
        """Update camera statistics in GUI"""
        try:
            self.gui.update_statistics(
                stats.get('fps', 0),
                stats.get('frames_processed', 0),
                stats.get('plates_detected', 0),
                stats.get('processing_fps', 0)
            )
            
            # Update status
            status = stats.get('status', 'Unknown')
            if 'Error' in status:
                self.gui.update_status(status, 'error')
            elif 'Connected' in status:
                self.gui.update_status(status, 'success')
            else:
                self.gui.update_status(status, 'normal')
                
        except Exception as e:
            logger.error(f"Error updating camera stats: {e}")
    
    def update_queue_stats(self, queue_sizes):
        """Update queue statistics"""
        total_queue = sum(queue_sizes.values())
        self.gui.update_statistics(
            self.camera.camera_info.get('fps', 0),
            self.camera.camera_info.get('frames_processed', 0),
            self.camera.camera_info.get('plates_detected', 0),
            total_queue
        )
    
    def request_ui_update(self):
        """Request UI update from worker thread"""
        with self.update_lock:
            self.update_requested = True
    
    def schedule_updates(self):
        """Schedule periodic UI updates"""
        # Update results
        if self.update_requested:
            with self.update_lock:
                self.update_requested = False
            self.update_results()
        
        # Schedule next update
        self.root.after(DISPLAY_CONFIG['results_update_interval_ms'], self.schedule_updates)
    
    def add_to_blacklist(self, plate_text, reason, danger_level='MEDIUM', notes=''):
        """Add plate to blacklist"""
        return self.db.add_to_blacklist(plate_text, reason, danger_level, notes)
    
    def remove_from_blacklist(self, plate_text):
        """Remove plate from blacklist"""
        return self.db.remove_from_blacklist(plate_text)
    
    def export_plate_history(self, plate_text):
        """Export history for specific plate"""
        try:
            import csv
            from tkinter import filedialog
            
            # Ask for file location
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title=f"Export History for {plate_text}"
            )
            
            if not file_path:
                return
            
            # Get plate detections
            detections = self.db.get_plate_detections(plate_text, limit=1000)
            
            # Write to CSV
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Timestamp', 'Raw Text', 'Confidence', 'Image Path'])
                
                for detection in detections:
                    writer.writerow(detection)
            
            tk.messagebox.showinfo("Export Complete", f"Exported {len(detections)} detections to {file_path}")
            logger.info(f"Exported plate history for {plate_text} to {file_path}")
            
        except Exception as e:
            tk.messagebox.showerror("Export Error", f"Failed to export: {e}")
            logger.error(f"Export error: {e}")
    
    def apply_settings(self):
        """Apply updated settings"""
        try:
            # Save to database
            self.db.save_settings()
            
            # Update camera parameters
            if self.camera:
                self.camera.update_engine_params()
            
            # Update Telegram state
            self.telegram.set_enabled(CONFIG['telegram_enabled'])
            
            logger.info("Settings applied successfully")
            
        except Exception as e:
            logger.error(f"Error applying settings: {e}")
            raise
    
    def on_closing(self):
        """Handle application closing with proper shutdown sequence"""
        # Prevent double shutdown
        if self.shutdown_in_progress:
            return

        self.shutdown_in_progress = True
        print("\n" + "="*60)
        print("SHUTDOWN SEQUENCE STARTED")
        print("="*60)

        self.shutdown_event.set()

        try:
            # STEP 1: Disconnect camera (stop capturing new frames)
            print("Step 1/5: Stopping camera capture...")
            if hasattr(self, 'camera') and self.camera:
                try:
                    self.camera.disconnect_camera()
                    print("  ✓ Camera disconnected")
                except Exception as e:
                    print(f"  ⚠ Camera disconnect error: {e}")

            # STEP 2: Stop all worker threads (process remaining queue items)
            print("Step 2/5: Stopping worker threads...")
            if hasattr(self, 'workers'):
                try:
                    self.workers.stop_all_workers()
                    print("  ✓ All workers stopped")
                except Exception as e:
                    print(f"  ⚠ Workers stop error: {e}")

            # STEP 3: Cleanup camera resources (virtual cam, telegram stream)
            print("Step 3/5: Cleaning up camera resources...")
            if hasattr(self, 'camera') and self.camera:
                try:
                    self.camera.cleanup()
                    print("  ✓ Camera resources cleaned")
                except Exception as e:
                    print(f"  ⚠ Camera cleanup error: {e}")

            # STEP 4: Close database connection
            print("Step 4/5: Closing database...")
            if hasattr(self, 'db') and self.db:
                try:
                    self.db.close()
                    print("  ✓ Database closed")
                except Exception as e:
                    print(f"  ⚠ Database close error: {e}")

            # STEP 5: Destroy GUI
            print("Step 5/5: Destroying GUI...")
            if hasattr(self, 'root'):
                try:
                    self.root.quit()
                    self.root.destroy()
                    print("  ✓ GUI destroyed")
                except Exception as e:
                    print(f"  ⚠ GUI destroy error: {e}")

            print("="*60)
            print("SHUTDOWN COMPLETE")
            print("="*60)

        except Exception as e:
            print(f"\n⚠⚠⚠ CRITICAL ERROR DURING SHUTDOWN: {e}")
            import traceback
            traceback.print_exc()

            # Force exit if critical error
            print("Forcing exit...")
            import sys
            sys.exit(0)
            


def main():
    """Main entry point"""
    app = None
    root = None
    
    def signal_handler(signum, frame):
        """Handle termination signals"""
        print(f"Received signal {signum}. Shutting down gracefully...")
        if app:
            try:
                app.on_closing()
            except Exception as e:
                print(f"Error during signal shutdown: {e}")
                import traceback
                traceback.print_exc()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create root window
        root = tk.Tk()
        
        # Create application
        app = LPRApplication(root)
        
        # Set close handler
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        
        # Register cleanup on exit
        def cleanup_on_exit():
            if app:
                try:
                    app.on_closing()
                except Exception as e:
                    print(f"Error during exit cleanup: {e}")
                    import traceback
                    traceback.print_exc()
        
        atexit.register(cleanup_on_exit)
        
        # Start main loop
        print("Starting main GUI loop (Press Ctrl+C to exit)")
        root.mainloop()
        
    except KeyboardInterrupt:
        print("Keyboard interrupt received")
        if app:
            try:
                app.on_closing()
            except Exception as e:
                print(f"Error during keyboard interrupt shutdown: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        if app:
            try:
                app.on_closing()
            except Exception as cleanup_e:
                print(f"Error during error cleanup: {cleanup_e}")
        sys.exit(1)
    finally:
        # Additional cleanup in case of any issues
        try:
            if hasattr(root, 'quit'):
                root.quit()
            if hasattr(root, 'destroy'):
                root.destroy()
        except:
            pass

if __name__ == "__main__":
    main()