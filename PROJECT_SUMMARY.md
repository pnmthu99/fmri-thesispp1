# Tóm tắt dự án: ADNI – MIND dự đoán FC (giai đoạn preprocess)

Cập nhật: 2026-11-25. File này dùng để bắt đầu phiên Claude mới trên máy trạm mà không phải giải thích lại.
Khi mở phiên mới, nói: "Đọc PROJECT_SUMMARY.md rồi tiếp tục từ mục Việc tiếp theo."

Thư mục code: `/home/thupnm/thupnm-wp/fmri-thesispp1` (git). Mọi đường dẫn, image và giới hạn tài nguyên nằm ở `config/paths.sh`.
Dữ liệu: `$WORK=/home/thupnm/thupnm-wp/adni_work` gồm `raw/` (tarball giải nén theo nhóm), `bids/` (BIDS gộp các nhóm), `tables/` (bảng query/ADNI), `freesurfer/`, `derivatives/`, `work/`, `logs/`, `license.txt`.
Thư mục cũ `thupnm-wp/bids` và `thupnm-wp/fmriprep` (ds002748) thuộc project khác, không dùng.

## 1. Mục tiêu nghiên cứu

- Cohort ADNI, 3 nhóm CN / MCI / AD. Mỗi subject đúng **1 T1 + 1 rs-fMRI**, đạt QC.
- **Aim 1:** Normative model chỉ fit trên CN (Ridge/MLP, cross-fitting 5 fold) dự đoán FC từ MIND, khoảng cách giữa vùng, cặp mạng, FD, scanner/phase, tuổi, giới. Tính residual chuẩn hóa = (FC quan sát − FC kỳ vọng) / SD kỳ vọng.
- **Aim 2:** Graph Transformer (edge-biased attention) trên graph **200 node**, cạnh gồm FC, MIND, residual. Phân loại NC/MCI, MCI/AD, NC/AD và 3 lớp. So sánh với LR, SVM, XGBoost, GCN, GAT, BrainNetCNN. Ablation: FC; FC+MIND; FC+MIND+residual.
- **Aim 3:** Diễn giải vùng, mạng và đặc trưng quan trọng.
- Đánh giá: nested CV chia theo subject, phân tầng; ComBat chỉ fit trên training fold. Validation ngoài trên **OASIS**.
- Feature: MIND (từ FreeSurfer), FC, ALFF.

## 2. Dữ liệu

- Ảnh tải từ ADNI theo danh sách Image ID lấy từ query DB của người dùng. Chẩn đoán lấy ở mốc **baseline (bl)**.
- Đã chuyển sang BIDS, nén, để tại `/shared-data/adni_sfmri` (bản gốc, **chỉ đọc**, không ghi vào đây).
- Giải nén vào thư mục account riêng trên máy trạm: `$WORK/bids`. **Mọi nhóm gộp chung một thư mục BIDS**; nhãn chẩn đoán để ở bảng riêng, pipeline không biết nhóm.
- Hiện có 3 tarball `ad_bids.tar.gz` (17 GB), `mci_bids.tar.gz` (61 GB), `cn_bids.tar.gz` (24 GB), **chưa phải bản final**. AD và MCI chắc chắn dùng được; CN chờ bản final. Làm **AD trước**, rồi MCI, CN thêm sau.
- Chuyển BIDS bằng **dcm2bids**. ID là `sub-<RID>`, **không có thư mục `ses-`**: nhiều ảnh phân biệt bằng `run-XX`, nên lần khám phải suy từ ngày chụp (JSON hoặc `sourcedata/`). Có `sourcedata/<PTID>`. Khi gộp nhóm phải kiểm tra trùng RID.
- Bảng query: khoinguyen lấy từ DB lab qua DBeaver. Người dùng sẽ gửi câu SQL và CSV kết quả vào `$WORK/tables/`. Nếu DB có `DXSUM`/`ADNIMERGE`/`MAYOADIRL_MRI_FMRI_NFQ` thì lấy từ DB, không thì tải trên IDA.
- Một subject có thể có **nhiều T1 hoặc nhiều BOLD**, nên cần script chọn ảnh.
- Kết quả kiểm tra AD (2026-11-25):
  - Query `tables/ad_fmri_image_ids.csv`: `visit JOIN mri JOIN fmri`, `visit_month=0`, raw_t1 + raw_fMRI. Có 179 dòng (tích chéo T1×fMRI trong cùng visit), 135 subject, 172 T1, 140 fMRI. `subject_id` là **hash**, không có RID/PTID/tuổi/giới. Ngày chụp ảnh (`record_date.1`) khác ngày visit (`record_date`).
  - BIDS `raw/ad_bids`: 122 subject (RID 4024–10879). 6 subject không có BOLD, 1 subject không có T1. JSON đã ẩn danh: **không có Image ID, ngày chụp hay RID**. `sourcedata/` rỗng, không có log dcm2bids, `participants.tsv` chỉ là file mẫu.
  - **Chưa nối được run trong BIDS với `image_id`.** Cần từ khoinguyen: bảng subject (hash → RID/PTID, tuổi, giới) và file mapping/log chuyển đổi (Image ID → `sub-X_run-Y`).
  - 48/125 BOLD là **multiband** (ADNI3/4, TR 0.607 s). Nếu loại hết multiband thì mất khoảng 40% dữ liệu → cần xem lại quy tắc "tách/loại multiband" ở mục 4.
