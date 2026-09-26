# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                             |
| ----------------- | ------------------------------------------------------------------------------------ |
| Họ và tên         | Phạm Văn Kiên                                                                        |
| MSSV              | 2A202602590                                                                          |
| Khóa/Lớp          | K4 - Lớp 3B                                                                          |
| Tên nhóm          | pkien1                                                                               |
| Vai trò chính     | Trưởng nhóm / Pipeline Integrator & Ingestion Engineer                               |
| Repository        | https://github.com/pvksssss/K4-L3B-Day10-Data-Pipeline-Data-Observability            |
| Ngày hoàn thành   | 2026-09-26                                                                           |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module / Deliverable | File / Hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| **Pipeline Configuration & Utils** | `src/core/config.py`, `src/core/utils.py` | Environment variables, `.env` | Đối tượng `Settings`, `Paths` và tiện ích I/O | Hoàn thành |
| **Crossref Ingestion & Fallback** | `src/ingestion/crossref.py` (`parse_crossref_payload`, `fetch_source_records`, `load_raw_records`) | Crossref REST API / Snapshot JSON | `data/raw/crossref_records.json` (24 PaperRecords) | Hoàn thành |
| **Data Cleaning & Schema Modeling** | `src/ingestion/cleaning.py` (`build_clean_dataframe`) | List `PaperRecord`, `run_date` | `data/clean/papers_clean.csv`, `papers_clean.json` (24 dòng) | Hoàn thành |
| **Synthetic Corruption & Repair** | `src/ingestion/corruption.py` (`corrupt_clean_dataframe`) | Clean DataFrame | `data/clean/papers_clean_corrupted.csv`, `corruption_log.json` | Hoàn thành |
| **Pipeline Orchestration** | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | Toàn bộ các module | `script/run_phase1.py`, `script/run_corruption_flow.py` (Exit code 0) | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên / Module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp Great Expectations 1.x & Freshness Gate | Thành viên 2 (`observability/quality.py`) | Viết helper serializable JSON và kiểm thử batch ephemeral của GX 1.x |
| Thiết lập bộ Pytest Test Suite toàn diện | Cả nhóm (`tests/`) | 27/27 test cases pass 100% |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File / Hàm / Artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng module Ingestion Crossref | `src/ingestion/crossref.py` | Tải 24 bài báo, retry 3 lần, fallback snapshot offline | `pytest tests/test_crossref.py -v` (8 passed) |
| Chuẩn hóa và làm sạch văn bản | `src/ingestion/cleaning.py` | Xóa thẻ XML, tạo 5-part `text_for_embedding`, tính `age_days` | `pytest tests/test_cleaning.py -v` (4 passed) |
| Triển khai 6 kịch bản Data Corruption | `src/ingestion/corruption.py` | Tiêm 6 dạng lỗi, lưu `corruption_log.json` | `pytest tests/test_corruption.py -v` (2 passed) |
| Điều phối luồng 3 trạng thái | `src/pipelines/corruption_flow.py` | Bảng so sánh đối chiếu Baseline vs Corrupted vs Repaired | `python script/run_corruption_flow.py` |

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Hệ thống RAG dễ bị suy thoái hiệu năng ngầm (**Silent Failure**) khi dữ liệu đầu vào bị lỗi (mất bài mới, xóa rỗng tóm tắt, chèn nhiễu, lùi ngày, trùng lặp) mà không gây crash chương trình. Cần một quy trình Ingestion có khả năng bảo toàn Data Lineage, làm sạch chuẩn mực, và cơ chế **Idempotent Repair** tự động chữa lành từ nguồn thô đáng tin cậy.

### Cách triển khai
1. **Ingestion & Fallback:** Bóc tách metadata từ `message.items` của Crossref, chuẩn hóa DOI và ngày ISO. Dùng `requests.Session` với retry backoff (xử lý mã lỗi `429/503`) và cơ chế fallback tự động nạp từ `crossref_response.json` khi offline.
2. **Cleaning Pipeline:** Loại bỏ thẻ JATS XML `<jats:p>` và ký tự rác bằng Regex và `html.unescape`. Tính số ngày tuổi `age_days = (run_date - published).days`. Ghép trường `text_for_embedding` theo cấu trúc 5 phần chuẩn hóa:
   ```text
   Title: <title>
   Authors: <authors_joined>
   Published: <published>
   Categories: <categories_joined>
   Summary: <summary>
   ```
