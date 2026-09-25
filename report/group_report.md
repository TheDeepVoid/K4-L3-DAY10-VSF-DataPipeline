# Báo cáo nhóm — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 |
| Tên nhóm | K4A-DAY10-VSF-DataPipeline |
| Repository | https://github.com/TheDeepVoid/K4-L3-DAY10-VSF-DataPipeline |
| Ngày hoàn thành | 2026-09-25 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| ---: | --- | --- | --- | --- |
| 1 | Bùi Thị Ngọc Trân | 2A202602529 | Data Foundation, reporting và demo UI | `crossref.py`, `cleaning.py`, Raw recovery, `report/`, `app.py` |
| 2 | Nguyễn Thị Mừng | 2A202602575 | Pipeline integration và Retrieval | `core/`, `phase1.py`, `corruption_flow.py`, MiniLM, ChromaDB, `retrieval/` |
| 3 | Nguyễn Hải Đăng | 2A202602963 | Observability và Evaluation | `quality.py`, Freshness SLA, `testset.py`, quality/comparison reports |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thiện pipeline RAG từ thu thập metadata Crossref đến quality gate, embedding, ChromaDB, evaluation, corruption và repair từ Raw. Snapshot Crossref được parse thành 24 `PaperRecord`, làm sạch thành 24 dòng duy nhất và lưu tại `data/clean/`. Baseline pipeline sinh embedding bằng `sentence-transformers/all-MiniLM-L6-v2`, benchmark 5 câu hỏi, metrics, quality reports và phase 1 report. Thí nghiệm corruption tạo 6 loại lỗi gồm mất record mới, summary rỗng, text noise, title bị cắt, ngày stale và duplicate rows. Tác động rõ nhất là retrieval hit rate giảm từ 1.0000 xuống 0.2000, còn mean token F1 giảm từ 0.3400 xuống 0.0000; quality gate chuyển từ PASS sang FAIL do duplicate và summary quá ngắn. Repair đọc lại `data/raw/crossref_records.json`, rebuild clean data và index, đưa quality gate về PASS và phục hồi toàn bộ metrics về baseline. Freshness vẫn PASS trong cả ba trạng thái vì stale ratio cao nhất là 2/24, dưới ngưỡng 25%. Giới hạn chính là LLM judge đang dùng fallback heuristic và Ragas chưa chạy; ngoài ra thí nghiệm đo tác động kết hợp của corruption, chưa cô lập từng lỗi riêng lẻ.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API hoặc snapshot offline
    -> raw response và raw records
    -> parse PaperRecord
    -> cleaning và data modeling
    -> Great Expectations + Freshness Gate
    -> MiniLM embedding + ChromaDB
    -> benchmark evaluation baseline
    -> inject 6 corruption scenarios
    -> corrupted re-index và re-evaluate
    -> rebuild clean data từ Raw snapshot
    -> repaired re-index và re-evaluate
    -> comparison report và Streamlit dashboard
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref payload/snapshot | Parse DOI, title, abstract, author, subject, ngày; fallback khi lỗi API | `data/raw/crossref_response.json`, `crossref_records.json` | Bùi Thị Ngọc Trân |
| Cleaning | `PaperRecord` | Normalize text, parse date, tính `age_days`, deduplicate, tạo embedding text | `data/clean/papers_clean.csv/json` | Bùi Thị Ngọc Trân |
| Embedding/index | Clean dataframe | MiniLM embedding, tạo collection theo trạng thái | `data/embeddings/`, ChromaDB local | Nguyễn Thị Mừng |
| Evaluation | Test set + index | Retrieval, QA answer, hit rate, token F1, judge | `data/results/*_metrics.json`, `*_answers.json` | Nguyễn Thị Mừng |
| Observability | Dataframe | GX 1.x expectations và Freshness SLA | `data/quality/*_quality_report.json`, freshness reports | Nguyễn Hải Đăng |
| Corruption/repair | Clean dataframe và Raw records | Tiêm 6 lỗi; rebuild repaired data từ Raw | `corruption_log.json`, repaired artifacts, comparison report | Bùi Thị Ngọc Trân + Nguyễn Thị Mừng |
| Orchestration | Settings và artifacts | Kết nối thứ tự các phase | `phase1_report.md`, `corruption_report.md` | Nguyễn Thị Mừng |
| Demo/report | Metrics và quality artifacts | Dashboard Streamlit và báo cáo nhóm/cá nhân | `app.py`, `report/` | Bùi Thị Ngọc Trân |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-5-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày; cảnh báo khi stale ratio > 25% |
| Random seed | Không dùng; corruption dùng lựa chọn deterministic theo thứ tự dataframe |

Không ghi API key hoặc nội dung `.env` vào report.

### Lệnh cài đặt

```powershell
python -m pip install -e .
```

