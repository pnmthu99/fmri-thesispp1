#!/usr/bin/env bash
# Bước 0: giải nén tarball của một nhóm từ $SRC_DATA (chỉ đọc) vào $RAW_DIR/<nhóm>_bids.
# Cách dùng (CHẠY TRONG TMUX):  bash 01_preprocess/00_extract.sh ad
# Chạy lại được: nếu đã có file đánh dấu .extract_done thì bỏ qua; nếu lần trước dừng giữa chừng
# thì giải nén lại đè lên (tar ghi đè file cũ).
# Bỏ qua tmp_dcm2bids/ (file tạm của dcm2bids, không cần).
set -euo pipefail
source "$(dirname "$0")/../config/paths.sh"

GROUP=${1:?"Thiếu tên nhóm: ad | mci | cn"}
TARBALL=$SRC_DATA/${GROUP}_bids.tar.gz
OUT=$RAW_DIR/${GROUP}_bids
DONE=$OUT/.extract_done
LOG=$LOG_DIR/extract_${GROUP}.log

[[ -f $TARBALL ]] || { echo "Không thấy $TARBALL"; exit 1; }
if [[ -f $DONE ]]; then
    echo "[$GROUP] đã giải nén xong trước đó ($(cat "$DONE")). Bỏ qua."
    exit 0
fi

mkdir -p "$RAW_DIR" "$LOG_DIR"
NCPU=$(( MAX_CPUS < 8 ? MAX_CPUS : 8 ))
echo "[$GROUP] bắt đầu $(date '+%F %T'): $TARBALL -> $RAW_DIR" | tee -a "$LOG"

# pigz giải nén nhanh hơn gzip; nice/ionice để nhường máy cho người dùng khác
nice -n 10 ionice -c2 -n7 \
    tar -I "pigz -p $NCPU" -xf "$TARBALL" -C "$RAW_DIR" \
        --exclude='*/tmp_dcm2bids' --exclude='*/tmp_dcm2bids/*' \
        --no-same-owner 2>&1 | tee -a "$LOG"

NSUB=$(find "$OUT" -maxdepth 1 -type d -name 'sub-*' | wc -l)
echo "$(date '+%F %T') subjects=$NSUB" > "$DONE"
echo "[$GROUP] xong $(date '+%F %T'): $NSUB subject trong $OUT" | tee -a "$LOG"
du -sh "$OUT" | tee -a "$LOG"
