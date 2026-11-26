#!/usr/bin/env bash
# Bước 6: XCP-D (denoise, censor, lọc, parcellate, FC, ALFF) trên output fMRIPrep. CHẠY TRONG TMUX.
#
# Cách dùng:
#   bash 01_preprocess/05_xcpd.sh sub-6854 ...      # các subject liệt kê
#   bash 01_preprocess/05_xcpd.sh --list file.txt   # danh sách subject
#   bash 01_preprocess/05_xcpd.sh --retry-failed
#   bash 01_preprocess/05_xcpd.sh --follow          # TỰ NỐI TIẾP: cứ subject nào xong fMRIPrep
#                                                   # (logs/fmriprep/<sub>.done) là chạy XCP-D;
#                                                   # dừng khi fMRIPrep hết việc và không còn gì chờ
#   Tùy chỉnh: XCPD_THREADS=4 XCPD_MEM_GB=16 XCPD_JOBS=3 XCPD_MOTION_FILTER=none|notch
#              XCPD_OUT=<thư mục output khác> (dùng khi chạy thử)
#
# Tham số đã chốt (PROJECT_SUMMARY mục 3 và review mục 5), --mode none nên phải khai báo đủ:
#   CIFTI fsLR-91k, atlas 4S256Parcels (dùng index 1–200 = Schaefer-200), 36P, despike,
#   censor FD > 0.5 mm, loại run còn < 240 s sau censor, band-pass 0.01–0.08 Hz (cần cho ALFF),
#   không smoothing, output censored (FC tính trên frame thật, không nội suy).
# Mỗi container chỉ thấy đúng thư mục fMRIPrep của subject đó (khỏi index cả 500 subject).
set -euo pipefail
SELF=$(readlink -f "$0")
source "$(dirname "$SELF")/../config/paths.sh"

THREADS=${XCPD_THREADS:-4}
MEM_GB=${XCPD_MEM_GB:-16}
JOBS=${XCPD_JOBS:-3}
MFILT=${XCPD_MOTION_FILTER:-none}
FMP=$DERIV_DIR/fmriprep
OUT=${XCPD_OUT:-$DERIV_DIR/xcp_d}
WRK=$WORK_TMP/xcp_d
LOGD=$LOG_DIR/xcp_d
[[ -n ${XCPD_OUT:-} ]] && LOGD=$OUT/_logs     # chạy thử: log riêng, không lẫn với log thật
mkdir -p "$OUT" "$WRK" "$LOGD"

one() {
    local sub=$1 log=$LOGD/$1.log
    [[ -f $LOGD/$sub.done ]] && return 0
    [[ -d $FMP/$sub ]] || { echo "Chưa có output fMRIPrep cho $sub"; return 1; }
    rm -f "$LOGD/$sub.failed"
    mkdir -p "$WRK/$sub"

    local mf=(--motion-filter-type "$MFILT")
    # notch cho nhịp thở người lớn (12–18 lần/phút), theo ví dụ trong tài liệu XCP-D / Fair et al. 2020
    [[ $MFILT == notch ]] && mf+=(--band-stop-min 12 --band-stop-max 18 --motion-filter-order 4)

    echo "$(date '+%F %T') BẮT ĐẦU $sub" | tee -a "$LOGD/_progress.log"
    if docker run --rm --name "xcpd_$sub" \
        -u "$(id -u):$(id -g)" -e HOME=/tmp -e TEMPLATEFLOW_HOME=/templateflow \
        --cpus "$THREADS" --memory "${MEM_GB}g" \
        -v "$FMP/dataset_description.json":/fmriprep/dataset_description.json:ro \
        -v "$FMP/$sub":/fmriprep/$sub:ro \
        -v "$OUT":/out -v "$WRK/$sub":/work \
        -v "$FS_LICENSE":/license.txt:ro -v "$WORK/templateflow":/templateflow \
        "$IMG_XCPD" /fmriprep /out participant \
        --participant-label "${sub#sub-}" \
        --mode none --input-type fmriprep --file-format cifti --output-layout bids \
        --atlases 4S256Parcels --min-coverage 0.5 \
        -p 36P --despike y --smoothing 0 \
        --dummy-scans auto \
        -f 0.5 --censor-between 0 --min-time 240 --output-type censored \
        --lower-bpf 0.01 --upper-bpf 0.08 --bpf-order 2 \
        "${mf[@]}" \
        --combine-runs n --output-run-wise-correlations y --warp-surfaces-native2std n \
        --linc-qc y --abcc-qc n \
        --fs-license-file /license.txt \
        --nprocs "$THREADS" --omp-nthreads "$THREADS" --mem-mb "$(( MEM_GB * 1000 - 1000 ))" \
        --resource-monitor --notrack -w /work \
        >"$log" 2>&1; then
        date '+%F %T' > "$LOGD/$sub.done"
        rm -rf "${WRK:?}/$sub"
        echo "$(date '+%F %T') XONG    $sub" | tee -a "$LOGD/_progress.log"
    else
        touch "$LOGD/$sub.failed"
        echo "$(date '+%F %T') LỖI     $sub  (xem $log)" | tee -a "$LOGD/_progress.log"
    fi
}

run_queue() {  # $@ = subjects
    local todo=()
    for s in "$@"; do [[ -f $LOGD/$s.done || -f $LOGD/$s.failed ]] || todo+=("$s"); done
    [[ ${#todo[@]} -eq 0 ]] && return 0
    echo "XCP-D: ${#todo[@]} subject, $JOBS song song × $THREADS core, ${MEM_GB} GB, motion filter=$MFILT. Log: $LOGD"
    printf "%s\n" "${todo[@]}" | xargs -P "$JOBS" -I{} bash "$SELF" --one {}
}

case "${1:-}" in
    --one)          one "$2"; exit 0 ;;
    --list)         mapfile -t SUBS < <(grep -v '^\s*$' "$2"); run_queue "${SUBS[@]}" ;;
    --retry-failed) mapfile -t SUBS < <(ls "$LOGD"/*.failed 2>/dev/null | xargs -rn1 basename | sed 's/\.failed$//')
                    rm -f "$LOGD"/*.failed; run_queue "${SUBS[@]}" ;;
    --follow)
        while true; do
            mapfile -t READY < <(ls "$LOG_DIR"/fmriprep/*.done 2>/dev/null | xargs -rn1 basename | sed 's/\.done$//')
            run_queue "${READY[@]}"
            if ! docker ps --format '{{.Names}}' | grep -q '^fmriprep_'; then
                # fMRIPrep không còn chạy: chạy nốt subject vừa xong rồi dừng
                mapfile -t READY < <(ls "$LOG_DIR"/fmriprep/*.done 2>/dev/null | xargs -rn1 basename | sed 's/\.done$//')
                run_queue "${READY[@]}"
                echo "$(date '+%F %T') fMRIPrep hết việc, dừng --follow"; break
            fi
            sleep 300
        done ;;
    "")             echo "Cần chỉ rõ subject, --list, --retry-failed hoặc --follow."; exit 1 ;;
    *)              run_queue "$@" ;;
esac
echo "XCP-D: done=$(ls "$LOGD"/*.done 2>/dev/null | wc -l), failed=$(ls "$LOGD"/*.failed 2>/dev/null | wc -l)"