- Người dùng có đủ dung lượng ổ đĩa.

## 3. Quyết định đã chốt

| Mục | Quyết định |
|---|---|
| Cấu trúc code | `01_preprocess/` (các bước riêng) và `02_features/` (MIND, FC, ALFF, distance). ComBat và model ở giai đoạn sau |
| Công cụ | MRIQC (chỉ QC) → fMRIPrep (preprocess) → XCP-D (denoise, FC, ALFF) |
| Version (giữ nguyên đến hết, kể cả OASIS) | `nipreps/mriqc:24.0.2`, `nipreps/fmriprep:25.2.7`, `pennlinc/xcp_d:26.3.0` |
| FreeSurfer | **Chạy lại từ đầu** bên trong fMRIPrep cho mọi subject, không dùng output cũ của lab (cohort khác) |
| Không gian output | CIFTI fsLR-91k: `--output-spaces MNI152NLin6Asym:res-2 --cifti-output 91k` |
| Atlas | XCP-D `4S256Parcels`, chỉ lấy 200 vùng vỏ não (Schaefer-200, suy từ tên atlas; cần xác nhận bằng file nhãn). MIND dùng đúng Schaefer-200 đó, map về từng subject |
| Denoise | Chính: `36P` (có GSR). Độ nhạy: `acompcor` (không GSR) |
| Motion | `--fd-thresh 0.5`; độ nhạy ở 0.3. FC phải lấy từ dữ liệu đã censor, không dùng dữ liệu interpolated |
| Lọc tần số | 0.01–0.08 Hz (cần cho ALFF), `--smoothing 0`, `--despike y` |
| SDC | `--use-syn-sdc warn`; ghi lại phương pháp SDC thực tế cho từng subject |
| Slice timing | Ảnh Philips thường thiếu `SliceTiming`; bổ sung từ bảng LONI `MAYOADIRL_MRI_FMRI_NFQ_*.csv` nếu được, nếu không thì cân nhắc `--ignore slicetiming` cho tất cả. Chốt sau audit |
| Chạy tăng dần | Được, vì mỗi subject chạy riêng. Ngưỡng QC dùng toàn bộ dữ liệu (MRIQC outlier, Euler theo site) và QC cuối tính lại khi có đủ 3 nhóm. Chốt denoise khi đã có CN |
| Chạy dài | Server **không có Slurm/Apptainer**, chỉ có Docker (chạy `-u $(id -u):$(id -g)`). Mọi việc dài chạy trong tmux phiên `adni`, mỗi việc một cửa sổ. Script phải chạy lại được sau sự cố: bỏ qua subject xong, dọn `IsRunning` của FreeSurfer |
| Tài nguyên | Máy 32 core, 125 GB RAM, dùng chung với người khác → giới hạn `MAX_CPUS=18`, `MAX_MEM_GB=72` |

## 4. Quy tắc chọn 1 T1 + 1 BOLD (cố định trước, không xét nhãn bệnh)

1. Lập bảng kê mọi T1/BOLD: subject, session, run, `SeriesDescription`, TR, số volume, Image ID, ngày chụp (nối với bảng query).
2. Lọc thô: bỏ BOLD dưới **4.5 phút** (chốt 2026-11-25), bỏ T1 đã qua xử lý. **Giữ multiband** (ADNI3/4: 482 vol × 0.607 s = 4.88 phút); khác biệt protocol xử lý bằng biến scanner/protocol trong model và ComBat.
3. Chạy MRIQC trên các ảnh ứng viên.
4. Chỉ giữ cặp T1 + BOLD cùng lần khám, đạt MRIQC; chọn lần khám gần mốc chẩn đoán baseline nhất.
5. BOLD: run dài nhất, rồi đến `fd_mean` thấp nhất. T1: theo **danh sách ưu tiên sequence chốt sẵn sau audit MCI**, rồi đến CNR cao nhất.
6. Không còn cặp hợp lệ thì loại subject và ghi lý do. Subject đã chọn thì không chọn lại khi thêm dữ liệu.
7. Xuất `manifest.tsv` và một file `--bids-filter-file` cho mỗi subject.

## 5. Pipeline preprocess

