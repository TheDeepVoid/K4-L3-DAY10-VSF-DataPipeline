# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

> Báo cáo này tập trung vào phần việc của tôi: Data Observability (Great Expectations 1.x + Freshness SLA), xây dựng benchmark test set và các báo cáo quality/comparison. Mọi số liệu trong báo cáo được đọc trực tiếp từ artifact trong `data/` và đối chiếu chéo với source code, không sao chép từ báo cáo nhóm. Những điểm khác với `group_report.md` được nêu rõ ở mục 8.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Hải Đăng |
| MSSV | 2A202602963 |
| Khóa/Lớp | K4 |
| Tên nhóm | K4A-DAY10-VSF-DataPipeline |
| Vai trò chính | Data Observability (GX 1.x + Freshness SLA) và Evaluation (test set, quality/comparison reports) |
| Repository | https://github.com/TheDeepVoid/K4-L3-DAY10-VSF-DataPipeline |
| Ngày hoàn thành | 2026-09-25 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Quality gate Great Expectations 1.x | `src/observability/quality.py`: `run_data_quality_checks` | Dataframe sạch 24 dòng, `Settings`, tên report theo trạng thái | `data/quality/baseline_quality_report.json`, `corrupted_quality_report.json`, `repaired_quality_report.json` | Hoàn thành |
| Freshness SLA | `quality.py`: `build_freshness_report` và khối `freshness` trong quality report | Cột `age_days`, `published`, `settings.freshness_threshold_days = 180` | `data/quality/freshness_report.json`, `corrupted_freshness_report.json`, `repaired_freshness_report.json` | Hoàn thành |
| Benchmark test set | `src/evaluation/testset.py`: `build_test_set`, `load_or_create_test_set` | Dataframe sạch đã dedupe | `data/eval/test_set.json` (5 samples, đủ 5 `question_type`) | Hoàn thành, giới hạn: 5 câu thay vì 10 như CP2/RUBRIC |
| Báo cáo đối chiếu 3 trạng thái | `src/observability/reporting.py`: `generate_corruption_report` (khối Quality và Freshness) | Metrics 3 trạng thái, quality 2 trạng thái, freshness 2 trạng thái | `data/reports/corruption_report.md` | Hoàn thành |

Phần không thuộc ownership của tôi nhưng có liên quan trực tiếp: `generate_phase1_report` và việc chạy hai flow (`src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`) do Nguyễn Thị Mừng phụ trách. Tôi không sửa logic orchestration, chỉ cung cấp và kiểm chứng hai tín hiệu quality/freshness mà các flow đó tiêu thụ.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Kiểm chứng quality/freshness artifact cho cả 3 trạng thái | Nguyễn Thị Mừng — `corruption_flow.py` | Đối chiếu `data/quality/*.json` với `data/clean/*.csv`: baseline 0 duplicate/0 summary ngắn/1 stale; corrupted 4 duplicate/4 summary ngắn/2 stale; repaired khớp baseline |
| Phân tích tác động từng scenario lỗi từ log và ground truth | Bùi Thị Ngọc Trân — `corruption.py` | Xác định 4/5 ground-truth `paper_id` trùng đúng 4 record bị `drop_latest_records`; kết luận đây là nguyên nhân chính của sụt hit rate |
| Chuẩn bị tín hiệu cho dashboard | Bùi Thị Ngọc Trân — `app.py` | Xác nhận `app.py` đọc `*_quality_report.json` và `*_freshness_report.json`; cung cấp ngưỡng 25% và ngày `latest_published` để hiển thị |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Dựng quality gate bằng GX 1.x lifecycle API | `src/observability/quality.py` | Suite gồm 6 expectation (row count, 3 not-null, unique, summary length) chạy trên ephemeral context; `success: true` ở baseline | `python script/run_phase1.py` → `baseline_quality_report.json` |
| Định nghĩa Freshness SLA | `quality.py`, `settings.freshness_threshold_days` | Ngưỡng 180 ngày, cảnh báo khi stale ratio > 25%; baseline 1/24 = 4.17% → `is_fresh: true` | `data/quality/freshness_report.json` |
| Sinh và ổn định benchmark test set | `src/evaluation/testset.py`, `data/eval/test_set.json` | 5 samples với `ground_truth_doc_ids` lấy từ `paper_id`; file được tái sử dụng nguyên vẹn cho baseline/corrupted/repaired | `data/eval/test_set.json` + `baseline_answers.json` |
| Xuất bảng đối chiếu 3 trạng thái | `reporting.py: generate_corruption_report`, `data/reports/corruption_report.md` | Bảng 4 metric × 3 trạng thái + bảng quality/freshness; quality gate `FAIL → PASS` | `data/reports/corruption_report.md` |
| Truy vết lỗi khi quality gate fail | Đối chiếu `corrupted_quality_report.json` với `data/clean/papers_clean_corrupted.csv` | Gate fail ở `expect_column_values_to_be_unique` và `expect_column_value_lengths_to_be_between`; 4 dòng summary < 30 ký tự và 4 `paper_id` trùng | Đếm trực tiếp trên CSV |

