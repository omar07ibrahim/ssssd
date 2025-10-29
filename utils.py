"""
Utility functions module for LPR Counter-Surveillance System
Contains helper functions and algorithms
"""

from PIL import Image, ImageEnhance
from datetime import datetime, timedelta
import csv
import json
from pathlib import Path
from config import logger, CONFIG

def levenshtein_distance(s1, s2):
    """
    Calculate Levenshtein distance between two strings
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Integer distance between strings
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def preprocess_image(image):
    """
    Apply preprocessing to improve recognition quality

    Args:
        image: PIL Image object

    Returns:
        Preprocessed PIL Image object (NEW object, caller must close original)
    """
    try:
        preprocessing_config = CONFIG.get('preprocessing', {})
        current_image = image

        # Apply contrast enhancement
        contrast_factor = preprocessing_config.get('contrast', 1.0)
        if contrast_factor != 1.0:
            enhancer = ImageEnhance.Contrast(current_image)
            new_image = enhancer.enhance(contrast_factor)
            # Close old image if it's not the original
            if current_image is not image:
                current_image.close()
            current_image = new_image

        # Apply brightness enhancement
        brightness_factor = preprocessing_config.get('brightness', 1.0)
        if brightness_factor != 1.0:
            enhancer = ImageEnhance.Brightness(current_image)
            new_image = enhancer.enhance(brightness_factor)
            # Close old image if it's not the original
            if current_image is not image:
                current_image.close()
            current_image = new_image

        # Apply sharpness enhancement
        sharpness_factor = preprocessing_config.get('sharpness', 1.0)
        if sharpness_factor != 1.0:
            enhancer = ImageEnhance.Sharpness(current_image)
            new_image = enhancer.enhance(sharpness_factor)
            # Close old image if it's not the original
            if current_image is not image:
                current_image.close()
            current_image = new_image

        return current_image
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}")
        return image

def format_duration(seconds):
    """
    Format duration in seconds to human-readable string
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string (e.g., "2h 15m", "45m", "30s")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        remaining_seconds = int(seconds % 60)
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        remaining_minutes = int((seconds % 3600) / 60)
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"

def format_timestamp(timestamp, format_string=None):
    """
    Format timestamp to string
    
    Args:
        timestamp: datetime object or timestamp string
        format_string: Optional format string
        
    Returns:
        Formatted timestamp string
    """
    if format_string is None:
        format_string = "%Y-%m-%d %H:%M:%S"
    
    try:
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        return timestamp.strftime(format_string)
    except Exception as e:
        logger.error(f"Timestamp formatting error: {e}")
        return str(timestamp)

def calculate_time_difference(start_time, end_time):
    """
    Calculate time difference between two timestamps
    
    Args:
        start_time: Start timestamp (datetime or string)
        end_time: End timestamp (datetime or string)
        
    Returns:
        timedelta object or None if error
    """
    try:
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)
        
        return end_time - start_time
    except Exception as e:
        logger.error(f"Time difference calculation error: {e}")
        return None

def export_to_csv(data, filepath, headers=None):
    """
    Export data to CSV file
    
    Args:
        data: List of tuples/lists to export
        filepath: Path to save CSV file
        headers: Optional list of column headers
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            if headers:
                writer.writerow(headers)
            
            for row in data:
                writer.writerow(row)
        
        logger.info(f"Data exported to {filepath}")
        return True
    except Exception as e:
        logger.error(f"CSV export error: {e}")
        return False

def export_to_json(data, filepath):
    """
    Export data to JSON file
    
    Args:
        data: Data to export (dict, list, etc.)
        filepath: Path to save JSON file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, default=str)
        
        logger.info(f"Data exported to {filepath}")
        return True
    except Exception as e:
        logger.error(f"JSON export error: {e}")
        return False

def validate_plate_format(plate_text, country_code=None):
    """
    Validate license plate format
    
    Args:
        plate_text: Plate text to validate
        country_code: Optional country code for specific validation
        
    Returns:
        True if valid, False otherwise
    """
    # ОТКЛЮЧЕНА ВАЛИДАЦИЯ - ПРИНИМАЕМ ВСЕ НОМЕРА
    # Просто проверяем что есть текст
    if not plate_text or len(plate_text) == 0:
        return False
    
    return True

