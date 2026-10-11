"""Integration smoke check using synthetic text, not a real resume."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from app import create_app
from app.parsers import parse_file

create_app({"START_WORKER": False})
root = Path(__file__).resolve().parents[1] / "test-results"
root.mkdir(exist_ok=True)
image = Image.new("RGB", (1500, 900), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 48)
for i, line in enumerate(["简历 张三", "学历：本科 专业：计算机科学", "技能：Python SQL Flask", "项目经历：使用Python完成数据分析项目。", "实习经历：后端开发实习生。"]):
    draw.text((80, 80 + i * 140), line, fill="black", font=font)
image.save(root / "ocr-sample.png")
image.save(root / "ocr-sample.pdf", "PDF", resolution=150)
for filename in ("ocr-sample.png", "ocr-sample.pdf"):
    result = parse_file(str(root / filename))
    assert "Python" in result, result
    assert "本科" in result, result
    print(filename, "OCR passed", flush=True)
    (root / (filename + ".md")).write_text(result, encoding="utf-8")
