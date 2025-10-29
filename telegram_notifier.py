"""
Telegram notification module for LPR Counter-Surveillance System
Handles all Telegram API interactions and notifications
"""

import os
import time
import requests
from queue import Queue
from io import BytesIO
from PIL import Image
from config import logger, CONFIG, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramNotifier:
    """Manages Telegram notifications for the LPR system"""
    
    def __init__(self, bot_token=None, chat_id=None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = CONFIG.get('telegram_enabled', True)
        self.message_queue = Queue()
        self.last_message_time = {}
        self.rate_limit_seconds = 120  # 2 minutes between duplicate alerts
        self.session = requests.Session()
        
        # Test connection on initialization
        if self.enabled:
            self.test_connection()
    
    def test_connection(self):
        """Test Telegram bot connection"""
        try:
            url = f"{self.base_url}/getMe"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                bot_info = response.json()
                logger.info(f"Telegram bot connected: {bot_info.get('result', {}).get('username', 'Unknown')}")
                return True
            else:
                logger.error(f"Telegram connection test failed: {response.status_code}")
                self.enabled = False
                return False
        except Exception as e:
            logger.error(f"Telegram connection test error: {e}")
            self.enabled = False
            return False
    
    def send_message(self, text, plate=None, priority='normal'):
        """
        Send text message to Telegram with rate limiting
        
        Args:
            text: Message text to send
            plate: Optional plate number for rate limiting
            priority: Message priority ('low', 'normal', 'high', 'critical')
        """
        if not self.enabled:
            return None
            
        try:
            # Rate limiting per plate
            if plate and priority != 'critical':
                now = time.time()
                if plate in self.last_message_time:
                    time_since_last = now - self.last_message_time[plate]
                    if time_since_last < self.rate_limit_seconds:
                        logger.info(f"Skipping duplicate Telegram alert for plate: {plate} (sent {time_since_last:.0f}s ago)")
                        return None
                
                self.last_message_time[plate] = now
                
                # Cleanup old entries (older than 10 minutes)
                self._cleanup_old_entries(now)
            
            # Format message based on priority
            if priority == 'critical':
                text = f"🔴 CRITICAL ALERT 🔴\n\n{text}"
            elif priority == 'high':
                text = f"🟠 HIGH PRIORITY 🟠\n\n{text}"
            
            # Send message
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_notification': priority == 'low'
            }
            
            response = self.session.post(url, data=data, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return None
                
            result = response.json()
            logger.info(f"Telegram message sent successfully (priority: {priority})")
            return result
            
        except requests.exceptions.Timeout:
            logger.error("Telegram message send timeout")
            return None
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return None
    
    def send_photo(self, photo_path=None, photo_data=None, caption="", priority='normal'):
        """
        Send photo to Telegram with compression
        
        Args:
            photo_path: Path to photo file
            photo_data: Photo data as bytes
            caption: Photo caption
            priority: Message priority
        """
        if not self.enabled:
            return None
            
        try:
            # Prepare photo data
            if photo_path:
                with Image.open(photo_path) as img:
                    photo_buffer = self._compress_image(img)
            elif photo_data:
                img = Image.open(BytesIO(photo_data))
                photo_buffer = self._compress_image(img)
            else:
                logger.error("No photo provided to send")
                return None
            
            # Format caption based on priority
            if priority == 'critical':
                caption = f"🔴 CRITICAL 🔴\n{caption}"
            elif priority == 'high':
                caption = f"🟠 HIGH PRIORITY 🟠\n{caption}"
            
            # Send photo
            url = f"{self.base_url}/sendPhoto"
            files = {'photo': ('plate.jpg', photo_buffer, 'image/jpeg')}
            data = {
                'chat_id': self.chat_id,
                'caption': caption[:1024],  # Telegram caption limit
                'parse_mode': 'HTML',
                'disable_notification': priority == 'low'
            }
            
            response = self.session.post(url, data=data, files=files, timeout=15)
            
            if response.status_code != 200:
                logger.error(f"Telegram photo send error: {response.status_code}")
                return None
                
            logger.info(f"Telegram photo sent successfully")
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            return None
    
    def send_document(self, file_path, caption=""):
        """Send document file to Telegram"""
        if not self.enabled:
            return None
            
        try:
            url = f"{self.base_url}/sendDocument"
            
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption[:1024],
                    'parse_mode': 'HTML'
                }
                
                response = self.session.post(url, data=data, files=files, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Telegram document send error: {response.status_code}")
                return None
                
            logger.info(f"Document {file_path} sent successfully")
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to send Telegram document: {e}")
            return None
    
    def send_location(self, latitude, longitude, title=""):
        """Send location to Telegram"""
        if not self.enabled:
            return None
            
        try:
            url = f"{self.base_url}/sendLocation"
            data = {
                'chat_id': self.chat_id,
                'latitude': latitude,
                'longitude': longitude
            }
            
            response = self.session.post(url, data=data, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Telegram location send error: {response.status_code}")
                return None
                
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to send Telegram location: {e}")
            return None
    
    def send_blacklist_alert(self, plate_text, reason, danger_level, timestamp, image_path=None):
        """Send formatted blacklist alert"""
        alert_msg = self._format_blacklist_alert(plate_text, reason, danger_level, timestamp)
        
        # Determine priority based on danger level
        priority_map = {
            'CRITICAL': 'critical',
            'HIGH': 'high',
            'MEDIUM': 'normal',
            'LOW': 'low'
        }
        priority = priority_map.get(danger_level, 'normal')
        
        # Send text alert
        self.send_message(alert_msg, plate=plate_text, priority=priority)
        
        # Send photo if available
        if image_path:
            self.send_photo(photo_path=image_path, caption=alert_msg, priority=priority)

    def send_blacklist_alert_no_limit(self, alert_msg, image_path, priority='critical'):
        """
        Send blacklist alert WITHOUT rate limiting
        Every detection is sent immediately
        """
        if not self.enabled:
            return None

        try:
            # Format with priority indicator
            if priority == 'critical':
                alert_msg = f"🔴 CRITICAL ALERT 🔴\n\n{alert_msg}"
            elif priority == 'high':
                alert_msg = f"🟠 HIGH PRIORITY 🟠\n\n{alert_msg}"

            # Send text message (no rate limit check)
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': alert_msg,
                'parse_mode': 'HTML',
                'disable_notification': False  # Always with sound
            }

            response = self.session.post(url, data=data, timeout=10)

            # Send photo if available
            if image_path and os.path.exists(image_path):
                try:
                    self.send_photo(photo_path=image_path, caption=alert_msg[:1024], priority=priority)
                except Exception as e:
                    logger.error(f"Error sending blacklist photo: {e}")

            logger.info("🚨 Blacklist alert sent (NO rate limit)")
            return response.json() if response.status_code == 200 else None

        except Exception as e:
            logger.error(f"Failed to send blacklist alert: {e}")
            return None

    def send_suspicious_alert(self, plate_text, duration_minutes, first_seen, current_time, image_path=None):
        """Send formatted suspicious presence alert"""
        alert_msg = self._format_suspicious_alert(plate_text, duration_minutes, first_seen, current_time)
        
        # Send text alert
        self.send_message(alert_msg, plate=plate_text, priority='high')
        
        # Send photo if available
        if image_path:
            self.send_photo(photo_path=image_path, caption=alert_msg, priority='high')
    
    def send_statistics_report(self, stats):
        """Send daily statistics report"""
        if not stats:
            return
            
        report = f"📊 <b>Daily Statistics Report</b> 📊\n"
        report += f"Date: {stats['date']}\n\n"
        report += f"🚗 Total Detections: <b>{stats['total_detections']}</b>\n"
        report += f"🎯 Unique Plates: <b>{stats['unique_plates']}</b>\n"
        report += f"⚠️ Suspicious Events: <b>{stats['suspicious_events']}</b>\n"
        report += f"🚫 Blacklist Hits: <b>{stats['blacklist_hits']}</b>\n"
        
        self.send_message(report, priority='low')
    
    def send_system_alert(self, alert_type, message):
        """Send system-level alerts"""
        alert_icons = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅'
        }
        
        icon = alert_icons.get(alert_type, '📢')
        formatted_msg = f"{icon} <b>System Alert</b>\n\n{message}"
        
        priority = 'high' if alert_type == 'error' else 'normal'
        self.send_message(formatted_msg, priority=priority)
    
    def _compress_image(self, img, max_size=(1024, 768), quality=85):
        """Compress image for Telegram sending"""
        try:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Resize if too large
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to buffer
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            buffer.seek(0)
            
            return buffer
        except Exception as e:
            logger.error(f"Error compressing image: {e}")
            return None
    
    def _format_blacklist_alert(self, plate_text, reason, danger_level, timestamp):
        """Format blacklist alert message"""
        emoji_map = {
            'CRITICAL': '🔴',
            'HIGH': '🟠',
            'MEDIUM': '🟡',
            'LOW': '🔵'
        }
        
        emoji = emoji_map.get(danger_level, '⚪')
        
        alert_msg = f"🚨 <b>BLACKLIST ALERT</b> 🚨\n\n"
        alert_msg += f"Plate: <b>{plate_text}</b>\n"
        alert_msg += f"Danger Level: {emoji} <b>{danger_level}</b>\n"
        alert_msg += f"Reason: {reason}\n"
        alert_msg += f"Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        alert_msg += f"\n⚡ Immediate action may be required!"
        
        return alert_msg
    
    def _format_suspicious_alert(self, plate_text, duration_minutes, first_seen, current_time):
        """Format suspicious presence alert message"""
        alert_msg = f"⚠️ <b>SUSPICIOUS PRESENCE ALERT</b> ⚠️\n\n"
        alert_msg += f"Plate: <b>{plate_text}</b>\n"
        alert_msg += f"Duration: <b>{duration_minutes} minutes</b>\n"
        alert_msg += f"First seen: {first_seen.strftime('%H:%M:%S')}\n"
        alert_msg += f"Current time: {current_time.strftime('%H:%M:%S')}\n"
        alert_msg += f"\n👁️ Vehicle has been present for an extended period"
        
        return alert_msg
    
    def _cleanup_old_entries(self, current_time, max_age=600):
        """Cleanup old rate limiting entries"""
        try:
            old_plates = [
                plate for plate, last_time in self.last_message_time.items()
                if current_time - last_time > max_age
            ]
            
            for plate in old_plates:
                del self.last_message_time[plate]
            
            if old_plates:
                logger.debug(f"Cleaned up {len(old_plates)} old rate limiting entries")
        except Exception as e:
            logger.error(f"Error cleaning up rate limiting entries: {e}")
    
    def set_enabled(self, enabled):
        """Enable or disable Telegram notifications"""
        self.enabled = enabled
        CONFIG['telegram_enabled'] = enabled
        logger.info(f"Telegram notifications {'enabled' if enabled else 'disabled'}")
    
    def is_enabled(self):
        """Check if Telegram notifications are enabled"""
        return self.enabled
    
    def get_updates(self):
        """Get updates from Telegram (for future bot commands implementation)"""
        if not self.enabled:
            return None
            
        try:
            url = f"{self.base_url}/getUpdates"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json().get('result', [])
            
            return None
        except Exception as e:
            logger.error(f"Error getting Telegram updates: {e}")
            return None