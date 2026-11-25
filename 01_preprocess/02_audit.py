#!/usr/bin/env python3
"""Bước 1: audit $BIDS_DIR. Chỉ đọc JSON và header NIfTI (không đọc dữ liệu ảnh).

Cách dùng:  python3 01_preprocess/02_audit.py
Output ($WORK/audit/):
  inventory.tsv        mỗi dòng một ảnh T1w/BOLD với metadata acquisition
  subject_summary.tsv  mỗi subject: số T1, số BOLD, nhóm, cờ cảnh báo
  report.txt           thống kê để chốt quy tắc chọn ảnh, slice timing, multiband
Nhóm (AD/MCI/CN) chỉ dùng để thống kê mô tả, KHÔNG dùng để lọc.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import nibabel as nib
import pandas as pd

ENV = dict(
    line.split("=", 1)
    for line in subprocess.run(
        ["bash", "-c", f"source {Path(__file__).resolve().parents[1]}/config/paths.sh && env"],
        capture_output=True, text=True, check=True).stdout.splitlines()
    if "=" in line
)
BIDS = Path(ENV["BIDS_DIR"])
OUT = Path(ENV["WORK"]) / "audit"
LABELS = Path(ENV["TABLES_DIR"]) / "group_labels.tsv"
MIN_BOLD_MIN = 4.5  # lọc thô: bỏ BOLD dưới 4.5 phút (chốt 2026-11-25, giữ multiband ADNI3/4 4.88 phút)

ENT = re.compile(r"(sub|acq|run|task)-([A-Za-z0-9]+)")
KEYS = ["Manufacturer", "ManufacturersModelName", "MagneticFieldStrength", "StudyDescription",
        "SeriesDescription", "ProtocolName", "PulseSequenceType", "SoftwareVersions",
        "RepetitionTime", "EchoTime", "FlipAngle", "InversionTime", "MultibandAccelerationFactor",
        "PhaseEncodingDirection", "TotalReadoutTime", "EffectiveEchoSpacing", "SliceThickness",
        "BidsGuess"]


def adni_phase(study_desc):
    s = str(study_desc).upper()
    for p in ("ADNI4", "ADNI3", "ADNIGO", "ADNI2"):
        if p in s:
            return p
    return ""


def row_for(nii: Path):
    ents = dict(ENT.findall(nii.name))
    js = nii.with_name(nii.name.replace(".nii.gz", ".json"))
    meta = json.loads(js.read_text()) if js.exists() else {}
    hdr = nib.load(str(nii)).header
    shape, zooms = hdr.get_data_shape(), hdr.get_zooms()
    kind = "bold" if nii.name.endswith("_bold.nii.gz") else "T1w"
    r = dict(participant_id=f"sub-{ents['sub']}", kind=kind, file=str(nii.relative_to(BIDS)),
             acq=ents.get("acq", ""), run=ents.get("run", ""), has_json=js.exists(),
             dim="x".join(map(str, shape[:3])), vox="x".join(f"{z:.2f}" for z in zooms[:3]))
    for k in KEYS:
        v = meta.get(k)
        r[k] = json.dumps(v) if isinstance(v, (list, dict)) else v
    r["adni_phase"] = adni_phase(meta.get("StudyDescription"))
    st = meta.get("SliceTiming")
    r["has_SliceTiming"] = bool(st)
    r["n_slices"] = shape[2] if len(shape) > 2 else None
    if kind == "bold":
        nvol = shape[3] if len(shape) > 3 else 1
        tr = meta.get("RepetitionTime") or (zooms[3] if len(zooms) > 3 else None)
        r["n_vols"] = nvol
        r["duration_min"] = round(nvol * tr / 60, 2) if tr else None
        r["multiband"] = (meta.get("MultibandAccelerationFactor") or 1) > 1
        r["has_TotalReadoutTime"] = meta.get("TotalReadoutTime") is not None
    return r


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    groups = pd.read_csv(LABELS, sep="\t") if LABELS.exists() else pd.DataFrame(columns=["participant_id", "group"])
    niis = sorted(BIDS.glob("sub-*/anat/*_T1w.nii.gz")) + sorted(BIDS.glob("sub-*/func/*_bold.nii.gz"))
    inv = pd.DataFrame([row_for(p) for p in niis]).merge(groups, on="participant_id", how="left")
    inv.to_csv(OUT / "inventory.tsv", sep="\t", index=False)

    subs = sorted(p.name for p in BIDS.glob("sub-*") if p.is_dir())
    t1 = inv[inv.kind == "T1w"].groupby("participant_id").size()
    bold = inv[inv.kind == "bold"]
    nb = bold.groupby("participant_id").size()
    nb_ok = bold[bold.duration_min >= MIN_BOLD_MIN].groupby("participant_id").size()
    ss = pd.DataFrame({"participant_id": subs})
    ss["n_T1w"] = ss.participant_id.map(t1).fillna(0).astype(int)
    ss["n_bold"] = ss.participant_id.map(nb).fillna(0).astype(int)
    ss["n_bold_ge5min"] = ss.participant_id.map(nb_ok).fillna(0).astype(int)
    ss = ss.merge(groups, on="participant_id", how="left")

    def flag(r):
        if r.n_T1w == 0: return "no_T1w"
        if r.n_bold == 0: return "no_bold"
        if r.n_bold_ge5min == 0: return "bold_lt5min"
        if r.n_T1w > 1 or r.n_bold_ge5min > 1: return "needs_selection"
        return "single_pair"
    ss["status"] = ss.apply(flag, axis=1)
    ss.to_csv(OUT / "subject_summary.tsv", sep="\t", index=False)

    L = []
    p = L.append
    vc = lambda s: s.value_counts(dropna=False).to_string()
    p(f"BIDS: {BIDS}\nSubject: {len(subs)}   T1w: {(inv.kind=='T1w').sum()}   BOLD: {len(bold)}\n")
    p("== Nhóm (chỉ mô tả)\n" + vc(ss.group))
    p("\n== Trạng thái subject\n" + pd.crosstab(ss.status, ss.group, margins=True).to_string())
    p("\n== BOLD: hãng máy × multiband\n" + pd.crosstab(bold.Manufacturer, bold.multiband, margins=True).to_string())
    p("\n== BOLD: ADNI phase × multiband\n" + pd.crosstab(bold.adni_phase, bold.multiband, margins=True).to_string())
    p("\n== BOLD: hãng máy × có SliceTiming\n" + pd.crosstab(bold.Manufacturer, bold.has_SliceTiming, margins=True).to_string())
    p("\n== BOLD: hãng máy × có TotalReadoutTime (cần cho SDC)\n" + pd.crosstab(bold.Manufacturer, bold.has_TotalReadoutTime, margins=True).to_string())
    p("\n== BOLD: TR × số volume × thời lượng\n" + vc(bold[["RepetitionTime", "n_vols", "duration_min"]].apply(tuple, axis=1)))
    p(f"\n== BOLD dưới {MIN_BOLD_MIN} phút\n" + (bold[bold.duration_min < MIN_BOLD_MIN][["file", "RepetitionTime", "n_vols", "duration_min"]].to_string(index=False) or "(không có)"))
    p("\n== BOLD SeriesDescription\n" + vc(bold.SeriesDescription))
    t1df = inv[inv.kind == "T1w"]
    p("\n== T1w SeriesDescription (để chốt danh sách ưu tiên)\n" + vc(t1df.SeriesDescription))
    p("\n== T1w hãng máy × acq\n" + pd.crosstab(t1df.Manufacturer, t1df.acq.replace("", "(none)"), margins=True).to_string())
    p("\n== T1w kích thước / voxel\n" + vc(t1df[["dim", "vox"]].apply(tuple, axis=1)))
    p("\n== Fieldmap: " + str(len(list(BIDS.glob("sub-*/fmap/*")))) + " file")
    p("\n== Subject cần chọn ảnh\n" + ss[ss.status == "needs_selection"][["participant_id", "n_T1w", "n_bold_ge5min"]].to_string(index=False))
    report = "\n".join(L)
    (OUT / "report.txt").write_text(report)
    print(report)
    print(f"\nĐã ghi: {OUT}/inventory.tsv, subject_summary.tsv, report.txt")


if __name__ == "__main__":
    main()
