"""Bổ sung SliceTiming (và sửa TR sai) cho BOLD thiếu SliceTiming, từ bảng NFQ của ADNI.

Cách dùng:  python3 01_preprocess/03c_slicetiming.py [--write]
  không --write: chỉ in kết quả đối chiếu; --write: ghi vào $WORK/bids (thay file, không sửa tại chỗ
  vì bids/ hard-link với raw/), bản JSON cũ lưu ở $WORK/audit/slicetiming_backup/, bảng tổng hợp
  $WORK/audit/slicetiming_fill.tsv.

Bảng (đặt ở $WORK/tables/, tải từ LONI, KHÔNG đưa lên git):
  MAYOADIRL_MRI_FMRI_NFQ_*.csv  (ADNIGO/2/3)   MRINFQ_*.csv  (ADNI4)
  SLICETIMING = giờ trong ngày (giây) của từng lát ở volume đầu → trừ giá trị nhỏ nhất.
Đối chiếu: cùng RID, cùng SeriesNumber (Philips ADNI4: JSON ghi 1401 = bảng 14), giờ chụp lệch < 120 s
  nếu JSON có AcquisitionTime, số giá trị = số lát của NIfTI, max < TR.
Không có dòng khớp duy nhất:
  - Philips đơn lát: quy luật protocol thấy trong bảng (lát chẵn trước rồi lẻ, bước TR/n; đúng 98% của
    1007 dòng Philips 48 lát TR 3 s). Nhiều dòng khớp nhưng cùng giá trị → dùng giá trị đó.
  - Siemens: interleaved chuẩn Siemens (n lẻ bắt đầu lát 0, n chẵn bắt đầu lát 1), như 135 subject
    Siemens 48 lát có SliceTiming trong dữ liệu.
  - Philips multiband (ADNI4, ParallelReductionFactorOutOfPlane > 1): KHÔNG điền. Bảng ghi n thời điểm
    khác nhau như đơn lát (sai với multiband) → để trống, fMRIPrep tự bỏ STC cho các run này.
Sửa TR: JSON ghi 6.02158 s cho 4 run ADNI2 Philips (140 vol) trong khi bảng và protocol là 3 s
  → sửa RepetitionTime trong JSON và pixdim[4] trong NIfTI.
"""
import csv, glob, json, os, shutil, sys, collections
import nibabel as nb

W = '/home/thupnm/thupnm-wp/adni_work'
BIDS, AUD = f'{W}/bids', f'{W}/audit'
WRITE = '--write' in sys.argv


def sec(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)


def norm(st):
    try: v = [float(x) for x in st.split('_')]
    except ValueError: return None
    m = min(v); return [round(x - m, 6) for x in v]


def philips_rule(n, tr):
    order = list(range(0, n, 2)) + list(range(1, n, 2)); t = [0.0] * n
    for k, i in enumerate(order): t[i] = round(k * tr / n, 6)
    return t


def siemens_rule(n, tr):
    order = (list(range(0, n, 2)) + list(range(1, n, 2))) if n % 2 else (list(range(1, n, 2)) + list(range(0, n, 2)))
    t = [0.0] * n
    for k, i in enumerate(order): t[i] = round(k * tr / n, 6)
    return t


rows = collections.defaultdict(list)
for f in glob.glob(f'{W}/tables/MAYOADIRL_MRI_FMRI_NFQ_*.csv'):
    for r in csv.DictReader(open(f)):
        rows[r['RID']].append(dict(t='MAYOADIRL', date=r['SCANDATE'], time=r['SERIESTIME'], sn=r['SERIESNUMBER'],
                                   tr=float(r['REPETITIONTIME'] or 0) / 1000, st=norm(r['SLICETIMING'] or 'x')))
for f in glob.glob(f'{W}/tables/MRINFQ_*.csv'):
    for r in csv.DictReader(open(f)):
        rows[r['RID']].append(dict(t='MRINFQ', date=r['StudyDate'], time=r['SeriesTime'], sn=r['SeriesNumber'],
                                   tr=float(r['RepetitionTime'] or 0) / 1000, st=norm(r['SliceTiming'] or 'x')))

