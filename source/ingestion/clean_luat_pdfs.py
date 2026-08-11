# -*- coding: utf-8 -*-
"""
clean_luat_pdfs.py — Giai đoạn 2: Trích xuất và làm sạch dữ liệu Luật Ngân hàng
==============================================================================
PHIÊN BẢN CHUYỂN ĐỔI: Chuyên biệt cho Hệ thống Pháp luật Ngân hàng - Tài chính
"""

import os
import re
import unicodedata
import logging
import json
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    raise ImportError("Chạy: pip install pdfplumber")

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **kwargs):
        return iterable

# ---------------------------------------------------------------------------
# Cấu hình đường dẫn — tương thích Colab và local
# ---------------------------------------------------------------------------
def get_base_dir() -> Path:
    """Tự động phát hiện môi trường Colab hoặc local."""
    colab_path = Path("/content/drive/MyDrive/project")
    if colab_path.exists():
        return colab_path
    try:
        return Path(__file__).resolve().parent.parent.parent
    except NameError:
        return Path(".").resolve().parent.parent

BASE_DIR         = get_base_dir()
RAW_LUAT_DIR     = BASE_DIR / "Data" / "raw"     / "luat"
CLEANED_LUAT_DIR = BASE_DIR / "Data" / "cleaned" / "luat"
LOG_DIR          = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Setup Logging
# ---------------------------------------------------------------------------
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"clean_luat_nganhang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ---------------------------------------------------------------------------
# Blacklist — Các file PDF KHÔNG xử lý hoặc bị loại bỏ
# ---------------------------------------------------------------------------
EXCLUDED_FILES = {
    # Ví dụ: Luật Các TCTD 2010 cũ đã hết hiệu lực hoàn toàn từ 01/07/2024
    "luat_47_2010_qh12_cac_to_chuc_tin_dung_het_hieu_luc.pdf",
}

# ---------------------------------------------------------------------------
# Per-file strategy cho Hệ thống Luật Ngân hàng - Tài chính
# ---------------------------------------------------------------------------
FILE_STRATEGIES = {
    # 1. Luật Ngân hàng Nhà nước Việt Nam (46/2010/QH12)
    "luat_46_2010_qh12_ngan_hang_nha_nuoc.pdf": {
        "keep_all": True,
    },
    
    # 2. Luật Các tổ chức tín dụng (32/2024/QH15)
    "luat_32_2024_qh15_cac_to_chuc_tin_dung.pdf": {
        "keep_all": True,
    },
    
    # 3. Luật Sửa đổi, bổ sung một số điều của Luật Đất đai, Luật Nhà ở, 
    #    Luật Kinh doanh BĐS và Luật Các TCTD (43/2024/QH15)
    "luat_43_2024_qh15_sua_doi_cac_luat.pdf": {
        "keep_all": True,
        "prepend_warning": (
            "⚠️ LƯU Ý: Luật 43/2024/QH15 sửa đổi, bổ sung hiệu lực và một số điều của "
            "Luật Đất đai 31/2024/QH15, Luật Nhà ở 27/2023/QH15, Luật Kinh doanh BĐS 29/2023/QH15 "
            "và Luật Các TCTD 32/2024/QH15 (có hiệu lực từ 01/08/2024).\n"
        )
    },
    
    # 4. Luật Sửa đổi, bổ sung một số điều của Luật Các TCTD (96/2025/QH15)
    "luat_96_2025_qh15_sua_doi_luat_tctd.pdf": {
        "keep_all": True,
        "prepend_warning": (
            "⚠️ LƯU Ý: Luật 96/2025/QH15 bổ sung, sửa đổi một số điều của "
            "Luật Các tổ chức tín dụng 32/2024/QH15 (có hiệu lực từ 15/10/2025).\n"
        )
    },
    
    # 5. Luật Phòng, chống rửa tiền (14/2022/QH15)
    "luat_14_2022_qh15_phong_chong_rua_tien.pdf": {
        "keep_all": True,
    },
}

# ---------------------------------------------------------------------------
# Regex làm sạch
# ---------------------------------------------------------------------------
RE_HEADER_NOISE  = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},.*about:blank$", re.MULTILINE)
RE_FOOTER_NOISE  = re.compile(r"about:blank\s+\d+/\d+|Thư viện pháp luật|Mã tra cứu|CỔNG THÔNG TIN ĐIỆN TỬ", re.IGNORECASE)
RE_PAGE_NUM      = re.compile(r"^(Trang\s+)?\d+(\s*/\s*\d+)?$", re.IGNORECASE)
RE_FORM_DOTS     = re.compile(r"(\.{5,}|_{5,})")
RE_CHECKBOX      = re.compile(r"([☐☑\uf06f])")

