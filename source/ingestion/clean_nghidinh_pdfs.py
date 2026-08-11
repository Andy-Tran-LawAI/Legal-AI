# -*- coding: utf-8 -*-
"""
clean_nghidinh_pdfs.py — Giai đoạn 2: Trích xuất và làm sạch dữ liệu Nghị định Ngân hàng
================================================================----------------------
PHIÊN BẢN CHUYỂN ĐỔI: Chuyên biệt cho Hệ thống Nghị định Ngành Ngân hàng - Tài chính
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
# BASE_DIR — tương thích Colab & local
# ---------------------------------------------------------------------------
def get_base_dir() -> Path:
    colab_path = Path("/content/drive/MyDrive/project")
    if colab_path.exists():
        return colab_path
    try:
        return Path(__file__).resolve().parent.parent.parent
    except NameError:
        return Path(".").resolve().parent.parent

BASE_DIR    = get_base_dir()
RAW_DIR     = BASE_DIR / "Data" / "raw"     / "nghidinh"
CLEANED_DIR = BASE_DIR / "Data" / "cleaned" / "nghidinh"
LOG_DIR     = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"clean_nghidinh_nganhang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
# Blacklist — Các file PDF KHÔNG xử lý
# ---------------------------------------------------------------------------
EXCLUDED_FILES = {
    # Ví dụ: Nghị định 101/2012/NĐ-CP đã hết hiệu lực hoàn toàn từ 01/07/2024
    "nd101_2012_thanh_toan_khong_dung_tien_mat_het_hieu_luc.pdf",
}

# ---------------------------------------------------------------------------
# Per-file strategy cho Hệ thống Nghị định Ngân hàng - Tài chính
# ---------------------------------------------------------------------------
FILE_STRATEGIES = {
    # 1. Nghị định 94/2025/NĐ-CP: Cơ chế thử nghiệm có kiểm soát (Regulatory Sandbox)
    "nd94_2025_co_che_thu_nghiem_ngan_hang.pdf": {
        "keep_all": True,
    },
    
    # 2. Nghị định 52/2024/NĐ-CP: Thanh toán không dùng tiền mặt
    "nd52_2024_thanh_toan_khong_dung_tien_mat.pdf": {
        "keep_all": True,
    },
    
    # 3. Nghị định 88/2019/NĐ-CP: Xử phạt VPHC lĩnh vực tiền tệ và ngân hàng
    "nd88_2019_xu_phat_tien_te_ngan_hang.pdf": {
        "keep_all": True,
    },
    
    # 4. Nghị định 143/2021/NĐ-CP: Sửa đổi, bổ sung NĐ 88/2019/NĐ-CP
    "nd143_2021_sua_doi_nd88_xu_phat.pdf": {
        "keep_all": True,
        "prepend_warning": (
            "⚠️ LƯU Ý: Nghị định 143/2021/NĐ-CP sửa đổi, bổ sung một số điều "
            "của Nghị định 88/2019/NĐ-CP về xử phạt VPHC trong lĩnh vực tiền tệ và ngân hàng.\n"
        )
    },
    
    # 5. Nghị định 86/2024/NĐ-CP: Trích lập dự phòng rủi ro và xử lý rủi ro TCTD
    "nd86_2024_trich_lap_du_phong_rui_ro.pdf": {
        "keep_all": True,
    },
    
    # 6. Nghị định 26/2025/NĐ-CP: Chức năng, nhiệm vụ, quyền hạn NHNN
    "nd26_2025_chuc_nang_nhiem_vu_nhnn.pdf": {
        "keep_all": True,
    },
    
    # 7. Nghị định 19/2023/NĐ-CP: Chi tiết Luật Phòng, chống rửa tiền
    "nd19_2023_chi_tiet_luat_phong_chong_rua_tien.pdf": {
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

# Tiêu đề cấu trúc văn bản quy phạm pháp luật Ngân hàng
RE_IS_HEADING    = re.compile(
    r"^(Phần\s+[IVXLCDM]+|Chương\s+[IVXLCDM]+|Mục\s+\d+|Điều\s+\d+|Khoản\s+\d+|"
    r"\d+\.\s+[A-ZĐÀÁẠẢÃ]|[a-z]\)\s+)",
    re.IGNORECASE
)

# Ký tự nối dòng hợp lệ
RE_MERGE_END     = re.compile(
    r'[a-zA-ZáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđĐ,;]$'
)

# ---------------------------------------------------------------------------
# Lọc block theo từ khóa (Dành cho strategy nâng cao nếu cần)
# ---------------------------------------------------------------------------
def should_keep_block(text: str, strategy: dict) -> bool:
    if strategy.get("keep_all", True):
        return True

    text_lower = text.lower()
    include_kws = strategy.get("include_section_keywords", [])
    exclude_kws = strategy.get("exclude_section_keywords", [])

    if include_kws:
        has_include = any(kw in text_lower for kw in include_kws)
        if not has_include:
            return False

    if exclude_kws:
        has_exclude = any(kw in text_lower for kw in exclude_kws)
        if has_exclude:
            return False

    return True


# ---------------------------------------------------------------------------
# Làm sạch text
# ---------------------------------------------------------------------------
def clean_text(raw_text: str, strategy: dict | None = None) -> str:
    if not raw_text:
        return ""

    text  = unicodedata.normalize("NFC", raw_text)
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if RE_HEADER_NOISE.match(line):  continue
        if RE_FOOTER_NOISE.search(line): continue
        if RE_PAGE_NUM.match(line):       continue

        line = RE_FORM_DOTS.sub(" [Cần điền thông tin] ", line)
        line = RE_CHECKBOX.sub(" [Lựa chọn] ", line).strip()
        if line in ("", "[Cần điền thông tin]", "[Lựa chọn]"):
            continue

        # Định dạng phân cấp Markdown chuẩn
        line = re.sub(r"^(Chương\s+[IVXLCDM]+.*|Phần\s+[IVXLCDM]+.*)$",
                      r"# \1", line, flags=re.IGNORECASE)
        line = re.sub(r"^(Mục\s+\d+.*)$",
                      r"## \1", line, flags=re.IGNORECASE)
        line = re.sub(r"^(Điều\s+\d+[.:].*|## Điều\s+\d+[.:].*)",
                      lambda m: "### " + m.group(0).lstrip("# "),
                      line, flags=re.IGNORECASE)

        # Bôi đậm ngày tháng
        line = re.sub(r"(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
                      r"**\1**", line, flags=re.IGNORECASE)

        cleaned_lines.append(line)

    # Nối dòng bị gãy — KHÔNG nối tiêu đề
    merged_lines = []
    for line in cleaned_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue
        prev = merged_lines[-1]
        if (RE_MERGE_END.search(prev[-1:])
                and (line[0].islower() or line[0] in 'áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ')
                and not RE_IS_HEADING.match(line)):
            merged_lines[-1] = prev + " " + line
        else:
            merged_lines.append(line)

    result = "\n".join(merged_lines)

    if strategy and strategy.get("prepend_warning"):
        result = f"> {strategy['prepend_warning']}\n\n{result}"

    return result


# ---------------------------------------------------------------------------
# Bảng → Markdown
# ---------------------------------------------------------------------------
def table_to_markdown(table_data: list) -> str:
    if not table_data:
        return ""
    table_data = [r for r in table_data if any(c and str(c).strip() for c in r)]
    if not table_data:
        return ""

    max_cols   = max(len(row) for row in table_data)
    table_data = [row + [""] * (max_cols - len(row)) for row in table_data]

    last_seen  = [""] * max_cols
    flattened  = []
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
        escaped = [c.replace("|", "\\|") for c in row]
        md_lines.append("| " + " | ".join(escaped) + " |")
        if i == 0:
            md_lines.append("|" + "|".join(["---"] * len(row)) + "|")

    return "\n".join(md_lines)


# ---------------------------------------------------------------------------
# Bbox helpers
# ---------------------------------------------------------------------------
def get_table_bboxes(page) -> list[tuple]:
    try:
        return [t.bbox for t in page.find_tables()]
    except Exception:
        return []

def is_inside_table(obj: dict, bboxes: list[tuple], tol: float = 2.0) -> bool:
    x0, top = obj.get("x0", 0), obj.get("top", 0)
    return any(
        tx0 - tol <= x0 <= tx1 + tol and ttop - tol <= top <= tbot + tol
        for tx0, ttop, tx1, tbot in bboxes
    )


# ---------------------------------------------------------------------------
# Xử lý chính
# ---------------------------------------------------------------------------
def process_pdfs():
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = list(RAW_DIR.glob("*.pdf"))
    logger.info(f"Tìm thấy {len(pdf_files)} file Nghị định Ngân hàng trong {RAW_DIR}")

    stats = {"total": len(pdf_files), "processed": 0, "skipped": 0, "errors": 0, "files": {}}

    for pdf_path in tqdm(pdf_files, desc="Xử lý Nghị định Ngân hàng", unit="file"):
        if pdf_path.name in EXCLUDED_FILES:
            logger.info(f"  [SKIP] {pdf_path.name} — nằm trong danh sách loại trừ")
            stats["skipped"] += 1
            continue

        strategy     = FILE_STRATEGIES.get(pdf_path.name, {"keep_all": True})
        full_content = []
        page_count = table_count = char_count = filtered_blocks = 0

        logger.info(f"  -> {pdf_path.name} | strategy: {'keep_all' if strategy.get('keep_all') else 'filtered'}")

        try:
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                for page in tqdm(pdf.pages, desc=f"   Trang {pdf_path.stem}", leave=False):
                    strict = {"vertical_strategy": "lines", "horizontal_strategy": "lines",
                              "snap_tolerance": 3, "join_tolerance": 3}

                    bboxes = get_table_bboxes(page)

                    if bboxes:
                        filtered_page = page.filter(lambda o: not is_inside_table(o, bboxes))
                        page_text = filtered_page.extract_text()
                    else:
                        page_text = page.extract_text()

                    if page_text:
                        cleaned = clean_text(page_text, strategy)
                        if cleaned:
                            if should_keep_block(cleaned, strategy):
                                full_content.append(cleaned)
                                char_count += len(cleaned)
                            else:
                                filtered_blocks += 1

                    for table in page.extract_tables(table_settings=strict):
                        md = table_to_markdown(table)
                        if md:
                            full_content.append("\n\n" + md + "\n\n")
                            table_count += 1

            out_name = pdf_path.stem + ".md"
            out_path = CLEANED_DIR / out_name
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(full_content))

            stats["processed"] += 1
            stats["files"][pdf_path.name] = {
                "pages": page_count, "tables": table_count,
                "chars": char_count, "filtered_blocks": filtered_blocks
            }
            logger.info(
                f"    ✓ {out_name} | {page_count}tr | {table_count}bảng | "
                f"{char_count:,}ký tự | {filtered_blocks} blocks bị lọc"
            )

        except Exception as e:
            logger.error(f"    ✗ Lỗi {pdf_path.name}: {e}", exc_info=True)
            stats["errors"] += 1

    logger.info("\n" + "="*60)
    logger.info(f"KẾT QUẢ: {stats['processed']} thành công | {stats['skipped']} bỏ qua | {stats['errors']} lỗi")
    stats_path = CLEANED_DIR / "_processing_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


if __name__ == "__main__":
    process_pdfs()
