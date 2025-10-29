"""
Database management module for LPR Counter-Surveillance System
Handles all database operations and queries
"""

import sqlite3
from datetime import datetime, timedelta
from threading import Lock
import json
from config import logger, CONFIG

class DatabaseManager:
    """Manages all database operations for the LPR system"""
    
    def __init__(self, db_path='lpr_surveillance.db'):
        self.db_path = db_path
        self.conn = None
        self.db_lock = Lock()
        self.init_database()
        
    def init_database(self):
        """Initialize database with all required tables"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)

            # Performance optimizations
            self.conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
            self.conn.execute("PRAGMA synchronous = NORMAL")  # Balanced durability
            self.conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            self.conn.execute("PRAGMA temp_store = MEMORY")  # Temp tables in memory
            self.conn.execute("PRAGMA mmap_size = 30000000000")  # 30GB memory-mapped I/O
            self.conn.execute("PRAGMA page_size = 4096")  # Optimal page size

            logger.info("⚡ SQLite optimized for maximum performance")
            
            cursor = self.conn.cursor()
            
            # Recognized plates table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recognized_plates (
                    plate_text_canonical TEXT PRIMARY KEY,
                    first_appearance_ts DATETIME,
                    last_appearance_ts DATETIME,
                    detection_count INTEGER DEFAULT 1,
                    country_code TEXT,
                    highest_confidence_achieved REAL,
                    is_suspiciously_present BOOLEAN DEFAULT 0,
                    is_blacklisted BOOLEAN DEFAULT 0,
                    last_detection_image_path TEXT,
                    last_detection_confidence REAL
                )
            ''')
            
            # Original detections table with grouping support
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS original_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_plate_text_ref TEXT,
                    raw_detected_text TEXT,
                    detection_ts DATETIME,
                    confidence REAL,
                    image_path TEXT,
                    parent_detection_id INTEGER DEFAULT NULL,
                    time_diff_seconds INTEGER DEFAULT 0,
                    is_grouped BOOLEAN DEFAULT 0,
                    FOREIGN KEY (canonical_plate_text_ref) REFERENCES recognized_plates(plate_text_canonical),
                    FOREIGN KEY (parent_detection_id) REFERENCES original_detections(id)
                )
            ''')
            
            # Plate variants table for tracking all variations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plate_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_plate_ref TEXT,
                    variant_text TEXT,
                    max_confidence REAL,
                    detection_count INTEGER DEFAULT 1,
                    last_seen DATETIME,
                    FOREIGN KEY (canonical_plate_ref) REFERENCES recognized_plates(plate_text_canonical)
                )
            ''')
            
            # Blacklist table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blacklist_plates (
                    plate_text TEXT PRIMARY KEY,
                    reason TEXT,
                    danger_level TEXT,
                    date_added DATETIME,
                    notes TEXT
                )
            ''')

            # Blacklist detections log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blacklist_detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_plate TEXT,
                    matched_blacklist_plate TEXT,
                    similarity_score REAL,
                    detection_ts DATETIME,
                    image_path TEXT,
                    FOREIGN KEY (matched_blacklist_plate) REFERENCES blacklist_plates(plate_text)
                )
            ''')

            # Index for fast queries on blacklist detections
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_blacklist_detections_ts
                ON blacklist_detections(detection_ts DESC)
            ''')

            # Application settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS application_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            # Statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE,
                    total_detections INTEGER DEFAULT 0,
                    unique_plates INTEGER DEFAULT 0,
                    suspicious_events INTEGER DEFAULT 0,
                    blacklist_hits INTEGER DEFAULT 0
                )
            ''')
            
            # Create indexes for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_plates_last_seen 
                ON recognized_plates(last_appearance_ts DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_blacklist_plate 
                ON blacklist_plates(plate_text)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_detections_canonical 
                ON original_detections(canonical_plate_text_ref)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_detections_timestamp 
                ON original_detections(detection_ts DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_plates_confidence 
                ON recognized_plates(highest_confidence_achieved DESC)
            ''')
            
            self.conn.commit()
            self.load_settings()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
            
    def load_settings(self):
        """Load settings from database into CONFIG"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT key, value FROM application_settings")
                for key, value in cursor.fetchall():
                    if key in CONFIG:
                        try:
                            if isinstance(CONFIG[key], bool):
                                CONFIG[key] = value.lower() == 'true'
                            elif isinstance(CONFIG[key], int):
                                CONFIG[key] = int(value)
                            elif isinstance(CONFIG[key], float):
                                CONFIG[key] = float(value)
                            elif key in ['preprocessing', 'plate_validation']:
                                try:
                                    loaded_data = json.loads(value)
                                    if isinstance(loaded_data, dict):
                                        CONFIG[key] = loaded_data
                                    else:
                                        logger.warning(f"Invalid JSON data type for {key}, keeping default")
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse JSON for {key}: {e}")
                            else:
                                CONFIG[key] = value
                        except Exception as e:
                            logger.warning(f"Failed to load setting {key}: {e}")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            
    def save_settings(self):
        """Save current settings from CONFIG to database"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                for key, value in CONFIG.items():
                    try:
                        if key == 'preprocessing' or key == 'plate_validation':
                            value_str = json.dumps(value)
                        else:
                            value_str = str(value)
                        
                        cursor.execute(
                            "INSERT OR REPLACE INTO application_settings (key, value) VALUES (?, ?)",
                            (key, value_str)
                        )
                    except Exception as e:
                        logger.error(f"Failed to save setting {key}: {e}")
                self.conn.commit()
                logger.info("Settings saved to database")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    def add_plate_detection(self, canonical_text, raw_text, confidence, timestamp, image_path=None):
        """Add a new plate detection with grouping support"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # Check for recent detections to group
                cursor.execute('''
                    SELECT id, detection_ts, image_path
                    FROM original_detections
                    WHERE canonical_plate_text_ref = ?
                    AND is_grouped = 0
                    ORDER BY detection_ts DESC
                    LIMIT 1
                ''', (canonical_text,))
                
                last_detection = cursor.fetchone()
                parent_id = None
                time_diff = 0
                is_grouped = False
                
                if last_detection:
                    last_id, last_ts_str, last_image = last_detection
                    try:
                        last_ts = datetime.fromisoformat(last_ts_str)
                        time_diff = (timestamp - last_ts).total_seconds()
                        
                        # Group if within 10 seconds
                        if time_diff < 10:
                            parent_id = last_id
                            is_grouped = True
                            # Don't save image if grouped (use parent's image)
                            if time_diff < 10:
                                image_path = None
                    except Exception as e:
                        logger.error(f"Error parsing timestamp: {e}")
                
                # Insert detection
                cursor.execute('''
                    INSERT INTO original_detections 
                    (canonical_plate_text_ref, raw_detected_text, detection_ts, confidence, 
                     image_path, parent_detection_id, time_diff_seconds, is_grouped)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (canonical_text, raw_text, timestamp, confidence, image_path, 
                      parent_id, int(time_diff), is_grouped))
                
                # Update plate variant
                self._update_plate_variant(canonical_text, raw_text, confidence, timestamp)
                
                self.conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding plate detection: {e}")
            return None
    
    def _update_plate_variant(self, canonical_ref, variant_text, confidence, timestamp):
        """Update or create plate variant record"""
        try:
            cursor = self.conn.cursor()
            
            # Check if variant exists
            cursor.execute('''
                SELECT id, max_confidence, detection_count
                FROM plate_variants
                WHERE canonical_plate_ref = ? AND variant_text = ?
            ''', (canonical_ref, variant_text))
            
            existing = cursor.fetchone()
            
            if existing:
                variant_id, max_conf, count = existing
                new_max_conf = max(max_conf, confidence)
                cursor.execute('''
                    UPDATE plate_variants
                    SET max_confidence = ?, detection_count = detection_count + 1, last_seen = ?
                    WHERE id = ?
                ''', (new_max_conf, timestamp, variant_id))
            else:
                cursor.execute('''
                    INSERT INTO plate_variants
                    (canonical_plate_ref, variant_text, max_confidence, detection_count, last_seen)
                    VALUES (?, ?, ?, 1, ?)
                ''', (canonical_ref, variant_text, confidence, timestamp))
            
            # Check if we should update canonical text
            self._check_update_canonical(canonical_ref)
            
        except Exception as e:
            logger.error(f"Error updating plate variant: {e}")
    
    def _check_update_canonical(self, current_canonical):
        """Check if canonical text should be updated to variant with highest confidence"""
        try:
            cursor = self.conn.cursor()
            
            # Get variant with highest confidence
            cursor.execute('''
                SELECT variant_text, max_confidence
                FROM plate_variants
                WHERE canonical_plate_ref = ?
                ORDER BY max_confidence DESC
                LIMIT 1
            ''', (current_canonical,))
            
            best_variant = cursor.fetchone()
            
            if best_variant and best_variant[0] != current_canonical:
                new_canonical, max_conf = best_variant
                
                # Update canonical text to best variant
                cursor.execute('''
                    UPDATE recognized_plates
                    SET plate_text_canonical = ?,
                        highest_confidence_achieved = ?
                    WHERE plate_text_canonical = ?
                ''', (new_canonical, max_conf, current_canonical))
                
                # Update references in other tables
                cursor.execute('''
                    UPDATE original_detections
                    SET canonical_plate_text_ref = ?
                    WHERE canonical_plate_text_ref = ?
                ''', (new_canonical, current_canonical))
                
                cursor.execute('''
                    UPDATE plate_variants
                    SET canonical_plate_ref = ?
                    WHERE canonical_plate_ref = ?
                ''', (new_canonical, current_canonical))
                
                logger.info(f"Updated canonical plate from {current_canonical} to {new_canonical} (confidence: {max_conf}%)")
                
        except Exception as e:
            logger.error(f"Error checking canonical update: {e}")
    
    def update_canonical_plate(self, canonical_text, confidence, timestamp, image_path=None):
        """Update existing canonical plate record"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE recognized_plates 
                    SET last_appearance_ts = ?,
                        detection_count = detection_count + 1,
                        highest_confidence_achieved = MAX(highest_confidence_achieved, ?),
                        last_detection_image_path = ?,
                        last_detection_confidence = ?
                    WHERE plate_text_canonical = ?
                ''', (timestamp, confidence, image_path, confidence, canonical_text))
                self.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating canonical plate: {e}")
            return False
    
    def create_canonical_plate(self, plate_text, country_code, confidence, timestamp, image_path=None):
        """Create new canonical plate record"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # Check if blacklisted
                cursor.execute(
                    "SELECT 1 FROM blacklist_plates WHERE plate_text = ?", 
                    (plate_text,)
                )
                is_blacklisted = cursor.fetchone() is not None
                
                cursor.execute('''
                    INSERT INTO recognized_plates 
                    (plate_text_canonical, first_appearance_ts, last_appearance_ts, 
                     detection_count, country_code, highest_confidence_achieved, 
                     is_blacklisted, last_detection_image_path, last_detection_confidence)
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                ''', (plate_text, timestamp, timestamp, country_code, 
                      confidence, is_blacklisted, image_path, confidence))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error creating canonical plate: {e}")
            return False
    
    def get_canonical_plates(self):
        """Get all canonical plate texts"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT plate_text_canonical FROM recognized_plates")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting canonical plates: {e}")
            return []
    
    def get_plate_info(self, plate_text):
        """Get detailed information about a specific plate"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT * FROM recognized_plates WHERE plate_text_canonical = ?
                ''', (plate_text,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting plate info: {e}")
            return None
    
    def get_plate_detections(self, plate_text, limit=50):
        """Get all detections for a specific plate with grouping info"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT id, raw_detected_text, detection_ts, confidence, image_path,
                           parent_detection_id, time_diff_seconds, is_grouped
                    FROM original_detections
                    WHERE canonical_plate_text_ref = ?
                    ORDER BY detection_ts DESC
                    LIMIT ?
                ''', (plate_text, limit))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting plate detections: {e}")
            return []
    
    def get_grouped_detections(self, plate_text, limit=50):
        """Get detections organized in tree structure"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # Get parent detections (not grouped)
                cursor.execute('''
                    SELECT id, raw_detected_text, detection_ts, confidence, image_path
                    FROM original_detections
                    WHERE canonical_plate_text_ref = ? AND parent_detection_id IS NULL
                    ORDER BY detection_ts DESC
                    LIMIT ?
                ''', (plate_text, limit))
                
                parents = cursor.fetchall()
                result = []
                
                for parent in parents:
                    parent_id = parent[0]
                    parent_data = {
                        'id': parent_id,
                        'text': parent[1],
                        'timestamp': parent[2],
                        'confidence': parent[3],
                        'image_path': parent[4],
                        'children': []
                    }
                    
                    # Get child detections
                    cursor.execute('''
                        SELECT id, raw_detected_text, detection_ts, confidence, time_diff_seconds
                        FROM original_detections
                        WHERE parent_detection_id = ?
                        ORDER BY detection_ts ASC
                    ''', (parent_id,))
                    
                    children = cursor.fetchall()
                    for child in children:
                        parent_data['children'].append({
                            'id': child[0],
                            'text': child[1],
                            'timestamp': child[2],
                            'confidence': child[3],
                            'time_diff': child[4]
                        })
                    
                    result.append(parent_data)
                
                return result
        except Exception as e:
            logger.error(f"Error getting grouped detections: {e}")
            return []
    
    def get_plate_variants(self, canonical_text):
        """Get all variants of a plate with statistics"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT variant_text, max_confidence, detection_count, last_seen
                    FROM plate_variants
                    WHERE canonical_plate_ref = ?
                    ORDER BY max_confidence DESC
                ''', (canonical_text,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting plate variants: {e}")
            return []
    
    def check_suspicious_presence(self, canonical_text, first_appearance, last_appearance):
        """Check and update suspicious presence status"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE recognized_plates 
                    SET is_suspiciously_present = 1 
                    WHERE plate_text_canonical = ?
                    AND is_suspiciously_present = 0
                ''', (canonical_text,))
                self.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating suspicious presence: {e}")
            return False
    
    def get_blacklist_info(self, plate_text):
        """Get blacklist information for a plate"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT reason, danger_level, date_added, notes
                    FROM blacklist_plates
                    WHERE plate_text = ?
                ''', (plate_text,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting blacklist info: {e}")
            return None

    def check_blacklist_fuzzy(self, plate_text, threshold=80):
        """
        Check blacklist with fuzzy matching using Levenshtein distance

        Args:
            plate_text: Plate number to check
            threshold: Minimum similarity percentage (0-100)

        Returns:
            Tuple (matched_plate, reason, danger_level, similarity) or None
        """
        try:
            blacklist_entries = self._get_blacklist_cached()

            if not blacklist_entries:
                return None

            from improved_levenshtein import calculate_similarity_score

            best_match = None
            best_score = 0

            for bl_plate, reason, danger_level in blacklist_entries:
                score = calculate_similarity_score(plate_text, bl_plate)

                if score >= threshold and score > best_score:
                    best_match = (bl_plate, reason, danger_level, score)
                    best_score = score

            return best_match

        except Exception as e:
            logger.error(f"Error in fuzzy blacklist check: {e}")
            return None

    def _get_blacklist_cached(self):
        """Get blacklist with caching (60 second TTL)"""
        import time

        # Initialize cache if not exists
        if not hasattr(self, '_blacklist_cache'):
            self._blacklist_cache = []
            self._blacklist_cache_time = 0
            self._blacklist_cache_ttl = 60  # 60 seconds

        current_time = time.time()

        # Refresh cache if expired
        if current_time - self._blacklist_cache_time > self._blacklist_cache_ttl:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT plate_text, reason, danger_level FROM blacklist_plates")
                self._blacklist_cache = cursor.fetchall()
                self._blacklist_cache_time = current_time
                logger.debug(f"Blacklist cache refreshed: {len(self._blacklist_cache)} entries")

        return self._blacklist_cache

    def log_blacklist_detection(self, detected_plate, matched_plate, similarity, timestamp):
        """Log blacklist detection for history"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO blacklist_detections
                    (detected_plate, matched_blacklist_plate, similarity_score, detection_ts)
                    VALUES (?, ?, ?, ?)
                ''', (detected_plate, matched_plate, similarity, timestamp))
                self.conn.commit()
        except Exception as e:
            logger.error(f"Error logging blacklist detection: {e}")

    def mark_as_suspicious(self, plate_text):
        """Mark a plate as suspicious in the database"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    UPDATE recognized_plates
                    SET is_suspicious = 1
                    WHERE plate_text_canonical = ?
                ''', (plate_text,))
                self.conn.commit()
                logger.info(f"Plate {plate_text} marked as suspicious")
        except Exception as e:
            logger.error(f"Error marking plate as suspicious: {e}")

    def add_to_blacklist(self, plate_text, reason, danger_level='MEDIUM', notes=''):
        """Add a plate to the blacklist"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO blacklist_plates (plate_text, reason, danger_level, date_added, notes)
                    VALUES (?, ?, ?, ?, ?)
                ''', (plate_text, reason, danger_level, datetime.now(), notes))
                
                # Update recognized_plates table
                cursor.execute('''
                    UPDATE recognized_plates 
                    SET is_blacklisted = 1 
                    WHERE plate_text_canonical = ?
                ''', (plate_text,))
                
                self.conn.commit()
                logger.info(f"Plate {plate_text} added to blacklist")
                return True
        except Exception as e:
            logger.error(f"Error adding to blacklist: {e}")
            return False
    
    def remove_from_blacklist(self, plate_text):
        """Remove a plate from the blacklist"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM blacklist_plates WHERE plate_text = ?", (plate_text,))
                cursor.execute('''
                    UPDATE recognized_plates 
                    SET is_blacklisted = 0 
                    WHERE plate_text_canonical = ?
                ''', (plate_text,))
                self.conn.commit()
                logger.info(f"Plate {plate_text} removed from blacklist")
                return True
        except Exception as e:
            logger.error(f"Error removing from blacklist: {e}")
            return False
    
    def get_all_blacklist(self):
        """Get all blacklisted plates"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    SELECT plate_text, reason, danger_level, date_added, notes 
                    FROM blacklist_plates 
                    ORDER BY date_added DESC
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting blacklist: {e}")
            return []
    
    def import_blacklist_from_data(self, blacklist_data):
        """Import blacklist from list of tuples (plate_text, reason, danger_level, notes)"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                success_count = 0
                
                for data in blacklist_data:
                    try:
                        plate_text, reason, danger_level, notes = data[:4]
                        cursor.execute('''
                            INSERT OR REPLACE INTO blacklist_plates 
                            (plate_text, reason, danger_level, date_added, notes)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (plate_text, reason, danger_level, datetime.now(), notes))
                        
                        # Update recognized_plates table
                        cursor.execute('''
                            UPDATE recognized_plates 
                            SET is_blacklisted = 1 
                            WHERE plate_text_canonical = ?
                        ''', (plate_text,))
                        
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Error importing plate {data}: {e}")
                        continue
                
                self.conn.commit()
                logger.info(f"Imported {success_count} plates to blacklist")
                return success_count
        except Exception as e:
            logger.error(f"Error importing blacklist: {e}")
            return 0
    
    def search_plates(self, search_term='', limit=100):
        """Search for plates matching the given term"""
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # First get plates with their best variants
                query = '''
                    SELECT 
                        rp.plate_text_canonical,
                        rp.detection_count,
                        rp.last_appearance_ts,
                        rp.first_appearance_ts,
                        rp.is_suspiciously_present,
                        rp.is_blacklisted,
                        rp.last_detection_confidence,
                        pv.variant_text,
                        pv.max_confidence
                    FROM recognized_plates rp
                    LEFT JOIN (
                        SELECT canonical_plate_ref, variant_text, max_confidence,
                               ROW_NUMBER() OVER (PARTITION BY canonical_plate_ref ORDER BY max_confidence DESC) as rn
                        FROM plate_variants
                    ) pv ON rp.plate_text_canonical = pv.canonical_plate_ref AND pv.rn = 1
                    WHERE rp.plate_text_canonical LIKE ? OR pv.variant_text LIKE ?
                    ORDER BY rp.last_appearance_ts DESC
                    LIMIT ?
                '''
                cursor.execute(query, (f'%{search_term}%', f'%{search_term}%', limit))
                
                results = []
                for row in cursor.fetchall():
                    # Use best variant if available, otherwise use canonical
                    best_text = row[7] if row[7] else row[0]
                    best_confidence = row[8] if row[8] else row[6]
                    
                    results.append((
                        best_text,  # Use best variant text
                        row[1],     # detection_count
                        row[2],     # last_appearance_ts
                        row[3],     # first_appearance_ts
                        row[4],     # is_suspiciously_present
                        row[5],     # is_blacklisted
                        best_confidence  # Use best confidence
                    ))
                
                return results
        except Exception as e:
            logger.error(f"Error searching plates: {e}")
            return []
    
    def get_statistics(self, date=None):
        """Get statistics for a specific date or today"""
        try:
            if date is None:
                date = datetime.now().date()
            
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # Get or create today's statistics
                cursor.execute('''
                    SELECT * FROM statistics WHERE date = ?
                ''', (date,))
                
                stats = cursor.fetchone()
                if not stats:
                    # Calculate statistics
                    cursor.execute('''
                        SELECT COUNT(*) FROM original_detections 
                        WHERE DATE(detection_ts) = ?
                    ''', (date,))
                    total_detections = cursor.fetchone()[0]
                    
                    cursor.execute('''
                        SELECT COUNT(DISTINCT canonical_plate_text_ref) 
                        FROM original_detections 
                        WHERE DATE(detection_ts) = ?
                    ''', (date,))
                    unique_plates = cursor.fetchone()[0]
                    
                    cursor.execute('''
                        SELECT COUNT(*) FROM recognized_plates 
                        WHERE is_suspiciously_present = 1 
                        AND DATE(last_appearance_ts) = ?
                    ''', (date,))
                    suspicious_events = cursor.fetchone()[0]
                    
                    cursor.execute('''
                        SELECT COUNT(*) FROM recognized_plates 
                        WHERE is_blacklisted = 1 
                        AND DATE(last_appearance_ts) = ?
                    ''', (date,))
                    blacklist_hits = cursor.fetchone()[0]
                    
                    # Save statistics
                    cursor.execute('''
                        INSERT OR REPLACE INTO statistics 
                        (date, total_detections, unique_plates, suspicious_events, blacklist_hits)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (date, total_detections, unique_plates, suspicious_events, blacklist_hits))
                    self.conn.commit()
                    
                    return {
                        'date': date,
                        'total_detections': total_detections,
                        'unique_plates': unique_plates,
                        'suspicious_events': suspicious_events,
                        'blacklist_hits': blacklist_hits
                    }
                else:
                    return {
                        'date': stats[1],
                        'total_detections': stats[2],
                        'unique_plates': stats[3],
                        'suspicious_events': stats[4],
                        'blacklist_hits': stats[5]
                    }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return None
    
    def cleanup_old_data(self, days_to_keep=30):
        """Clean up old detection data"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            with self.db_lock:
                cursor = self.conn.cursor()
                
                # Delete old detections
                cursor.execute('''
                    DELETE FROM original_detections 
                    WHERE detection_ts < ?
                ''', (cutoff_date,))
                
                deleted_detections = cursor.rowcount
                
                # Delete plates with no recent detections
                cursor.execute('''
                    DELETE FROM recognized_plates 
                    WHERE last_appearance_ts < ? 
                    AND is_blacklisted = 0
                ''', (cutoff_date,))
                
                deleted_plates = cursor.rowcount
                
                self.conn.commit()
                logger.info(f"Cleanup: Deleted {deleted_detections} detections and {deleted_plates} plates")
                return deleted_detections, deleted_plates
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0, 0
    
    def export_data(self, filepath, start_date=None, end_date=None):
        """Export data to CSV file"""
        import csv
        
        try:
            with self.db_lock:
                cursor = self.conn.cursor()
                
                query = '''
                    SELECT plate_text_canonical, first_appearance_ts, last_appearance_ts,
                           detection_count, country_code, highest_confidence_achieved,
                           is_suspiciously_present, is_blacklisted
                    FROM recognized_plates
                '''
                
                conditions = []
                params = []
                
                if start_date:
                    conditions.append("first_appearance_ts >= ?")
                    params.append(start_date)
                
                if end_date:
                    conditions.append("last_appearance_ts <= ?")
                    params.append(end_date)
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY last_appearance_ts DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
            # Write to CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    'Plate', 'First Seen', 'Last Seen', 'Detection Count', 
                    'Country', 'Highest Confidence', 'Suspicious', 'Blacklisted'
                ])
                
                for row in rows:
                    writer.writerow(row)
            
            logger.info(f"Data exported to {filepath}")
            return len(rows)
        except Exception as e:
            logger.error(f"Export error: {e}")
            return 0
    
    def close(self):
        """Close database connection"""
        if self.conn:
            with self.db_lock:
                self.conn.close()
                self.conn = None
                logger.info("Database connection closed")