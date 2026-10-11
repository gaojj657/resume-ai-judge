from pathlib import Path
from threading import Lock
from PIL import Image, ImageOps

_ocr_lock = Lock()
_ocr = None


def image_text(image):
    global _ocr
    import numpy as np
    with _ocr_lock:
        if _ocr is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise ValueError("图片或扫描PDF需要OCR，请安装 requirements-ocr.txt 后重启") from exc
            _ocr = PaddleOCR(use_doc_orientation_classify=True, enable_mkldnn=False,
                             use_doc_unwarping=False, use_textline_orientation=True,
                             text_detection_model_name="PP-OCRv5_mobile_det",
                             text_recognition_model_name="PP-OCRv5_mobile_rec")
        image = ImageOps.exif_transpose(image).convert("RGB")
        result = list(_ocr.predict(np.asarray(image)))
        return "\n".join(text for page in result for text in page.get("rec_texts", []))


def parse_file(path, max_pages=30):
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(path)
        blocks = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                text = Paragraph(child, doc).text.strip()
                if text:
                    blocks.append(text)
            elif tag == "tbl":
                rows = [[cell.text.replace("\n", " ").replace("|", "／") for cell in row.cells]
                        for row in Table(child, doc).rows]
                if rows:
                    blocks.append("\n".join(" | ".join(row) for row in rows))
        text = "\n\n".join(f"[段落{i + 1}]\n{block}" for i, block in enumerate(blocks))
    elif suffix == ".pdf":
        import pdfplumber
        import pypdfium2 as pdfium
        blocks = []
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > max_pages:
                raise ValueError(f"PDF最多支持{max_pages}页")
            for i, page in enumerate(pdf.pages):
                extracted = (page.extract_text() or "").strip()
                if len(extracted.replace(" ", "")) < 20:
                    document = pdfium.PdfDocument(path)
                    try:
                        render_page = document[i]
                        bitmap = render_page.render(scale=2)
                        try:
                            extracted = image_text(bitmap.to_pil())
                        finally:
                            bitmap.close()
                            render_page.close()
                    finally:
                        document.close()
                blocks.append(f"## 第{i + 1}页\n\n{extracted}")
        text = "\n\n".join(blocks)
    else:
        with Image.open(path) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("图片尺寸过大，请压缩后上传")
            text = "## 第1页\n\n" + image_text(image)
    if not text.strip() or len(text.strip()) < 15:
        raise ValueError("未识别到足够的文本，请检查文件内容")
    if len(text) > 100_000:
        raise ValueError("解析文本过长，请精简文档；系统未截断内容")
    return text