3. **Synthetic Corruption:** Triển khai 6 kịch bản tác động trực tiếp vào các chiều chất lượng: Drop 20% bài mới, Blank summary, Noise injection, Truncate title, Stale date (-400 ngày), Duplicate rows.
4. **Idempotent Repair:** Tái tạo sạch sẽ dataframe từ `data/raw/crossref_records.json` và tạo collection riêng `papers-repaired` trong ChromaDB để tránh ô nhiễm vector space.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| **Input** | JSON thô từ Crossref API / Snapshot local (`crossref_response.json`) |
| **Output** | `papers_clean.csv`, `papers_clean.json`, `papers_clean_corrupted.json`, `papers_clean_repaired.json` |
| **Module phụ thuộc** | `core/config.py`, `core/utils.py` |
| **Module sử dụng output** | `retrieval/index.py` (Embedding & Indexing), `observability/quality.py` (Quality Gate) |
| **Điều kiện lỗi cần xử lý** | Mất mạng / HTTP 429 ➔ Fallback local snapshot; Dữ liệu thiếu trường bắt buộc ➔ Bỏ qua an toàn |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
pytest -v
```
- **Kết quả mong đợi:** Exit code 0, 27 tests passed, xuất đầy đủ metrics và báo cáo Markdown.
- **Kết quả thực tế:** Chạy hoàn hảo, Hit Rate đạt 1.000 ở Baseline & Repaired, giảm xuống 0.600 ở Corrupted.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn cách tổ chức lưu trữ và phục hồi dữ liệu trong luồng Corruption và Repair.
- **Các phương án đã cân nhắc:**
  - *Phương án 1:* Ghi đè trực tiếp lên file clean và collection ChromaDB ban đầu.
  - *Phương án 2:* Cô lập thành 3 bộ artifact và 3 collection ChromaDB độc lập (`papers-baseline`, `papers-corrupted`, `papers-repaired`).
- **Phương án đã chọn:** Phương án 2 (Cô lập 3 collection riêng biệt).
- **Lý do:** Giữ nguyên vẹn tính bất biến và Data Lineage, cho phép so sánh đối đầu (A/B testing) công bằng trên cùng một tập benchmark test set mà không lo vector embeddings bị lẫn lộn giữa các trạng thái.
- **Bằng chứng:** Bảng kết quả so sánh tại `data/reports/corruption_report.md` thể hiện rõ nét sự khác biệt giữa 3 trạng thái.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Khi chạy `run_corruption_flow.py` trên môi trường mock workspace trong test, `evaluate_pipeline` báo lỗi `FileNotFoundError` do `test_set.json` chưa được sinh ra trước khi chạy đánh giá baseline.
- **Nguyên nhân:** File `corruption_flow.py` giả định `test_set.json` luôn có sẵn từ pha 1.
- **Cách xử lý:** Bổ sung logic tự động kiểm tra và sinh `test_set.json` nếu chưa tồn tại:
  ```python
  if not paths.eval_testset.exists():
      build_test_set(clean_df, paths.eval_testset)
  ```
- **Cách xác minh:** `pytest tests/test_corruption_flow.py` chạy thành công (PASS) ngay lập tức.
- **Điều học được:** Mọi pipeline stage phải có tính độc lập cao và tự bảo đảm các tiền điều kiện (preconditions) để có thể chạy độc lập trong bất kỳ môi trường thử nghiệm nào.

---

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu từ Crossref đến Vector Index:** Dữ liệu thô từ Crossref API $\rightarrow$ bóc tách thành `PaperRecord` $\rightarrow$ làm sạch và tạo `text_for_embedding` $\rightarrow$ sinh embedding vector 384 chiều từ `all-MiniLM-L6-v2` $\rightarrow$ nạp vào ChromaDB với không gian cosine.
2. **Evaluation Set & Ground-truth IDs:** Bộ 10 câu hỏi chuẩn hóa sử dụng ID tài liệu gốc (`ground_truth_doc_ids`) để kiểm tra xem khi query, ChromaDB có truy xuất đúng bài báo đó trong Top-4 context hay không (`retrieval_hit_rate`), đồng thời so sánh câu trả lời với `ground_truth` để đo `token_f1`.
3. **Quality Checks vs Freshness Monitoring:** Quality checks (GX 1.x) kiểm tra tính hợp lệ về cấu trúc (schema, null, uniqueness, độ dài text), trong khi Freshness SLA kiểm tra tính mới về mặt thời gian (`age_days > 180`).
4. **Dùng chung Test Set:** Giữ nguyên test set giúp loại bỏ biến số ngẫu nhiên của câu hỏi, đảm bảo sự thay đổi chỉ số phản ánh 100% chất lượng của dữ liệu đầu vào.
5. **Tiêu chí Repair thành công:** Repair thành công khi Data Quality Gate và Freshness SLA chuyển từ FAIL về PASS, đồng thời `retrieval_hit_rate` và `token_f1` phục hồi về mức 1.000 (100%).

---

## 8. Phân tích kết quả

### Metrics chính

| Metric / Signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | **1.000** | **0.600** | **1.000** | Giảm 40% do drop bài và nhiễu ➔ Phục hồi 100% |
| `mean_token_f1` | **1.000** | **0.651** | **1.000** | Câu trả lời bị sai lệch/cắt cụt ➔ Phục hồi 100% |
| `judge_accuracy` | **1.000** | **0.700** | **1.000** | Phục hồi hoàn toàn về 100% |
| `mean_judge_score` | **5.000** | **3.400** | **5.000** | Điểm chất lượng trung bình phục hồi về 5/5 |
| Quality Checks (GX 1.x) | **PASS** | **FAIL** | **PASS** | Bắt được vi phạm unique và độ dài summary |
| Freshness Status | **PASS** (4.2%) | **FAIL** (38.1%) | **PASS** (4.2%) | Bắt được tỷ lệ bài cũ vượt ngưỡng 25% |

### Kết luận từ số liệu
1. `Data Corruption (Noise + Drop + Truncate)` $\rightarrow$ `GX 1.x FAIL & Freshness FAIL` $\rightarrow$ `Hit Rate giảm từ 1.000 xuống 0.600, F1 giảm xuống 0.651`.
2. `Idempotent Repair từ Raw Snapshot` $\rightarrow$ `GX 1.x PASS & Freshness PASS` $\rightarrow$ `Hit Rate và F1 phục hồi 100% về 1.000`.

**Kịch bản ảnh hưởng rõ nhất:** Kịch bản **Drop 20% latest records** và **Noise injection** gây tác động nghiêm trọng nhất vì làm mất hoàn toàn ngữ cảnh truy xuất và phá hủy biểu diễn không gian vector của MiniLM.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Data Lineage là kim chỉ nam:** Luôn bảo toàn raw data snapshot ban đầu trước khi thực hiện bất kỳ biến đổi nào để có thể khôi phục idempotent bất cứ lúc nào.
2. **Data Observability chặn đứng Silent Failure:** Đặt Quality Gate (Great Expectations 1.x) và Freshness SLA ở đầu luồng giúp phát hiện sớm dữ liệu bẩn trước khi đi vào vector database.
3. **Vector Space Isolation:** Luôn cô lập các collection trong ChromaDB khi thử nghiệm các trạng thái dữ liệu khác nhau để tránh vector pollution.

### Nếu có thêm thời gian
Xây dựng thêm một **Auto-Healing Daemon** chạy ngầm: khi Quality Gate phát hiện vi phạm, hệ thống tự động kích hoạt tiến trình re-fetch và rebuild vector index mà không cần bất kỳ sự can thiệp thủ công nào.

---

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Văn Kiên  
**Ngày xác nhận:** 2026-09-26
