import re

DRIVE_FILE_ID = re.compile(r"drive\.google\.com/file/d/(?P<id>[a-zA-Z0-9_-]+)")
DOCS_PATH = re.compile(
    r"^https://docs\.google\.com/(?P<kind>document|spreadsheets|presentation)/d/(?P<id>[a-zA-Z0-9_-]+)"
)


def link_download_target(file_path):
    """Turn a stored preview/share URL into one that triggers a download."""
    if not file_path:
        return file_path
    drive_match = DRIVE_FILE_ID.search(file_path)
    if drive_match:
        file_id = drive_match.group("id")
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    docs_match = DOCS_PATH.match(file_path.split("?")[0].split("#")[0])
    if docs_match:
        kind = docs_match.group("kind")
        doc_id = docs_match.group("id")
        if kind == "spreadsheets":
            return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=xlsx"
        if kind == "presentation":
            return f"https://docs.google.com/presentation/d/{doc_id}/export/pptx"
        return f"https://docs.google.com/document/d/{doc_id}/export?format=pdf"
    return file_path
