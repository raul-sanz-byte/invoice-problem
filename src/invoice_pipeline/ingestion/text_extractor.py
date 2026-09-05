from pathlib import Path
from invoice_pipeline.models import FileFormat
from invoice_pipeline.llm_client import LLMClient

from .pdf_extractor import extract_from_pdf
from .json_extractor import extract_from_json
from .csv_extractor import extract_from_csv
from .xml_extractor import extract_from_xml
from .email_extractor import extract_from_email
from .txt_extractor import extract_from_text

def extract_text(file_path: str | Path, file_format: FileFormat, llm_client: LLMClient | None = None) -> tuple[str, dict | None]:
    """Router that dispatches to format-specific extractors."""
    path = Path(file_path)
    
    if file_format == FileFormat.PDF:
        text = extract_from_pdf(path, llm_client)
        return text, None
        
    # Read content for text-based formats
    content = ""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(path, 'r', encoding='latin-1') as f:
                content = f.read()
        except IOError:
            pass
    except IOError:
        pass

    if file_format == FileFormat.JSON:
        extracted = extract_from_json(content, llm_client=llm_client)
        return content, extracted
    elif file_format == FileFormat.CSV:
        extracted = extract_from_csv(content, llm_client=llm_client)
        if isinstance(extracted, dict):
            return content, extracted
        return extracted, None
    elif file_format == FileFormat.XML:
        extracted = extract_from_xml(content, llm_client=llm_client)
        return content, extracted
    elif file_format == FileFormat.EMAIL:
        body, metadata = extract_from_email(content)
        return body, metadata
    elif file_format == FileFormat.TEXT:
        text = extract_from_text(content)
        return text, None
        
    return content, None
