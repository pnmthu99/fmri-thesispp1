#!/usr/bin/env bash
# Xem nhanh tiến độ toàn dự án, không cần vào tmux.
# Cách dùng:  bash ~/thupnm-wp/fmri-thesispp1/status.sh
source "$(dirname "$(readlink -f "$0")")/config/paths.sh"

echo "===== $(date '+%F %T') ====="
echo "--- tmux (phiên adni) ---"
if tmux has-session -t adni 2>/dev/null; then
    tmux list-windows -t adni -F '  cửa sổ #{window_index}: #{window_name}  (lệnh đang chạy: #{pane_current_command})'
else
    echo "  Không có phiên adni"
fi

echo "--- Giải nén ---"
for g in ad mci cn; do
    if   [[ -f $RAW_DIR/${g}_bids/.extract_done ]]; then echo "  $g: xong ($(cat "$RAW_DIR/${g}_bids/.extract_done"))"
    elif [[ -d $RAW_DIR/${g}_bids ]];               then echo "  $g: ĐANG chạy, đã có $(du -sh "$RAW_DIR/${g}_bids" | cut -f1)"
    else                                                 echo "  $g: chưa"; fi
done

echo "--- BIDS gộp ---"
if [[ -f $TABLES_DIR/group_labels.tsv ]]; then
    tail -n +2 "$TABLES_DIR/group_labels.tsv" | cut -f2 | sort | uniq -c | sed 's/^/  /'
fi
echo "  tổng: $(ls -d "$BIDS_DIR"/sub-* 2>/dev/null | wc -l) subject"

for step in mriqc fmriprep xcp_d; do
    L=$LOG_DIR/$step
    [[ -d $L ]] || continue
    echo "--- $step ---"
    echo "  xong: $(ls "$L"/*.done 2>/dev/null | wc -l) / $(ls -d "$BIDS_DIR"/sub-* | wc -l)   lỗi: $(ls "$L"/*.failed 2>/dev/null | wc -l)   đang chạy: $(docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${step}_")"
    [[ -f $L/_progress.log ]] && tail -3 "$L/_progress.log" | sed 's/^/  /'
done

echo "--- Máy ---"
echo "  load: $(cut -d' ' -f1-3 /proc/loadavg) / $(nproc) core   RAM trống: $(free -g | awk '/Mem/{print $7}') GB   đĩa trống: $(df -h "$WORK" | awk 'NR==2{print $4}')"
echo "  container đang chạy: $(docker ps -q 2>/dev/null | wc -l)"
