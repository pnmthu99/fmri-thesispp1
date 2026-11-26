"""ALFF sau XCP-D (XCP-D chạy với --skip alff). CHẠY TRONG CONTAINER XCP-D (cùng numpy/nibabel/atlas).

Cách dùng (05_xcpd.sh tự gọi sau mỗi subject):
    python 05b_alff.py /xcpd sub-6854 [--compare]
      /xcpd     : thư mục output XCP-D (có sub-X/func/)
      --compare : so với ALFF do XCP-D tính (file *_stat-alff_*), dùng để kiểm chứng trên pilot

Công thức theo đúng xcp_d 26.3.0 (utils/restingstate.compute_alff + parcellate_alff_wf):
  - Mỗi grayordinate: lấy frame còn lại sau censor, trừ mean, chia SD, Lomb-Scargle chuẩn hóa
    (scipy.signal.lombscargle normalize=True, precenter=False, floating_mean=False) tại các thời điểm
    thật của frame; lưới tần số linspace(0, fs/2, n//2+1)[1:] với n = số volume sau dummy;
    ALFF = 2 * mean(sqrt(P)[i_hp:i_lp]) * SD, i_hp/i_lp = tần số gần 0.01 / 0.08 Hz nhất.
  - Parcel: trung bình các grayordinate có tín hiệu (bỏ vertex toàn 0/NaN) trong parcel 4S256;
    parcel có coverage <= min-coverage (đọc từ stat-coverage của XCP-D) → NaN.
Khác XCP-D đúng 1 điểm: SD (nhân ở cuối) tính trên frame thật, vì output censored không còn frame
nội suy (XCP-D tính SD trên chuỗi đã nội suy). Tốc độ: các hàm sin/cos chỉ phụ thuộc thời điểm và
tần số nên tính một lần cho cả 91k grayordinate, và chỉ tính các tần số trong dải (≈ 1/10 lưới).
"""
import glob
import json
import sys
import time

import nibabel as nb
import numpy as np
import pandas as pd

LOW_PASS, HIGH_PASS, MIN_COVERAGE = 0.08, 0.01, 0.5
ATLAS = "4S256Parcels"
ATLAS_DIR = "/home/xcp_d/.cache/xcp_d/AtlasPack/tpl-fsLR"


def lombscargle_many(t, Y, freqs):
    """scipy.signal.lombscargle(t, y, freqs, normalize=True) cho mọi hàng của Y (vertex × time)."""
    w = 1.0 / t.size                                    # weights = 1/N (scipy mặc định)
    ft = t[:, None] * freqs[None, :]                    # time × freq
    cos, sin = np.cos(ft), np.sin(ft)
    CC = w * (cos * cos).sum(0)
    SS = 1.0 - CC
    CS = w * (cos * sin).sum(0)
    tau = 0.5 * np.arctan2(2.0 * CS, CC - SS)
    c_tau, s_tau = np.cos(ft - tau), np.sin(ft - tau)
    YC = w * (Y @ c_tau)                                # vertex × freq
    YS = w * (Y @ s_tau)
    CC = w * (c_tau * c_tau).sum(0)
    SS = 1.0 - CC
    eps = np.finfo(np.float64).epsneg
    CC, SS = np.maximum(CC, eps), np.maximum(SS, eps)
    pgram = 2.0 * (YC * YC / CC + YS * YS / SS)
    YY = w * (Y * Y).sum(1, keepdims=True)
    return pgram * 0.5 / YY


