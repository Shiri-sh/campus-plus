import link_download


def test_drive_preview_url_becomes_export_download():
    url = "https://drive.google.com/file/d/abc123XYZ/preview"
    assert link_download.link_download_target(url) == (
        "https://drive.google.com/uc?export=download&id=abc123XYZ"
    )


def test_docs_document_url_exports_pdf():
    url = "https://docs.google.com/document/d/doc1/edit?usp=sharing"
    assert link_download.link_download_target(url) == (
        "https://docs.google.com/document/d/doc1/export?format=pdf"
    )


def test_non_google_link_is_unchanged():
    url = "https://example.com/video.mp4"
    assert link_download.link_download_target(url) == url
