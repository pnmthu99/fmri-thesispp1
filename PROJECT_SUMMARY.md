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
| Atlas | XCP-D `4S256Parcels`, chỉ lấy **index 1–200** = Schaefer2018 v0.14.3, 200 parcels, 7 networks (100 LH + 100 RH, tên `LH_Vis_1`…`RH_Default_pCunPCC_3`), **đã xác nhận 2026-11-25** từ file nhãn trong image (bản copy: `$WORK/atlases/4S256Parcels/`). Index 201–256 là dưới vỏ/tiểu não (CIT168, HCP thalamus/subcortical, MDTB cerebellum), không dùng. MIND dùng `Schaefer2018_200Parcels_7Networks_order` (cùng thứ tự), map về từng subject |
| Denoise | Chính: `36P` (có GSR). Độ nhạy: `acompcor` (không GSR) |
| Motion | `--fd-thresh 0.5`; độ nhạy ở 0.3. FC phải lấy từ dữ liệu đã censor, không dùng dữ liệu interpolated |
| Lọc tần số | 0.01–0.08 Hz (cần cho ALFF), `--smoothing 0`, `--despike y` |
| SDC | `--use-syn-sdc warn`; ghi lại phương pháp SDC thực tế cho từng subject |
| Slice timing | **BẬT STC** (chốt 2026-11-28, giống pipeline ADNI rs-fMRI 2025–26). SliceTiming thiếu bổ sung từ bảng NFQ của ADNI (`03c_slicetiming.py`) → 499/509 subject có STC; 10 Philips ADNI4 multiband (2 AD, 8 MCI) không có STC (bảng ghi như đơn lát, sai với MB3), ghi `stc_applied` làm covariate/sensitivity |
| Chạy tăng dần | Được, vì mỗi subject chạy riêng. Ngưỡng QC dùng toàn bộ dữ liệu (MRIQC outlier, Euler theo site) và QC cuối tính lại khi có đủ 3 nhóm. Chốt denoise khi đã có CN |
| Chạy dài | Server **không có Slurm/Apptainer**, chỉ có Docker (chạy `-u $(id -u):$(id -g)`). Mọi việc dài chạy trong tmux phiên `adni`, mỗi việc một cửa sổ. Script phải chạy lại được sau sự cố: bỏ qua subject xong, dọn `IsRunning` của FreeSurfer |
| Tài nguyên | Máy 32 core, 125 GB RAM, dùng chung với người khác → giới hạn `MAX_CPUS=26`, `MAX_MEM_GB=100` (2 user khác dùng < 1 core, 10–17 GB; chừa 6 core / 25 GB) |

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

- Chốt 2026-11-25: BOLD ≥ 4.5 phút, giữ multiband, QC cuối ≥ 4 phút sau censor. Số trong `sub-XXXX` là RID (đã xác nhận).
- MRIQC AD đang chạy (`01_preprocess/03_mriqc.sh`, 2 core / 8 GB mỗi subject, khoảng 11 phút/subject). Giới hạn chung tăng lên 26 core / 100 GB (2 user khác dùng < 1 core).
- `01_preprocess/04_fmriprep.sh`: chạy fMRIPrep theo từng subject, chạy lại được, dọn `IsRunning`, nhận `$WORK/filters/<sub>.json` nếu có, TemplateFlow chung ở `$WORK/templateflow`. Mặc định 8 core / 32 GB.
- **Chạy thử fMRIPrep sub-6179** (Siemens Skyra, TR 3 s, 197 vol) bắt đầu 2026-11-25 14:45 trong tmux cửa sổ `fmriprep-test`: workflow dựng OK, SyN-SDC (EstimatorType.ANAT) và slice timing bật, FreeSurfer đang chạy. Mục đích: bắt lỗi kỹ thuật, đo thời gian và RAM, chưa phải pilot.
- MCI: khoinguyen đã xác nhận bản hiện tại là final → đang giải nén, gộp, audit.
- CN: khoinguyen đang chuẩn bị bản final. **Xử lý trên chính máy này, cùng hàng đợi, cùng script** (không chia máy, vì CN là nhóm tham chiếu của normative model).

