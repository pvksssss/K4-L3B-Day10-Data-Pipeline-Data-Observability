# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                                                                             |
| ----------------- | ------------------------------------------------------------------------------------ |
| Khóa/Lớp          | K4 - Lớp 3B                                                                          |
| Tên nhóm          |unknown                                                                   |
| Repository        | https://github.com/pvksssss/K4-L3B-Day10-unknown-Data-Pipeline-Data-Observability    |
| Ngày hoàn thành   | 2026-09-26                                                                           |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Phạm Văn Kiên | 2A202602590 |  Pipeline Integrator& Data Foundation & Ingestion Engineer | `core/config.py`, `script/run_phase1.py`, `script/run_corruption_flow.py`,  |
| 2 | Hồ Hoàng Phương Anh | 2A202602460 | RAG & Vector Storage Engineer & Observability & Evaluation Specialist | `src/retrieval/index.py`, `src/retrieval/embeddings.py`, ChromaDB,  `src/observability/quality.py` (GX 1.x), `src/evaluation/testset.py`, reports |

---

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành toàn diện 100% các mục tiêu từ Checkpoint 0 đến Checkpoint 5 cùng bộ kiểm thử tự động 27/27 test cases (Pytest).
- **Baseline Pipeline (CP0–CP3):** Xây dựng luồng thu thập 24 bài báo khoa học từ Crossref API (hỗ trợ retry backoff và fallback offline snapshot), làm sạch loại bỏ JATS XML tags, tính toán `age_days`, sinh trường `text_for_embedding` 5 phần chuẩn hóa, đánh index vào ChromaDB collection `papers-baseline` sử dụng mô hình MiniLM-L6-v2. Đạt chỉ số hoàn hảo trên tập benchmark 10 câu hỏi: **Retrieval Hit Rate 1.000**, **Token F1 1.000**, **Judge Score 5.000/5.0**. Quality Gate chuẩn Great Expectations 1.x và Freshness SLA (4.2% stale <= 25%) đều đạt **PASS**.
- **Data Corruption (CP4):** Tiêm 6 kịch bản lỗi tổng hợp (Drop 20% bài mới, Blank summary, Noise injection, Truncate title, Stale date lùi 400 ngày, Duplicate rows). Kết quả gây ra hiện tượng **Silent Failure** nghiêm trọng: Retrieval Hit Rate sụt giảm từ **1.000 xuống 0.600**, Token F1 giảm xuống **0.651**, GX Quality Gate và Freshness SLA đều chuyển sang **FAIL** (tỷ lệ bài cũ tăng lên 38.1%).
- **Idempotent Repair & Self-Healing (CP5):** Khôi phục dữ liệu sạch tự động từ nguồn snapshot thô bất biến `data/raw/crossref_records.json`, tái lập chỉ mục vector `papers-repaired` và đưa toàn bộ chỉ số hiệu năng phục hồi trọn vẹn **100% (Hit Rate 1.000, F1 1.000, GX PASS, Freshness PASS)**.

---

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API / Offline Snapshot
    │
    ▼ (CP0: Ingestion)
data/raw/crossref_response.json & crossref_records.json
    │
    ▼ (CP1: Cleaning & Schema Modeling)
data/clean/papers_clean.csv & papers_clean.json
    ├──> [GX 1.x Quality Gate & Freshness SLA] ──> data/quality/baseline_quality_report.json
    ├──> [Evaluation Test Set Generator] ───────> data/eval/test_set.json (10 questions)
    │
    ▼ (CP2: ChromaDB Vector Indexing)
data/chroma/ (Collection: papers-baseline)
    │
    ▼ (CP3: Baseline Evaluation & Phase 1 Report)
data/results/baseline_metrics.json ──> data/reports/phase1_report.md
    │
    ▼ (CP4: Synthetic Corruption - 6 Scenarios)
data/clean/papers_clean_corrupted.json ──> ChromaDB (papers-corrupted)
    │ ──> data/results/corrupted_metrics.json & data/results/corruption_log.json
    │
    ▼ (CP5: Idempotent Repair from Raw Snapshot)
data/clean/papers_clean_repaired.json ───> ChromaDB (papers-repaired)
    │ ──> data/results/repaired_metrics.json
    ▼
