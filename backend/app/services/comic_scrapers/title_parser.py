"""
Title Parser for Comic Scrapers
Centralized parsing of comic titles, issue numbers, volumes, bundles, and formats.
Replaces inline regex across zonacomics.py, megacomics.py, cbrcomics.py, comic_service.py
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TitleInfo:
    """Parsed information from a comic title"""
    # Original and cleaned title
    original_title: str = ""
    clean_title: str = ""

    # Issue info
    issue_number: Optional[int] = None

    # Volume info
    volume_number: Optional[int] = None

    # Range info (for bundles/collections)
    range_start: Optional[int] = None
    range_end: Optional[int] = None
    total_issues: Optional[int] = None

    # Bundle/collection format
    is_complete: bool = False
    is_collection: bool = False
    format_type: Optional[str] = None  # TPB, HC, Omnibus, Deluxe

    # Year
    year: Optional[int] = None

    @property
    def is_range(self) -> bool:
        return self.range_start is not None and self.range_end is not None

    @property
    def issues_covered(self) -> Optional[List[int]]:
        """Returns list of issue numbers covered by this range"""
        if self.is_range:
            return list(range(self.range_start, self.range_end + 1))
        if self.total_issues:
            return list(range(1, self.total_issues + 1))
        return None


# ============================================================================
# ISSUE NUMBER EXTRACTION
# ============================================================================

# Ordered by specificity (most specific first)
ISSUE_PATTERNS = [
    # #N, #01, #001 (most common)
    (r'#\s*0*(\d+)', 'issue_hash'),
    # [N] standalone bracket
    (r'\[(\d{1,3})\]', 'issue_bracket'),
    # Issue N / Issue 01
    (r'[Ii]ssue\s+0*(\d+)', 'issue_word'),
    # Numero N / Número N
    (r'[Nn][uú]mero\s+0*(\d+)', 'numero'),
    # Capitulo N / Capítulo N
    (r'[Cc]ap[ií]tulo\s+0*(\d+)', 'capitulo'),
]


def extract_issue_number(text: str) -> Optional[int]:
    """Extract issue number from text using multiple patterns"""
    for pattern, _ in ISSUE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


# ============================================================================
# VOLUME EXTRACTION
# ============================================================================

VOLUME_PATTERNS = [
    # Vol. N, Vol N, Volume N, Volumen N
    r'[Vv]ol(?:umen|ume)?\.?\s*(\d+)',
    # Tomo N
    r'[Tt]omo\s*0*(\d+)',
    # v3, v.3 (short form)
    r'\b[Vv]\.?\s*(\d+)\b',
]


def extract_volume_number(text: str) -> Optional[int]:
    """Extract volume number from text"""
    for pattern in VOLUME_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


# ============================================================================
# RANGE EXTRACTION (bundles/collections)
# ============================================================================

RANGE_PATTERNS = [
    # #1-5, #1-#5, #01-30
    (r'#\s*0*(\d+)\s*[-–]\s*#?\s*0*(\d+)', 'hash_range'),
    # Issues 1-30, Issue #1-#30
    (r'[Ii]ssues?\s*#?\s*0*(\d+)\s*[-–]\s*#?\s*0*(\d+)', 'issues_range'),
    # #1 al 30, #1 al #30 (Spanish)
    (r'#\s*0*(\d+)\s+al\s+#?\s*0*(\d+)', 'al_range'),
    # [X/Y], [X/Y?], [X/Y??]
    (r'\[(\d+)/(\d+)\?*\]', 'bracket_fraction'),
    # [X de Y] (Spanish: "5 de 5")
    (r'\[(\d+)\s+de\s+(\d+)\]', 'de_range'),
    # Volumen X Al Y (Spanish)
    (r'[Vv]olumen\s+(\d+)\s+[Aa]l\s+(\d+)', 'volumen_al'),
]


def extract_range(text: str) -> tuple:
    """
    Extract range from text.
    Returns (start, end) or (None, None) if no range found.
    """
    for pattern, _ in RANGE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


# ============================================================================
# TOTAL ISSUES EXTRACTION
# ============================================================================

TOTAL_PATTERNS = [
    # [9 Tomos], [9 tomos]
    r'\[(\d+)\s+[Tt]omos?\]',
    # [80 números], [80 numeros]
    r'\[(\d+)\s+[Nn][uú]meros?\]',
    # [15 volúmenes], [15 volumenes]
    r'\[(\d+)\s+[Vv]ol[uú]menes?\]',
    # (30 issues)
    r'\((\d+)\s+issues?\)',
    # X issues (in description text)
    r'(\d+)\s+issues?',
]


def extract_total_issues(text: str) -> Optional[int]:
    """Extract total issue count from text"""
    for pattern in TOTAL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


# ============================================================================
# FORMAT DETECTION
# ============================================================================

FORMAT_PATTERNS = {
    'TPB': r'\bTPB\b',
    'HC': r'\bHC\b',
    'Omnibus': r'\b[Oo]mnibus\b',
    'Deluxe': r'\b[Dd]eluxe\b',
    'Integral': r'\b[Ii]ntegral\b',
    'Absolute': r'\b[Aa]bsolute\b',
}

COMPLETE_PATTERNS = [
    r'\b[Cc]ompleto\b',
    r'\b[Cc]omplete\b',
    r'\b[Cc]ompleta\b',
    r'\bSaga\s+[Cc]ompleta\b',
    r'\bSerie\s+[Cc]ompleta\b',
    r'\b[Cc]olecci[oó]n\s+[Cc]ompleta\b',
]

COLLECTION_PATTERNS = [
    r'\b[Cc]olecci[oó]n\b',
    r'\b[Cc]ollection\b',
    r'\b[Cc]ollects?\b',
]


def detect_format(text: str) -> Optional[str]:
    """Detect comic format (TPB, HC, Omnibus, etc.)"""
    for fmt, pattern in FORMAT_PATTERNS.items():
        if re.search(pattern, text):
            return fmt
    return None


def is_complete(text: str) -> bool:
    """Check if text indicates a complete series"""
    return any(re.search(p, text) for p in COMPLETE_PATTERNS)


def is_collection(text: str) -> bool:
    """Check if text indicates a collection"""
    return any(re.search(p, text) for p in COLLECTION_PATTERNS)


# ============================================================================
# YEAR EXTRACTION
# ============================================================================

def extract_year(text: str) -> Optional[int]:
    """Extract publication year from text"""
    # (2019) - in parentheses first (most specific)
    match = re.search(r'\((\d{4})\)', text)
    if match:
        year = int(match.group(1))
        if 1900 <= year <= 2099:
            return year

    # Año: 2019 (Spanish metadata)
    match = re.search(r'[Aa][ñn]o\s*:\s*(\d{4})', text)
    if match:
        return int(match.group(1))

    # Standalone year
    match = re.search(r'\b(19|20)\d{2}\b', text)
    if match:
        return int(match.group())
    return None


# ============================================================================
# TITLE CLEANING
# ============================================================================

def clean_title(title: str) -> str:
    """Remove metadata brackets, format indicators, etc. from title"""
    cleaned = title
    # Remove [X/Y], [X Tomos], etc.
    cleaned = re.sub(r'\s*\[.*?\]', '', cleaned)
    # Remove (2019), (TPB), etc.
    cleaned = re.sub(r'\s*\((?:\d{4}|TPB|HC|Omnibus|Deluxe)\)', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_title(title: str) -> str:
    """Normalize title for comparison (lowercase, no punctuation, single spaces)"""
    normalized = title.lower()
    normalized = re.sub(r'\s*\(.*?\)\s*', ' ', normalized)
    normalized = re.sub(r'\s*\[.*?\]\s*', ' ', normalized)
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


# ============================================================================
# FILE SIZE EXTRACTION
# ============================================================================

def extract_file_size(text: str) -> Optional[str]:
    """Extract file size from text (e.g., '500 MB', '1.5 GB')"""
    # Tamaño: 500 MB (Spanish)
    match = re.search(r'[Tt]ama[ñn]o\s*:\s*([\d.,]+\s*[GMK]?B)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Generic: 500 MB, 1.5 GB
    match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|GB)', text, re.IGNORECASE)
    if match:
        return match.group(0)
    return None


# ============================================================================
# FILENAME-BASED ISSUE EXTRACTION (for downloaded files)
# ============================================================================

FILENAME_ISSUE_PATTERNS = [
    # #01, #1 (most specific)
    (r'#\s*0*(\d+)', 'hash'),
    # Issue 01
    (r'[Ii]ssue\s*0*(\d+)', 'issue'),
    # Tomo 01
    (r'[Tt]omo\s*0*(\d+)', 'tomo'),
    # Trailing number before extension: _01.cbz, -03.cbr, .05.cbz
    (r'[-_\s.]0*(\d{1,3})\.[a-zA-Z]{2,4}$', 'trailing'),
    # Vol/Volume/Volumen as last resort
    (r'[Vv]ol(?:ume|umen)?\.?\s*(\d+)', 'volume'),
]


def extract_issue_from_filename(filename: str) -> Optional[int]:
    """Extract issue number from a filename, using priority-based patterns"""
    for pattern, _ in FILENAME_ISSUE_PATTERNS:
        match = re.search(pattern, filename)
        if match:
            return int(match.group(1))
    return None


# ============================================================================
# MAIN PARSER
# ============================================================================

def parse_title(title: str) -> TitleInfo:
    """
    Parse a comic title and extract all available information.

    Args:
        title: Raw comic title string

    Returns:
        TitleInfo with all extracted metadata
    """
    info = TitleInfo(original_title=title)
    info.clean_title = clean_title(title)
    info.issue_number = extract_issue_number(title)
    info.volume_number = extract_volume_number(title)
    info.range_start, info.range_end = extract_range(title)
    info.total_issues = extract_total_issues(title)
    info.is_complete = is_complete(title)
    info.is_collection = is_collection(title)
    info.format_type = detect_format(title)
    info.year = extract_year(title)

    # If we have a [X/Y] pattern, total_issues should be Y
    if info.is_range and info.range_end and not info.total_issues:
        info.total_issues = info.range_end

    return info