- MCI đã gộp (395 subject, không trùng RID). Tổng 517 subject: 347 đúng 1 cặp, 163 cần chọn ảnh, 7 thiếu ảnh. AD và MCI rất cân bằng về hãng máy (Siemens 66/64%, Philips 20/22%, GE 14/14%), multiband (39/39%) và TR. MRIQC MCI tự chạy sau AD (tmux `mriqc-mci`, `MRIQC_JOBS=9`).
- Review pipeline 2026-11-25, **cần chốt trước pilot** (đề xuất trong ngoặc):
  1. Slice timing: Philips (22% BOLD) không có SliceTiming → (`--ignore slicetiming` cho tất cả, để đồng nhất).
  2. SDC: Philips không có PhaseEncodingDirection → SyN-SDC bị bỏ qua ở Philips → (pilot so sánh trên vài subject: SyN cho tất cả sau khi bổ sung PED cho Philips, hoặc không SDC cho tất cả).
  3. Motion: multiband TR 0.6–0.8 s có nhiễu hô hấp trong tham số motion làm FD tăng giả → (XCP-D `--motion-filter-type notch` cho run TR < 1 s; kiểm tra phân bố FD theo protocol trong pilot).
  4. Độ dài scan khác nhau (4.9–10 phút) → (lưu parcel timeseries đã censor, tự tính FC trong `02_features`; làm thêm phân tích độ nhạy cắt về cùng thời lượng).
  5. XCP-D `--mode none`: khai báo đủ `--file-format cifti --input-type fmriprep --atlases 4S256Parcels --nuisance-regressors 36P --despike y --lower-bpf 0.01 --upper-bpf 0.08 --bpf-order 2 --fd-thresh 0.5 --min-time 240 --output-type censored --dummy-scans auto --smoothing 0 --min-coverage 0.5 --linc-qc y --abcc-qc n`. Kiểm tra ALFF được tính trên dữ liệu nào.
  6. MRIQC outlier theo lớp protocol (hãng máy × multiband), không chỉ theo hãng; xem trực quan báo cáo của ảnh bị đánh dấu và một mẫu ngẫu nhiên. FreeSurfer: Euler + xem trực quan, chú ý AD (teo não).
  7. Harmonization: nhiều site nhỏ → ComBat theo scanner/protocol thay vì từng site. Vẫn cần tuổi, giới (ADNIMERGE theo RID).

- Cập nhật 2026-11-25 21:50:
  - **fMRIPrep chạy thử sub-6179 xong trong 2 giờ 42 phút** (8 core, gồm cả FreeSurfer). Output 1.1 GB + FreeSurfer 296 MB. Còn phải xem RAM đỉnh và báo cáo HTML để chọn tài nguyên cho pilot.
  - **MRIQC lỗi hết RAM ở 8 GB**: 24 subject AD bị OOM ở synthstrip; sub-5018 bị OOM rồi **treo 6 tiếng** làm hàng đợi AD không kết thúc; sub-6820 bị `BrokenProcessPool` (có lẽ cũng OOM). Đã sửa: 16 GB/subject (`MRIQC_MEM_GB`) và timeout 3 giờ/job (`MRIQC_TIMEOUT`), quá giờ thì dừng container và đánh dấu lỗi. Hàng đợi MCI + chạy lại AD lỗi đang chạy 12 job.
  - **sub-6264 (AD): file BOLD hỏng ngay trong tarball gốc** (gzip bị cắt cụt, 32112640 byte). Cần khoinguyen chuyển đổi lại. Đang kiểm tra gzip mọi file → `$WORK/audit/gzip_check.tsv`.
  - Số trong `sub-XXXX` là RID: 395/405 thư mục PTID trong `mci_bids/sourcedata` khớp `sub-<phần số cuối PTID>`.

