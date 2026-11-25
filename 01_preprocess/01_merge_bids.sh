#!/usr/bin/env bash
# Bước 0b: gộp một nhóm từ $RAW_DIR/<nhóm>_bids vào $BIDS_DIR (BIDS chung, pipeline không biết nhóm).
# Cách dùng:  bash 01_preprocess/01_merge_bids.sh ad
#
# - Dùng hard link (cp -al): không tốn thêm dung lượng, file trong bids/ là file thật (Docker đọc được).
# - Bỏ file JSON không có ảnh .nii.gz đi kèm (sidecar mồ côi) và ghi vào log.
# - Subject đã có trong bids/: cùng nhóm thì bỏ qua (chạy lại an toàn); KHÁC nhóm thì báo trùng RID, không ghi đè.
# - Nhãn nhóm ghi vào $TABLES_DIR/group_labels.tsv (ngoài BIDS).
set -euo pipefail
source "$(dirname "$0")/../config/paths.sh"

GROUP=${1:?"Thiếu tên nhóm: ad | mci | cn"}
SRC=$RAW_DIR/${GROUP}_bids
LABELS=$TABLES_DIR/group_labels.tsv
LOG=$LOG_DIR/merge_${GROUP}.log
[[ -f $SRC/.extract_done ]] || { echo "Chưa giải nén xong $SRC"; exit 1; }

mkdir -p "$BIDS_DIR" "$TABLES_DIR" "$LOG_DIR"
[[ -f $LABELS ]] || printf "participant_id\tgroup\n" > "$LABELS"
if [[ ! -f $BIDS_DIR/dataset_description.json ]]; then
cat > "$BIDS_DIR/dataset_description.json" <<'EOF'
{
    "Name": "ADNI rs-fMRI baseline (CN/MCI/AD merged)",
    "BIDSVersion": "1.9.0",
    "DatasetType": "raw",
    "GeneratedBy": [{"Name": "dcm2bids"}, {"Name": "fmri-thesispp1/01_merge_bids.sh"}]
}
EOF
fi

echo "== merge $GROUP $(date '+%F %T')" >> "$LOG"
n_new=0; n_skip=0; n_clash=0; n_orphan=0
for d in "$SRC"/sub-*/; do
    sub=$(basename "$d")
    prev=$(awk -F'\t' -v s="$sub" '$1==s{print $2}' "$LABELS")
    if [[ -n $prev ]]; then
        if [[ $prev == "$GROUP" ]]; then n_skip=$((n_skip+1)); continue; fi
        echo "TRÙNG RID: $sub đã thuộc nhóm '$prev', bỏ qua bản của '$GROUP'" | tee -a "$LOG"
        n_clash=$((n_clash+1)); continue
    fi
    [[ -e $BIDS_DIR/$sub ]] && { echo "LỖI: $BIDS_DIR/$sub tồn tại nhưng không có trong $LABELS" | tee -a "$LOG"; exit 1; }

    cp -al "$d" "$BIDS_DIR/$sub"
    # bỏ sidecar mồ côi
    while IFS= read -r j; do
        if [[ ! -f ${j%.json}.nii.gz && ! -f ${j%.json}.nii ]]; then
            echo "Bỏ JSON mồ côi: ${j#$BIDS_DIR/}" >> "$LOG"; rm -f "$j"; n_orphan=$((n_orphan+1))
        fi
    done < <(find "$BIDS_DIR/$sub" -name '*.json')
    printf "%s\t%s\n" "$sub" "$GROUP" >> "$LABELS"
    n_new=$((n_new+1))
done

msg="[$GROUP] thêm mới $n_new, đã có $n_skip, trùng RID $n_clash, bỏ JSON mồ côi $n_orphan. Tổng subject trong bids/: $(ls -d "$BIDS_DIR"/sub-* | wc -l)"
echo "$msg" | tee -a "$LOG"
