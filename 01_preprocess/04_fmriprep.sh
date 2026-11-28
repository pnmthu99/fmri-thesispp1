#!/usr/bin/env bash
# Bước 4–5: fMRIPrep (FreeSurfer chạy lại từ đầu) cho từng subject. CHẠY TRONG TMUX.
#
# Cách dùng:
#   bash 01_preprocess/04_fmriprep.sh sub-6179 ...     # các subject liệt kê
#   bash 01_preprocess/04_fmriprep.sh --list file.txt  # danh sách subject (mỗi dòng 1 sub)
#   bash 01_preprocess/04_fmriprep.sh --retry-failed
#   Tùy chỉnh tài nguyên:  FMRIPREP_THREADS=4 FMRIPREP_MEM_GB=16 FMRIPREP_JOBS=6 bash ...
#   Slice timing:  BẬT (mặc định FMRIPREP_IGNORE=""). SliceTiming còn thiếu đã được bổ sung từ bảng NFQ
#   của ADNI bằng 03c_slicetiming.py (499/509 subject); 10 Philips ADNI4 multiband vẫn thiếu → fMRIPrep
#   tự bỏ STC cho các run đó. FMRIPREP_IGNORE=slicetiming để tắt cho tất cả.
#
# Chạy lại được: có $LOG_DIR/fmriprep/<sub>.done thì bỏ qua. Trước khi chạy, xóa file IsRunning
# của FreeSurfer (còn sót nếu lần trước bị dừng giữa chừng) để recon-all chạy tiếp được.
# Nếu có $WORK/filters/<sub>.json (từ bước chọn ảnh) thì truyền --bids-filter-file.
# Đổi số job khi đang chạy:  pkill -USR1 -u $(id -u) -x xargs  (+1)  |  -USR2 (−1)
set -euo pipefail
SELF=$(readlink -f "$0")
source "$(dirname "$SELF")/../config/paths.sh"

THREADS=${FMRIPREP_THREADS:-4}     # FreeSurfer phần lớn đơn luồng; 8 core: sub-6179 mất 2 giờ 42 phút
MEM_GB=${FMRIPREP_MEM_GB:-16}
IGNORE=${FMRIPREP_IGNORE-}
JOBS=${FMRIPREP_JOBS:-$(( MAX_CPUS / THREADS ))}
OUT=$DERIV_DIR/fmriprep
WRK=$WORK_TMP/fmriprep
LOGD=$LOG_DIR/fmriprep
FILTERS=$WORK/filters
TPLFLOW=$WORK/templateflow
mkdir -p "$OUT" "$WRK" "$LOGD" "$FS_DIR" "$TPLFLOW"

one() {
    local sub=$1 log=$LOGD/$1.log
    [[ -f $LOGD/$sub.done ]] && return 0
    rm -f "$LOGD/$sub.failed"
    rm -f "$FS_DIR/$sub"/scripts/IsRunning.* 2>/dev/null || true
    mkdir -p "$WRK/$sub"

    local filt=() fmount=() ign=()
    [[ -n $IGNORE ]] && ign=(--ignore $IGNORE)
    if [[ -f $FILTERS/$sub.json ]]; then
        fmount=(-v "$FILTERS/$sub.json":/filter.json:ro); filt=(--bids-filter-file /filter.json)
    fi

    echo "$(date '+%F %T') BẮT ĐẦU $sub" | tee -a "$LOGD/_progress.log"
    if docker run --rm --name "fmriprep_$sub" \
        -u "$(id -u):$(id -g)" -e HOME=/tmp -e TEMPLATEFLOW_HOME=/templateflow \
        --cpus "$THREADS" --memory "${MEM_GB}g" \
        -v "$BIDS_DIR":/data:ro -v "$OUT":/out -v "$WRK/$sub":/work \
        -v "$FS_DIR":/fs -v "$FS_LICENSE":/license.txt:ro -v "$TPLFLOW":/templateflow \
        "${fmount[@]}" \
        "$IMG_FMRIPREP" /data /out participant \
        --participant-label "${sub#sub-}" "${filt[@]}" \
        --fs-license-file /license.txt --fs-subjects-dir /fs \
        --output-spaces MNI152NLin6Asym:res-2 --cifti-output 91k \
        --use-syn-sdc warn "${ign[@]}" \
        --skip-bids-validation \
        --nthreads "$THREADS" --omp-nthreads "$(( THREADS < 8 ? THREADS : 8 ))" \
        --mem-mb "$(( MEM_GB * 1000 - 2000 ))" \
        --resource-monitor --notrack -w /work \
        >"$log" 2>&1; then
        date '+%F %T' > "$LOGD/$sub.done"
        rm -rf "${WRK:?}/$sub"
        echo "$(date '+%F %T') XONG    $sub" | tee -a "$LOGD/_progress.log"
    else
        touch "$LOGD/$sub.failed"   # giữ work dir để chạy lại tiếp từ chỗ dừng
        echo "$(date '+%F %T') LỖI     $sub  (xem $log)" | tee -a "$LOGD/_progress.log"
    fi
}

case "${1:-}" in
    --one)          one "$2"; exit 0 ;;
    --list)         mapfile -t SUBS < <(grep -v '^\s*$' "$2") ;;
    --retry-failed) mapfile -t SUBS < <(ls "$LOGD"/*.failed 2>/dev/null | xargs -rn1 basename | sed 's/\.failed$//') ;;
    "")             echo "Cần chỉ rõ subject (chưa chạy toàn bộ khi chưa có manifest)."; exit 1 ;;
    *)              SUBS=("$@") ;;
esac

TODO=()
for s in "${SUBS[@]}"; do [[ -f $LOGD/$s.done ]] || TODO+=("$s"); done
echo "fMRIPrep: ${#TODO[@]} subject, $JOBS song song × $THREADS core, ${MEM_GB} GB/subject, ignore='${IGNORE}'. Log: $LOGD"
[[ ${#TODO[@]} -eq 0 ]] && exit 0
printf "%s\n" "${TODO[@]}" | xargs -P "$JOBS" -I{} bash "$SELF" --one {}
echo "Hết hàng đợi: done=$(ls "$LOGD"/*.done 2>/dev/null | wc -l), failed=$(ls "$LOGD"/*.failed 2>/dev/null | wc -l)"