- **2026-11-26: MRIQC xong** (516/517; chỉ sub-6264 lỗi do BOLD hỏng). Kiểm tra gzip 1214 ảnh: chỉ file đó hỏng. Group report ở `derivatives/mriqc/group_{T1w,bold}.{tsv,html}`.
- **Chọn ảnh xong** (`01_preprocess/03b_select.py` → `$WORK/selection/`, `$WORK/filters/<sub>.json` cho mọi subject được chọn):
  - Chọn được **509/517** (AD 114, MCI 395). Loại 8 AD: 6 không có BOLD, 1 không có T1, sub-6264 (file hỏng).
  - Outlier Tukey theo lớp protocol (BOLD: hãng × MB; T1: hãng × MPRAGE/IR-FSPGR), chỉ phía xấu; nhẹ 1.5·IQR, nặng 3·IQR. T1: cjv, cnr, efc, qi_1, snr_total (bỏ fber vì = -1 ở 312/686 T1). BOLD: fd_mean, tsnr, dvars_std, aor, aqi, efc.
  - T1 ưu tiên: chuẩn (Accelerated MPRAGE / Philips MPRAGE / IR-FSPGR) > Philips SENSE2 > HS/CS (ADNI4) > _ND/ORIG; outlier nặng xuống cuối; rồi CNR. BOLD: outlier nặng xuống cuối, rồi dài nhất, rồi fd_mean.
  - **88 subject được chọn có ảnh outlier (27 nặng)** → `selection/qc_review.tsv`, cần xem báo cáo MRIQC bằng mắt trước khi quyết định loại. Outlier chủ yếu: BOLD aor/aqi/fd_mean, T1 cjv.
  - fd_mean trung vị AD > MCI ở mọi lớp (vd Siemens MB 0.214 vs 0.161) → motion là biến gây nhiễu cần kiểm soát.

- **Chính sách QC ĐÃ CHỐT 2026-11-26 (giữ mẫu tối đa, chỉ loại dữ liệu thật sự không dùng được)**. Tham khảo chính: Rutherford et al. 2026, "A Pipeline for ADNI Resting-State Functional MRI Processing and Quality Control" (arXiv 2602.03278; ADNI GO/2/3, fMRIPrep + MRIQC): giữ 2026/2611 session (78%). Họ loại: outlier MRIQC ở ±4 SD sau biến đổi SHASH (9% session), FreeSurfer/fMRIPrep lỗi, Euler outlier theo site, > 30% frame bị censor (FD > 0.5 mm) hoặc < 5 phút sạch. Philips thiếu PED → chạy lại không SDC, giữ lại và gắn cờ.
  - Loại cứng: file hỏng, thiếu cặp, FreeSurfer/fMRIPrep lỗi không sửa được, đăng ký ảnh hỏng khi xem bằng mắt.
  - MRIQC: KHÔNG tự loại theo ngưỡng. **Chốt 2026-11-26: bỏ bước xem bằng mắt báo cáo MRIQC** (như Rutherford: MRIQC chỉ dùng tự động); outlier chỉ dùng để ưu tiên khi chọn ảnh và được ghi lại (`selection/qc_review.tsv`). Xem bằng mắt chuyển sang báo cáo fMRIPrep của subject có vấn đề (lỗi, Euler xấu, nhiều frame bị censor).
  - Motion: chính = còn ≥ 4 phút sau censor FD > 0.5 mm (lỏng hơn Rutherford 5 phút, để giữ run multiband 4.9 phút); fd_mean làm covariate. Độ nhạy: tiêu chí Rutherford (≤ 30% censor, ≥ 5 phút) và tiêu chí chặt (mean FD ≤ 0.25 mm).
  - Euler: chỉ loại outlier cực đoan theo protocol, sau khi xem bằng mắt.
  - Vì AD chuyển động nhiều hơn: kiểm tra model không học motion (tương quan output với fd_mean, đánh giá trên tập motion-matched).

