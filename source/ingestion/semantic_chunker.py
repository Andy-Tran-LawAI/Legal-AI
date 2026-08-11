# -*- coding: utf-8 -*-
"""
semantic_chunker.py — Giai đoạn 3: Phân đoạn ngữ cảnh (Semantic Chunking)
================================================================--------
Tự động bóc tách và phân đoạn các file Markdown pháp luật Ngân hàng
thành các Chunks ngữ nghĩa cấp Điều/Khoản/Điểm kèm Context Enrichment & Metadata.
"""

import os
import re
import json
import yaml
import hashlib
import logging
from pathlib import Path
from datetime import datetime

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
        return Path(__file__).resolve().parent.parent
    except NameError:
        return Path(".").resolve().parent

BASE_DIR    = get_base_dir()
CLEANED_DIR = BASE_DIR / "Data" / "cleaned"
CHUNKED_DIR = BASE_DIR / "Data" / "chunked"
JSONL_PATH  = BASE_DIR / "Data" / "all_banking_chunks.jsonl"
LOG_DIR     = BASE_DIR / "logs"

# ---------------------------------------------------------------------------
# FULL METADATA LOOKUP TABLE (37 VĂN BẢN PHÁP LUẬT NGÂN HÀNG)
# ---------------------------------------------------------------------------
DOC_METADATA_LOOKUP = {
    # 1. NHÓM LUẬT
    "luat_cac_to_chuc_tin_dung_2024": {
        "doc_name": "Luật Các tổ chức tín dụng 2024",
        "doc_code": "32/2024/QH15",
        "issuer": "Quốc hội",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "luat_nhnn_2010": {
        "doc_name": "Luật Ngân hàng Nhà nước Việt Nam 2010",
        "doc_code": "46/2010/QH12",
        "issuer": "Quốc hội",
        "issue_year": 2010,
        "effective_date": "2011-01-01",
        "status": "active"
    },
    "luat_phong_chong_rua_tien_2022": {
        "doc_name": "Luật Phòng, chống rửa tiền 2022",
        "doc_code": "14/2022/QH15",
        "issuer": "Quốc hội",
        "issue_year": 2022,
        "effective_date": "2023-03-01",
        "status": "active"
    },
    "luat_giao_dich_dien_tu_2023": {
        "doc_name": "Luật Giao dịch điện tử 2023",
        "doc_code": "20/2023/QH15",
        "issuer": "Quốc hội",
        "issue_year": 2023,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "luat_bao_ve_quyen_loi_nguoi_dung_2023": {
        "doc_name": "Luật Bảo vệ quyền lợi người tiêu dùng 2023",
        "doc_code": "19/2023/QH15",
        "issuer": "Quốc hội",
        "issue_year": 2023,
        "effective_date": "2024-07-01",
        "status": "active"
    },

    # 2. NHÓM NGHỊ ĐỊNH
    "nd52_2024_thanh_toan_khong_dung_tien_mat": {
        "doc_name": "Nghị định quy định về thanh toán không dùng tiền mặt",
        "doc_code": "52/2024/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "nd94_2025_co_che_thu_nghiem_co_dieu_kien_sandbox": {
        "doc_name": "Nghị định Cơ chế thử nghiệm có điều kiện trong lĩnh vực ngân hàng (Sandbox)",
        "doc_code": "94/2025/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2025,
        "effective_date": "2025-07-01",
        "status": "active"
    },
    "nd88_2019_san_phat_vphc_tien_te_ngan_hang": {
        "doc_name": "Nghị định Xử phạt vi phạm hành chính trong lĩnh vực tiền tệ và ngân hàng",
        "doc_code": "88/2019/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2019,
        "effective_date": "2019-12-31",
        "status": "active"
    },
    "nd143_2021_sua_doi_nd88_xpvphc_ngan_hang": {
        "doc_name": "Nghị định sửa đổi, bổ sung Nghị định 88/2019/NĐ-CP về xử phạt VPHC ngân hàng",
        "doc_code": "143/2021/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2021,
        "effective_date": "2022-01-01",
        "status": "active"
    },
    "nd86_2024_trich_lap_du_phong_rui_ro_tctd": {
        "doc_name": "Nghị định Mức trích lập, phương pháp trích lập dự phòng rủi ro của TCTD",
        "doc_code": "86/2024/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "nd26_2025_chuc_nang_nhiem_vu_nhnn": {
        "doc_name": "Nghị định Quy định chức năng, nhiệm vụ, quyền hạn và cơ cấu tổ chức của NHNN",
        "doc_code": "26/2025/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2025,
        "effective_date": "2025-03-01",
        "status": "active"
    },
    "nd19_2023_quy_dinh_chi_tiet_luat_pcrt": {
        "doc_name": "Nghị định Quy định chi tiết một số điều của Luật Phòng, chống rửa tiền",
        "doc_code": "19/2023/NĐ-CP",
        "issuer": "Chính phủ",
        "issue_year": 2023,
        "effective_date": "2023-04-28",
        "status": "active"
    },

    # 3. NHÓM THÔNG TƯ
    "tt15_2024_dich_vu_thanh_toan_khong_dung_tien_mat": {
        "doc_name": "Thông tư Cung ứng dịch vụ thanh toán không dùng tiền mặt",
        "doc_code": "15/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt18_2024_hoat_dong_the_ngan_hang": {
        "doc_name": "Thông tư Quy định về hoạt động thẻ ngân hàng",
        "doc_code": "18/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt17_2024_mo_va_su_dung_tai_khoan_thanh_toan": {
        "doc_name": "Thông tư Quy định việc mở và sử dụng tài khoản thanh toán",
        "doc_code": "17/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt25_2025_sua_doi_tt17_tai_khoan_thanh_toan": {
        "doc_name": "Thông tư Sửa đổi, bổ sung Thông tư 17/2024/TT-NHNN về tài khoản thanh toán",
        "doc_code": "25/2025/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2025,
        "effective_date": "2025-03-01",
        "status": "active"
    },
    "tt40_2024_trung_gian_thanh_toan": {
        "doc_name": "Thông tư Quy định về hoạt động cung ứng dịch vụ trung gian thanh toán",
        "doc_code": "40/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt41_2024_giam_sat_he_thong_thanh_toan": {
        "doc_name": "Thông tư Quy định về giám sát các hệ thống thanh toán",
        "doc_code": "41/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-12-31",
        "status": "active"
    },
    "tt39_2016_cho_vay_to_chuc_tin_dung": {
        "doc_name": "Thông tư Quy định về hoạt động cho vay của TCTD",
        "doc_code": "39/2016/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2016,
        "effective_date": "2017-03-15",
        "status": "active"
    },
    "tt06_2023_sua_doi_tt39_cho_vay": {
        "doc_name": "Thông tư Sửa đổi, bổ sung Thông tư 39/2016/TT-NHNN về cho vay",
        "doc_code": "06/2023/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2023,
        "effective_date": "2023-09-01",
        "status": "active"
    },
    "tt12_2024_sua_doi_tt39_cho_vay": {
        "doc_name": "Thông tư Sửa đổi, bổ sung Thông tư 39/2016/TT-NHNN về cho vay",
        "doc_code": "12/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt07_2024_dai_ly_thanh_toan": {
        "doc_name": "Thông tư Quy định về hoạt động đại lý thanh toán",
        "doc_code": "07/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt06_2025_sua_doi_tt07_dai_ly_thanh_toan": {
        "doc_name": "Thông tư Sửa đổi, bổ sung Thông tư 07/2024/TT-NHNN về đại lý thanh toán",
        "doc_code": "06/2025/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2025,
        "effective_date": "2025-02-15",
        "status": "active"
    },
    "tt49_2018_tien_gui_co_ky_han": {
        "doc_name": "Thông tư Quy định về tiền gửi có kỳ hạn",
        "doc_code": "49/2018/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2018,
        "effective_date": "2019-07-05",
        "status": "active"
    },
    "tt48_2018_tien_gui_tiet_kiem": {
        "doc_name": "Thông tư Quy định về tiền gửi tiết kiệm",
        "doc_code": "48/2018/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2018,
        "effective_date": "2019-07-05",
        "status": "active"
    },
    "tt48_2024_lai_suat_tien_gui_vnd": {
        "doc_name": "Thông tư Quy định về áp dụng lãi suất tiền gửi bằng Đồng Việt Nam",
        "doc_code": "48/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-11-20",
        "status": "active"
    },
    "tt02_2025_phat_hanh_chung_chi_tien_gui": {
        "doc_name": "Thông tư Quy định về việc TCTD phát hành chứng chỉ tiền gửi",
        "doc_code": "02/2025/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2025,
        "effective_date": "2025-03-01",
        "status": "active"
    },
    "tt06_2019_dau_tu_truc_tiep_ngoai_hoi": {
        "doc_name": "Thông tư Quản lý ngoại hối đối với hoạt động đầu tư trực tiếp vào Việt Nam",
        "doc_code": "06/2019/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2019,
        "effective_date": "2019-09-06",
        "status": "active"
    },
    "tt09_2020_an_toan_he_thong_thong_tin": {
        "doc_name": "Thông tư Quy định về an toàn hệ thống thông tin trong hoạt động ngân hàng",
        "doc_code": "09/2020/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2020,
        "effective_date": "2021-01-01",
        "status": "active"
    },
    "tt50_2024_an_toan_bao_mat_dich_vu_truc_tuyen": {
        "doc_name": "Thông tư Quy định về an toàn, bảo mật cho việc cung cấp dịch vụ trực tuyến",
        "doc_code": "50/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2025-01-01",
        "status": "active"
    },
    "tt64_2024_giao_dien_lap_trinh_ung_dung_mo": {
        "doc_name": "Thông tư Quy định về giao diện lập trình ứng dụng mở (Open API)",
        "doc_code": "64/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2025-01-01",
        "status": "active"
    },
    "tt32_2024_mang_luoi_ngan_hang_thuong_mai": {
        "doc_name": "Thông tư Quy định về mạng lưới hoạt động của ngân hàng thương mại",
        "doc_code": "32/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt08_2025_sua_doi_mang_luoi_va_phong_giao_dich": {
        "doc_name": "Thông tư Sửa đổi, bổ sung quy định về mạng lưới hoạt động ngân hàng",
        "doc_code": "08/2025/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2025,
        "effective_date": "2025-03-01",
        "status": "active"
    },
    "tt61_2024_bao_lanh_ngan_hang": {
        "doc_name": "Thông tư Quy định về bảo lãnh ngân hàng",
        "doc_code": "61/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-12-31",
        "status": "active"
    },
    "tt38_2024_hoat_dong_tu_van_tctd": {
        "doc_name": "Thông tư Quy định về hoạt động tư vấn của các tổ chức tín dụng",
        "doc_code": "38/2024/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2024,
        "effective_date": "2024-07-01",
        "status": "active"
    },
    "tt14_2025_ty_le_an_toan_von_nhtm": {
        "doc_name": "Thông tư Quy định về tỷ lệ an toàn vốn của ngân hàng thương mại",
        "doc_code": "14/2025/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2025,
        "effective_date": "2025-09-01",
        "status": "active"
    },
    "tt09_2023_huong_dan_phong_chong_rua_tien": {
        "doc_name": "Thông tư Hướng dẫn thực hiện một số điều của Luật Phòng, chống rửa tiền",
        "doc_code": "09/2023/TT-NHNN",
        "issuer": "Ngân hàng Nhà nước",
        "issue_year": 2023,
        "effective_date": "2023-07-28",
        "status": "active"
    }
}

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"banking_chunker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
# REGEX & CONSTANTS
# ---------------------------------------------------------------------------
RE_DIEU   = re.compile(r"(?:^|\n)(?:###?\s*)?Điều\s+(\d+)[.:]?\s*(.*)", re.IGNORECASE)
RE_KHOAN  = re.compile(r"^(\d+)\.(?=\s+[A-ZĐÀÁẠẢÃẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ])", re.MULTILINE)
RE_DIEM   = re.compile(r"(?:^|;\s+)([a-zđ])\)(?=\s+)", re.MULTILINE)

THRESH_DIEU  = 600
MIN_CHUNK    = 20

# ---------------------------------------------------------------------------
# CLASS: LegalSemanticChunker
# ---------------------------------------------------------------------------
class LegalSemanticChunker:
    def count_tokens(self, text: str) -> int:
        return int(len(text.split()) * 1.3)

    def split_into_articles(self, full_text: str) -> list[tuple[str, str, str]]:
        articles = []
        lines = full_text.splitlines()

        current_num = "0"
        current_title = "Giới thiệu"
        current_lines = []

        for line in lines:
            m = RE_DIEU.match(line.strip())
            if m:
                if current_lines:
                    articles.append((current_num, current_title, "\n".join(current_lines)))
                current_num = m.group(1)
                current_title = m.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            articles.append((current_num, current_title, "\n".join(current_lines)))

        return articles

    def split_article_into_khoans(self, text: str) -> list[tuple[str, str]]:
        parts = RE_KHOAN.split(text)
        khoans = []
        if len(parts) <= 1:
            return [("0", text)]
        if parts[0].strip():
            khoans.append(("0", parts[0].strip()))
        
        i = 1
        while i + 1 < len(parts):
            khoan_num = parts[i]
            content = parts[i + 1]
            khoans.append((khoan_num, f"{khoan_num}.{content}"))
            i += 2
        return khoans

    def parse_markdown(self, file_path: Path, doc_type: str) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        file_stem = file_path.stem
        meta_info = DOC_METADATA_LOOKUP.get(file_stem, {
            "doc_name": file_stem.replace("_", " ").title(),
            "doc_code": "Chưa xác định",
            "issuer": "Ngân hàng Nhà nước",
            "issue_year": None,
            "effective_date": "Chưa xác định",
            "status": "active"
        })

        articles = self.split_into_articles(full_text)
        chunks = []

        for dieu_num, dieu_title, dieu_content in articles:
            if self.count_tokens(dieu_content) < MIN_CHUNK:
                continue

            # Nếu Điều ngắn -> Giữ nguyên làm 1 chunk
            if self.count_tokens(dieu_content) <= THRESH_DIEU:
                chunk = self._make_chunk_dict(
                    text=dieu_content,
                    file_stem=file_stem,
                    file_path=file_path,
                    doc_type=doc_type,
                    meta_info=meta_info,
                    dieu_num=dieu_num,
                    dieu_title=dieu_title,
                    khoan_num=None,
                    level=1
                )
                chunks.append(chunk)
            else:
                # Nếu Điều quá dài -> Chia theo Khoản (Level 2)
                khoans = self.split_article_into_khoans(dieu_content)
                for khoan_num, khoan_content in khoans:
                    if self.count_tokens(khoan_content) < MIN_CHUNK:
                        continue
                    chunk = self._make_chunk_dict(
                        text=khoan_content,
                        file_stem=file_stem,
                        file_path=file_path,
                        doc_type=doc_type,
                        meta_info=meta_info,
                        dieu_num=dieu_num,
                        dieu_title=dieu_title,
                        khoan_num=khoan_num if khoan_num != "0" else None,
                        level=2
                    )
                    chunks.append(chunk)

        return chunks

    def _make_chunk_dict(
        self, text: str, file_stem: str, file_path: Path, doc_type: str,
        meta_info: dict, dieu_num: str, dieu_title: str,
        khoan_num: str | None, level: int
    ) -> dict:
        khoan_part = f"_khoan{khoan_num}" if khoan_num else ""
        chunk_id = f"{file_stem}_dieu{dieu_num}{khoan_part}"
        
        # Context Enrichment: Tiêu đề được đưa thẳng vào nội dung content
        doc_header = f"Văn bản: {meta_info['doc_name']} ({meta_info['doc_code']})"
        dieu_header = f"Điều {dieu_num}: {dieu_title}" if dieu_num != "0" else ""
        
        enriched_content = text.strip()
        if dieu_header and not enriched_content.startswith(f"Điều {dieu_num}"):
            enriched_content = f"{doc_header}\n{dieu_header}\n{enriched_content}"
        else:
            enriched_content = f"{doc_header}\n{enriched_content}"

        return {
            "chunk_id": chunk_id,
            "content": enriched_content,
            "metadata": {
                "doc_id": file_stem,
                "doc_name": meta_info["doc_name"],
                "doc_code": meta_info["doc_code"],
                "doc_type": doc_type,
                "issuer": meta_info["issuer"],
                "issue_year": meta_info["issue_year"],
                "effective_date": meta_info["effective_date"],
                "status": meta_info["status"],
                "source_file": file_path.name,
                "dieu_number": int(dieu_num) if dieu_num.isdigit() else dieu_num,
                "dieu_title": dieu_title,
                "khoan_number": khoan_num,
                "level": level,
                "token_estimate": self.count_tokens(enriched_content),
                "char_count": len(enriched_content)
            }
        }

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def process_semantic_chunking():
    CHUNKED_DIR.mkdir(parents=True, exist_ok=True)
    chunker = LegalSemanticChunker()

    md_files = list(CLEANED_DIR.rglob("*.md"))
    logger.info(f"Tìm thấy {len(md_files)} file Markdown trong {CLEANED_DIR}")

    all_chunks_list = []
    total_chunks = 0
    stats = {"total_files": len(md_files), "processed_files": 0, "total_chunks": 0, "details": {}}

    for md_path in tqdm(md_files, desc="Semantic Chunking", unit="file"):
        if md_path.name.startswith("_"):
            continue

        rel_path = md_path.relative_to(CLEANED_DIR)
        doc_type = rel_path.parts[0] if len(rel_path.parts) > 1 else "ngan_hang"
        
        output_dir = CHUNKED_DIR / rel_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        out_json_path = output_dir / f"{md_path.stem}_chunks.json"

        try:
            chunks = chunker.parse_markdown(md_path, doc_type)
            
            # Ghi file JSON riêng
            with open(out_json_path, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)

            all_chunks_list.extend(chunks)
            num_chunks = len(chunks)
            total_chunks += num_chunks
            stats["processed_files"] += 1
            stats["details"][str(rel_path)] = num_chunks
            
            logger.info(f"  ✓ {rel_path} -> {num_chunks} chunks")

        except Exception as e:
            logger.error(f"  ✗ Lỗi xử lý file {rel_path}: {e}", exc_info=True)

    # Xuất toàn bộ chunks ra 1 file JSONL duy nhất cho Qdrant / ChromaDB / Milvus
    logger.info(f"Đang xuất file JSONL tập trung cho Vector DB: {JSONL_PATH}")
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for chunk in all_chunks_list:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    stats["total_chunks"] = total_chunks
    logger.info("\n" + "="*60)
    logger.info(f"HOÀN THÀNH CHUNKING NGÂN HÀNG: {stats['processed_files']} file | Tổng số Chunks: {total_chunks}")
    
    stats_path = CHUNKED_DIR / "_chunking_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats

if __name__ == "__main__":
    process_semantic_chunking()
