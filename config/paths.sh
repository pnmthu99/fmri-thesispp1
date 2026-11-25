# Đường dẫn và tài nguyên dùng chung. Mọi script: source "$(dirname "$0")/../config/paths.sh"
export WORK=/home/thupnm/thupnm-wp/adni_work
export SRC_DATA=/shared-data/adni_sfmri          # bản gốc, CHỈ ĐỌC
export RAW_DIR=$WORK/raw                          # giải nén theo nhóm: raw/ad_bids, raw/mci_bids...
export BIDS_DIR=$WORK/bids                        # BIDS gộp mọi nhóm (pipeline không biết nhóm)
export TABLES_DIR=$WORK/tables                    # bảng query ADNI, LONI...
export FS_DIR=$WORK/freesurfer
export DERIV_DIR=$WORK/derivatives
export WORK_TMP=$WORK/work
export LOG_DIR=$WORK/logs
export FS_LICENSE=$WORK/license.txt

# Version cố định đến hết dự án (kể cả OASIS)
export IMG_MRIQC=nipreps/mriqc:24.0.2
export IMG_FMRIPREP=nipreps/fmriprep:25.2.7
export IMG_XCPD=pennlinc/xcp_d:26.3.0

# Máy dùng chung (32 core, 125 GB), 2 người khác dùng ít → ưu tiên dự án này nhưng chừa phần cho họ.
# Còn ~6 core / 25 GB cho người khác. Thấy họ chạy nặng thì giảm job (xem từng script).
export MAX_CPUS=26
export MAX_MEM_GB=100