- **Pilot fMRIPrep bắt đầu 2026-11-26 09:52** (tmux `fmriprep-pilot`, 6 song song × 4 core × 16 GB, `--ignore slicetiming`). 16 subject (8 AD, 8 MCI) trong `selection/pilot.txt`, chọn ngẫu nhiên seed 42 theo cấu hình: Siemens MB TR 0.607 ×2, 0.788 ×1, Siemens SB ×1, GE SB ×2, GE MB (TR 1.5) ×2, Philips 48 lát TR 3 ×2, 36 lát TR 2.25, 51 lát TR 1.5, TR 6.02; ca khó sub-7021 (FD 1.08) và sub-5231 (Philips FD 3.7); sub-4679 (Philips phải chọn T1).
  - Lỗi đã sửa: filter fMRIPrep 25.2 chỉ nhận chuỗi; entity vắng mặt ghi `"<Query.NONE: 1>"`, run ghi `"01"`. Đã kiểm tra bằng `--boilerplate-only` (sub-6669 chọn đúng run-01). sub-6669 được xếp chạy lại sau hàng đợi.
  - 6 BOLD Siemens cũng thiếu PhaseEncodingDirection (như Philips) → chạy không SDC (vd sub-6665).
  - sub-6179 (test cũ) đã chạy CÓ slice timing → lượt chính thức phải chạy lại phần BOLD (FreeSurfer dùng lại).
  - Báo cáo MRIQC: `derivatives/mriqc/sub-*_{T1w,bold}.html` (thư mục gốc, không nằm trong `sub-*/`). Mục lục cần xem: `derivatives/mriqc/_qc_review.html`; ghi quyết định vào `selection/qc_visual.tsv`.
  - Cần xem sau pilot: thời gian/RAM, SDC Philips, % frame bị censor theo protocol (quyết định notch filter), lỗi FreeSurfer.
  - sub-10871, sub-10859, sub-6669 lỗi filter lúc 09:53 (trước khi sửa) → chạy lại 10:50 ở tmux `fmriprep-retry`.
  - Marker `logs/fmriprep/sub-6179.done` đổi thành `.done_test_with_stc` → lượt chính thức chạy lại sub-6179.
- **`01_preprocess/05_xcpd.sh`** (2026-11-26): XCP-D theo từng subject, `--mode none` với đủ tham số (CIFTI, 4S256Parcels, 36P, despike, FD 0.5, `--censor-between 0`, `--min-time 240`, censored, 0.01–0.08 Hz, không smoothing, run-wise FC, linc-qc). Mỗi container chỉ mount `fmriprep/sub-X` + `dataset_description.json`. `--follow`: tự chạy XCP-D cho subject vừa xong fMRIPrep, dừng khi fMRIPrep hết việc. `XCPD_MOTION_FILTER=notch` (12–18 bpm) chờ quyết định từ pilot. Chạy thử trên sub-6179 vào `$WORK_TMP/xcpd_test` (không lẫn output thật): **OK, 7 phút**. Timeseries 191 frame (6 bị censor) × 256 parcel (cột 1–200 = Schaefer, không parcel nào NaN), FC 256×256, ALFF 1×256. Tương quan FD–DVARS 0.63 → 0.07 sau denoise. **ALFF = Lomb-Scargle trên dữ liệu đã censor (không nội suy), 0.01–0.08 Hz** → review mục 5 xong.
  - Từ 2026-11-26 11:15: tmux `xcpd` chạy `05_xcpd.sh --follow` (3 job × 4 core) cho pilot.
