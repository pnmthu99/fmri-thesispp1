#!/usr/bin/env python3
"""Bước 3: đánh dấu outlier MRIQC theo lớp protocol và chọn 1 T1 + 1 BOLD cho mỗi subject.

Cách dùng:  python3 01_preprocess/03b_select.py
Đầu vào:  $WORK/audit/inventory.tsv, $DERIV_DIR/mriqc/group_{T1w,bold}.tsv
Đầu ra:   $WORK/selection/
  iqm_flags.tsv      mọi ảnh: lớp protocol, IQM chính, chỉ số nào là outlier (nhẹ / nặng)
  manifest.tsv       mỗi subject 1 dòng: ảnh được chọn hoặc lý do loại
  qc_review.tsv      ảnh ĐƯỢC CHỌN mà có outlier → cần xem báo cáo MRIQC bằng mắt
  subjects_fmriprep.txt  danh sách subject cho 04_fmriprep.sh --list
  report.txt
  $WORK/filters/<sub>.json   --bids-filter-file cho fMRIPrep

Nguyên tắc (cố định trước, KHÔNG dùng nhãn bệnh):
- Outlier tính trong từng lớp protocol (BOLD: hãng × multiband; T1: hãng × họ sequence), vì IQM
  khác hẳn giữa các lớp (vd tSNR của multiband thấp hơn nhiều). Ngưỡng Tukey: ngoài [Q1 − k·IQR,
  Q3 + k·IQR], chỉ xét phía "xấu"; k=1.5 là nhẹ, k=3 là nặng. Outlier chỉ để ưu tiên khi chọn và để
  xem bằng mắt, CHƯA tự động loại subject.
- Loại cứng: BOLD < 4.5 phút, ảnh không có IQM (MRIQC lỗi / file hỏng), subject không còn cặp.
- T1: ưu tiên sequence theo danh sách cố định (để mọi subject cùng protocol dùng cùng loại T1),
  ảnh outlier nặng xuống cuối, rồi CNR cao nhất.
- BOLD: ảnh outlier nặng xuống cuối, rồi dài nhất, rồi fd_mean thấp nhất.
- Mọi ảnh trùng của một subject đều cùng buổi chụp (cùng StudyDescription và máy, kiểm tra 2026-11-26).
"""
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

WORK = Path(os.environ.get("WORK", "/home/thupnm/thupnm-wp/adni_work"))
DERIV = Path(os.environ.get("DERIV_DIR", WORK / "derivatives"))
OUT = WORK / "selection"
FILTERS = WORK / "filters"
MIN_BOLD_MIN = 4.5
K_MILD, K_SEVERE = 1.5, 3.0

# IQM chính: +1 = càng cao càng xấu, -1 = càng thấp càng xấu
# fber bỏ: = -1 (lỗi, nền ảnh bằng 0) ở 312/686 T1
IQM_T1 = {"cjv": +1, "cnr": -1, "efc": +1, "qi_1": +1, "snr_total": -1}
IQM_BOLD = {"fd_mean": +1, "tsnr": -1, "dvars_std": +1, "aor": +1, "aqi": +1, "efc": +1}


def t1_rank(desc: str) -> int:
    """Thứ hạng sequence T1 (nhỏ = ưu tiên)."""
    d = desc.upper()
    if d.endswith("_ND") or d.startswith("ORIG"):
        return 4          # chưa hiệu chỉnh méo gradient (ND / ORIG)
    if d.startswith(("HS ", "CS ")):
        return 3          # biến thể nhanh của ADNI4 (high-speed / compressed sensing)
    if "SENSE2" in d:
        return 2          # Philips ADNI2: chọn MPRAGE thường, SENSE2 là dự phòng
    return 1              # Accelerated MPRAGE / MPRAGE / IR-FSPGR chuẩn


def t1_family(desc: str) -> str:
    return "IRFSPGR" if "FSPGR" in desc.upper() else "MPRAGE"


