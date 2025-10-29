"""
Improved Levenshtein distance algorithm for license plate matching
"""

import re
from config import logger

# Character similarity mappings (common OCR mistakes)
SIMILAR_CHARS = {
    '0': ['O', 'Q', 'D'],
    'O': ['0', 'Q', 'D'],
    '1': ['I', 'L', '7'],
    'I': ['1', 'L', '7'],
    'L': ['1', 'I', '7'],
    '5': ['S'],
    'S': ['5'],
    '8': ['B'],
    'B': ['8'],
    '6': ['G'],
    'G': ['6', 'C'],
    'C': ['G', 'O'],
    '2': ['Z'],
    'Z': ['2'],
    'E': ['F'],
    'F': ['E'],
    'P': ['R'],
    'R': ['P'],
    'M': ['N'],
    'N': ['M'],
    'U': ['V'],
    'V': ['U'],
    'K': ['X'],
    'X': ['K'],
}

def normalize_plate(plate_text):
    """
    Normalize plate text for comparison
    Remove spaces, dashes, dots and convert to uppercase
    """
    if not plate_text:
        return ""
    
    # Convert to uppercase
    normalized = plate_text.upper()
    
    # Remove all separators and special characters
    normalized = re.sub(r'[\s\-_.,/\\]', '', normalized)
    
    return normalized

def improved_levenshtein(s1, s2, consider_similar=True):
    """
    Improved Levenshtein distance with:
    - Character similarity consideration
    - Different weights for different operations
    - Normalization before comparison
    """
    
    # Normalize both strings
    s1_norm = normalize_plate(s1)
    s2_norm = normalize_plate(s2)
    
    # If normalized strings are identical, distance is 0
    if s1_norm == s2_norm:
        return 0
    
    len1, len2 = len(s1_norm), len(s2_norm)
    
    # Initialize distance matrix
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    # Initialize first row and column
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j
    
    # Calculate distances
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            char1 = s1_norm[i - 1]
            char2 = s2_norm[j - 1]
            
            if char1 == char2:
                # Characters match - no cost
                cost = 0
            elif consider_similar and are_similar_chars(char1, char2):
                # Similar characters - reduced cost
                cost = 0.5
            else:
                # Different characters - full cost
                cost = 1
            
            # Calculate minimum distance
            deletion = matrix[i - 1][j] + 1
            insertion = matrix[i][j - 1] + 1
            substitution = matrix[i - 1][j - 1] + cost
            
            matrix[i][j] = min(deletion, insertion, substitution)
    
    return matrix[len1][len2]

def are_similar_chars(char1, char2):
    """
    Check if two characters are similar (commonly confused in OCR)
    """
    if char1 == char2:
        return True
    
    # Check if char2 is in the similar chars list for char1
    if char1 in SIMILAR_CHARS and char2 in SIMILAR_CHARS[char1]:
        return True
    
    # Check reverse mapping
    if char2 in SIMILAR_CHARS and char1 in SIMILAR_CHARS[char2]:
        return True
    
    return False

def calculate_similarity_score(s1, s2):
    """
    Calculate similarity score between 0 and 100
    Higher score means more similar
    """
    distance = improved_levenshtein(s1, s2)
    max_len = max(len(normalize_plate(s1)), len(normalize_plate(s2)))
    
    if max_len == 0:
        return 100.0
    
    # Convert distance to similarity percentage
    similarity = (1 - distance / max_len) * 100
    return max(0, min(100, similarity))

def find_best_match(target_plate, plate_list, threshold=80):
    """
    Find best matching plate from a list
    
    Args:
        target_plate: The plate to match
        plate_list: List of plates to search in
        threshold: Minimum similarity score to consider a match (0-100)
    
    Returns:
        Tuple of (best_match, similarity_score) or (None, 0) if no match
    """
    best_match = None
    best_score = 0
    
    for plate in plate_list:
        score = calculate_similarity_score(target_plate, plate)
        if score >= threshold and score > best_score:
            best_match = plate
            best_score = score
    
    return best_match, best_score

def group_similar_plates(plate_list, threshold=85):
    """
    Group similar plates together
    
    Args:
        plate_list: List of plates to group
        threshold: Similarity threshold for grouping
    
    Returns:
        List of groups, each group is a list of similar plates
    """
    groups = []
    processed = set()
    
    for i, plate1 in enumerate(plate_list):
        if i in processed:
            continue
        
        group = [plate1]
        processed.add(i)
        
        for j, plate2 in enumerate(plate_list[i+1:], start=i+1):
            if j in processed:
                continue
            
            # Check similarity with any plate in current group
            for group_plate in group:
                score = calculate_similarity_score(group_plate, plate2)
                if score >= threshold:
                    group.append(plate2)
                    processed.add(j)
                    break
        
        groups.append(group)
    
    return groups

def get_adaptive_threshold(plate_length):
    """
    Get adaptive threshold based on plate length
    Shorter plates need higher similarity, longer plates can have more variations
    """
    if plate_length <= 4:
        return 90  # Very strict for short plates
    elif plate_length <= 6:
        return 85
    elif plate_length <= 8:
        return 80
    else:
        return 75  # More lenient for long plates

def merge_plate_variants(variants):
    """
    Merge plate variants and return the most common pattern
    
    Args:
        variants: List of tuples (plate_text, confidence)
    
    Returns:
        Best variant based on confidence and frequency
    """
    if not variants:
        return None
    
    # Count frequency and track max confidence for each normalized form
    normalized_stats = {}
    
    for plate_text, confidence in variants:
        normalized = normalize_plate(plate_text)
        
        if normalized not in normalized_stats:
            normalized_stats[normalized] = {
                'count': 0,
                'max_confidence': 0,
                'best_original': plate_text,
                'all_variants': []
            }
        
        stats = normalized_stats[normalized]
        stats['count'] += 1
        stats['all_variants'].append(plate_text)
        
        if confidence > stats['max_confidence']:
            stats['max_confidence'] = confidence
            stats['best_original'] = plate_text
    
    # Find best variant based on confidence and frequency
    best_normalized = max(
        normalized_stats.keys(),
        key=lambda k: (
            normalized_stats[k]['max_confidence'] * 0.7 +  # 70% weight on confidence
            normalized_stats[k]['count'] * 30  # 30% weight on frequency
        )
    )
    
    return normalized_stats[best_normalized]['best_original']