# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                             |
| ----------------- | ------------------------------------------------------------------------------------ |
| Họ và tên         | Hồ Hoàng Phương Anh                                                                  |
| MSSV              | 2A202602460                                                                          |
| Khóa/Lớp          | K4-L3B                                                                               |
| Tên nhóm          | unknown                                                                              |
| Vai trò chính     | RAG, Vector Storage & Data Observability Specialist                                  |
| Repository        | https://github.com/pvksssss/K4-L3B-Day10-unknown-Data-Pipeline-Data-Observability    |
| Ngày hoàn thành   | 2026-09-26                                                                           |

---

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module / Deliverable | File / Hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| **Embedding & Vector Storage** | `src/retrieval/embeddings.py`, `src/retrieval/index.py` | Clean / Corrupted / Repaired DataFrame | 3 ChromaDB collections (`papers-baseline`, `papers-corrupted`, `papers-repaired`), `data/embeddings/*.json` | Hoàn thành |
| **Data Observability (GX 1.x & Freshness)** | `src/observability/quality.py` (`run_data_quality_checks`, `build_freshness_report`) | DataFrame 3 trạng thái, `Settings` | `data/quality/*.json` (4 Expectations + Freshness SLA) | Hoàn thành |
| **Benchmark Test Set Generator** | `src/evaluation/testset.py` (`build_test_set`) | Clean DataFrame | `data/eval/test_set.json` (10 câu hỏi chuẩn hóa qua 4 nhóm) | Hoàn thành |
| **Metrics Evaluation & Reporting** | `src/observability/reporting.py` (`generate_phase1_report`, `generate_corruption_report`) | Pipeline Evaluation bundles | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên / Module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Hỗ trợ Ingestion & Cleaning verification | Thành viên 1 (`ingestion/cleaning.py`) | Xác minh cấu trúc 5 phần của `text_for_embedding` và lọc thẻ XML |
| Tích hợp luồng chạy và kiểm thử | Cả nhóm (`script/`, `tests/`) | Đảm bảo 27/27 test cases pass 100% |

---

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File / Hàm / Artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Quản lý Vector Store & Embeddings | `src/retrieval/index.py` | Quản lý mô hình MiniLM-L6-v2 và 3 collection ChromaDB | `pytest tests/test_phase1.py -v` |
| Thiết lập Data Quality Gate | `src/observability/quality.py` | Chuẩn hóa Great Expectations 1.x Ephemeral Context và Freshness SLA | `pytest tests/test_quality.py -v` (6 passed) |
| Xây dựng bộ Test Set chuẩn hóa | `src/evaluation/testset.py` | Sinh 10 câu hỏi phân bổ đều trên 4 dạng (`summary`, `authors`, `date`, `categories`) | `pytest tests/test_testset.py -v` (3 passed) |
| Đo lường và sinh Báo cáo 3 trạng thái | `src/observability/reporting.py` | Bảng đối chiếu định lượng Baseline vs Corrupted vs Repaired | `python script/run_corruption_flow.py` |

---

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết
Xây dựng chốt kiểm dịch chất lượng dữ liệu tự động (**Data Observability Gate**) trước khi nạp vào Vector Database, đo lường chính xác mức độ suy giảm của RAG khi dữ liệu bị lỗi và đảm bảo hệ thống đánh giá khách quan thông qua bộ benchmark test set cố định.

### Cách triển khai
1. **Great Expectations 1.x Quality Gate:** Sử dụng hoàn toàn **GX 1.x Fluent API** (Ephemeral Context, Pandas Data Source, Data Asset, Batch Definition) để xác thực 4 Expectations cốt lõi:
   - `ExpectTableRowCountToBeBetween`: Số dòng từ 1 đến 24.
   - `ExpectColumnValuesToNotBeNull`: `paper_id` và `title` không null.
   - `ExpectColumnValuesToBeUnique`: `paper_id` không trùng lặp.
   - `ExpectColumnValueLengthsToBeBetween`: Độ dài tóm tắt `summary` từ 20 đến 20,000 ký tự.
