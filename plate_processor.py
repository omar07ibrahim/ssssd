"""
Plate processing module for LPR Counter-Surveillance System
Handles plate recognition, validation, and processing logic
"""

import re
from datetime import datetime, timedelta
from threading import Lock
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from DTKLPR5 import LicensePlate
from config import logger, CONFIG, IMAGE_CONFIG
from utils import preprocess_image
from improved_levenshtein import (
    improved_levenshtein, 
    normalize_plate, 
    calculate_similarity_score,
    get_adaptive_threshold,
    find_best_match
)

class PlateProcessor:
    """Processes detected license plates with validation and consolidation"""
    
    def __init__(self, db_manager, telegram_notifier):
        self.db = db_manager
        self.telegram = telegram_notifier
        self.processing_lock = Lock()
        self.recent_plates = {}  # Cache for recent plate detections
        self.cache_timeout = 300  # 5 minutes cache timeout
        self.suspicious_alert_times = {}  # Track last suspicious alert time per plate
        self.suspicious_alert_interval = 10  # Minimum 10 seconds between suspicious alerts
        
    def process_plate(self, plate: LicensePlate):
        """
        Process detected plate with validation and Levenshtein consolidation

        Args:
            plate: LicensePlate object from detection

        Returns:
            Canonical plate text if processed successfully, None otherwise
        """
        with self.processing_lock:
            try:
                # Extract and normalize plate data
                plate_data = self._extract_plate_data(plate)

                if not plate_data:
                    return None

                # Validate plate
                if not self._validate_plate(plate_data):
                    return None

                # Find or create canonical plate
                canonical_text = self._find_or_create_canonical(plate_data)

                # Save image if enabled
                image_path = None
                if CONFIG['save_images']:
                    image_path = self._save_plate_image(plate, plate_data['timestamp'], canonical_text)

                # Update database
                self._update_database(canonical_text, plate_data, image_path)

                # Check for alerts
                self._check_alerts(canonical_text, plate_data['timestamp'], image_path)

                # Update cache
                self._update_cache(canonical_text, plate_data)

                return canonical_text

            except Exception as e:
                logger.error(f"Plate processing error: {e}")
                return None
            finally:
                # CRITICAL: Explicitly destroy DTK LicensePlate object to free resources
                if plate:
                    try:
                        plate.destroy()
                    except Exception as e:
                        logger.debug(f"Error destroying plate object: {e}")
    
    def _extract_plate_data(self, plate: LicensePlate):
        """Extract and normalize data from plate object"""
        try:
            plate_text = plate.Text().upper().replace(' ', '')
            confidence = plate.Confidence()
            timestamp = datetime.now()
            country_code = plate.CountryCode()
            
            return {
                'text': plate_text,
                'raw_text': plate.Text(),
                'confidence': confidence,
                'timestamp': timestamp,
                'country_code': country_code,
                'plate_object': plate
            }
        except Exception as e:
            logger.error(f"Error extracting plate data: {e}")
            return None
    
    def _validate_plate(self, plate_data):
        """Validate plate detection based on configured criteria"""
        try:
            # УБРАЛ ВСЮ ВАЛИДАЦИЮ - ПРИНИМАЕМ ВСЕ НОМЕРА
            # Просто проверяем что есть текст
            text = plate_data['text']
            if not text or len(text) == 0:
                return False
            
            # Логируем все номера для отладки
            confidence = plate_data['confidence']
            logger.info(f"Plate detected: {text} (confidence: {confidence}%)")
            
            return True
            
        except Exception as e:
            logger.error(f"Plate validation error: {e}")
            return False
    
    def _validate_country_format(self, plate_text, country_code):
        """Validate plate format based on country-specific rules"""
        # ОТКЛЮЧЕНА ВАЛИДАЦИЯ ПО СТРАНАМ - ПРИНИМАЕМ ВСЕ ФОРМАТЫ
        return True
    
    def _find_or_create_canonical(self, plate_data):
        """Find existing canonical plate or create new one using improved Levenshtein"""
        plate_text = plate_data['text']
        
        # Get all canonical plates from database
        canonical_plates = self.db.get_canonical_plates()
        
        if not canonical_plates:
            # No existing plates, create new canonical
            self.db.create_canonical_plate(
                plate_text,
                plate_data['country_code'],
                plate_data['confidence'],
                plate_data['timestamp']
            )
            logger.info(f"Created first canonical plate: {plate_text}")
            return plate_text
        
        # Use adaptive threshold based on plate length
        normalized_length = len(normalize_plate(plate_text))
        threshold = get_adaptive_threshold(normalized_length)
        
        # Find best match using improved algorithm
        best_match, similarity_score = find_best_match(
            plate_text, 
            canonical_plates, 
            threshold
        )
        
        if best_match:
            logger.info(f"Matched plate {plate_text} to canonical {best_match} (similarity: {similarity_score:.1f}%)")
            return best_match
        else:
            # No good match found, create new canonical plate
            self.db.create_canonical_plate(
                plate_text,
                plate_data['country_code'],
                plate_data['confidence'],
                plate_data['timestamp']
            )
            logger.info(f"Created new canonical plate: {plate_text} (no match above {threshold}% threshold)")
            return plate_text
    
    def _update_database(self, canonical_text, plate_data, image_path):
        """Update database with detection information"""
        try:
            # Update canonical plate record
            self.db.update_canonical_plate(
                canonical_text,
                plate_data['confidence'],
                plate_data['timestamp'],
                image_path
            )
            
            # Add original detection record
            self.db.add_plate_detection(
                canonical_text,
                plate_data['raw_text'],
                plate_data['confidence'],
                plate_data['timestamp'],
                image_path
            )
            
            # Check and update suspicious presence
            plate_info = self.db.get_plate_info(canonical_text)
            if plate_info:
                first_appearance = datetime.fromisoformat(plate_info[1])
                duration = plate_data['timestamp'] - first_appearance
                
                if duration > timedelta(minutes=CONFIG['suspicious_duration_minutes']):
                    self.db.check_suspicious_presence(
                        canonical_text,
                        first_appearance,
                        plate_data['timestamp']
                    )
            
        except Exception as e:
            logger.error(f"Database update error: {e}")
    
    def _check_alerts(self, canonical_text, timestamp, image_path):
        """Check and send alerts for blacklist and suspicious presence"""
        try:
            # === FUZZY BLACKLIST CHECK ===
            threshold = CONFIG.get('blacklist_similarity_threshold', 80)
            fuzzy_match = self.db.check_blacklist_fuzzy(canonical_text, threshold)

            if fuzzy_match:
                matched_plate, reason, danger_level, similarity = fuzzy_match

                # Log the match
                logger.warning(
                    f"🚨 BLACKLIST MATCH: {canonical_text} → {matched_plate} "
                    f"(similarity: {similarity:.1f}%)"
                )

                # Send alert (NO rate limiting for blacklist)
                self._send_blacklist_alert(
                    canonical_text,
                    matched_plate,
                    reason,
                    danger_level,
                    similarity,
                    timestamp,
                    image_path
                )

                # Log to database
                self.db.log_blacklist_detection(
                    canonical_text,
                    matched_plate,
                    similarity,
                    timestamp
                )
            
            # Check suspicious presence
            plate_info = self.db.get_plate_info(canonical_text)
            if plate_info:
                first_appearance = datetime.fromisoformat(plate_info[1])
                is_suspicious = plate_info[6]
                duration = timestamp - first_appearance
                duration_minutes = int(duration.total_seconds() / 60)

                threshold_minutes = CONFIG['suspicious_duration_minutes']

                # Send alert if suspicious (with rate limiting)
                if duration_minutes > threshold_minutes:
                    # Check if enough time passed since last alert (10 seconds)
                    should_send = self._should_send_suspicious_alert(canonical_text, timestamp)

                    if should_send:
                        self.telegram.send_suspicious_alert(
                            canonical_text,
                            duration_minutes,
                            first_appearance,
                            timestamp,
                            image_path
                        )
                        logger.warning(f"⚠️ Suspicious presence alert sent for plate: {canonical_text}")

                        # Update last alert time
                        self._update_suspicious_alert_time(canonical_text, timestamp)

                    # Mark as suspicious if not already marked
                    if not is_suspicious:
                        self.db.mark_as_suspicious(canonical_text)
                    
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")

    def _send_blacklist_alert(self, detected_plate, matched_plate, reason,
                             danger_level, similarity, timestamp, image_path):
        """
        Send blacklist alert to Telegram (NO rate limiting)
        """
        try:
            alert_msg = self._format_fuzzy_blacklist_alert(
                detected_plate,
                matched_plate,
                reason,
                danger_level,
                similarity,
                timestamp
            )

            # Priority based on danger level
            priority_map = {
                'CRITICAL': 'critical',
                'HIGH': 'high',
                'MEDIUM': 'normal',
                'LOW': 'low'
            }
            priority = priority_map.get(danger_level, 'critical')

            # Send to Telegram (will use no-limit method)
            self.telegram.send_blacklist_alert_no_limit(
                alert_msg,
                image_path,
                priority
            )

        except Exception as e:
            logger.error(f"Error sending blacklist alert: {e}")

    def _format_fuzzy_blacklist_alert(self, detected, matched, reason,
                                      danger_level, similarity, timestamp):
        """Format fuzzy match blacklist alert message"""
        emoji_map = {
            'CRITICAL': '🔴',
            'HIGH': '🟠',
            'MEDIUM': '🟡',
            'LOW': '🔵'
        }

        emoji = emoji_map.get(danger_level, '⚪')

        msg = f"🚨 <b>BLACKLIST ALERT</b> 🚨\n\n"
        msg += f"Detected: <b>{detected}</b>\n"

        if detected != matched:
            msg += f"Matched: <b>{matched}</b>\n"
            msg += f"Similarity: <b>{similarity:.1f}%</b>\n"

        msg += f"Danger Level: {emoji} <b>{danger_level}</b>\n"
        msg += f"Reason: {reason}\n"
        msg += f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += f"\n⚡ <b>IMMEDIATE ACTION REQUIRED!</b>"

        return msg

    def _should_send_suspicious_alert(self, plate_text, current_time):
        """
        Check if enough time passed since last suspicious alert (10 seconds)

        Args:
            plate_text: Plate number
            current_time: Current timestamp

        Returns:
            True if should send alert, False otherwise
        """
        if plate_text not in self.suspicious_alert_times:
            return True

        last_alert_time = self.suspicious_alert_times[plate_text]
        time_diff = (current_time - last_alert_time).total_seconds()

        return time_diff >= self.suspicious_alert_interval

    def _update_suspicious_alert_time(self, plate_text, timestamp):
        """Update last alert time for suspicious plate"""
        self.suspicious_alert_times[plate_text] = timestamp

    def _save_plate_image(self, plate: LicensePlate, timestamp, canonical_text):
        """Save plate detection image with annotations"""
        frame_image_original = None
        frame_image_processed = None
        plate_image = None

        try:
            # Create directory structure
            date_dir = timestamp.strftime(IMAGE_CONFIG['date_format'])
            safe_text = self._sanitize_filename(canonical_text)
            save_dir = Path(IMAGE_CONFIG['detection_dir']) / date_dir / safe_text
            save_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename
            filename = f"{timestamp.strftime(IMAGE_CONFIG['time_format'])}.jpg"
            filepath = save_dir / filename

            # Get original frame image
            frame_image_original = plate.GetImage()
            if frame_image_original is None:
                logger.error("Failed to get frame image from plate")
                return None

            # Apply preprocessing (returns NEW image)
            frame_image_processed = preprocess_image(frame_image_original)

            # Close original since we have processed version
            if frame_image_processed is not frame_image_original:
                frame_image_original.close()
                frame_image_original = None

            # Annotate image (modifies in-place, no new image)
            frame_image_processed = self._annotate_image(frame_image_processed, plate)

            # Save full frame image
            frame_image_processed.save(
                str(filepath),
                'JPEG',
                quality=CONFIG.get('image_quality', 95)
            )

            # Save cropped plate image
            plate_image = plate.GetPlateImage()
            if plate_image:
                plate_filepath = save_dir / f"plate_{filename}"
                plate_image.save(
                    str(plate_filepath),
                    'JPEG',
                    quality=CONFIG.get('image_quality', 95)
                )

            logger.debug(f"Saved images for plate {canonical_text} to {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save plate image: {e}")
            return None
        finally:
            # Ensure ALL images are closed to free memory
            if frame_image_original:
                try:
                    frame_image_original.close()
                except:
                    pass
            if frame_image_processed:
                try:
                    frame_image_processed.close()
                except:
                    pass
            if plate_image:
                try:
                    plate_image.close()
                except:
                    pass
    
    def _annotate_image(self, image, plate):
        """Add bounding box and text annotations to image"""
        try:
            draw = ImageDraw.Draw(image)
            
            # Try to load font
            try:
                font = ImageFont.truetype("arial.ttf", 20)
                small_font = ImageFont.truetype("arial.ttf", 14)
            except Exception:
                font = ImageFont.load_default()
                small_font = font
            
            # Draw bounding box
            box_color = "red" if plate.Confidence() < 80 else "green"
            draw.rectangle(
                [(plate.X(), plate.Y()),
                 (plate.X() + plate.Width(), plate.Y() + plate.Height())],
                outline=box_color,
                width=3
            )
            
            # Add text label
            label = f"{plate.Text()} ({plate.Confidence()}%)"
            label_y = max(0, plate.Y() - 25)
            
            # Add background for text
            bbox = draw.textbbox((plate.X(), label_y), label, font=font)
            draw.rectangle(bbox, fill=box_color)
            draw.text(
                (plate.X(), label_y),
                label,
                fill="white",
                font=font
            )
            
            # Add timestamp
            timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            draw.text(
                (10, 10),
                timestamp_text,
                fill="yellow",
                font=small_font,
                stroke_width=1,
                stroke_fill="black"
            )
            
            # Add country code if available
            country = plate.CountryCode()
            if country:
                draw.text(
                    (10, 30),
                    f"Country: {country}",
                    fill="yellow",
                    font=small_font,
                    stroke_width=1,
                    stroke_fill="black"
                )
            
            return image
            
        except Exception as e:
            logger.error(f"Error annotating image: {e}")
            return image
    
    def _sanitize_filename(self, text):
        """Sanitize text for use in filename"""
        # Remove invalid characters
        safe_text = re.sub(r'[<>:"/\\|?*]', '_', text)
        # Limit length
        max_length = IMAGE_CONFIG.get('max_filename_length', 50)
        return safe_text[:max_length]
    
    def _update_cache(self, canonical_text, plate_data):
        """Update recent plates cache"""
        try:
            current_time = datetime.now()
            
            # Clean old entries
            old_plates = [
                plate for plate, data in self.recent_plates.items()
                if (current_time - data['timestamp']).total_seconds() > self.cache_timeout
            ]
            
            for plate in old_plates:
                del self.recent_plates[plate]
            
            # Add/update current plate
            self.recent_plates[canonical_text] = {
                'timestamp': current_time,
                'confidence': plate_data['confidence'],
                'country': plate_data['country_code']
            }
            
        except Exception as e:
            logger.error(f"Cache update error: {e}")
    
    def get_recent_plates(self):
        """Get list of recently detected plates from cache"""
        return list(self.recent_plates.keys())
    
    def clear_cache(self):
        """Clear the recent plates cache and old suspicious alert times"""
        self.recent_plates.clear()

        # Clean old suspicious alert times (older than 1 hour)
        current_time = datetime.now()
        old_plates = []
        for plate_text, last_time in self.suspicious_alert_times.items():
            if (current_time - last_time).total_seconds() > 3600:  # 1 hour
                old_plates.append(plate_text)

        for plate in old_plates:
            del self.suspicious_alert_times[plate]

        logger.info(f"Plate cache cleared, removed {len(old_plates)} old suspicious alert times")
    
    def process_batch(self, plates):
        """Process multiple plates in batch"""
        results = []
        for plate in plates:
            result = self.process_plate(plate)
            if result:
                results.append(result)
        return results
    
    def get_processing_statistics(self):
        """Get statistics about plate processing"""
        return {
            'cached_plates': len(self.recent_plates),
            'cache_timeout': self.cache_timeout,
            'validation_config': CONFIG.get('plate_validation', {}),
            'levenshtein_threshold': CONFIG.get('levenshtein_threshold', 2)
        }