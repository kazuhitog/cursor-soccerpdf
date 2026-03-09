from pathlib import Path
from typing import List

import pdfplumber


def read_pdf_lines(pdf_path: Path) -> List[str]:
    """
    PDF からテキストを行単位で取得してリストで返す。
    行の前後の空白は strip 済み。
    """
    pdf_path = Path(pdf_path)
    lines: List[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if line:
                    lines.append(line)
    return lines


__all__ = ["read_pdf_lines"]

