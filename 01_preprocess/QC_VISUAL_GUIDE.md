# Hướng dẫn QC bằng mắt (MRIQC, sau đó fMRIPrep)

**Cập nhật 2026-11-26: KHÔNG xem bằng mắt báo cáo MRIQC** (MRIQC chỉ dùng tự động, như Rutherford et al. 2026); phần T1w/BOLD dưới đây giữ lại để tham khảo khi xem báo cáo fMRIPrep.

Chính sách đã chốt (2026-11-26): **chỉ loại dữ liệu thật sự không dùng được**. Khi phân vân thì GIỮ,
ghi `doubtful`, để fMRIPrep / XCP-D quyết định tiếp (FreeSurfer lỗi, < 4 phút sạch sau censor).
Dựa trên: Provins et al. 2023 (Front. Neuroimaging, QC protocol MRIQC + fMRIPrep), tài liệu MRIQC,
Rutherford et al. 2026 (pipeline ADNI).

Ghi quyết định vào `$WORK/selection/qc_visual.tsv` (tab): `participant_id  modality  decision  note`
với `modality` = T1w | bold, `decision` = keep | doubtful | exclude. Không xem nhãn nhóm khi review.

## Cách xem

- Khuyến nghị (không cần tải về): trên máy trạm
  `cd ~/thupnm-wp/adni_work/derivatives/mriqc && python3 -m http.server 8765 --bind 127.0.0.1`,
  trên laptop `ssh -N -L 8765:127.0.0.1:8765 <user>@<máy trạm>`, rồi mở `http://localhost:8765/_qc_review.html`.
- Hoặc tải `$WORK/selection/mriqc_review_27.tgz` (~475 MB, 27 subject outlier nặng), giải nén, mở `_qc_review.html`.
  Đây là hình ảnh dữ liệu ADNI: chỉ để trên máy của mình, không chia sẻ, xóa khi xong.
- Mỗi báo cáo: phần **Visual reports** (ảnh mosaic), **Extended reports** (nền ảnh), bảng IQM, và metadata.

## T1w — loại (exclude) khi

| Vấn đề | Nhìn ở đâu | Loại khi |
|---|---|---|
| Chuyển động: nhòe, vệt sóng (ringing) song song quanh vỏ não | zoomed mosaic | Không còn phân biệt được chất xám / chất trắng ở phần lớn não |
| Não bị cắt mất (FOV) | mosaic | Mất một phần lớn vỏ não hoặc tiểu não |
| Ghosting / wrap-around | mosaic + background | Bản sao chồng lên mô não |
| Artifact kim loại, mất tín hiệu | mosaic | Vùng mất tín hiệu lớn trong vỏ não |
| Không đồng nhất cường độ (INU) cực mạnh | mosaic | Một vùng não quá tối / sáng tới mức không thấy tương phản |
| Bất thường lớn (u, nhồi máu lớn, phẫu thuật) | mosaic | Tổn thương lớn làm sai giải phẫu (KHÔNG loại vì teo não, giãn não thất, tổn thương chất trắng: đó là bệnh) |

Giữ: nhiễu nhẹ, nhòe nhẹ, teo não (AD), nền có vệt nhẹ. `cjv` / `cnr` xấu nhưng ảnh nhìn ổn → keep.

## BOLD — loại (exclude) khi

| Vấn đề | Nhìn ở đâu | Loại khi |
|---|---|---|
| Phủ não thiếu | mean mosaic | Mất cả đỉnh não hoặc phần lớn tiểu não / thùy thái dương (mất nhẹ vùng trán ổ mắt / thái dương dưới là bình thường) |
| Ghosting / sọc lát cắt | mean + stdev mosaic | Bản sao rõ chồng lên não, hoặc sọc xen kẽ giữa các lát ở nhiều volume |
| Artifact trong stdev | stdev mosaic | Vòng / sọc / vùng sáng lớn không theo giải phẫu (mạch máu, rìa não, não thất sáng là bình thường) |
| Carpet plot hỏng | carpet + FD/DVARS | Phần lớn thời gian là vệt dọc (spike) hoặc cường độ trôi mạnh; nếu chỉ có vài spike → keep (XCP-D cắt) |
| Chuyển động | FD | KHÔNG loại vì FD ở bước này: XCP-D censor FD > 0.5 và loại khi còn < 4 phút |

`aor` / `aqi` cao thường do vài spike trong carpet plot → thường keep.

## fMRIPrep report (sau khi chạy) — loại khi

- FreeSurfer lỗi hoặc bề mặt sai rõ (bao cả màng cứng / mất thùy) ở bảng phân đoạn và bề mặt.
- Đăng ký BOLD → T1 sai rõ (viền chất trắng lệch hẳn ở hình coregistration).
- Đăng ký T1 → MNI sai rõ.
- Philips / Siemens không có PED: chạy không SDC là chấp nhận được, chỉ ghi nhận.
- Euler number: dùng để ưu tiên subject cần xem bề mặt; loại chỉ khi nhìn thấy bề mặt hỏng.