def flag_outliers(df: pd.DataFrame, iqms: dict, cls: str) -> pd.DataFrame:
    df = df.copy()
    df["n_mild"] = 0
    df["n_severe"] = 0
    df["outlier_iqms"] = ""
    for c, sign in iqms.items():
        for _, g in df.groupby(cls):
            x = g[c]
            q1, q3 = x.quantile([0.25, 0.75])
            iqr = q3 - q1
            if sign > 0:
                mild, sev = x > q3 + K_MILD * iqr, x > q3 + K_SEVERE * iqr
            else:
                mild, sev = x < q1 - K_MILD * iqr, x < q1 - K_SEVERE * iqr
            df.loc[g.index[mild.values], "n_mild"] += 1
            df.loc[g.index[sev.values], "n_severe"] += 1
            tag = np.where(sev, f"{c}!!", f"{c}!")
            for i in g.index[mild.values]:
                df.at[i, "outlier_iqms"] += ("," if df.at[i, "outlier_iqms"] else "") + tag[g.index.get_loc(i)]
    return df


def entities(fname: str) -> dict:
    acq = re.search(r"_acq-([A-Za-z0-9]+)", fname)
    run = re.search(r"_run-([0-9]+)", fname)
    return {"acquisition": acq.group(1) if acq else None,
            "run": int(run.group(1)) if run else None}