- **Quy tắc motion chốt (2026-11-26):** loại run còn < 240 s sạch (mặc định XCP-D `--min-time`) HOẶC > 30% frame bị cắt FD > 0.5 (Rutherford et al. 2026). Không dùng ngưỡng 5 phút của Rutherford vì 129/509 scan (toàn bộ là ADNI4, RID ≥ 10000; AD 33/114, MCI 96/395) chỉ dài 4.7–4.9 phút do protocol. Pilot: sub-4219 bị loại thêm (30.2%) → còn 12/16.
- **Pilot fMRIPrep xong 16/16, không lỗi** (2026-11-26, ~4.4–5.2 giờ/subject khi 9 song song × 4 core). XCP-D: 13 xong, 3 **bị loại vì < 240 s sạch sau censor FD > 0.5**: sub-5231 (Philips SB, FD TB 3.7 mm, còn 114 s), sub-10871 (GE MB, 166.5 s), sub-10776 (Philips SB 4.9 phút, 225 s — sát ngưỡng). Ghi là `logs/xcp_d/<sub>.excluded`, không phải `.failed`.
- **Phân tích pilot (2026-11-26)**, 16 subject:
  - fMRIPrep: 2.8–5.4 giờ/subject (trung vị 4.4) khi 9 song song × 4 core; không subject nào lỗi. Đĩa: fMRIPrep ~0.9–1.2 GB (Siemens MB ~3.9 GB), FreeSurfer ~0.3 GB, XCP-D 0.1–0.4 GB → ~2 GB/subject, ~1 TB cho 509 (còn trống 2.7 TB).
  - SDC: SyN fieldmap-less cho Siemens/GE có PED; "None" cho Philips (cả 8) và sub-6665 (Siemens không có PED), đúng như dự kiến. Đăng ký BOLD→T1: bbregister cả 16, không fallback. Slice timing: không áp dụng (đã chốt). Non-steady-state: 0–3 volume.
  - Euler (lh/rh orig.nofix): hầu hết −2 đến −40; cao nhất sub-6869 (−90/−60), sub-6854 (−60/−40), sub-5231 (−38/−58, đã bị loại vì motion) → người dùng xem bề mặt FreeSurfer trong báo cáo fMRIPrep của 6869, 6854.
  - Denoise: tương quan FD–DVARS 0.27–0.89 → −0.30–0.34. sub-7021 FD TB 0.91 do vài spike, sau censor 0.12 → dùng `mean_fd_post_censoring` (linc_qc) làm covariate thay vì FD thô.
  - Nhịp thở trong tham số motion: run TR ≤ 1.5 s có 21–68% công suất trans_y ở 0.2–0.3 Hz. Notch (lọc thử 0.2–0.3 Hz) giảm mean FD 10–60% nhưng % frame bị cắt chỉ đổi 0–1% (trừ sub-10871: 44 → 33%, vẫn > 30%). Đề xuất: **không bật notch** (định nghĩa FD giữ như nhau cho mọi protocol, vì TR 3 s không lọc được); hiệu ứng FD giả của MB hấp thụ bằng protocol trong ComBat/covariate.
- **ALFF tách khỏi XCP-D** (2026-11-26): hàm `compute_alff` của XCP-D tính Lomb-Scargle ở 486 tần số × từng grayordinate → ~11 giờ CPU cho run 973 volume (sub-6854 mất 6 giờ; 65 subject Siemens MB). XCP-D nay chạy `--skip alff`; `01_preprocess/05b_alff.py` tính ngay sau (trong container XCP-D) từ `desc-denoised_bold.dtseries.nii` + `outliers.tsv`: cùng công thức (khớp hàm XCP-D tới 1e-15 trên dữ liệu giả), chỉ tính tần số trong dải, vector hóa → **2–4 giây/subject**. Khác XCP-D 1 điểm: SD nhân cuối tính trên frame thật (XCP-D dùng chuỗi đã nội suy). So với ALFF XCP-D trên pilot: sub-6854 (không censor) trùng hoàn toàn; 4024/6665/10021 r ≥ 0.99 (parcel), ALFF mình thấp hơn 0.5–5%. Output: `*_stat-alff_desc-lomb_bold.tsv` (parcel) và `*_stat-alff_desc-lomb_boldmap.dscalar.nii`. ALFF dùng làm **node feature** (Aim 2).
- `05_xcpd.sh --follow` không còn chờ cả đợt (trước đó 9 subject bị kẹt sau sub-6854): có chỗ trống là nhận subject mới. `--alff sub-X` để chỉ tính lại ALFF.

