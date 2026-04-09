import json
import csv
from pathlib import Path

def parse_file(path: str) -> str:
    ext = Path(path).suffix.lower()

    if ext in [".txt", ".md", ".py"]:
        return open(path, "r", encoding="utf-8").read()

    if ext == ".json":
        return json.dumps(json.load(open(path)), indent=2)

    if ext == ".csv":
        with open(path) as f:
            return "\n".join(",".join(row) for row in csv.reader(f))

    if ext == ".pdf":
        from pdfminer.high_level import extract_text
        return extract_text(path)

    if ext == ".docx":
        import docx
        d = docx.Document(path)
        return "\n".join(p.text for p in d.paragraphs)

    return "[Unsupported file]"