| Bước | Việc | Output |
|---|---|---|
| 0 | Giải nén sang `$WORK/bids` | BIDS làm việc |
| 1 | Audit: BIDS validator, CuBIDS, thống kê acquisition và metadata | Bảng kê, nhóm acquisition |
| 2 | MRIQC trên ảnh ứng viên, lọc outlier không dùng nhãn | Danh sách đạt QC |
| 3 | Chọn ảnh theo mục 4 | `manifest.tsv`, filter |
| 4 | Pilot 10–20 subject, phủ các hãng máy | Chốt flag, thời gian, dung lượng |
| 5 | fMRIPrep toàn bộ (`--fs-subjects-dir $WORK/freesurfer`) | BOLD fsLR-91k, confounds, FreeSurfer |
| 6 | XCP-D `--mode none` khai báo đủ tham số | FC, ALFF, QC |
| 7 | QC cuối | `qc_final.tsv` |

QC cuối dự kiến theo pipeline ADNI (arXiv 2602.03278): loại khi censor trên 30% số frame, còn dưới **4 phút** dữ liệu sau censor (chốt 2026-11-25, thay cho 5 phút vì multiband), hoặc Euler number là outlier trong từng site. Thêm: kiểm tra coverage của 200 node (vùng trán ổ mắt và thái dương dễ bị NaN).
`qc_final.tsv` cần các cột: mean FD, số frame còn lại, hãng máy, phase, tuổi, giới, nhóm, phương pháp SDC.

Lưu ý cho giai đoạn feature: code MIND (github.com/isebenius/MIND) mới được test với FreeSurfer 5.3; với Schaefer có thể phải sửa danh sách vùng bị loại (medial wall).

## 6. Trạng thái và việc tiếp theo

Đã làm (2026-11-25):
- Tạo `$WORK`, `config/paths.sh`, `.gitignore`, `git init`. Copy `license.txt`.
- `01_preprocess/00_extract.sh <ad|mci|cn>`: giải nén vào `$WORK/raw/<nhóm>_bids`, bỏ `tmp_dcm2bids/`, đánh dấu xong bằng `.extract_done`, log ở `$WORK/logs/extract_<nhóm>.log`.
- Đang chạy trong tmux `adni`: cửa sổ `extract-ad` (giải nén AD) và `pull` (pull 3 image đúng version; trên máy đang có bản cũ fmriprep 25.2.5 và xcp_d 26.2.0, không dùng).

- AD đã giải nén (122 subject), pull đủ 3 image, gộp vào `$WORK/bids` (`01_preprocess/01_merge_bids.sh`, hard link, bỏ 7 JSON mồ côi, nhãn ở `tables/group_labels.tsv`).
- Audit AD (`01_preprocess/02_audit.py` → `$WORK/audit/inventory.tsv`, `subject_summary.tsv`, `report.txt`):
  - 57 subject đúng 1 T1 + 1 BOLD; 25 cần chọn ảnh; 6 không có BOLD; 1 không có T1; **33 chỉ có BOLD dưới 5 phút**.
  - BOLD dưới 5 phút phần lớn là protocol multiband chuẩn ADNI3/4 (482 vol × 0.607 s = 4.88 phút). **Quy tắc "bỏ BOLD < 5 phút" và "loại multiband" phải xem lại**, nếu không sẽ mất khoảng 1/3 AD.
  - **Không có fieldmap** → SDC chỉ có fieldmap-less SyN.
  - **Philips (24 BOLD): thiếu SliceTiming, TotalReadoutTime và PhaseEncodingDirection** → không có slice timing, SyN-SDC sẽ bị bỏ qua nếu không bổ sung PED.
  - T1: 12 loại SeriesDescription (MPRAGE, Accelerated MPRAGE, IR-FSPGR...).
- `status.sh`: xem nhanh tiến độ mà không cần vào tmux.

Việc tiếp theo:
1. Chốt các quyết định: ngưỡng thời lượng BOLD, multiband, Philips (slice timing, PED), danh sách ưu tiên T1.
2. Viết và chạy MRIQC cho AD.
3. Chọn ảnh (25 subject), pilot fMRIPrep.
4. (Đã xác nhận) số trong `sub-XXXX` là RID: 395/405 thư mục PTID trong `mci_bids/sourcedata` khớp `sub-<phần số cuối PTID>`.

Lưu ý dữ liệu ADNI: Claude chỉ đọc metadata (tên file, JSON, bảng), không đọc nội dung ảnh.

## 7. Nguồn tham khảo chính

- Pipeline ADNI rs-fMRI: https://arxiv.org/abs/2602.03278 (code: github.com/mandymejia/ADNI_fMRI_protocol)
- MIND: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10400419/ và https://github.com/isebenius/MIND
- fMRIPrep: https://fmriprep.org/en/stable/usage.html
- XCP-D: https://xcp-d.readthedocs.io/en/latest/