- **Slice timing bổ sung (2026-11-28)**: bảng `MAYOADIRL_MRI_FMRI_NFQ_27Nov2026.csv` (ADNIGO/2/3) và `MRINFQ_27Nov2026.csv` (ADNI4) trong `$WORK/tables/`. `01_preprocess/03c_slicetiming.py --write` ghi 120 JSON BOLD (thay file, bỏ hard link, raw/ giữ nguyên; bản cũ ở `audit/slicetiming_backup/`, tổng hợp `audit/slicetiming_fill.tsv`, mỗi JSON có `SliceTimingSource`):
  - 92 run Philips lấy thẳng từ bảng (RID + SeriesNumber + giờ chụp ±120 s + số lát; giá trị = giờ trong ngày → trừ min).
  - 12 run Philips suy ra theo quy luật protocol (lát chẵn trước rồi lẻ, bước TR/n; đúng 98% của 1007 dòng Philips 48 lát TR 3 s); 6 run Siemens 49 lát suy ra theo interleaved Siemens (giống 135 subject Siemens 48 lát).
  - 10 run Philips ADNI4 MB (TR 1.5 s): bảng ghi 51 thời điểm khác nhau (đơn lát) → không dùng, fMRIPrep tự bỏ STC.
  - **Sửa TR**: 4 run ADNI2 Philips (sub-4171, 4219, 4229, 4237; 140 vol) JSON/NIfTI ghi TR 6.02158 s, bảng NFQ và protocol ADNI2 là 3 s → sửa cả JSON và pixdim[4]. Kết quả pilot cũ của sub-4219 không dùng được.
  - Bảng NFQ có cột `OVERALLQC` (QC của Mayo) để đối chiếu với MRIQC sau.
- **Chạy toàn bộ (2026-11-28 11:59)**: tmux `adni:fmriprep` (508 subject, 9 × 4 core, STC bật) và `adni:xcpd` (`--follow`, 2 job). Pilot (chạy không STC) chuyển sang `derivatives/_pilot_nostc/` và chạy lại (FreeSurfer dùng lại); riêng sub-10776 giữ nguyên (không có SliceTiming, đã bị loại vì motion).

Việc tiếp theo:
1. Chốt 7 điểm review ở trên (chờ người dùng).
2. (Đã bỏ) Xem bằng mắt MRIQC. Thay bằng xem báo cáo fMRIPrep của subject có vấn đề sau khi chạy.
3. Chọn tài nguyên fMRIPrep từ lần chạy thử, pilot 10–20 subject phủ Siemens/GE/Philips/multiband.
4. Viết runner nối fMRIPrep → XCP-D tự động theo từng subject.
5. CN: khi có bản final → `00_extract cn` → `01_merge cn` → audit → MRIQC → chạy lại `03b_select.py` (tính lại ngưỡng outlier trên toàn bộ).
6. Lấy tuổi, giới (ADNIMERGE theo RID). Báo khoinguyen chuyển đổi lại sub-6264.
7. (Hoãn đến khi có đợt bổ sung AD/MCI) Sửa `00_extract.sh` nhận tên tarball tùy ý (vd `ad_bids_batch2.tar.gz`) và `01_merge_bids.sh` tách nhãn nhóm khỏi tên thư mục; báo ra subject đã có mà đợt mới thêm ảnh (hiện bị bỏ qua lặng lẽ) để chọn ảnh/chạy lại. Đợt mới nên là tarball riêng chỉ chứa subject mới.

Lưu ý dữ liệu ADNI: Claude chỉ đọc metadata (tên file, JSON, bảng), không đọc nội dung ảnh.

## 7. Nguồn tham khảo chính

- Pipeline ADNI rs-fMRI: https://arxiv.org/abs/2602.03278 (code: github.com/mandymejia/ADNI_fMRI_protocol)
- MIND: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10400419/ và https://github.com/isebenius/MIND
- fMRIPrep: https://fmriprep.org/en/stable/usage.html
- XCP-D: https://xcp-d.readthedocs.io/en/latest/