data/reports/corruption_report.md (3-State Comparison Table)
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output / Artifact | Owner |
| --- | --- | --- | --- | --- |
| **Ingestion** | Crossref REST API / Snapshot | Bóc tách metadata, retry 429/503, fallback offline | `data/raw/crossref_records.json` | Phạm Văn Kiên |
| **Cleaning** | Raw `PaperRecord` objects | Strip XML/HTML tags, tính `age_days`, tạo `text_for_embedding` 5 phần | `data/clean/papers_clean.csv`, `papers_clean.json` | Phạm Văn Kiên |
| **Embedding / Index** | Clean / Corrupted / Repaired DF | Sinh vector MiniLM-L6-v2, tạo ChromaDB collections (`cosine`) | `data/chroma/`, `data/embeddings/*.json` | Hồ Hoàng Phương Anh |
| **Evaluation** | Clean DataFrame | Sinh bộ 10 câu hỏi đa dạng qua 4 dạng (`summary`, `authors`, `date`, `categories`) | `data/eval/test_set.json` | Hồ Hoàng Phương Anh |
| **Observability** | DataFrame (3 trạng thái) | Kiểm thử GX 1.x (4 expectations), đo Freshness SLA (180 ngày) | `data/quality/*.json` | Hồ Hoàng Phương Anh |
| **Corruption / Repair** | Clean DataFrame / Raw records | Tiêm 6 kịch bản lỗi, log biến đổi; Idempotent repair từ raw records | `data/results/corruption_log.json`, `papers_clean_repaired.json` | Phạm Văn Kiên |
| **Orchestration** | Toàn bộ pipeline | Kết nối end-to-end các pha, xuất báo cáo Markdown đối chiếu 3 trạng thái | `phase1_report.md`, `corruption_report.md` | Phạm Văn Kiên |

---

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến / Cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `mock` (hoặc `gemini`, `openai` khi có key) |
| `LLM_MODEL` | `gemini-2.5-flash` |
| Embedding Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Cosine Space | ChromaDB HNSW space: `cosine` |

### Lệnh cài đặt

```bash
uv sync
# Hoặc pip install:
python -m pip install -e .
```

### Lệnh chạy

1. **Chạy Baseline Pipeline (Pha 1):**
```bash
python script/run_phase1.py
```
2. **Chạy Luồng Corruption, Observability & Idempotent Repair (Pha 2):**
```bash
python script/run_corruption_flow.py
```
3. **Chạy toàn bộ Test Suite (27 test cases):**
```bash
pytest -v
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| `run_phase1.py` | Thành công (Exit code 0) | 2026-09-26 | `data/reports/phase1_report.md` |
| `run_corruption_flow.py` | Thành công (Exit code 0) | 2026-09-26 | `data/reports/corruption_report.md` |
| `pytest` | 27/27 PASSED (100%) | 2026-09-26 | Console test summary |

---

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu
- **Source:** Crossref REST API (`https://api.crossref.org/works`)
- **Query:** `agentic retrieval augmented generation large language model`
- **Filter:** `from-pub-date:2026-03-30,has-abstract:true`
- **Số record:** 24 bài báo
- **Cơ chế Retry/Backoff:** 3 lần retry exponential backoff khi gặp HTTP `429/500/502/503/504`. Tự động fallback sang file snapshot offline `data/raw/crossref_response.json` khi chạy không mạng.

### Clean Schema và Quy tắc Cleaning

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu / sai |
| --- | --- | --- | --- | --- |
| `paper_id` | `str` | Có | Normalized DOI duy nhất | Bỏ qua bản ghi nếu thiếu DOI |
| `title` | `str` | Có | Tiêu đề bài báo sạch | Bỏ qua bản ghi nếu thiếu title |
| `summary` | `str` | Có | Tóm tắt không chứa XML/HTML | Xóa thẻ JATS XML `<jats:p>`, unescape HTML |
| `authors` | `list[str]` | Không | Danh sách tên tác giả | Ghép Given + Family name |
| `categories` | `list[str]` | Không | Danh mục chủ đề | Lấy từ `subject` Crossref |
| `published` | `str` | Có | Ngày công bố ISO YYYY-MM-DD | Lấy từ `date-parts` với fallback an toàn |
| `age_days` | `int` | Có | Số ngày tuổi so với `run_date` | `(run_date - published).days` |
| `text_for_embedding` | `str` | Có | Văn bản chuẩn 5 phần | Ghép Title, Authors, Published, Categories, Summary |

---

## 6. Evaluation setup

- **Số câu hỏi:** 10 câu hỏi benchmark chuẩn hóa (`q01` đến `q10`).
- **Phân bổ `question_type`:**
  - 3 câu `summary`: Tóm tắt nội dung chính bài báo.
  - 3 câu `authors`: Danh sách tác giả bài báo.
  - 2 câu `date`: Ngày công bố bài báo.
  - 2 câu `categories`: Danh mục phân loại bài báo.
- **Tính nhất quán:** Bộ test set (`data/eval/test_set.json`) được cố định và sử dụng chung cho cả 3 trạng thái (**Baseline, Corrupted, Repaired**) để đảm bảo tính khách quan và so sánh chính xác mức độ suy giảm cũng như khả năng phục hồi.

