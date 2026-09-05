import json
from pathlib import Path

from invoice_pipeline.models import FileFormat

def detect_format(file_path: str | Path, content: str | None = None) -> FileFormat:
    """Detects the format of an input file."""
    path = Path(file_path)
    
    # Check PDF magic bytes if content is not provided as string
    if path.exists() and path.is_file():
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
                if header.startswith(b'%PDF'):
                    return FileFormat.PDF
        except IOError:
            pass
            
    # Read text content if not provided
    if content is None:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except IOError:
                return FileFormat.TEXT
        except IOError:
            return FileFormat.TEXT

    stripped = content.strip()
    if not stripped:
        return FileFormat.TEXT

    # JSON
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            json.loads(content)
            return FileFormat.JSON
        except json.JSONDecodeError:
            pass

    # XML
    if stripped.startswith('<?xml') or (stripped.startswith('<') and '>' in stripped):
        # basic heuristic for XML
        return FileFormat.XML

    # Email
    lines = content.splitlines()
    first_10_lines = lines[:10]
    has_from = False
    has_to_or_subject = False
    for line in first_10_lines:
        lower_line = line.lower()
        if lower_line.startswith('from:'):
            has_from = True
        if lower_line.startswith('to:') or lower_line.startswith('subject:'):
            has_to_or_subject = True
            
    if has_from and has_to_or_subject:
        return FileFormat.EMAIL

    # CSV
    # Check for consistent delimiter patterns (commas/tabs) across multiple lines
    if len(lines) > 1:
        commas_first = lines[0].count(',')
        tabs_first = lines[0].count('\t')
        
        is_csv = False
        if commas_first > 0 or tabs_first > 0:
            is_csv = True
            # Check a few lines to see if they have similar delimiters
            for line in lines[1:5]:
                if not line.strip():
                    continue
                if commas_first > 0 and line.count(',') == 0:
                    is_csv = False
                    break
                if tabs_first > 0 and line.count('\t') == 0:
                    is_csv = False
                    break
        if is_csv:
            return FileFormat.CSV

    return FileFormat.TEXT