2. **Freshness SLA Monitoring:** Đo lường độ trễ dữ liệu dựa trên `age_days`. Cảnh báo `is_fresh = False` khi tỷ lệ bài báo quá hạn (`age_days > 180`) vượt quá 25%.
3. **Benchmark Test Set:** Xây dựng thuật toán sinh 10 câu hỏi tất định từ clean dataframe, bao gồm: 3 câu `summary`, 3 câu `authors`, 2 câu `date`, 2 câu `categories`. Mỗi câu hỏi lưu kèm `ground_truth_doc_ids` phục vụ tính `retrieval_hit_rate` và `token_f1`.
4. **Vector Storage Management:** Quản lý ChromaDB Client, cấu hình khoảng cách cosine (`hnsw:space: cosine`), tách biệt hoàn toàn 3 collection: `papers-baseline`, `papers-corrupted`, `papers-repaired`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| **Input** | Clean DataFrame, Corrupted DataFrame, Repaired DataFrame |
| **Output** | `data/quality/*.json`, `data/eval/test_set.json`, `data/reports/corruption_report.md` |
| **Module phụ thuộc** | `core/config.py`, `retrieval/embeddings.py`, `retrieval/index.py` |
| **Module sử dụng output** | `pipelines/phase1.py`, `pipelines/corruption_flow.py` |
| **Điều kiện lỗi cần xử lý** | Dữ liệu rỗng hoặc không đủ 10 dòng ➔ Báo lỗi `ValueError` chi tiết |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
pytest tests/test_quality.py tests/test_testset.py -v
```
- **Kết quả mong đợi:** Toàn bộ test quality & testset pass, GX 1.x trả về kết quả serializable.
- **Kết quả thực tế:** 100% tests pass, báo cáo 3 trạng thái phản ánh chính xác sự sụt giảm và phục hồi.

---

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn chuẩn triển khai Great Expectations (GX 0.x Dataset API cũ vs GX 1.x Fluent API mới).
- **Các phương án đã cân nhắc:**
  - *Phương án 1:* Dùng GX 0.x cũ (`ge.from_pandas(df)`).
  - *Phương án 2:* Dùng GX 1.x Fluent API (`context.data_sources.add_pandas(...)`).
- **Phương án đã chọn:** Phương án 2 (GX 1.x Fluent API).
- **Lý do:** GX 1.x là chuẩn chính thức hiện tại, tương thích hoàn toàn với Python 3.11–3.13, tránh các lỗi deprecation / crash runtime và đáp ứng chuẩn yêu cầu chấm điểm trong Rubric (tránh bị trừ 10 điểm).
- **Bằng chứng:** Code chạy mượt mà không có bất kỳ warning deprecation nào và xuất file JSON report chuẩn cấu trúc.

---

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Khi chạy `pytest tests/test_quality.py`, đối tượng kết quả trả về của GX 1.x chứa các kiểu dữ liệu nội bộ không thể serialize trực tiếp ra file JSON (`TypeError: Object of type ... is not JSON serializable`).
- **Nguyên nhân:** Great Expectations 1.x trả về các đối tượng `ExpectationValidationResult` phức tạp.
- **Cách xử lý:** Viết parser thu gọn trích xuất các trường thiết yếu (`expectation_type`, `success`, `observed_value`, `unexpected_count`) thành dict thuần túy trước khi ghi file.
- **Cách xác minh:** Test case `test_quality_report_is_json_serializable` chạy thành công (PASS).
- **Điều học được:** Khi tích hợp các framework lớn như Great Expectations, luôn cần một lớp adapter / serializer để chuẩn hóa kết quả đầu ra thành format JSON an toàn.

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
1. `Data Corruption` $\rightarrow$ `GX 1.x FAIL & Freshness FAIL` $\rightarrow$ `Hit Rate giảm từ 1.000 xuống 0.600, F1 giảm xuống 0.651`.
2. `Idempotent Repair` $\rightarrow$ `GX 1.x PASS & Freshness PASS` $\rightarrow$ `Hit Rate và F1 phục hồi 100% về 1.000`.

---

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất
1. **Tầm quan trọng của Data Observability:** Không có Quality Gate, hệ thống RAG sẽ bị Silent Failure mà không ai hay biết.
2. **Tính nghiêm ngặt của Benchmark:** Đánh giá RAG cần bộ câu hỏi đa dạng (Summary, Authors, Date, Categories) và cố định để đo lường công bằng.
3. **Quản lý Vector Index độc lập:** Tách biệt các collection giúp bảo vệ tính toàn vẹn của dữ liệu serving.

### Nếu có thêm thời gian
Tích hợp thêm một **Observability Dashboard (Streamlit / Gradio)** hiển thị trực quan các biểu đồ phân bố độ tuổi bài báo, radar chart so sánh chất lượng 3 trạng thái và cảnh báo real-time khi vi phạm Freshness SLA.

---

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Hồ Hoàng Phương Anh  
**Ngày xác nhận:** 2026-09-26