---

## 7. Kết quả Baseline (Pha 1)

### Artifact Checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/crossref_records.json` | Đầy đủ | 24 records |
| Cleaned dataset | `data/clean/papers_clean.csv`, `.json` | Đầy đủ | 24 rows cleaned |
| Embedding manifest | `data/embeddings/papers_embeddings.json` | Đầy đủ | Model MiniLM-L6-v2 |
| Evaluation set | `data/eval/test_set.json` | Đầy đủ | 10 câu hỏi |
| Baseline metrics | `data/results/baseline_metrics.json` | Đầy đủ | Hit rate: 1.000 |
| Quality/freshness | `data/quality/baseline_quality_report.json` | Đầy đủ | GX 1.x: PASS |
| Baseline report | `data/reports/phase1_report.md` | Đầy đủ | Markdown evidence |

### Baseline Metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | **1.000** | 10/10 câu hỏi tìm thấy đúng tài liệu gốc trong Top-4 context |
| `mean_token_f1` | **1.000** | Câu trả lời trích xuất khớp hoàn hảo với ground-truth |
| `judge_accuracy` | **1.000** | Toàn bộ 10 câu trả lời được đánh giá chính xác |
| `mean_judge_score` | **5.000** | Điểm tuyệt đối 5/5 trên thang đo chất lượng |

---

## 8. Data Quality & Freshness SLA

### Great Expectations 1.x Quality Checks

| Check | Quality Dimension | Ngưỡng / Kỳ vọng | Kết quả Baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `ExpectTableRowCountToBeBetween` | Completeness | 1 đến 24 dòng | **PASS** (24 dòng) | `baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` | Validity | `paper_id` not null | **PASS** (0 null) | `baseline_quality_report.json` |
| `ExpectColumnValuesToBeUnique` | Uniqueness | `paper_id` unique | **PASS** (0 trùng lặp) | `baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` | Validity | `title` not null | **PASS** (0 null) | `baseline_quality_report.json` |
| `ExpectColumnValueLengthsToBeBetween` | Completeness | `summary` 20–20,000 ký tự | **PASS** | `baseline_quality_report.json` |

### Freshness SLA
- **Ngưỡng quy định:** Tỷ lệ bài báo quá hạn (`age_days > 180`) không vượt quá 25%.
- **Kết quả đo thực tế:**
  - Bài mới nhất: `2026-07-22` | Bài cũ nhất: `2026-03-28`.
  - Số bài quá hạn: 1 / 24 (Tỷ lệ: 4.2% <= 25%).
  - Trạng thái Freshness: **PASS (is_fresh = True)**.

---

## 9. Synthetic Corruption Scenarios & Idempotent Repair

| Corruption Scenario | Cơ chế tạo lỗi | Số record bị ảnh hưởng | Tín hiệu Quality Gate | Tác động thực tế lên RAG | Cơ chế Repair |
| --- | --- | ---: | --- | --- | --- |
| **1. Drop Latest Records** | Xóa bỏ 20% bài báo mới nhất (5 bài) | 5 bài | Row count giảm còn 19 | Trực tiếp gây Retrieval Miss đối với câu hỏi về bài mới | Tải/đọc lại từ raw snapshot ban đầu |
| **2. Blank Summary** | Xóa rỗng `summary = ""` | 1 bài | GX check độ dài summary **FAIL** | Mất ngữ cảnh tóm tắt, trả lời sai | Nạp lại summary sạch từ `crossref_records.json` |
| **3. Inject Noise** | Chèn chuỗi rác `### NOISE CORRUPTED DATA ###` | 1 bài | Embedding vector bị lệch tâm | Giảm mạnh cosine similarity, rớt khỏi Top-4 | Khôi phục nguyên bản text từ raw |
| **4. Truncate Title** | Cắt ngắn tiêu đề `< 8` ký tự (`"AI RAG"`) | 1 bài | Phá vỡ exact match lookup | Agent không thể lookup chính xác bài báo | Tái lập tiêu đề đầy đủ từ raw |
| **5. Stale Dates** | Lùi ngày xuất bản về quá khứ 400 ngày | 6 bài | Freshness SLA **FAIL** (38.1% stale > 25%) | Không trực tiếp làm sai text nhưng vi phạm SLA dữ liệu mới | Khôi phục ngày xuất bản chuẩn ISO |
| **6. Duplicate Rows** | Nhân bản record đầu tiên | 1 bài | GX uniqueness check **FAIL** | Tăng trùng lặp context khi retrieve | Áp dụng logic khử trùng lặp theo `paper_id` |

---

## 10. Bảng so sánh đối chiếu 3 trạng thái

