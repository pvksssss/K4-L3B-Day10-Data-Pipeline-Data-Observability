# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `unknown`
- **Mã Nhóm / Lớp:** `K4-L3B`
- **Tên Repository Nộp Bài:** `https://github.com/pvksssss/K4-L3B-Day10-Data-Pipeline-Data-Observability`

---

## # Thành viên (2 Thành viên)

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Phạm Văn Kiên | 2A202602590 | | Trưởng nhóm / Pipeline Integrator & Ingestion (`core/`, `ingestion/`, `phase1.py`, `corruption_flow.py`) | `report/2A202602590_PhamVanKien.md` |
| 2 | Hồ Hoàng Phương Anh | 2A202602460 | | RAG, Vector Index & Observability (`retrieval/`, `quality.py` GX 1.x, `testset.py`, reporting) | `report/2A202602460_HoangPhuongAnh.md` |

---

## # Cá nhân

### ## PhamVanKien-2A202602590
- **Vai trò:** Trưởng nhóm, Pipeline Integrator & Data Ingestion.
- **Công việc chi tiết đã hoàn thành:**
  - Thiết lập cấu hình hệ thống `core/config.py` và đường dẫn artifacts `core/utils.py`.
  - Xây dựng module thu thập Crossref API với cơ chế Fallback offline trong `src/ingestion/crossref.py` và làm sạch dữ liệu trong `src/ingestion/cleaning.py`.
  - Kết nối luồng thực thi trong `src/pipelines/phase1.py` và `src/pipelines/corruption_flow.py`.
  - Triển khai bộ 6 kịch bản tiêm lỗi dữ liệu và cơ chế Idempotent Repair.
- **Điều học được / Đóng góp chính:**
  - Hiểu sâu sắc về thiết kế Idempotent Pipeline, quản lý trạng thái luồng dữ liệu đa tầng và phục hồi tự động khi có sự cố dữ liệu.

### ## Hồ Hoàng Phương Anh- 2A202602460
- **Vai trò:** Phụ trách RAG, Vector Database, Data Observability & Benchmark Evaluation.
- **Công việc chi tiết đã hoàn thành:**
  - Quản lý mô hình embedding `sentence-transformers/all-MiniLM-L6-v2` và nạp 3 collection riêng biệt trong ChromaDB (`papers-baseline`, `papers-corrupted`, `papers-repaired`).
  - Thiết lập Quality Gate theo chuẩn mới **Great Expectations 1.x** và giám sát Freshness SLA trong `src/observability/quality.py`.
  - Xây dựng bộ câu hỏi đánh giá chuẩn trong `src/evaluation/testset.py`.
  - Đo lường và xuất bảng đối chiếu 3 trạng thái vào `data/reports/corruption_report.md`.
- **Điều học được / Đóng góp chính:**
  - Cách cô lập không gian vector để so sánh khách quan và thiết lập hệ thống cảnh báo sớm chặn đứng hiện tượng Silent Failure trước khi dữ liệu vào serving layer.
