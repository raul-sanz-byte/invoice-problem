import email
from email.policy import default

def extract_from_email(content: str) -> tuple[str, dict]:
    """Extracts the invoice text and metadata from an email body."""
    msg = email.message_from_string(content, policy=default)
    
    metadata = {
        'from': msg.get('From', ''),
        'to': msg.get('To', ''),
        'subject': msg.get('Subject', ''),
        'date': msg.get('Date', '')
    }
    
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                body_bytes = part.get_payload(decode=True)
                if body_bytes:
                    body += body_bytes.decode(part.get_content_charset('utf-8') or 'utf-8', errors='replace')
    else:
        body_bytes = msg.get_payload(decode=True)
        if body_bytes:
            body = body_bytes.decode(msg.get_content_charset('utf-8') or 'utf-8', errors='replace')
        else:
            body = msg.get_payload()

    # Simple signature stripping
    body_lines = body.splitlines()
    cleaned_lines = []
    for line in body_lines:
        lower_line = line.strip().lower()
        if lower_line in ('best regards', 'best regards,', 'sincerely', 'sincerely,', 'thanks,', 'thanks'):
            break
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines).strip(), metadata