| Metric / Signal | Baseline (Sạch) | Corrupted (Bẩn) | Repaired (Phục hồi) | Thay đổi do Corruption | Mức phục hồi sau Repair | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | **1.000** | **0.600** | **1.000** | Giảm 40% | **100%** | Dữ liệu bị drop & noise làm hỏng truy vấn |
| `mean_token_f1` | **1.000** | **0.651** | **1.000** | Giảm 34.9% | **100%** | Câu trả lời bị sai lệch/cắt cụt |
| `judge_accuracy` | **1.000** | **0.700** | **1.000** | Giảm 30% | **100%** | Độ tin cậy câu trả lời giảm sút |
| `mean_judge_score` | **5.000** | **3.400** | **5.000** | Giảm 1.6 điểm | **100%** | Chất lượng tổng thể phục hồi hoàn toàn |
| Quality Checks (GX 1.x) | **PASS** | **FAIL** | **PASS** | Báo động đỏ | **Khôi phục PASS** | Bắt được vi phạm unique & summary length |
| Freshness SLA | **PASS** (4.2%) | **FAIL** (38.1%) | **PASS** (4.2%) | Vi phạm ngưỡng 25% | **Khôi phục PASS** | Đưa tỷ lệ bài cũ về dưới ngưỡng an toàn |

### Hai kết luận nhân quả then chốt:
1. **Dữ liệu bẩn dẫn đến Silent Failure:** Khi dữ liệu bị tiêm lỗi (xóa tóm tắt, cắt ngắn tiêu đề, chèn nhiễu), hệ thống RAG không báo lỗi crash code mà âm thầm trả về kết quả sai hoặc thiếu chính xác (Hit Rate giảm từ 1.000 xuống 0.600). Nhờ có Data Observability Gate (GX 1.x + Freshness SLA), hệ thống đã bắt được sự cố ngay lập tức.
2. **Idempotent Repair giúp phục hồi tự động 100%:** Bằng cách duy trì data lineage và raw snapshot bất biến, cơ chế repair tái tạo lại clean dataset và vector index `papers-repaired`, giúp toàn bộ các chỉ số retrieval và QA lấy lại phong độ hoàn hảo 100% mà không cần sửa tay.

---

## 11. Vấn đề tích hợp quan trọng đã xử lý

- **Triệu chứng:** Khi chạy Great Expectations trên môi trường Python 3.13 / Windows, các hàm cũ của GX 0.x gây crash do không tương thích module `great_expectations.dataset`.
- **Nguyên nhân:** Great Expectations đã chuyển dịch hoàn toàn sang **GX 1.x Fluent API** và quản lý batch qua `DataAsset` và `BatchDefinition`.
- **Cách xử lý:** Thiết kế lại toàn bộ hàm `run_data_quality_checks` trong `src/observability/quality.py` theo đúng chuẩn Ephemeral Context của GX 1.x:
  ```python
  context = gx.get_context(mode="ephemeral")
  data_source = context.data_sources.add_pandas("papers")
  data_asset = data_source.add_dataframe_asset(name="normalized_papers")
  batch_def = data_asset.add_batch_definition_whole_dataframe("all_papers")
  batch = batch_def.get_batch(batch_parameters={"dataframe": df})
  ```
- **Xác minh:** Kiểm thử tự động `tests/test_quality.py` chạy qua 100% và file `data/quality/baseline_quality_report.json` được tuần tự hóa JSON chuẩn mực.

---

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| Corpus hiện tại gồm 24 bài báo mẫu | Chưa thử nghiệm được tải lớn (Big Data) | Mở rộng ingestion phân trang (pagination) lên 1,000+ bài báo với phân vùng Partition |
| Đánh giá LLM Judge mặc định chạy fallback offline | Chưa kiểm tra chi tiết các sắc thái văn phong phức tạp | Cấu hình tích hợp Ragas end-to-end qua LLM API Key thật khi triển khai Cloud |

---

## 13. Checklist nghiệm thu bài nộp

- [x] Thông tin nhóm và link GitHub chính xác.
- [x] Phân công trách nhiệm khớp với từng module và deliverable thực tế.
- [x] Đã chạy kiểm chứng thành công `run_phase1.py` và `run_corruption_flow.py`.
- [x] Sử dụng chung bộ test set 10 câu cho cả 3 trạng thái.
- [x] Bảng số liệu đối chiếu khớp 100% với các file trong `data/results/` và `data/reports/`.
- [x] Báo cáo Data Quality và Freshness thể hiện đúng thực tế kiểm định.
- [x] Toàn bộ 27 test cases Pytest passed.
- [x] Tuyệt đối không commit file `.env`, API Key hay token bí mật vào repository.