# Phát hiện tiêu đề cấu trúc Ngân hàng — KHÔNG được nối với dòng trên
RE_IS_HEADING    = re.compile(
    r"^(Phần\s+[IVXLCDM]+|Chương\s+[IVXLCDM]+|Mục\s+\d+|Điều\s+\d+|Khoản\s+\d+|"
    r"\d+\.\s+[A-ZĐÀÁẠẢÃ]|[a-z]\)\s+)",
    re.IGNORECASE
)

# Ký tự kết thúc câu hợp lệ để nối dòng
RE_MERGE_ELIGIBLE_END = re.compile(
    r'[a-zA-ZáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđĐ,;]$'
)

# ---------------------------------------------------------------------------
# Hàm làm sạch text
# ---------------------------------------------------------------------------
def clean_text(raw_text: str, strategy: dict | None = None) -> str:
    """
    Làm sạch text văn bản luật Ngân hàng: loại nhiễu, định dạng Markdown, nối dòng.
    """
    if not raw_text:
        return ""

    text = unicodedata.normalize("NFC", raw_text)
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # --- Lọc nhiễu trang/đầu trang/cuối trang ---
        if RE_HEADER_NOISE.match(line):   continue
        if RE_FOOTER_NOISE.search(line):  continue
        if RE_PAGE_NUM.match(line):        continue

        # --- Lọc biểu mẫu điền ---
        line = RE_FORM_DOTS.sub(" [Cần điền thông tin] ", line)
        line = RE_CHECKBOX.sub(" [Lựa chọn] ", line).strip()
        if line in ("", "[Cần điền thông tin]", "[Lựa chọn]"):
            continue

        # --- Định dạng phân cấp Markdown chuẩn ---
        line = re.sub(
            r"^(Chương\s+[IVXLCDM]+.*|Phần\s+[IVXLCDM]+.*)$",
            r"# \1", line, flags=re.IGNORECASE
        )
        line = re.sub(
            r"^(Mục\s+\d+.*)$",
            r"## \1", line, flags=re.IGNORECASE
        )
        line = re.sub(
            r"^(Điều\s+\d+[.:].*|## Điều\s+\d+[.:].*)",
            lambda m: "### " + m.group(0).lstrip("# "),
            line, flags=re.IGNORECASE
        )

        # --- Bôi đậm ngày tháng/số hiệu văn bản ---
        line = re.sub(
            r"(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
            r"**\1**", line, flags=re.IGNORECASE
        )

        cleaned_lines.append(line)

    # --- Nối dòng bị gãy ---
    merged_lines = []
    for line in cleaned_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue

        prev = merged_lines[-1]
        prev_ends_mid_sentence = RE_MERGE_ELIGIBLE_END.search(prev[-1:]) if prev else False
        curr_is_heading        = RE_IS_HEADING.match(line)
        curr_starts_lowercase  = (
            line[0].islower() or
            line[0] in 'áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ'
        )

        if prev_ends_mid_sentence and curr_starts_lowercase and not curr_is_heading:
            merged_lines[-1] = prev + " " + line
        else:
            merged_lines.append(line)

    result = "\n".join(merged_lines)

    if strategy and strategy.get("prepend_warning"):
        result = f"> {strategy['prepend_warning']}\n\n{result}"

    return result


# ---------------------------------------------------------------------------
# Chuyển bảng sang Markdown
# ---------------------------------------------------------------------------
def table_to_markdown(table_data: list) -> str:
    """Chuyển list-of-lists thành Markdown Table, flatten ô gộp chiều dọc."""
    if not table_data:
        return ""

    table_data = [
        row for row in table_data
        if any(cell and str(cell).strip() for cell in row)
    ]
    if not table_data:
        return ""

    max_cols = max(len(row) for row in table_data)
    table_data = [row + [""] * (max_cols - len(row)) for row in table_data]

    last_seen = [""] * max_cols
    flattened = []

    for row in table_data:
        new_row = []
        for j, cell in enumerate(row):
            cell_str = str(cell).replace("\n", " ").strip() if cell else ""
            if not cell_str and last_seen[j]:
                cell_str = last_seen[j]
            elif cell_str:
                last_seen[j] = cell_str
            new_row.append(cell_str)
        flattened.append(new_row)

    md_lines = []
    for i, row in enumerate(flattened):
        escaped = [cell.replace("|", "\\|") for cell in row]
        md_lines.append("| " + " | ".join(escaped) + " |")
        if i == 0:
            md_lines.append("|" + "|".join(["---"] * len(row)) + "|")

    return "\n".join(md_lines)


