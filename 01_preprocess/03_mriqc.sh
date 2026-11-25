#!/usr/bin/env bash
# Bước 2: MRIQC (chỉ QC) trên mọi T1w + BOLD trong $BIDS_DIR. CHẠY TRONG TMUX.
#
# Cách dùng:
#   bash 01_preprocess/03_mriqc.sh                 # mọi subject chưa xong
#   bash 01_preprocess/03_mriqc.sh sub-4024 ...    # chỉ các subject liệt kê
#   bash 01_preprocess/03_mriqc.sh --retry-failed  # chạy lại các subject lỗi
#   bash 01_preprocess/03_mriqc.sh group           # group report (sau khi xong participant)
#
# Chạy lại được: subject có $LOG_DIR/mriqc/<sub>.done thì bỏ qua.
# Mỗi subject: 1 container, log riêng ở $LOG_DIR/mriqc/<sub>.log; lỗi thì tạo <sub>.failed.
# --no-sub: KHÔNG gửi IQM lên web API của MRIQC (dữ liệu ADNI). --notrack: tắt telemetry.
set -euo pipefail
SELF=$(readlink -f "$0")
source "$(dirname "$SELF")/../config/paths.sh"

THREADS=2                                  # core mỗi subject (MRIQC thực tế dùng ~1–1.6 core)
MEM_GB=8                                   # RAM mỗi subject (thực tế < 2 GB)
JOBS=${MRIQC_JOBS:-$(( MAX_CPUS / THREADS ))}  # số subject song song (mặc định 26/2 = 13)
# Đổi số job khi đang chạy, không cần dừng:  pkill -USR1 -u $(id -u) -x xargs  (+1)  |  -USR2 (−1)
OUT=$DERIV_DIR/mriqc
WRK=$WORK_TMP/mriqc
LOGD=$LOG_DIR/mriqc
mkdir -p "$OUT" "$WRK" "$LOGD"

run_docker() {  # $1 = tên container (= tên thư mục work riêng), còn lại = tham số mriqc
    local name=$1; shift
    mkdir -p "$WRK/$name"
    docker run --rm --name "$name" \
        -u "$(id -u):$(id -g)" -e HOME=/tmp \
        --cpus "$THREADS" --memory "${MEM_GB}g" \
        -v "$BIDS_DIR":/data:ro -v "$OUT":/out -v "$WRK/$name":/work \
        "$IMG_MRIQC" /data /out "$@" \
        --no-sub --notrack -w /work \
        --nprocs "$THREADS" --omp-nthreads "$THREADS" --mem "$MEM_GB" \
        --fd_thres 0.5
}

one() {  # chạy 1 subject
    local sub=$1 log=$LOGD/$1.log
    [[ -f $LOGD/$sub.done ]] && return 0
    rm -f "$LOGD/$sub.failed"
    echo "$(date '+%F %T') BẮT ĐẦU $sub" | tee -a "$LOGD/_progress.log"
    if run_docker "mriqc_$sub" participant --participant-label "${sub#sub-}" -m T1w bold >"$log" 2>&1; then
        date '+%F %T' > "$LOGD/$sub.done"
        rm -rf "${WRK:?}/mriqc_$sub"
        echo "$(date '+%F %T') XONG    $sub" | tee -a "$LOGD/_progress.log"
    else
        touch "$LOGD/$sub.failed"
        echo "$(date '+%F %T') LỖI     $sub  (xem $log)" | tee -a "$LOGD/_progress.log"
    fi
}

case "${1:-}" in
    --one)   one "$2"; exit 0 ;;
    group)   run_docker mriqc_group group 2>&1 | tee "$LOGD/group.log"; exit 0 ;;
    --retry-failed) mapfile -t SUBS < <(ls "$LOGD"/*.failed 2>/dev/null | xargs -rn1 basename | sed 's/\.failed$//') ;;
    "")      mapfile -t SUBS < <(ls -d "$BIDS_DIR"/sub-* | xargs -n1 basename) ;;
    *)       SUBS=("$@") ;;
esac

TODO=()
for s in "${SUBS[@]}"; do [[ -f $LOGD/$s.done ]] || TODO+=("$s"); done
echo "MRIQC: ${#TODO[@]} subject cần chạy, $JOBS song song × $THREADS core, ${MEM_GB} GB/subject. Log: $LOGD"
[[ ${#TODO[@]} -eq 0 ]] && exit 0
printf "%s\n" "${TODO[@]}" | xargs -P "$JOBS" -I{} bash "$SELF" --one {}
echo "Hết hàng đợi: done=$(ls "$LOGD"/*.done 2>/dev/null | wc -l), failed=$(ls "$LOGD"/*.failed 2>/dev/null | wc -l)"