def main():
    OUT.mkdir(exist_ok=True)
    FILTERS.mkdir(exist_ok=True)
    inv = pd.read_csv(WORK / "audit/inventory.tsv", sep="\t")
    inv["bids_name"] = inv.file.map(lambda f: Path(f).name.replace(".nii.gz", ""))

    # ---------- IQM + outlier ----------
    q1 = pd.read_csv(DERIV / "mriqc/group_T1w.tsv", sep="\t")
    qb = pd.read_csv(DERIV / "mriqc/group_bold.tsv", sep="\t")
    t1 = inv[inv.kind == "T1w"].merge(q1[["bids_name", *IQM_T1]], on="bids_name", how="left")
    bo = inv[inv.kind == "bold"].merge(qb[["bids_name", *IQM_BOLD]], on="bids_name", how="left")
    t1["has_iqm"] = t1.cnr.notna()
    bo["has_iqm"] = bo.tsnr.notna()
    t1["rank"] = t1.SeriesDescription.map(t1_rank)
    t1["cls"] = t1.Manufacturer + "_" + t1.SeriesDescription.map(t1_family)
    bo["cls"] = bo.Manufacturer + "_" + np.where(bo.multiband == True, "MB", "SB")
    bo["long_enough"] = bo.duration_min >= MIN_BOLD_MIN

    t1f = flag_outliers(t1[t1.has_iqm], IQM_T1, "cls")
    bof = flag_outliers(bo[bo.has_iqm & bo.long_enough], IQM_BOLD, "cls")
    t1 = t1.join(t1f[["n_mild", "n_severe", "outlier_iqms"]])
    bo = bo.join(bof[["n_mild", "n_severe", "outlier_iqms"]])

    keep = ["participant_id", "kind", "file", "cls", "SeriesDescription", "duration_min", "has_iqm",
            "n_mild", "n_severe", "outlier_iqms"]
    allimg = pd.concat([t1.assign(duration_min=np.nan)[keep + [*IQM_T1]],
                        bo[keep + [*IQM_BOLD]]], ignore_index=True)
    allimg.to_csv(OUT / "iqm_flags.tsv", sep="\t", index=False, float_format="%.4g")

    # ---------- chọn ảnh ----------
    t1c = t1[t1.has_iqm].sort_values(
        ["participant_id", "n_severe", "rank", "cnr"], ascending=[True, True, True, False])
    boc = bo[bo.has_iqm & bo.long_enough].sort_values(
        ["participant_id", "n_severe", "duration_min", "fd_mean"], ascending=[True, True, False, True])
    best_t1 = t1c.groupby("participant_id").head(1).set_index("participant_id")
    best_bo = boc.groupby("participant_id").head(1).set_index("participant_id")
    n_t1 = t1.groupby("participant_id").size()
    n_bo = bo.groupby("participant_id").size()

    rows = []
    for sub in sorted(inv.participant_id.unique()):
        r = {"participant_id": sub, "n_T1w": int(n_t1.get(sub, 0)), "n_bold": int(n_bo.get(sub, 0))}
        reasons = []
        if r["n_T1w"] == 0:
            reasons.append("không có T1")
        elif sub not in best_t1.index:
            reasons.append("không có T1 qua được MRIQC")
        if r["n_bold"] == 0:
            reasons.append("không có BOLD")
        elif sub not in best_bo.index:
            b = bo[bo.participant_id == sub]
            reasons.append("BOLD < 4.5 phút" if not b.long_enough.any() else "không có BOLD qua được MRIQC")
        if reasons:
            r.update(status="excluded", reason="; ".join(reasons))
        else:
            a, b = best_t1.loc[sub], best_bo.loc[sub]
            r.update(status="selected", reason="",
                     T1w=a.file, T1w_desc=a.SeriesDescription, T1w_cls=a.cls,
                     T1w_outliers=a.outlier_iqms, T1w_n_severe=int(a.n_severe),
                     bold=b.file, bold_desc=b.SeriesDescription, bold_cls=b.cls,
                     bold_TR=b.RepetitionTime, bold_vols=int(b.n_vols), bold_min=round(b.duration_min, 2),
                     fd_mean=round(b.fd_mean, 4), bold_outliers=b.outlier_iqms, bold_n_severe=int(b.n_severe),
                     selection_needed=bool(r["n_T1w"] > 1 or n_bo.get(sub, 0) > 1))
            et, eb = entities(a.file), entities(b.file)
            filt = {"t1w": {"datatype": "anat", "suffix": "T1w", **et},
                    "bold": {"datatype": "func", "suffix": "bold", "task": "rest", **eb}}
            (FILTERS / f"{sub}.json").write_text(json.dumps(filt, indent=2) + "\n")
        rows.append(r)
    man = pd.DataFrame(rows)
    man.to_csv(OUT / "manifest.tsv", sep="\t", index=False)
    sel = man[man.status == "selected"]
    sel.participant_id.to_csv(OUT / "subjects_fmriprep.txt", index=False, header=False)

    review = sel[(sel.T1w_outliers.fillna("") != "") | (sel.bold_outliers.fillna("") != "")]
    review = review.assign(severe=(review.T1w_n_severe + review.bold_n_severe) > 0)
    review.sort_values(["severe", "participant_id"], ascending=[False, True])[
        ["participant_id", "severe", "T1w", "T1w_outliers", "bold", "bold_outliers", "fd_mean"]
    ].to_csv(OUT / "qc_review.tsv", sep="\t", index=False)

    # ---------- report (nhãn nhóm chỉ dùng để MÔ TẢ, sau khi đã chọn xong) ----------
    lab = pd.read_csv(WORK / "tables/group_labels.tsv", sep="\t").set_index("participant_id").group
    man["group"] = man.participant_id.map(lab)
    review = review.assign(group=review.participant_id.map(lab))
    L = []
    L.append(f"Subject: {len(man)}   chọn được: {len(sel)}   loại: {(man.status == 'excluded').sum()}\n")
    L.append("== Trạng thái theo nhóm\n" + pd.crosstab(man.status, man.group, margins=True).to_string() + "\n")
    L.append("== Lý do loại\n" + man[man.status == "excluded"][["participant_id", "group", "reason"]].to_string(index=False) + "\n")
    L.append("== Ảnh đánh dấu outlier (ảnh có IQM, BOLD >= 4.5 phút), theo lớp protocol")
    for name, d in (("T1w", t1f), ("BOLD", bof)):
        L.append(f"-- {name}\n" + d.groupby("cls").agg(
            n=("file", "size"), mild=("n_mild", lambda x: (x > 0).sum()),
            severe=("n_severe", lambda x: (x > 0).sum())).to_string())
    L.append("\n== Ảnh được chọn có outlier (cần xem bằng mắt): "
             f"{len(review)} subject, trong đó {review.severe.sum()} có outlier nặng")
    L.append(pd.crosstab(review.severe, review.group, margins=True).to_string() + "\n")
    L.append("== T1 được chọn (SeriesDescription)\n" + sel.T1w_desc.value_counts().to_string() + "\n")
    L.append("== Lớp protocol BOLD được chọn × nhóm\n" + pd.crosstab(sel.bold_cls, man.loc[sel.index, "group"], margins=True).to_string() + "\n")
    L.append("== fd_mean BOLD được chọn theo lớp × nhóm (trung vị)\n"
             + sel.assign(group=man.loc[sel.index, "group"]).pivot_table(
                 index="bold_cls", columns="group", values="fd_mean", aggfunc="median").round(3).to_string() + "\n")
    multi = sel[sel.selection_needed]
    L.append(f"== Subject phải chọn ảnh: {len(multi)}; T1 được chọn:\n" + multi.T1w_desc.value_counts().to_string())
    txt = "\n".join(L)
    (OUT / "report.txt").write_text(txt + "\n")
    print(txt)
    print(f"\nĐã ghi {OUT}/ và {len(sel)} filter trong {FILTERS}/")


if __name__ == "__main__":
    main()