subs = [l.strip() for l in open(f'{W}/selection/subjects_fmriprep.txt') if l.strip()]
res = []
for s in subs:
    for j in sorted(glob.glob(f'{BIDS}/{s}/func/*_bold.json')):
        d = json.load(open(j))
        if 'SliceTiming' in d: continue
        nii = j.replace('.json', '.nii.gz'); n = nb.load(nii).shape[2]
        tr = float(d['RepetitionTime']); sn = d.get('SeriesNumber'); at = d.get('AcquisitionTime'); man = d['Manufacturer']
        mb = (d.get('ParallelReductionFactorOutOfPlane') or d.get('MultibandAccelerationFactor') or 1) > 1
        c = [r for r in rows.get(str(int(s[4:])), []) if r['st'] and len(r['st']) == n
             and (r['sn'] == str(sn) or (sn and sn >= 100 and r['sn'] == str(sn // 100)))]
        if at: c = [r for r in c if abs(sec(r['time']) - sec(at)) < 120]
        tr_new, st = tr, None
        if c and abs(c[0]['tr'] - tr) > 0.05 and all(abs(r['tr'] - c[0]['tr']) < 0.05 for r in c):
            tr_new = c[0]['tr']
        if mb and man == 'Philips':
            kind, src = 'none', 'Philips multiband: bảng ghi như đơn lát, không dùng'
        elif c and all(r['st'] == c[0]['st'] for r in c) and max(c[0]['st']) < tr_new:
            kind, st = 'table', c[0]['st']
            src = '; '.join(f"{r['t']} {r['date']} {r['time']} SN{r['sn']}" for r in c[:3])
        elif man == 'Philips':
            kind, st, src = 'inferred', philips_rule(n, tr_new), f'Philips protocol rule ({len(c)} dòng bảng)'
        else:
            kind, st, src = 'inferred', siemens_rule(n, tr_new), f'Siemens interleaved rule ({len(c)} dòng bảng)'
        res.append(dict(sub=s, file=os.path.relpath(j, BIDS), manufacturer=man, n_slices=n, multiband=mb,
                        tr_json=tr, tr_new=tr_new, kind=kind, source=src, st=st))

print(collections.Counter((r['manufacturer'], r['kind']) for r in res))
for r in res:
    if r['kind'] != 'table' or r['tr_new'] != r['tr_json']:
        print(r['file'], r['n_slices'], r['tr_json'], '->', r['tr_new'], r['kind'], r['source'])

if WRITE:
    os.makedirs(f'{AUD}/slicetiming_backup', exist_ok=True)
    for r in res:
        j = f"{BIDS}/{r['file']}"
        shutil.copy2(j, f"{AUD}/slicetiming_backup/{os.path.basename(j)}")
        d = json.load(open(j))
        if r['st']:
            d['SliceTiming'] = r['st']
            d['SliceTimingSource'] = f"{r['kind']}: {r['source']} (03c_slicetiming.py)"
        if r['tr_new'] != r['tr_json']:
            d['RepetitionTime'] = r['tr_new']
            d['RepetitionTimeNote'] = f"sửa từ {r['tr_json']} theo bảng NFQ/protocol ADNI2 (03c_slicetiming.py)"
            nii = j.replace('.json', '.nii.gz'); img = nb.load(nii)
            hdr = img.header.copy(); hdr['pixdim'][4] = r['tr_new']; hdr.set_xyzt_units('mm', 'sec')
            tmp = nii + '.tmp.nii.gz'
            nb.Nifti1Image(img.dataobj, img.affine, hdr).to_filename(tmp); os.replace(tmp, nii)
        tmp = j + '.tmp'; json.dump(d, open(tmp, 'w'), indent=2); os.replace(tmp, j)   # thay file → bỏ hard link
    with open(f'{AUD}/slicetiming_fill.tsv', 'w') as f:
        f.write('sub\tfile\tmanufacturer\tn_slices\tmultiband\ttr_json\ttr_new\tkind\tsource\n')
        for r in res:
            f.write('\t'.join(str(r[k]) for k in ['sub', 'file', 'manufacturer', 'n_slices', 'multiband', 'tr_json', 'tr_new', 'kind', 'source']) + '\n')
    print('Đã ghi', len(res), 'file JSON')