### Lệnh chạy

```powershell
python script/run_phase1.py
python script/run_corruption_flow.py
streamlit run app.py --server.port 8502
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công | 2026-09-25 | `baseline_metrics.json`, `phase1_report.md` |
| Corruption flow | Thành công | 2026-09-25 | `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_report.md` |
| Streamlit dashboard | Thành công | 2026-09-25 | `http://localhost:8502`, health check trả `ok` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API hoặc `data/raw/crossref_response.json` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:<180 ngày trước>,has-abstract:true` |
| Thời điểm lấy dữ liệu | Snapshot local được dùng cho reproducible run; ngày chạy 2026-09-25 |
| Số record nhận được | 24 |
| Cơ chế retry/backoff | Khi `REFRESH_SOURCE` bật, gọi live API; HTTP 429/request error/JSON error chuyển sang snapshot offline. Không ghi nhận retry backoff nhiều lần trong flow hiện tại. |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | string | Có | DOI chuẩn hóa | Bỏ record nếu thiếu |
| `title` | string | Có | Tiêu đề | Bỏ record nếu rỗng |
| `summary` | string | Có | Abstract đã bỏ XML/JATS | Bỏ record nếu rỗng |
| `authors` | list[string] | Không | Danh sách tác giả | Dùng list rỗng nếu thiếu |
| `categories` | list[string] | Không | Chuyên ngành | Dùng list rỗng nếu thiếu |
| `published` | ISO date string | Có | Ngày xuất bản | Bỏ record nếu parse lỗi |
| `authors_joined` | string | Có trong clean | Tác giả nối bằng dấu phẩy | Tạo từ `authors` |
| `categories_joined` | string | Không | Chuyên ngành nối bằng dấu phẩy | Tạo từ `categories` |
| `age_days` | integer | Có trong clean | Tuổi dữ liệu tại run date | Tính từ `published` |
| `text_for_embedding` | string | Có trong clean | Context 5 phần cho embedding | Dựng từ các cột clean |

### Quy tắc cleaning

| Quy tắc | Quality dimension | Số record bị tác động | Cách xác minh |
| --- | --- | ---: | --- |
| Loại whitespace thừa và thẻ XML/JATS | Validity | 24 records được normalize | `crossref.py`, clean JSON |
| Loại record thiếu DOI/title/summary hoặc ngày lỗi | Completeness/Validity | 0 record snapshot bị loại | Clean row count = 24 |
| Chuẩn hóa DOI lowercase và bỏ URL prefix | Validity/Uniqueness | 24 records | `paper_id` trong raw/clean |
| Khử duplicate theo `paper_id` | Uniqueness | Baseline không có duplicate | Quality report baseline PASS |
| Tạo `age_days` và `text_for_embedding` | Timeliness/Usability | 24 records | Clean CSV/JSON |

