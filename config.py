"""
Configuration module for LPR Counter-Surveillance System
Contains all system settings and global configurations
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging - reduced verbosity
logging.basicConfig(
    level=logging.WARNING,  # Changed from INFO to WARNING
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='lpr_system.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# Option to disable file logging
DISABLE_FILE_LOGGING = True
if DISABLE_FILE_LOGGING:
    logger.handlers = []
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

# Library path configuration
lib_path = os.getenv('LIB_PATH', '../../lib/windows/x64/')
os.environ['PATH'] = lib_path + os.pathsep + os.environ['PATH']

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Database configuration
DATABASE_PATH = os.getenv('DATABASE_PATH', 'lpr_surveillance.db')

# Global configurations
CONFIG = {
    'camera_index': 1,
    'camera_width': 1920,
    'camera_height': 1080,
    'levenshtein_threshold': 2,
    'suspicious_duration_minutes': 2,
    'min_plate_width': 80,
    'max_plate_width': 400,
    'countries': 'AZ,RU,GE,AM,TR',
    'fps_limit': 0,
    'duplicate_delay': 2000,
    'confirmation_count': 1,
    'num_threads': 0,
    'telegram_enabled': True,
    'telegram_stream_enabled': True,
    'telegram_stream_session': os.getenv('TELEGRAM_STREAM_SESSION', 'stream_bot'),
    'telegram_stream_api_id': int(os.getenv('TELEGRAM_STREAM_API_ID', '0')) if os.getenv('TELEGRAM_STREAM_API_ID') else 0,
    'telegram_stream_api_hash': os.getenv('TELEGRAM_STREAM_API_HASH', ''),
    'telegram_stream_chat_id': int(os.getenv('TELEGRAM_STREAM_CHAT_ID', '0')) if os.getenv('TELEGRAM_STREAM_CHAT_ID') else 0,
    'telegram_stream_delay_seconds': 10,
    'telegram_stream_camera_name': 'OBS Virtual Camera',
    'telegram_stream_ffmpeg_params': '-video_size 1920x1080 -framerate 30 -c:v libx264 -preset fast -b:v 4M -maxrate 4M -bufsize 8M -pix_fmt yuv420p -g 60',
    'telegram_stream_camera_retry_attempts': 15,
    'telegram_stream_camera_retry_delay': 2,
    'save_images': True,
    'image_quality': 95,
    'display_skip_rate': 2,  # GUI display: every Nth frame (1=all, 2=every 2nd)
    'virtual_camera_skip_rate': 2,  # Virtual camera: every Nth frame
    'blacklist_similarity_threshold': 80,  # Minimum similarity % for blacklist fuzzy matching
    'auto_connect_camera': False,  # Auto-connect camera on startup
    'preprocessing': {
        'contrast': 1,
        'brightness': 1,
        'sharpness': 1
    },
    'plate_validation': {
        'min_length': 1,  # Изменено с 3 на 1
        'max_length': 99,  # Изменено с 10 на 99 - принимаем любую длину
        'allowed_chars': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ .'  # Добавлены дополнительные символы
    }
}

# Queue sizes configuration
QUEUE_SIZES = {
    'plate_queue': 100,
    'telegram_queue': 50,
    'db_queue': 50,
    'image_queue': 50
}

# Display configuration
DISPLAY_CONFIG = {
    'window_title': 'LPR Counter-Surveillance System v2.0',
    'window_geometry': '1400x800',
    'video_display_size': (640, 480),
    'update_interval_ms': 1000,
    'results_update_interval_ms': 2000,
    'max_results_display': 100
}

# Image saving configuration
IMAGE_CONFIG = {
    'detection_dir': 'detections',
    'date_format': '%Y-%m-%d',
    'time_format': '%H%M%S_%f',
    'max_filename_length': 50,
    'thumbnail_size': (1024, 768),
    'jpeg_quality': 85
}

# Error messages
ERROR_MESSAGES = {
    1: "Failed to open camera",
    2: "Failed to read frame",
    3: "End of video file"
}

def save_config_to_file(filepath='config.json'):
    """Save current configuration to JSON file"""
    try:
        with open(filepath, 'w') as f:
            json.dump(CONFIG, f, indent=4)
        logger.info(f"Configuration saved to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        return False

def load_config_from_file(filepath='config.json'):
    """Load configuration from JSON file"""
    global CONFIG
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                loaded_config = json.load(f)
                CONFIG.update(loaded_config)
                logger.info(f"Configuration loaded from {filepath}")
                return True
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
    return False

def get_config_value(key, default=None):
    """Get configuration value with fallback default"""
    return CONFIG.get(key, default)

def set_config_value(key, value):
    """Set configuration value"""
    CONFIG[key] = value
    logger.debug(f"Configuration updated: {key} = {value}")

def validate_config():
    """Validate configuration values"""
    errors = []
    
    # Validate camera settings
    if CONFIG['camera_width'] <= 0 or CONFIG['camera_height'] <= 0:
        errors.append("Invalid camera resolution")
    
    # Validate plate width settings
    if CONFIG['min_plate_width'] >= CONFIG['max_plate_width']:
        errors.append("Min plate width must be less than max plate width")
    
    # Validate image quality
    if not 0 <= CONFIG['image_quality'] <= 100:
        errors.append("Image quality must be between 0 and 100")
    
    # Validate preprocessing values
    for key in ['contrast', 'brightness', 'sharpness']:
        if not 0.1 <= CONFIG['preprocessing'][key] <= 3.0:
            errors.append(f"Preprocessing {key} must be between 0.1 and 3.0")
    
    return errors

# Initialize configuration on module load
load_config_from_file()