# ---------------------------------------------------------------------------
# Xử lý Bbox Bảng
# ---------------------------------------------------------------------------
def get_table_bboxes(page) -> list[tuple]:
    try:
        return [tbl.bbox for tbl in page.find_tables()]
    except Exception:
        return []


def is_inside_table(obj: dict, bboxes: list[tuple], tolerance: float = 2.0) -> bool:
    x0 = obj.get("x0", 0)
    top = obj.get("top", 0)
    for (tx0, ttop, tx1, tbottom) in bboxes:
        if (tx0 - tolerance <= x0 and
                x0 <= tx1 + tolerance and
                ttop - tolerance <= top and
                top <= tbottom + tolerance):
            return True
    return False


# ---------------------------------------------------------------------------
# Hàm xử lý chính
# ---------------------------------------------------------------------------
def process_law_pdfs():
    CLEANED_LUAT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = list(RAW_LUAT_DIR.glob("*.pdf"))
    logger.info(f"Tìm thấy {len(pdf_files)} file Luật Ngân hàng trong {RAW_LUAT_DIR}")

    stats = {
        "total": len(pdf_files),
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "files": {}
    }

    for pdf_path in tqdm(pdf_files, desc="Xử lý Luật Ngân hàng", unit="file"):
        if pdf_path.name in EXCLUDED_FILES:
            logger.info(f"  [SKIP] {pdf_path.name} — nằm trong danh sách loại trừ")
            stats["skipped"] += 1
            continue

        strategy = FILE_STRATEGIES.get(pdf_path.name, {"keep_all": True})
        logger.info(f"  -> Đang xử lý: {pdf_path.name} | strategy: {strategy}")

        full_content = []
        page_count   = 0
        table_count  = 0
        char_count   = 0

        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)

                for page in tqdm(pdf.pages, desc=f"   Trang {pdf_path.stem}", leave=False):
                    strict_settings = {
                        "vertical_strategy":   "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance":      3,
                        "join_tolerance":      3,
                    }

                    table_bboxes = get_table_bboxes(page)

                    if table_bboxes:
                        filtered_page = page.filter(
                            lambda obj: not is_inside_table(obj, table_bboxes)
                        )
                        page_text = filtered_page.extract_text()
                    else:
                        page_text = page.extract_text()

                    if page_text:
                        cleaned = clean_text(page_text, strategy)
                        if cleaned:
                            full_content.append(cleaned)
                            char_count += len(cleaned)

                    extracted_tables = page.extract_tables(table_settings=strict_settings)
                    for table in extracted_tables:
                        md_table = table_to_markdown(table)
                        if md_table:
                            full_content.append("\n\n" + md_table + "\n\n")
                            table_count += 1

            output_filename = pdf_path.stem + ".md"
            output_path     = CLEANED_LUAT_DIR / output_filename

            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(full_content))

            stats["processed"] += 1
            stats["files"][pdf_path.name] = {
                "pages": page_count,
                "tables": table_count,
                "chars": char_count,
                "output": str(output_path)
            }
            logger.info(
                f"    ✓ Hoàn tất: {output_filename} "
                f"| {page_count} trang | {table_count} bảng | {char_count:,} ký tự"
            )

        except Exception as e:
            logger.error(f"    ✗ Lỗi khi xử lý {pdf_path.name}: {e}", exc_info=True)
            stats["errors"] += 1

    logger.info("\n" + "="*60)
    logger.info("THỐNG KÊ XỬ LÝ LUẬT NGÂN HÀNG:")
    logger.info(f"  Tổng:         {stats['total']}")
    logger.info(f"  Thành công:   {stats['processed']}")
    logger.info(f"  Bỏ qua:       {stats['skipped']}")
    logger.info(f"  Lỗi:          {stats['errors']}")

    stats_path = CLEANED_LUAT_DIR / "_processing_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info(f"  Stats đã lưu tại: {stats_path}")

    return stats


if __name__ == "__main__":
    process_law_pdfs()