def compute_alff(data, keep, tr, n_vol):
    """data: vertex × frame-còn-lại; keep: mặt nạ (n_vol,) frame giữ lại."""
    sd = data.std(axis=1)
    alff = np.zeros(data.shape[0])
    ok = sd > 0
    Y = data[ok].astype(np.float64)
    Y = (Y - Y.mean(1, keepdims=True)) / Y.std(1, keepdims=True)
    t = (np.arange(n_vol) * tr)[keep]
    fs = 1.0 / tr
    f_all = np.linspace(0, 0.5 * fs, n_vol // 2 + 1)[1:]
    i0, i1 = np.argmin(np.abs(f_all - HIGH_PASS)), np.argmin(np.abs(f_all - LOW_PASS))
    freqs = 2 * np.pi * f_all[i0:i1]
    P = np.empty((Y.shape[0], freqs.size))
    for s in range(0, Y.shape[0], 8192):                # chia khối cho đỡ RAM
        P[s:s + 8192] = lombscargle_many(t, Y[s:s + 8192], freqs)
    alff[ok] = 2 * np.sqrt(P).mean(1) * sd[ok]
    return alff


def main(xcpd, sub, compare=False):
    t0 = time.time()
    func = f"{xcpd}/{sub}/func"
    bolds = sorted(glob.glob(f"{func}/{sub}_*desc-denoised_bold.dtseries.nii"))
    if not bolds:
        raise SystemExit(f"{sub}: không có desc-denoised_bold.dtseries.nii")
    atlas = nb.load(f"{ATLAS_DIR}/tpl-fsLR_atlas-{ATLAS}_den-91k_dseg.dlabel.nii")
    lab = np.asarray(atlas.get_fdata()).ravel().astype(int)
    names = pd.read_table(f"{ATLAS_DIR}/tpl-fsLR_atlas-{ATLAS}_den-91k_dseg.tsv")
    for bold in bolds:
        stem = bold.split("_space-")[0]
        img = nb.load(bold)
        data = np.asarray(img.get_fdata(dtype=np.float32)).T          # vertex × frame
        tr = float(img.header.get_axis(0).step)
        mask = pd.read_table(f"{stem}_outliers.tsv")["denoising"].to_numpy() == 0
        if mask.sum() != data.shape[1]:
            raise SystemExit(f"{bold}: {data.shape[1]} frame nhưng outliers giữ {mask.sum()}")
        alff = compute_alff(data, mask, tr, mask.size)

        # dense: dscalar cùng brain model với BOLD
        bm = img.header.get_axis(1)
        out_d = f"{stem}_space-fsLR_den-91k_stat-alff_desc-lomb_boldmap.dscalar.nii"
        nb.Cifti2Image(alff[None, :].astype(np.float32),
                       header=(nb.cifti2.ScalarAxis(["alff"]), bm)).to_filename(out_d)

        # parcel: trung bình vertex có tín hiệu, rồi che parcel coverage thấp
        good = ~np.all((data == 0) | np.isnan(data), axis=1)
        cov = pd.read_table(f"{stem}_space-fsLR_atlas-{ATLAS}_stat-coverage_bold.tsv")
        row = {}
        for idx, name in zip(names["index"], names["name"]):
            sel = (lab == idx) & good
            v = alff[sel].mean() if sel.any() else np.nan
            row[name] = v if float(cov[name].iloc[0]) > MIN_COVERAGE else np.nan
        out_p = f"{stem}_space-fsLR_atlas-{ATLAS}_stat-alff_desc-lomb_bold.tsv"
        pd.DataFrame([row]).to_csv(out_p, sep="\t", index=False, na_rep="n/a")
        json.dump({"Description": "ALFF (Lomb-Scargle trên dữ liệu đã censor, theo xcp_d 26.3.0; "
                                  "SD tính trên frame thật). Tạo bởi 01_preprocess/05b_alff.py",
                   "LowPass": LOW_PASS, "HighPass": HIGH_PASS, "MinCoverage": MIN_COVERAGE,
                   "RepetitionTime": tr, "NFramesKept": int(mask.sum()), "NVolumes": int(mask.size)},
                  open(out_p.replace(".tsv", ".json"), "w"), indent=1)
        print(f"{bold.rsplit('/', 1)[1]}: {mask.sum()}/{mask.size} frame, "
              f"{time.time() - t0:.0f} s", flush=True)

        if compare:
            ref_d = glob.glob(f"{stem}_space-fsLR_den-91k_stat-alff_boldmap.dscalar.nii")
            ref_p = glob.glob(f"{stem}_space-fsLR_atlas-{ATLAS}_stat-alff_bold.tsv")
            if ref_d:
                r = np.asarray(nb.load(ref_d[0]).get_fdata()).ravel()
                m = (r != 0) & (alff != 0)
                print(f"  dense  r={np.corrcoef(r[m], alff[m])[0, 1]:.5f}  "
                      f"median |Δ|/ref={np.median(np.abs(alff[m] - r[m]) / r[m]):.4f}  "
                      f"ratio median={np.median(alff[m] / r[m]):.4f}")
            if ref_p:
                a = pd.read_table(ref_p[0]).iloc[0].astype(float)
                b = pd.Series(row).astype(float)
                m = a.notna() & b.notna()
                print(f"  parcel r={np.corrcoef(a[m], b[m])[0, 1]:.5f}  NaN XCP-D={a.isna().sum()} "
                      f"của mình={b.isna().sum()}  max |Δ|/ref={(abs(a[m] - b[m]) / a[m]).max():.4f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--compare" in sys.argv)
