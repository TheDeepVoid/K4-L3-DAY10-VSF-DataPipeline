# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

> Báo cáo này tập trung vào phần việc cá nhân: thu thập Crossref, làm sạch dữ liệu và khôi phục dữ liệu từ Raw. Các mục chưa có artifact thực tế được ghi rõ là chưa hoàn thành.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Bùi Thị Ngọc Trân |
| MSSV | 2A202602529 |
| Khóa/Lớp | K4 |
| Tên nhóm | K4A-DAY10-VSF-DataPipeline |
| Vai trò chính | Data ingestion, data cleaning và Raw recovery |
| Repository | https://github.com/TheDeepVoid/K4-L3-DAY10-VSF-DataPipeline |
| Ngày hoàn thành | 2026-09-25 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Thu thập và chuẩn hóa metadata Crossref | `src/ingestion/crossref.py`: `parse_crossref_payload`, `fetch_source_records`, `load_raw_records` | Crossref payload hoặc `data/raw/crossref_response.json` | `data/raw/crossref_records.json`, danh sách `PaperRecord` | Hoàn thành |
| Làm sạch và tạo dữ liệu cho embedding | `src/ingestion/cleaning.py`: `build_clean_dataframe` | Danh sách `PaperRecord`, `run_date` | `data/clean/papers_clean.csv`, `papers_clean.json` | Hoàn thành |
| Khôi phục dữ liệu từ Raw | `load_raw_records`, `build_clean_dataframe`, `corruption_flow.py` | Raw snapshot Crossref | Repaired clean data, repaired metrics và comparison report | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp dữ liệu sạch vào baseline pipeline | `src/pipelines/phase1.py`, retrieval/index | Baseline pipeline chạy với 24 records và tạo ChromaDB local |
| Kiểm tra contract dữ liệu cho quality gate | `src/observability/quality.py` | Quality gate baseline trả `success: true` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Parse Crossref metadata | `src/ingestion/crossref.py` | Chuẩn hóa DOI, title, abstract, authors, categories và ngày ISO 8601 | Fetch từ snapshot trả 24 records |
| Fallback offline | `data/raw/crossref_response.json` | Pipeline tiếp tục chạy khi không gọi API live | `fetch_source_records` đọc snapshot và trả 24 records |
| Làm sạch dữ liệu | `src/ingestion/cleaning.py` | 24 dòng sạch, có `age_days`, helper columns và `text_for_embedding` | Clean checkpoint trả 24 dòng |
| Khôi phục dữ liệu gốc | `data/raw/crossref_records.json` | Raw records có thể nạp lại qua `load_raw_records` để rebuild clean data | Đã kiểm tra load raw và chạy lại cleaning |

Output quan trọng nhất là `data/clean/papers_clean.json` gồm 24 bản ghi duy nhất, có thể dùng trực tiếp cho embedding và quality gate.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Crossref trả dữ liệu lồng nhau, abstract có thể chứa JATS/XML, title nằm trong list và ngày xuất bản nằm trong `date-parts`. Ngoài ra, pipeline cần tiếp tục làm việc khi API bị giới hạn tốc độ hoặc phòng lab mất mạng. Dữ liệu sau ingestion cũng cần có schema ổn định để dùng cho embedding, quality checks và khôi phục.

### Cách triển khai

`parse_crossref_payload` duyệt `message.items`, chuẩn hóa DOI về dạng lowercase không có tiền tố URL, loại thẻ XML/HTML khỏi abstract, gom tên tác giả và chuyên ngành, rồi chuyển ngày Crossref sang ISO 8601. Record thiếu DOI, title hoặc summary bị loại khỏi output.

`fetch_source_records` ưu tiên gọi API khi `REFRESH_SOURCE` được bật. Nếu request lỗi, gặp `429`, hoặc JSON không hợp lệ, pipeline đọc `data/raw/crossref_response.json`. Sau đó payload được parse và lưu thành `data/raw/crossref_records.json`.

`build_clean_dataframe` chuẩn hóa text, parse ngày, tính `age_days = (run_date - published).days`, tạo `authors_joined`, `categories_joined`, `summary_chars` và `text_for_embedding`, rồi khử trùng lặp theo `paper_id`.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref payload hoặc raw JSON; mỗi record gồm DOI, title, abstract, author, subject và ngày |
| Output | `PaperRecord` và dataframe sạch có 24 dòng duy nhất |
| Module phụ thuộc | `core.config.Settings`, `core.utils`, pandas, requests |
| Module sử dụng output | `cleaning.py`, `quality.py`, `retrieval/index.py`, baseline pipeline |
| Điều kiện lỗi cần xử lý | Mất mạng, HTTP 429, thiếu abstract/title/DOI, ngày không parse được, duplicate DOI |

### Cách xác minh

```powershell
python -c "from core.config import load_settings; from ingestion.crossref import fetch_source_records; s=load_settings(); r=fetch_source_records(s); print(len(r))"

python -c "from datetime import datetime, timezone; from core.config import load_settings; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s=load_settings(); df=build_clean_dataframe(load_raw_records(s.paths.raw_records_json), datetime.now(timezone.utc)); print(len(df))"
```