def create_directory_structure():
    """
    Create necessary directory structure for the application
    
    Returns:
        True if successful, False otherwise
    """
    try:
        directories = [
            Path('detections'),
            Path('logs'),
            Path('exports'),
            Path('config'),
            Path('backups')
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        
        logger.info("Directory structure created/verified")
        return True
    except Exception as e:
        logger.error(f"Error creating directory structure: {e}")
        return False

def get_file_size_mb(filepath):
    """
    Get file size in megabytes
    
    Args:
        filepath: Path to file
        
    Returns:
        File size in MB or None if error
    """
    try:
        size_bytes = Path(filepath).stat().st_size
        return size_bytes / (1024 * 1024)
    except Exception as e:
        logger.error(f"Error getting file size: {e}")
        return None

def cleanup_old_files(directory, days_to_keep=30, extensions=None):
    """
    Clean up old files from directory
    
    Args:
        directory: Directory path to clean
        days_to_keep: Number of days to keep files
        extensions: Optional list of file extensions to clean (e.g., ['.jpg', '.png'])
        
    Returns:
        Number of files deleted
    """
    try:
        directory = Path(directory)
        if not directory.exists():
            return 0
        
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)
        deleted_count = 0
        
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                # Check extension if specified
                if extensions and file_path.suffix not in extensions:
                    continue
                
                # Check file age
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    file_path.unlink()
                    deleted_count += 1
        
        logger.info(f"Deleted {deleted_count} old files from {directory}")
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning up old files: {e}")
        return 0

def generate_report_filename(report_type='report'):
    """
    Generate filename for reports with timestamp
    
    Args:
        report_type: Type of report (e.g., 'daily', 'weekly', 'plates')
        
    Returns:
        Generated filename string
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{report_type}_{timestamp}"

def calculate_statistics(data_list):
    """
    Calculate basic statistics for a list of numbers
    
    Args:
        data_list: List of numbers
        
    Returns:
        Dict with min, max, average, median, total
    """
    if not data_list:
        return {
            'min': 0,
            'max': 0,
            'median': 0,
            'total': 0,
            'average': 0
        }
    
    sorted_data = sorted(data_list)
    length = len(sorted_data)
    
    total = sum(sorted_data)
    average = total / length if length > 0 else 0
    
    return {
        'min': min(sorted_data),
        'max': max(sorted_data),
        'average': average,
        'median': sorted_data[length // 2] if length % 2 else (sorted_data[length // 2 - 1] + sorted_data[length // 2]) / 2,
        'total': total
    }

def normalize_plate_text(plate_text):
    """
    Normalize plate text for comparison
    
    Args:
        plate_text: Original plate text
        
    Returns:
        Normalized plate text
    """
    if not plate_text:
        return ""
    
    # Remove spaces and convert to uppercase
    normalized = plate_text.upper().replace(' ', '')
    
    # Remove common separators
    for char in ['-', '_', '.', ',']:
        normalized = normalized.replace(char, '')
    
    return normalized

def is_similar_plate(plate1, plate2, threshold=2):
    """
    Check if two plates are similar using Levenshtein distance
    
    Args:
        plate1: First plate text
        plate2: Second plate text
        threshold: Maximum distance to consider similar
        
    Returns:
        True if similar, False otherwise
    """
    plate1_norm = normalize_plate_text(plate1)
    plate2_norm = normalize_plate_text(plate2)
    
    if not plate1_norm or not plate2_norm:
        return False
    
    distance = levenshtein_distance(plate1_norm, plate2_norm)
    return distance <= threshold

def get_system_info():
    """
    Get system information for debugging
    
    Returns:
        Dict with system information
    """
    import platform
    import psutil
    
    try:
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'processor': platform.processor(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
            'memory_available_gb': round(psutil.virtual_memory().available / (1024**3), 2),
            'disk_usage_percent': psutil.disk_usage('/').percent
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        return {}

def validate_config():
    """
    Validate application configuration
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check camera settings
    if CONFIG.get('camera_width', 0) <= 0 or CONFIG.get('camera_height', 0) <= 0:
        errors.append("Invalid camera resolution settings")
    
    # Check plate width settings
    min_width = CONFIG.get('min_plate_width', 0)
    max_width = CONFIG.get('max_plate_width', 0)
    if min_width >= max_width or min_width <= 0:
        errors.append("Invalid plate width settings")
    
    # Check image quality
    quality = CONFIG.get('image_quality', 95)
    if not 0 <= quality <= 100:
        errors.append("Image quality must be between 0 and 100")
    
    # Check preprocessing values
    preprocessing = CONFIG.get('preprocessing', {})
    for key in ['contrast', 'brightness', 'sharpness']:
        value = preprocessing.get(key, 1.0)
        if not 0.1 <= value <= 3.0:
            errors.append(f"Preprocessing {key} must be between 0.1 and 3.0")
    
    return errors