Output cụ thể nhất do phần việc của tôi tạo ra là `data/quality/corrupted_quality_report.json`: đây là bằng chứng duy nhất chứng minh quality gate phát hiện được dữ liệu bẩn trước khi số liệu agent sụt (`success: false` trong khi `freshness` vẫn `is_fresh: true`), và nó là cơ sở để kết luận ở mục 8 rằng gate chỉ bắt được 2 trong 6 kịch bản lỗi.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline RAG chỉ "chạy được" thì chưa đủ: nếu dữ liệu xuống cấp mà không có chốt chặn, hệ thống vẫn trả câu trả lời như thường và hỏng âm thầm (silent failure). Vấn đề tôi phụ trách là làm cho chất lượng dữ liệu trở thành tín hiệu quan sát được trước bước index, và tạo một bộ benchmark cố định để mọi thay đổi metric đo được đều quy về chất lượng dữ liệu chứ không về việc đổi câu hỏi.

### Cách triển khai

Quality gate dùng đúng lifecycle API của GX 1.x, theo thứ tự bắt buộc: `gx.get_context(mode="ephemeral")` → `context.data_sources.add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `ExpectationSuite` → `context.suites.add(suite)` → `ValidationDefinition` → `context.validation_definitions.add(...)` → `run()`. Suite gồm 6 expectation ánh xạ theo quality dimension: row count trong khoảng 5–5000 (Completeness), `paper_id`/`title`/`text_for_embedding` không null (Completeness), `paper_id` unique (Uniqueness), `summary` dài ≥ 30 ký tự (Validity). Hàm nhận tham số `report_name` nên cùng một code path sinh ra ba file quality report cho ba trạng thái, tránh phải sao chép logic.

Freshness SLA tính hoàn toàn từ `age_days` đã có sẵn ở cleaning thay vì parse lại ngày: `stale_rows = count(age_days > 180)`, `is_fresh = stale_rows / total_rows <= 0.25`. Cùng một dataframe được gọi hai lần — một lần qua `run_data_quality_checks` để ghi quality + freshness vào một file, một lần qua `build_freshness_report` để ghi file freshness riêng — vì dashboard và báo cáo đối chiếu đọc hai nguồn khác nhau.

Benchmark test set sinh deterministic từ 5 dòng đầu của dataframe đã dedupe, phủ `summary`, `authors`, `date`, `category`, `multi_hop`; `ground_truth_doc_ids` lấy trực tiếp `paper_id` nên đối chiếu được với metadata mà ChromaDB lưu. `load_or_create_test_set` ưu tiên đọc file đã tồn tại, nhờ đó cùng một bộ 5 câu hỏi được dùng cho cả ba lần đánh giá.

Một hạn chế tôi phát hiện khi đọc lại output: mảng `expectations` trong JSON chỉ lưu `type` và `success`, nên ba expectation `expect_column_values_to_not_be_null` trông giống hệt nhau và không biết cột nào fail. Tôi chưa sửa vì `app.py` và `corruption_flow.py` đang tiêu thụ shape này.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Dataframe sạch có `paper_id`, `title`, `summary`, `published`, `age_days`, `text_for_embedding`; `Settings` cho threshold và đường dẫn; `report_name` là chuỗi trạng thái |
| Output | `data/quality/<report_name>_quality_report.json` (`success`, `freshness`, `expectations`) và file freshness riêng (`latest_published`, `oldest_published`, `stale_rows`, `total_rows`, `is_fresh`) |
| Module phụ thuộc | `great_expectations` 1.x, `pandas`, `core.config.Settings` |
| Module sử dụng output | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, `src/observability/reporting.py`, `app.py` |
| Điều kiện lỗi cần xử lý | Dataframe rỗng (GX fail, freshness không chia được), cột `age_days`/`published` thiếu, cột bắt buộc của corruption không có, context GX đã đăng ký trùng tên |

### Cách xác minh

```bash
# Kiểm định quality gate trên clean data (CP1) — tạo thêm data/quality/test_quality_report.json
python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Quality check status = {res[\"success\"]}')"

# Đọc lại ba trạng thái, không chạy lại pipeline
python -c "import json,glob; [print(p.split('/')[-1], json.load(open(p))['success'], json.load(open(p))['freshness']['stale_rows']) for p in sorted(glob.glob('data/quality/*_quality_report.json'))]"

# Đối chiếu gate với dữ liệu thật (read-only)
python -c "import pandas as pd; [print(k, len(d), d.paper_id.duplicated().sum(), (d.summary.str.len()<30).sum()) for k in ['','_corrupted','_repaired'] for d in [pd.read_csv(f'data/clean/papers_clean{k}.csv')]]"
```

- **Kết quả mong đợi:** `True` cho clean data; `True / False / True` cho baseline/corrupted/repaired; số dòng 24 ở cả ba file.
- **Kết quả thực tế:** `True`; `baseline=True, corrupted=False, repaired=True` (kèm `test=True` từ lần kiểm định CP1); 24/24/24 dòng, duplicate `0/4/0`, summary ngắn `0/4/0`.
- **Artifact/log:** `data/quality/baseline_quality_report.json`, `corrupted_quality_report.json`, `repaired_quality_report.json`, `test_quality_report.json`, `freshness_report.json`, `corrupted_freshness_report.json`, `repaired_freshness_report.json`.

Cách tôi đối chiếu lại các con số trong báo cáo này: mọi giá trị `success`, `stale_rows`, `stale_ratio`, số dòng, số duplicate và số summary ngắn đều được đọc lại từ chính các file JSON/CSV trong `data/` bằng script chỉ dùng thư viện chuẩn, thay vì chỉ tin vào `corruption_report.md`. Riêng câu lệnh có `pandas`/`great_expectations` ở trên là lệnh kiểm định của nhóm trong CP1, cần môi trường đã cài; các số liệu tương ứng đã được tôi xác nhận lại bằng cách đọc artifact.

Lưu ý thao tác: **không** chạy lại `build_test_set(df, settings.paths.eval_testset)` trên repo hiện tại. Hàm này ghi đè `data/eval/test_set.json` bằng câu hỏi do generator sinh ra, khác với bản đã curated, và làm thay đổi cả ba metrics. Tôi chỉ đọc file, không sinh lại test set sau lần chạy đầu.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** ở CP4/CP5, quality gate chắc chắn sẽ FAIL trên dữ liệu bị tiêm lỗi. Nếu gate được dùng như một chốt chặn cứng thì pipeline dừng trước bước index và không sinh ra bằng chứng sụt giảm — đúng thứ mà lab yêu cầu đo.
- **Các phương án đã cân nhắc:** (1) tách quality gate và freshness thành hai entry point, và `raise`/exit khi gate FAIL; (2) gộp cả hai thành một hàm trả về đồng thời `success` và khối `freshness`, ghi một file cho mỗi trạng thái và không dừng flow.
- **Phương án đã chọn:** phương án (2). Gate được xem là **tín hiệu quan sát** được ghi lại và hiển thị, không phải cổng chặn.
- **Lý do:** (i) giữ được bằng chứng đo lường: `corrupted_metrics.json` với hit rate 0.2 chỉ tồn tại vì flow vẫn index và evaluate; (ii) một entry point cho cả ba lần gọi giảm rủi ro lệch contract giữa baseline/corrupted/repaired; (iii) trade-off được chấp nhận có chủ ý: dữ liệu FAIL vẫn đi vào ChromaDB, nên phải đọc `success` ở báo cáo và dashboard mới thấy được cảnh báo.
- **Bằng chứng quyết định phù hợp:** `corrupted_quality_report.json` có `success: false` nhưng vẫn chứa đầy đủ khối `freshness`, và `corrupted_metrics.json` vẫn được sinh với `retrieval_hit_rate: 0.2`. Nếu chọn phương án (1), hai artifact này không tồn tại và toàn bộ cột "Corrupted" trong `corruption_report.md` sẽ trống.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** snippet GX rút gọn kiểu cũ không chạy được trên GX 1.x (repo yêu cầu `great-expectations>=1.16.1`; báo cáo nhóm ghi lại môi trường chạy ở 1.23) — dùng các method cũ của data context sẽ hỏng ngay khi đăng ký suite, trước khi expectation nào được chạy. Tôi không lưu traceback gốc vào artifact nên không dán nguyên văn chuỗi lỗi; nguyên nhân thì xác định được. Kèm theo là lỗi môi trường `ModuleNotFoundError: No module named 'core'` khiến không import được `observability.quality` để kiểm chứng.
- **Lệnh hoặc bước tái hiện:** gọi `run_data_quality_checks` theo cách viết của tài liệu GX 0.x, rồi chạy lệnh kiểm định CP1 ở terminal chưa cài project.
- **Nguyên nhân gốc:** (i) GX 1.x bỏ API data context cũ, bắt buộc đi qua `ValidationDefinition` và phải đăng ký suite/validation definition vào context trước khi `run()` — đây là khác biệt về vòng đời API, không phải lỗi dữ liệu; (ii) project dùng `src` layout chưa được cài editable nên `src` không nằm trong `sys.path`.
- **Cách xử lý:** (i) viết lại `run_data_quality_checks` theo chuỗi `data_source → asset → batch_definition → suite → context.suites.add → ValidationDefinition → context.validation_definitions.add → run()` với `mode="ephemeral"`; (ii) phần môi trường do nhóm xử lý bằng `python -m pip install -e .` trong `.venv` — phần này không phải việc của tôi, tôi chỉ xác nhận lại bằng cách chạy được lệnh kiểm định sau khi cài.
- **Cách xác minh sau khi sửa:** `python script/run_phase1.py` và `python script/run_corruption_flow.py` chạy exit code 0, sinh đủ 3 quality report; kiểm định CP1 in ra `Quality check status = True` và tạo `data/quality/test_quality_report.json`.
- **Điều học được:** với thư viện bản lớn, phải kiểm tra version thật của môi trường trước khi dùng snippet tài liệu; và lỗi API versioning trông giống hệt lỗi dữ liệu nếu chỉ nhìn thông báo cuối cùng.

Nếu chưa xử lý xong:

- **Phạm vi bị ảnh hưởng:** kết luận "scenario nào ảnh hưởng nhất" ở mục 8, và khả năng truy vết lỗi từ quality report.
- **Những gì đã loại trừ:** (i) loại trừ giả thuyết "noise/truncate title là nguyên nhân chính" — 4 `ground_truth_doc_ids` trong `test_set.json` trùng đúng 4 `paper_id` của scenario `drop_latest_records`; (ii) loại trừ giả thuyết "corruption làm hỏng toàn bộ index" — 24/24 vector vẫn được index và 1/5 câu vẫn hit; (iii) loại trừ giả thuyết "repair chỉ vá tại chỗ" — `papers_clean_repaired.csv` khớp baseline ở duplicate, summary length và `age_days`.
- **Bước tiếp theo:** chạy 6 lần, mỗi lần chỉ tiêm một scenario rồi đo delta hit rate riêng, để thay kết luận suy luận bằng phép đo trực tiếp; đồng thời thêm `column`/`kwargs` vào từng expectation và `evaluated_at` + `dataset_fingerprint` vào quality report.

## 7. Hiểu biết về luồng end-to-end

1. Crossref payload được giữ nguyên ở `data/raw/crossref_response.json`, parse thành `PaperRecord` rồi cleaning thành dataframe có `age_days` và `text_for_embedding`. Dataframe này đi qua quality gate của tôi trước, rồi mới được MiniLM embed và nạp vào ChromaDB với `record_id = paper_id::index` nhưng metadata giữ `paper_id` — đó là lý do ground truth kiểu `paper_id` vẫn đo được.
2. Mỗi sample có `ground_truth_doc_ids`. `retrieval_hit` được tính khi bất kỳ ID trong `ground_truth_doc_ids` xuất hiện trong `retrieved_doc_ids`; `token_f1` so overlap token giữa `ground_truth` và `answer`; judge chấm 1–5 và trả `correct`. Tổng hợp mới thành 4 metric trong `*_metrics.json`.
3. Quality checks trả lời "dữ liệu có đúng hợp đồng không" (schema, null, unique, độ dài, số dòng) và dùng cơ chế pass/fail. Freshness trả lời "dữ liệu còn đủ mới không" và dùng tỷ lệ ngưỡng. Trong bài này tôi cố ý tách hai tín hiệu này vì chúng trả lời hai câu hỏi khác nhau: baseline dữ liệu đúng hợp đồng nhưng vẫn có 1/24 bài quá hạn, còn trạng thái corrupted sai hợp đồng lại vẫn "fresh" về mặt tỷ lệ.
4. Cùng test set là điều kiện để phép so sánh có nghĩa. Nếu mỗi trạng thái dùng bộ câu hỏi khác nhau thì `1.0 → 0.2` có thể do câu hỏi khó hơn chứ không phải do dữ liệu. Vì vậy tôi cố ý không sinh lại test set giữa các lần chạy và ghi rõ điều này trong báo cáo nhóm.
5. Repair được coi là thành công khi đồng thời thỏa: quality gate về `success: true`, freshness về `is_fresh: true` với `stale_rows` không tăng so với baseline, và 4 metric quay lại đúng giá trị baseline. Ở lần chạy này cả hai điều kiện đều đạt, nhưng tôi không coi đó là bằng chứng mạnh về tính bền vững vì test set chỉ có 5 câu.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.2000 | 1.0000 | Giảm đúng 4/5 câu; 4 `paper_id` ground truth trùng với 4 record mới nhất bị drop |
| `mean_token_f1` | 0.3400 | 0.0000 | 0.3400 | Về 0 vì 5/5 câu trả sai nội dung, không phải vì retrieval hỏng hoàn toàn |
| `judge_accuracy` | 0.2000 | 0.0000 | 0.2000 | Chỉ câu hỏi ngày là đúng; đây là giới hạn của bộ test chứ không phải hậu quả corruption |
| `mean_judge_score` | 2.0000 | 1.2000 | 2.0000 | Giảm 0.8 rồi hồi đúng baseline |
| Quality checks | PASS | FAIL | PASS | Fail ở `expect_column_values_to_be_unique` và `expect_column_value_lengths_to_be_between` |
| Freshness status | PASS | PASS | PASS | Stale rows 1 → 2 → 1, tỷ lệ 4.17% → 8.33% → 4.17%, vẫn dưới ngưỡng 25% |

### Kết luận từ số liệu

1. **Drop 4 record mới nhất** (quality gate không bắt được, freshness cũng không báo) → retrieval hit rate `1.0 → 0.2`, token F1 `0.34 → 0.0`, judge score `2.0 → 1.2`. Bằng chứng trực tiếp: `paper_ids` của scenario `drop_latest_records` trong `corruption_log.json` trùng với `ground_truth_doc_ids` của 4/5 câu hỏi trong `test_set.json`; câu `multi_hop` là câu duy nhất còn hit vì một trong hai ID của nó không nằm trong nhóm bị drop.
2. **Repair từ Raw snapshot** → quality gate `FAIL → PASS`, stale rows `2/24 → 1/24`, `latest_published` trở lại `2026-07-22` → cả 4 metric trở lại đúng baseline. Bằng chứng: `repaired_quality_report.json` có `success: true` và `stale_rows: 1`; `repaired_metrics.json` trùng baseline ở mọi con số.

**Corruption nào ảnh hưởng rõ nhất và vì sao:** `drop_latest_records`, không phải `inject_text_noise` hay `truncate_title` như dự đoán ban đầu của nhóm. Lý do: nó xóa mất đúng 4 tài liệu làm ground truth của 4 câu hỏi, nên retrieval không còn tài liệu nào chứa ID cần tìm — đây là loại hỏng không thể bù bằng reranking. Đáng chú ý thứ hai, `duplicate_rows` gây thiệt hại âm thầm: trong `corrupted_answers.json`, `retrieved_doc_ids` của `q-summary-001` chứa `10.1145/3637528.3671824` hai lần và của `q-category-001` chứa `10.1145/3637528.3671822` hai lần, tức mỗi câu mất 1 trong 4 khe của `top_k=4` cho một bản sao, trong khi 3 câu còn lại không có khe nào bị chiếm. Đây là hậu quả trực tiếp của expectation uniqueness bị fail mà chỉ nhìn `retrieval_hit_rate` thì không thấy.

**Kết quả khác với kỳ vọng ban đầu:**

- Tôi dự đoán freshness sẽ FAIL ở trạng thái corrupted. Thực tế vẫn PASS vì `duplicate_rows` bù lại số dòng đã mất, giữ mẫu số ở 24, nên tỷ lệ chỉ là 2/24 = 8.33%. Với corpus 24 dòng, một record bằng 4.17% nên phải có hơn 6 record quá hạn mới vượt ngưỡng 25% — nghĩa là SLA hiện tại gần như không phát hiện được sự cố freshness thật. Tôi đã kiểm tra lại bằng cách đếm trực tiếp `age_days > 180` trên `papers_clean_corrupted.csv` (2 dòng) thay vì chỉ tin `freshness_report.json`.
- Tôi dự đoán 6 kịch bản lỗi sẽ làm quality gate fail. Thực tế gate chỉ fail 2 expectation, tức bắt được `blank_summary` và `duplicate_rows`; `drop_latest_records`, `inject_text_noise`, `truncate_title`, `stale_date` đều lọt qua. Đáng lưu ý, `corruption_log.json` ghi `blank_summary` ảnh hưởng 2 dòng nhưng `ExpectColumnValueLengthsToBeBetween` thất bại trên **4** dòng, vì 2 dòng bị blank rồi lại bị nhân bản thêm một lần nữa. Đây là bằng chứng cụ thể rằng một lỗi có thể khuếch đại lỗi khác, và quality check ở mức row không nhìn thấy hiệu ứng nhân bản.
- Baseline có hit rate 1.0 nhưng `mean_token_f1` chỉ 0.34 và `judge_accuracy` 0.2. Tôi đã truy nguyên từng câu trong `baseline_answers.json`: trong `qa.py`, `_extract_answer` chỉ nhận diện các cụm `who authored`/`list the authors` và `what categories`, còn câu hỏi đã curated lại dùng "Who are the authors of the study", "Which specialist fields does ... belong to" và "Compare the research focus of ... including the specialist fields". Ba câu đó không khớp pattern nào nên rơi xuống nhánh mặc định lấy câu đầu tiên của `summary`, dẫn tới `token_f1` lần lượt là 0.0, 0.0 và 0.1212. Câu hỏi ngày khớp "When was" nên lấy đúng `published` và đạt F1 = 1.0, là câu duy nhất được judge chấm `correct: true`. Nghĩa là phần bị giới hạn là evaluation harness, không phải chất lượng retrieval — và nếu không sửa thì không thể dùng `mean_token_f1` để kết luận về chất lượng dữ liệu.
- **Khác biệt cần sửa trong `group_report.md`:** báo cáo nhóm mục 2 và mục 7 viết rằng LLM judge rơi về heuristic fallback. Tôi đã kiểm tra cả ba file `*_answers.json`: không có chuỗi `"Fallback heuristic judge used because the LLM evaluator was unavailable."`, lý do của judge là văn bản tiếng Anh phân tích cụ thể (ví dụ "off by 31 days"), và điểm 2 trong `q-summary-001` không thể do heuristic sinh ra vì heuristic chỉ trả 5/3/1. Suy ra judge chạy LLM thật. Tôi ghi lại ở đây vì đây là module của tôi; đề xuất cập nhật mục 2 và mục 7 của báo cáo nhóm và giữ nguyên giới hạn "Ragas skipped" vì `RUN_RAGAS` không được bật (đúng trong cả ba file metrics).

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Quality gate chỉ làm được đúng phần mà nó được viết để soi. 4 trong 6 kịch bản lỗi lọt qua suite hiện tại, nên "PASS" không đồng nghĩa "dữ liệu tốt" — phải đọc từng expectation, không chỉ đọc `success`.
2. Ngưỡng tỷ lệ rất nhạy với cỡ corpus. Với 24 dòng, một record chiếm 4.17% nên SLA 25% gần như không bao giờ kích hoạt; cần theo dõi thêm số lượng tuyệt đối và độ mới của `latest_published`, không chỉ tỷ lệ.
3. Metric suy giảm có thể do chính harness đo, không chỉ do dữ liệu. Phải đọc `*_answers.json` từng câu thay vì chỉ đọc 4 con số tổng hợp, nếu không sẽ kết luận sai nguyên nhân.

### Nếu có thêm thời gian

Tôi sẽ làm "observability có chiều thời gian": thêm `evaluated_at`, `run_date` và `dataset_fingerprint` (hash danh sách `paper_id` + số dòng) vào quality report và freshness report, đồng thời ghi kèm `column`/`kwargs` của từng expectation để report tự chỉ ra cột nào fail. Lý do: hiện tại không có mốc thời gian nào trong artifact nên không thể phát hiện drift giữa hai lần chạy, và báo cáo không đọc được cột lỗi. Cách đo cải thiện: chạy lại gate hai lần cách nhau vài ngày, `diff` hai report và phải nhìn ra được `latest_published` đã trôi; sau đó dựng một case giả lập 7/24 record quá hạn để chứng minh cảnh báo freshness bắt đầu kích hoạt.

## 10. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Hải Đăng
**Ngày xác nhận:** 2026-09-25