- **Kết quả mong đợi:** lần lượt `24` và `24`.
- **Kết quả thực tế:** đã nhận được 24 raw records và 24 clean rows.
- **Artifact/log:** `data/raw/crossref_response.json`, `data/raw/crossref_records.json`, `data/clean/papers_clean.csv`, `data/clean/papers_clean.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** API Crossref có thể unavailable hoặc trả `429`, nhưng bài lab vẫn cần chạy reproducibly.
- **Các phương án đã cân nhắc:** bắt buộc gọi API live mỗi lần; hoặc lưu snapshot raw và dùng fallback offline.
- **Phương án đã chọn:** lưu nguyên payload tại `data/raw/crossref_response.json` và tự động fallback sang snapshot khi live request thất bại.
- **Lý do:** snapshot bảo toàn lineage, không phụ thuộc mạng và cho phép mọi thành viên chạy cùng một input. Đổi lại, dữ liệu offline có thể không phải dữ liệu mới nhất.
- **Bằng chứng:** fallback đã nạp được 24 records; clean artifact cũng có 24 dòng và quality gate baseline trả `success: true`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `ModuleNotFoundError: No module named 'core'`.
- **Lệnh hoặc bước tái hiện:** chạy lệnh checkpoint trong terminal chưa cài project ở chế độ editable.
- **Nguyên nhân gốc:** Python path chưa nhận thư mục `src`, không phải lỗi parser hoặc dữ liệu.
- **Cách xử lý:** kích hoạt đúng `.venv` và cài project bằng `python -m pip install -e .`; khi cần, chạy bằng `.venv\Scripts\python.exe` và thêm `src` vào `sys.path` để kiểm tra độc lập.
- **Cách xác minh sau khi sửa:** ingestion trả 24 records, cleaning trả 24 rows, baseline pipeline exit code 0.
- **Điều học được:** cần kiểm tra interpreter và package path trước khi kết luận code pipeline bị lỗi.

## 7. Hiểu biết về luồng end-to-end

1. Crossref payload được lưu nguyên bản, parse thành `PaperRecord`, rồi cleaning tạo dataframe có `text_for_embedding`; dataframe này được quality gate kiểm tra trước khi đưa vào MiniLM và ChromaDB.
2. Mỗi benchmark sample có `ground_truth_doc_ids`. Retrieval hit được tính khi ID của tài liệu đúng xuất hiện trong các tài liệu truy hồi; token F1 và judge so sánh câu trả lời với `ground_truth`.
3. Quality checks kiểm tra schema, null, duplicate, row count và độ dài summary. Freshness monitoring riêng theo dõi tỷ lệ record có `age_days > 180`.
4. Dùng cùng test set cho baseline, corrupted và repaired để thay đổi metric phản ánh chất lượng dữ liệu, không bị trộn với thay đổi câu hỏi hoặc ground truth.
5. Repair được xem là thành công khi dữ liệu sau repair có artifact hợp lệ, quality gate pass, freshness ratio hợp lệ và metrics quay lại baseline. Flow đã tạo `repaired_metrics.json`; kết quả thực tế cho thấy các metrics repaired trùng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.2000 | 1.0000 | Corruption làm mất 80% hit rate; repair phục hồi hoàn toàn |
| `mean_token_f1` | 0.3400 | 0.0000 | 0.3400 | Answer quality sụt về 0 và trở lại baseline sau repair |
| `judge_accuracy` | 0.2000 | 0.0000 | 0.2000 | Corrupted answers bị đánh giá sai; repaired trùng baseline |
| `mean_judge_score` | 2.0000 | 1.2000 | 2.0000 | Điểm judge giảm 0.8 rồi phục hồi |
| Quality checks | PASS | FAIL | PASS | Corrupted fail ở uniqueness và summary length; repaired pass |
| Freshness status | PASS | PASS | PASS | Corrupted có 2/24 stale nhưng 8.33% chưa vượt ngưỡng 25% |

### Kết luận từ số liệu

1. **Data corruption** → quality gate chuyển `PASS` thành `FAIL` do duplicate IDs và summary quá ngắn, trong khi freshness vẫn `PASS` với 2/24 stale → retrieval hit rate giảm từ `1.0` xuống `0.2` và token F1 giảm từ `0.34` xuống `0`.
2. **Repair từ Raw** → đọc lại `crossref_records.json`, rebuild clean dataframe và index → quality gate chuyển từ `FAIL` về `PASS`, stale rows giảm từ `2/24` xuống `1/24`, retrieval hit rate và các metrics quay lại đúng baseline.

Corruption ảnh hưởng rõ nhất là tác động kết hợp của việc drop latest records, truncate title và inject text noise, làm retrieval hit rate giảm 80%; không thể quy mức giảm này cho riêng từng kịch bản vì chúng được tiêm trong cùng một lần chạy. Về quality gate, duplicate rows và blank summary bị phát hiện trực tiếp qua uniqueness và summary length; stale date chỉ tạo cảnh báo freshness vì tỷ lệ 8.33% còn dưới ngưỡng 25%.

Kết quả khác kỳ vọng ban đầu là baseline `retrieval_hit_rate` đạt 1.0 nhưng `mean_token_f1` chỉ 0.34 và judge accuracy là 0.20. Điều này cho thấy truy hồi đúng tài liệu chưa đảm bảo câu trả lời khớp ground truth, đặc biệt khi answer extraction và judge fallback còn đơn giản.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Raw snapshot giúp pipeline reproducible và có thể khôi phục mà không phụ thuộc API hoặc mạng.
2. Cleaning không chỉ là xóa ký tự rác; schema, ngày tháng, duplicate key và text tổng hợp đều ảnh hưởng đến các bước sau.
3. Retrieval hit cao không đồng nghĩa answer quality cao; cần theo dõi nhiều metric cùng quality/freshness signals.

### Nếu có thêm thời gian

Đã hoàn thiện và chạy `corruption_flow.py`. Cải thiện tiếp theo là thêm test tự động kiểm tra tính idempotent: chạy repair hai lần phải tạo cùng schema, cùng số dòng và cùng các metrics với baseline.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Bùi Thị Ngọc Trân
**Ngày xác nhận:** 2026-09-25
