"""
Background workers module for LPR Counter-Surveillance System
Manages all background threads and asynchronous operations
"""

import time
from queue import Queue, Empty
from threading import Thread, Event, Lock
from datetime import datetime
from config import logger, CONFIG, QUEUE_SIZES

class WorkerManager:
    """Manages all background worker threads"""
    
    def __init__(self, app_controller):
        self.app = app_controller
        self.stop_flag = Event()
        self.workers = []
        
        # Initialize queues
        self.plate_queue = Queue(maxsize=QUEUE_SIZES['plate_queue'])
        self.telegram_queue = Queue(maxsize=QUEUE_SIZES['telegram_queue'])
        self.db_queue = Queue(maxsize=QUEUE_SIZES['db_queue'])
        self.image_queue = Queue(maxsize=QUEUE_SIZES['image_queue'])
        
        # Worker statistics
        self.stats_lock = Lock()
        self.worker_stats = {
            'plates_processed': 0,
            'telegram_sent': 0,
            'db_operations': 0,
            'images_saved': 0,
            'errors': 0
        }
    
    def start_all_workers(self):
        """Start all worker threads"""
        workers_config = [
            ('PlateWorker', self.plate_worker, 1),
            ('TelegramWorker', self.telegram_worker, 1),
            ('DatabaseWorker', self.database_worker, 1),
            ('ImageWorker', self.image_worker, 1),
            ('UIUpdateWorker', self.ui_update_worker, 1),
            ('CleanupWorker', self.cleanup_worker, 1),
            ('StatisticsWorker', self.statistics_worker, 1)
        ]
        
        for name, worker_func, count in workers_config:
            for i in range(count):
                thread_name = f"{name}-{i}" if count > 1 else name
                thread = Thread(target=worker_func, name=thread_name, daemon=True)
                thread.start()
                self.workers.append(thread)
                logger.info(f"Started worker thread: {thread_name}")
        
        logger.info(f"Started {len(self.workers)} worker threads")
    
    def stop_all_workers(self):
        """Stop all worker threads"""
        logger.info("Stopping all worker threads...")
        self.stop_flag.set()
        
        # Clear queues to unblock workers that might be waiting
        try:
            while True:
                self.plate_queue.get_nowait()
        except Empty:
            pass

        try:
            while True:
                self.telegram_queue.get_nowait()
        except Empty:
            pass

        try:
            while True:
                self.db_queue.get_nowait()
        except Empty:
            pass

        try:
            while True:
                self.image_queue.get_nowait()
        except Empty:
            pass
        
        # Wait for threads to finish (with timeout)
        for thread in self.workers:
            thread.join(timeout=8)  # Увеличенный таймаут
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")
        
        logger.info("All worker threads stopped")
    
    def plate_worker(self):
        """Process detected license plates"""
        logger.info("Plate worker started")
        
        while not self.stop_flag.is_set():
            try:
                plate = self.plate_queue.get(timeout=0.5)
                
                # Process the plate
                canonical = self.app.processor.process_plate(plate)
                
                if canonical:
                    with self.stats_lock:
                        self.worker_stats['plates_processed'] += 1
                    
                    # Trigger UI update
                    self.app.request_ui_update()
                    
                    logger.debug(f"Processed plate: {canonical}")
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Plate worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Plate worker stopped")
    
    def telegram_worker(self):
        """Send Telegram notifications"""
        logger.info("Telegram worker started")
        
        while not self.stop_flag.is_set():
            try:
                item = self.telegram_queue.get(timeout=0.5)
                
                if not item:
                    continue
                
                message_type = item[0]
                
                if message_type == 'message':
                    text = item[1]
                    plate = item[2] if len(item) > 2 else None
                    priority = item[3] if len(item) > 3 else 'normal'
                    
                    self.app.telegram.send_message(text, plate, priority)
                    
                elif message_type == 'photo':
                    photo_path = item[1]
                    caption = item[2] if len(item) > 2 else ""
                    priority = item[3] if len(item) > 3 else 'normal'
                    
                    self.app.telegram.send_photo(
                        photo_path=photo_path,
                        caption=caption,
                        priority=priority
                    )
                
                elif message_type == 'alert':
                    alert_type = item[1]
                    data = item[2]
                    
                    if alert_type == 'blacklist':
                        self.app.telegram.send_blacklist_alert(**data)
                    elif alert_type == 'suspicious':
                        self.app.telegram.send_suspicious_alert(**data)
                
                with self.stats_lock:
                    self.worker_stats['telegram_sent'] += 1
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Telegram worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Telegram worker stopped")
    
    def database_worker(self):
        """Handle database operations"""
        logger.info("Database worker started")
        
        while not self.stop_flag.is_set():
            try:
                operation = self.db_queue.get(timeout=0.5)
                
                if not operation:
                    continue
                
                op_type = operation[0]
                
                if op_type == 'update_image_path':
                    canonical_text, image_path = operation[1], operation[2]
                    # Update image path in database
                    # This is now handled in plate_processor
                    pass
                
                elif op_type == 'save_settings':
                    self.app.db.save_settings()
                
                elif op_type == 'cleanup':
                    days_to_keep = operation[1] if len(operation) > 1 else 30
                    self.app.db.cleanup_old_data(days_to_keep)
                
                with self.stats_lock:
                    self.worker_stats['db_operations'] += 1
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Database worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Database worker stopped")
    
    def image_worker(self):
        """Handle image saving operations"""
        logger.info("Image worker started")
        
        while not self.stop_flag.is_set():
            try:
                image_data = self.image_queue.get(timeout=0.5)
                
                if not image_data:
                    continue
                
                # Image saving is now handled in plate_processor
                # This worker can be used for additional image processing
                
                with self.stats_lock:
                    self.worker_stats['images_saved'] += 1
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Image worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Image worker stopped")
    
    def ui_update_worker(self):
        """Periodically update UI elements"""
        logger.info("UI update worker started")
        last_update = time.time()
        update_interval = 1.0  # Update every second
        
        while not self.stop_flag.is_set():
            try:
                current_time = time.time()
                
                if current_time - last_update >= update_interval:
                    # Update camera statistics
                    if self.app.camera:
                        stats = self.app.camera.get_statistics()
                        self.app.update_camera_stats(stats)
                    
                    # Update queue sizes
                    queue_sizes = {
                        'plate': self.plate_queue.qsize(),
                        'telegram': self.telegram_queue.qsize(),
                        'db': self.db_queue.qsize(),
                        'image': self.image_queue.qsize()
                    }
                    self.app.update_queue_stats(queue_sizes)
                    
                    last_update = current_time
                
                time.sleep(0.1)  # Small sleep to prevent CPU spinning
                
            except Exception as e:
                logger.error(f"UI update worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("UI update worker stopped")
    
    def cleanup_worker(self):
        """Periodic cleanup tasks with garbage collection"""
        logger.info("Cleanup worker started")
        last_cleanup = time.time()
        last_gc = time.time()
        cleanup_interval = 3600  # Run every hour
        gc_interval = 300  # GC every 5 minutes

        while not self.stop_flag.is_set():
            try:
                current_time = time.time()

                # === GARBAGE COLLECTION (every 5 minutes) ===
                if current_time - last_gc >= gc_interval:
                    import gc
                    collected = gc.collect()
                    logger.debug(f"⚡ GC: collected {collected} objects")
                    last_gc = current_time

                # === FULL CLEANUP (every hour) ===
                if current_time - last_cleanup >= cleanup_interval:
                    # Clean old detection images
                    from utils import cleanup_old_files
                    deleted = cleanup_old_files(
                        'detections',
                        days_to_keep=CONFIG.get('image_retention_days', 30),
                        extensions=['.jpg', '.jpeg', '.png']
                    )

                    if deleted > 0:
                        logger.info(f"Cleanup: Deleted {deleted} old image files")

                    # Clean old database records
                    self.db_queue.put(('cleanup', 30))

                    # Clear plate processor cache
                    if self.app.processor:
                        self.app.processor.clear_cache()

                    # Full garbage collection after cleanup
                    import gc
                    gc.collect()
                    logger.info("⚡ Full GC completed after cleanup")

                    last_cleanup = current_time

                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Cleanup worker stopped")
    
    def statistics_worker(self):
        """Calculate and report statistics"""
        logger.info("Statistics worker started")
        last_report = time.time()
        report_interval = 300  # Report every 5 minutes
        
        while not self.stop_flag.is_set():
            try:
                current_time = time.time()
                
                if current_time - last_report >= report_interval:
                    with self.stats_lock:
                        stats = self.worker_stats.copy()
                    
                    # Log statistics
                    logger.info(f"Worker statistics: {stats}")
                    
                    # Send daily report at midnight
                    now = datetime.now()
                    if now.hour == 0 and now.minute < 5:
                        daily_stats = self.app.db.get_statistics()
                        if daily_stats:
                            self.telegram_queue.put((
                                'message',
                                self._format_daily_report(daily_stats),
                                None,
                                'low'
                            ))
                    
                    last_report = current_time
                
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Statistics worker error: {e}")
                with self.stats_lock:
                    self.worker_stats['errors'] += 1
        
        logger.info("Statistics worker stopped")
    
    def _format_daily_report(self, stats):
        """Format daily statistics report"""
        report = f"📊 Daily Report - {stats['date']}\n"
        report += "=" * 30 + "\n"
        report += f"Total Detections: {stats['total_detections']}\n"
        report += f"Unique Plates: {stats['unique_plates']}\n"
        report += f"Suspicious Events: {stats['suspicious_events']}\n"
        report += f"Blacklist Hits: {stats['blacklist_hits']}\n"
        return report
    
    def add_plate_to_queue(self, plate):
        """Add plate to processing queue"""
        try:
            self.plate_queue.put_nowait(plate)
            return True
        except:
            logger.warning("Plate queue is full")
            return False
    
    def add_telegram_message(self, message_type, *args):
        """Add message to Telegram queue"""
        try:
            self.telegram_queue.put_nowait((message_type, *args))
            return True
        except:
            logger.warning("Telegram queue is full")
            return False
    
    def add_db_operation(self, operation_type, *args):
        """Add operation to database queue"""
        try:
            self.db_queue.put_nowait((operation_type, *args))
            return True
        except:
            logger.warning("Database queue is full")
            return False
    
    def add_image_to_queue(self, image_data):
        """Add image to processing queue"""
        try:
            self.image_queue.put_nowait(image_data)
            return True
        except:
            logger.warning("Image queue is full")
            return False
    
    def get_queue_sizes(self):
        """Get current queue sizes"""
        return {
            'plate': self.plate_queue.qsize(),
            'telegram': self.telegram_queue.qsize(),
            'db': self.db_queue.qsize(),
            'image': self.image_queue.qsize()
        }
    
    def get_worker_stats(self):
        """Get worker statistics"""
        with self.stats_lock:
            return self.worker_stats.copy()
    
    def reset_statistics(self):
        """Reset worker statistics"""
        with self.stats_lock:
            for key in self.worker_stats:
                self.worker_stats[key] = 0
        logger.info("Worker statistics reset")
    
    def is_running(self):
        """Check if workers are running"""
        return not self.stop_flag.is_set() and any(t.is_alive() for t in self.workers)