`text_for_embedding` gồm `Title`, `Authors`, `Published`, `Categories`, `Summary`. Document ID trong ChromaDB có dạng `paper_id::index`; metadata vẫn giữ `paper_id` để đo retrieval hit.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 5 |
| Các `question_type` | `summary`, `authors`, `date`, `category`, `multi_hop` |
| Ground-truth document ID | Lấy từ `paper_id` của record được chọn trong clean dataframe |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB local; `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 mặc định; smoke test dùng 2 |
| LLM provider/model | Cấu hình `openai`/`gpt-5-mini`; judge fallback heuristic trong lần chạy do evaluator LLM không được gọi thành công |
| Test set dùng chung | `data/eval/test_set.json` |

Giữ nguyên test set để mọi thay đổi metrics đến từ chất lượng dataset/index, không đến từ việc đổi câu hỏi, ground truth hoặc benchmark distribution.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | Snapshot và normalized records |
| Cleaned dataset | `data/clean/` | Có | Baseline, corrupted, repaired CSV/JSON |
| Embedding manifest/index | `data/embeddings/` | Có | Ba embedding manifests |
| Evaluation set | `data/eval/test_set.json` | Có | 5 samples, 5 question types |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | 5 evaluation samples |
| Quality/freshness | `data/quality/` | Có | GX và freshness cho ba trạng thái |
| Baseline report | `data/reports/phase1_report.md` | Có | Markdown baseline report |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | Tất cả benchmark đều truy hồi đúng ground-truth document |
| `mean_token_f1` | 0.3400 | Câu trả lời có overlap một phần với ground truth |
| `judge_accuracy` | 0.2000 | Chỉ 20% câu được heuristic judge đánh giá đúng |
| `mean_judge_score` | 2.0000 | Điểm trung bình thấp; cần lưu ý judge không phải LLM pass thực tế |
| Ragas | N/A/skipped | Chỉ chạy khi `RUN_RAGAS=1`; lần này không bật |

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| Row count | Completeness | 5–5000 | PASS, 24 | `baseline_quality_report.json` |
| `paper_id` not null | Completeness | Không null | PASS | `baseline_quality_report.json` |
| `title` not null | Completeness | Không null | PASS | `baseline_quality_report.json` |
| `text_for_embedding` not null | Completeness | Không null | PASS | `baseline_quality_report.json` |
| `paper_id` unique | Uniqueness | Không duplicate | PASS | `baseline_quality_report.json` |
| `summary` length | Validity | Tối thiểu 30 ký tự | PASS | `baseline_quality_report.json` |

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataframe trước embedding |
| Timestamp mới nhất | 2026-07-22 |
| Ngưỡng freshness | `age_days > 180`; stale ratio tối đa 25% |
| Trạng thái baseline | Fresh |
| Lý do | 1/24 stale, tương đương 4.17%, thấp hơn 25% |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| Drop latest records | Bỏ 4 record mới nhất | 4 | Freshness tăng, retrieval giảm | Dataset được bù dòng bởi duplicate để giữ 24 rows | Rebuild từ Raw |
| Blank summary | Gán summary rỗng | 2 | Summary length fail | Quality gate fail | Rebuild từ Raw |
| Inject text noise | Thêm chuỗi noise vào embedding text | 3 | Retrieval/embedding suy giảm | Hit rate giảm trong combined run | Rebuild từ Raw |
| Truncate title | Cắt title còn dưới 10 ký tự | 2 | Retrieval suy giảm | Làm sai context/title matching | Rebuild từ Raw |
| Stale date | Đổi published về 2021-09-26 | 2 | Stale rows tăng | 2/24 stale, vẫn dưới ngưỡng 25% | Rebuild từ Raw |
| Duplicate rows | Nhân bản 4 dòng | 4 | Unique expectation fail | Quality gate FAIL | Rebuild từ Raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log đủ 6 scenario, action, số dòng và paper IDs bị tác động.

Repair đọc lại `data/raw/crossref_records.json`, không dùng dataframe corrupted làm nguồn sự thật. Sau đó pipeline chạy lại cleaning, quality, freshness, embedding và evaluation với cùng `test_set.json`.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.2000 | 1.0000 | -0.8000 | 100% | Phục hồi hoàn toàn |
| `mean_token_f1` | 0.3400 | 0.0000 | 0.3400 | -0.3400 | 100% | Phục hồi hoàn toàn |
| `judge_accuracy` | 0.2000 | 0.0000 | 0.2000 | -0.2000 | 100% | Dựa trên heuristic judge |
| `mean_judge_score` | 2.00 | 1.20 | 2.00 | -0.80 | 100% | Trở lại baseline |
| Quality checks pass/fail | PASS | FAIL | PASS | PASS→FAIL | PASS | Duplicate/summary length được phát hiện |
| Freshness status | PASS | PASS | PASS | Không đổi status | PASS | Stale rows 1→2→1 |

Kết luận nhân quả:

1. Corruption kết hợp làm xuất hiện duplicate IDs và summary ngắn → quality gate FAIL; đồng thời làm retrieval hit rate giảm `1.0 → 0.2` và token F1 giảm `0.34 → 0`.
2. Repair bằng Raw snapshot → clean dataframe và index được rebuild độc lập → quality gate PASS, stale rows giảm `2/24 → 1/24`, các metrics quay lại baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Một số lệnh checkpoint báo `ModuleNotFoundError: No module named 'core'`; GX 1.x cũng yêu cầu suite/validation definition được đăng ký vào ephemeral context.
- **Nguyên nhân:** Project dùng `src` layout chưa được cài editable; GX 1.23 yêu cầu lifecycle API đầy đủ hơn snippet rút gọn.
- **Cách xử lý:** Dùng `.venv`, chạy `python -m pip install -e .`; trong quality gate dùng `gx.get_context(mode="ephemeral")`, đăng ký suite và validation definition trước khi run.
- **Cách xác minh:** Baseline và corruption flow chạy exit code 0, sinh đủ metrics/reports; Streamlit health check trả `ok`.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| LLM judge fallback heuristic; Ragas skipped | Judge metrics chưa đại diện cho một LLM evaluator thật | Cấu hình credential hợp lệ, bật LLM judge/Ragas và ghi rõ provider trong report |
| Corruption được tiêm cùng một lần chạy | Không cô lập được tác động riêng của từng lỗi | Chạy từng scenario độc lập và so sánh delta metrics |
| Snapshot có 24 bài báo | Kết luận chưa đại diện corpus production lớn | Chạy thêm nhiều batch Crossref và theo dõi drift theo thời gian |
| ChromaDB local artifact được tạo lại khi build | Không phù hợp cho deploy nhiều máy | Dùng persistent vector service hoặc artifact registry |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn tất báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
