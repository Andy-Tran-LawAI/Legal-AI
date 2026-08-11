# -*- coding: utf-8 -*-
"""
clean_thongtu_pdfs.py — Giai đoạn 2: Trích xuất và làm sạch dữ liệu Thông tư Ngân hàng
================================================================--------------------
PHIÊN BẢN CẬP NHẬT: Tích hợp Hệ thống 25 Thông tư Ngân hàng Nhà nước Việt Nam
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
# BASE_DIR
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
RAW_DIR     = BASE_DIR / "Data" / "raw"     / "thongtu"
CLEANED_DIR = BASE_DIR / "Data" / "cleaned" / "thongtu"
LOG_DIR     = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"clean_thongtu_nganhang_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
# Blacklist
# ---------------------------------------------------------------------------
EXCLUDED_FILES = set()

# ---------------------------------------------------------------------------
# Per-file strategy cho Danh sách Thông tư Ngân hàng
# ---------------------------------------------------------------------------
FILE_STRATEGIES = {
    # nhóm Thanh toán & Tài khoản
    "tt15_2024_dich_vu_thanh_toan_khong_dung_tien_mat.pdf": {"keep_all": True},
    "tt18_2024_hoat_dong_the_ngan_hang.pdf": {"keep_all": True},
    "tt17_2024_mo_va_su_dung_tai_khoan_thanh_toan.pdf": {"keep_all": True},
    "tt25_2025_sua_doi_tt17_tai_khoan_thanh_toan.pdf": {
        "keep_all": True,
        "merge_into": "tt17_2024_mo_va_su_dung_tai_khoan_thanh_toan.md",
        "prepend_marker": "\n\n---\n## [SỬA ĐỔI BỔ SUNG — THÔNG TƯ 25/2025/TT-NHNN]\n\n"
    },
    "tt40_2024_trung_gian_thanh_toan.pdf": {"keep_all": True},
    "tt41_2024_giam_sat_he_thong_thanh_toan.pdf": {"keep_all": True},

    # Nhóm Tín dụng & Cho vay
    "tt39_2016_cho_vay_to_chuc_tin_dung.pdf": {"keep_all": True},
    "tt06_2023_sua_doi_tt39_cho_vay.pdf": {
        "keep_all": True,
        "merge_into": "tt39_2016_cho_vay_to_chuc_tin_dung.md",
        "prepend_marker": "\n\n---\n## [SỬA ĐỔI BỔ SUNG — THÔNG TƯ 06/2023/TT-NHNN]\n\n"
    },
    "tt12_2024_sua_doi_tt39_cho_vay.pdf": {
        "keep_all": True,
        "merge_into": "tt39_2016_cho_vay_to_chuc_tin_dung.md",
        "prepend_marker": "\n\n---\n## [SỬA ĐỔI BỔ SUNG — THÔNG TƯ 12/2024/TT-NHNN]\n\n"
    },

    # Nhóm Đại lý thanh toán
    "tt07_2024_dai_ly_thanh_toan.pdf": {"keep_all": True},
    "tt06_2025_sua_doi_tt07_dai_ly_thanh_toan.pdf": {
        "keep_all": True,
        "merge_into": "tt07_2024_dai_ly_thanh_toan.md",
        "prepend_marker": "\n\n---\n## [SỬA ĐỔI BỔ SUNG — THÔNG TƯ 06/2025/TT-NHNN]\n\n"
    },

    # Nhóm Huy động vốn, Tiền gửi, Lãi suất
    "tt49_2018_tien_gui_co_ky_han.pdf": {"keep_all": True},
    "tt48_2018_tien_gui_tiet_kiem.pdf": {"keep_all": True},
    "tt48_2024_lai_suat_tien_gui_vnd.pdf": {"keep_all": True},
    "tt02_2025_phat_hanh_chung_chi_tien_gui.pdf": {"keep_all": True},

    # Nhóm Ngoại hối, An toàn hệ thống, Mạng lưới & Khác
    "tt06_2019_dau_tu_truc_tiep_ngoai_hoi.pdf": {"keep_all": True},
    "tt09_2020_an_toan_he_thong_thong_tin.pdf": {"keep_all": True},
    "tt50_2024_an_toan_bao_mat_dich_vu_truc_tuyen.pdf": {"keep_all": True},
    "tt64_2024_giao_dien_lap_trinh_ung_dung_mo.pdf": {"keep_all": True},
    "tt32_2024_mang_luoi_ngan_hang_thuong_mai.pdf": {"keep_all": True},
    "tt08_2025_sua_doi_mang_luoi_va_phong_giao_dich.pdf": {
        "keep_all": True,
        "merge_into": "tt32_2024_mang_luoi_ngan_hang_thuong_mai.md",
        "prepend_marker": "\n\n---\n## [SỬA ĐỔI BỔ SUNG — THÔNG TƯ 08/2025/TT-NHNN]\n\n"
    },
    "tt61_2024_bao_lanh_ngan_hang.pdf": {"keep_all": True},
    "tt38_2024_hoat_dong_tu_van_tctd.pdf": {"keep_all": True},
    "tt14_2025_ty_le_an_toan_von_nhtm.pdf": {"keep_all": True},
    "tt09_2023_huong_dan_phong_chong_rua_tien.pdf": {"keep_all": True},
}

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
RE_HEADER_NOISE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},.*about:blank$", re.MULTILINE)
RE_FOOTER_NOISE = re.compile(r"about:blank\s+\d+/\d+|Thư viện pháp luật|Mã tra cứu|CỔNG THÔNG TIN ĐIỆN TỬ", re.IGNORECASE)
RE_PAGE_NUM     = re.compile(r"^(Trang\s+)?\d+(\s*/\s*\d+)?$", re.IGNORECASE)
RE_FORM_DOTS    = re.compile(r"(\.{5,}|_{5,})")
RE_CHECKBOX     = re.compile(r"([☐☑\uf06f])")
RE_IS_HEADING   = re.compile(
    r"^(Điều\s+\d+|Khoản\s+\d+|Chương\s+[IVXLCDM]+|Phần\s+[IVXLCDM]+|"
    r"Mục\s+\d+|\d+\.\s+[A-ZĐÀÁẠẢÃ]|[a-z]\)\s+)",
    re.IGNORECASE
)
RE_MERGE_END    = re.compile(
    r'[a-zA-ZáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđĐ,;]$'
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def should_keep_block(text: str, strategy: dict) -> bool:
    if strategy.get("keep_all", True):
        return True
    text_lower = text.lower()
    inc = strategy.get("include_section_keywords", [])
    exc = strategy.get("exclude_section_keywords", [])
    if inc and not any(k in text_lower for k in inc):
        return False
    if exc and any(k in text_lower for k in exc):
        return False
    return True


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


def clean_text(raw_text: str, strategy: dict | None = None) -> str:
    if not raw_text:
        return ""
    text  = unicodedata.normalize("NFC", raw_text)
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:                        continue
        if RE_HEADER_NOISE.match(line):     continue
        if RE_FOOTER_NOISE.search(line):    continue
        if RE_PAGE_NUM.match(line):         continue
        line = RE_FORM_DOTS.sub(" [Cần điền thông tin] ", line)
        line = RE_CHECKBOX.sub(" [Lựa chọn] ", line).strip()
        if line in ("", "[Cần điền thông tin]", "[Lựa chọn]"):
            continue

        line = re.sub(r"^(Chương\s+[IVXLCDM]+.*|Phần\s+[IVXLCDM]+.*)$",
                      r"# \1", line, flags=re.IGNORECASE)
        line = re.sub(r"^(Mục\s+\d+.*)$",
                      r"## \1", line, flags=re.IGNORECASE)
        line = re.sub(r"^(Điều\s+\d+[.:].*)",
                      lambda m: "### " + m.group(0).lstrip("# "),
                      line, flags=re.IGNORECASE)
        line = re.sub(r"(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})",
                      r"**\1**", line, flags=re.IGNORECASE)
        cleaned_lines.append(line)

    merged_lines = []
    for line in cleaned_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue
        prev = merged_lines[-1]
        if (RE_MERGE_END.search(prev[-1:])
                and (line[0].islower() or
                     line[0] in 'áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ')
                and not RE_IS_HEADING.match(line)):
            merged_lines[-1] = prev + " " + line
        else:
            merged_lines.append(line)

    result = "\n".join(merged_lines)
    if strategy and strategy.get("prepend_warning"):
        result = f"> {strategy['prepend_warning']}\n\n{result}"
    return result


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
            cs = str(cell).replace("\n", " ").strip() if cell else ""
            if not cs and last_seen[j]:
                cs = last_seen[j]
            elif cs:
                last_seen[j] = cs
            new_row.append(cs)
        flattened.append(new_row)
    md_lines = []
    for i, row in enumerate(flattened):
        escaped = [c.replace("|", "\\|") for c in row]
        md_lines.append("| " + " | ".join(escaped) + " |")
        if i == 0:
            md_lines.append("|" + "|".join(["---"] * len(row)) + "|")
    return "\n".join(md_lines)


# ---------------------------------------------------------------------------
# Xử lý một file PDF
# ---------------------------------------------------------------------------
def process_single_pdf(pdf_path: Path, output_dir: Path, strategy: dict) -> dict:
    full_content = []
    page_count = table_count = char_count = filtered_blocks = 0

    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            strict = {"vertical_strategy": "lines", "horizontal_strategy": "lines",
                      "snap_tolerance": 3, "join_tolerance": 3}

            bboxes = get_table_bboxes(page)
            if bboxes:
                page_text = page.filter(lambda o: not is_inside_table(o, bboxes)).extract_text()
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
    out_path = output_dir / out_name

    merge_target = strategy.get("merge_into")
    if merge_target:
        target_path = output_dir / merge_target
        if target_path.exists():
            marker = strategy.get("prepend_marker", "\n\n---\n## [SỬA ĐỔI BỔ SUNG]\n\n")
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(marker)
                f.write("\n\n".join(full_content))
            logger.info(f"    ✓ Merged {pdf_path.name} → {target_path.name}")
        else:
            logger.warning(f"    ⚠ Không tìm thấy target merge: {target_path}, lưu riêng")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(full_content))
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(full_content))

    return {
        "pages": page_count, "tables": table_count,
        "chars": char_count, "filtered_blocks": filtered_blocks
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def process_pdfs():
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = list(RAW_DIR.rglob("*.pdf"))
    logger.info(f"Tìm thấy {len(pdf_files)} file thông tư trong {RAW_DIR}")

    stats = {"total": len(pdf_files), "processed": 0, "skipped": 0, "errors": 0, "files": {}}

    for pdf_path in tqdm(pdf_files, desc="Xử lý Thông tư Ngân hàng", unit="file"):
        if pdf_path.name in EXCLUDED_FILES:
            logger.info(f"  [SKIP] {pdf_path.name}")
            stats["skipped"] += 1
            continue

        rel_path   = pdf_path.relative_to(RAW_DIR)
        output_dir = CLEANED_DIR / rel_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        strategy = FILE_STRATEGIES.get(pdf_path.name, {"keep_all": True})
        logger.info(f"  -> {rel_path} | {'keep_all' if strategy.get('keep_all') else 'filtered'}")

        try:
            file_stats = process_single_pdf(pdf_path, output_dir, strategy)
            stats["processed"] += 1
            stats["files"][str(rel_path)] = file_stats
            logger.info(
                f"    ✓ {pdf_path.stem}.md | "
                f"{file_stats['pages']}tr | {file_stats['tables']}bảng | "
                f"{file_stats['chars']:,}ký tự | {file_stats['filtered_blocks']} blocks lọc"
            )
        except Exception as e:
            logger.error(f"    ✗ Lỗi {rel_path}: {e}", exc_info=True)
            stats["errors"] += 1

    logger.info("\n" + "="*60)
    logger.info(f"KẾT QUẢ: {stats['processed']} thành công | {stats['skipped']} bỏ qua | {stats['errors']} lỗi")
    stats_path = CLEANED_DIR / "_processing_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


if __name__ == "__main__":
    process_pdfs()
