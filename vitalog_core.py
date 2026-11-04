"""VITALOG: 기록 검증·집계·CSV 보관·인쇄용 요약. API 호출 없음."""
import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from statistics import median
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

KST = timezone(timedelta(hours=9))
CONTEXTS = ["공복(8시간 이상)", "식전", "식후", "취침 전", "기타"]
METHODS = ["손끝 채혈", "CGM", "검사실 혈장검사"]
COLUMNS = ["record_id", "measured_at", "item", "value", "unit", "context", "minutes_after_meal", "method", "note_json"]

def decimal(value):
    try: result = Decimal(str(value))
    except InvalidOperation: raise ValueError("올바른 숫자를 입력하세요.") from None
    if not result.is_finite() or result <= 0: raise ValueError("수치는 0보다 큰 유한한 숫자여야 합니다.")
    return result

def normalized(record):
    value = decimal(record["value"])
    return value * 18 if record["unit"] == "mmol/L" else value

def make_record(at, item, value, unit, context, method, note="", minutes=None, record_id=None):
    try:
        dt = datetime.fromisoformat(str(at))
        rid = str(UUID(str(record_id))) if record_id else str(uuid4())
    except (ValueError, TypeError): raise ValueError("날짜·시간 또는 기록 ID 형식이 올바르지 않습니다.") from None
    if dt.tzinfo is None: raise ValueError("측정 시각에 시간대(+09:00)가 필요합니다.")
    dt = dt.astimezone(KST)
    if dt > datetime.now(KST) + timedelta(minutes=5): raise ValueError("미래의 측정 시각은 기록할 수 없습니다.")
    v = decimal(value)
    if item not in ("혈당", "HbA1c"): raise ValueError("혈당 또는 HbA1c 기록만 지원합니다.")
    if not isinstance(note, str) or len(note) > 500: raise ValueError("메모는 500자 이내여야 합니다.")
    if item == "혈당":
        if unit not in ("mg/dL", "mmol/L") or context not in CONTEXTS or method not in METHODS:
            raise ValueError("혈당의 단위·측정 조건·방법을 확인하세요.")
        mg = v * 18 if unit == "mmol/L" else v
        if mg > 2000: raise ValueError("입력값 또는 혈당 단위를 확인하세요. 이 실습은 2000 mg/dL 이하의 숫자를 지원합니다.")
        if context == "식후":
            try:
                mins = Decimal(str(minutes))
                if not mins.is_finite() or mins != mins.to_integral_value() or not 1 <= mins <= 480: raise ValueError
                minutes = int(mins)
            except (InvalidOperation, TypeError, ValueError): raise ValueError("식후 기록에는 식후 경과 시간(1~480분)을 입력하세요.") from None
        else: minutes = None
    else:
        if unit != "%" or context != "검사실" or method != "검사실": raise ValueError("HbA1c는 검사실 측정값(%)으로 기록하세요.")
        if v > 30: raise ValueError("HbA1c의 수치와 단위(%)를 확인하세요.")
        minutes = None
    return dict(record_id=rid, measured_at=dt.isoformat(timespec="seconds"), item=item, value=str(v),
                unit=unit, context=context, minutes_after_meal=minutes, method=method, note=note)

def export_csv(records):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    for r in records:
        row = {k: r.get(k, "") for k in COLUMNS}
        row["note_json"] = json.dumps(r["note"], ensure_ascii=False)  # 수식 실행 방지 + 원문 복원
        writer.writerow(row)
    return stream.getvalue().encode("utf-8-sig")

def import_csv(data):
    if len(data) > 2_000_000: raise ValueError("CSV는 2MB 이하로 올려 주세요.")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        if reader.fieldnames != COLUMNS: raise ValueError("VITALOG에서 저장한 CSV 양식을 사용하세요.")
        rows = []
        for index, r in enumerate(reader, 2):
            if index > 5001: raise ValueError("한 번에 5000개 이하의 기록을 불러올 수 있습니다.")
            try:
                if None in r or not r["record_id"]: raise ValueError("Invalid row")
                note = json.loads(r["note_json"])
                rows.append(make_record(r["measured_at"], r["item"], r["value"], r["unit"], r["context"],
                    r["method"], note, r["minutes_after_meal"] or None, r["record_id"]))
            except (ValueError, KeyError, TypeError): raise ValueError(f"CSV {index}행의 날짜·수치·단위·조건·메모를 확인하세요.") from None
        return rows
    except (UnicodeError, csv.Error): raise ValueError("UTF-8 형식의 VITALOG CSV 파일을 확인하세요.") from None

def merge_records(existing, incoming):
    merged = {r["record_id"]: r for r in existing}
    added = duplicate = 0
    for r in incoming:
        old = merged.get(r["record_id"])
        if old is not None:
            if old != r: raise ValueError("같은 기록 ID에 다른 내용이 있습니다. 원본 파일을 확인하세요.")
            duplicate += 1
        else: merged[r["record_id"]] = r; added += 1
    return sorted(merged.values(), key=lambda r: (r["measured_at"], r["record_id"])), added, duplicate

def select_period(records, start, end):
    return [r for r in records if start <= datetime.fromisoformat(r["measured_at"]).astimezone(KST).date() <= end]

def group_label(r):
    condition = r["context"] + (f" {r['minutes_after_meal']}분" if r["context"] == "식후" else "")
    return condition + " · " + r["method"]

def unit_stats(records, unit="mg/dL"):
    if unit not in ("mg/dL", "mmol/L"): raise ValueError("지원하지 않는 혈당 단위입니다.")
    groups = defaultdict(list)
    for r in records:
        if r["item"] == "혈당": groups[group_label(r)].append(r)
    stats = []
    for label, rows in sorted(groups.items()):
        values = [normalized(r) / (18 if unit == "mmol/L" else 1) for r in rows]
        digits = 2 if unit == "mmol/L" else 1
        stats.append({"조건·방법": label, "측정 건수": len(rows), "기록 일수": len({r['measured_at'][:10] for r in rows}),
                      "평균": round(float(sum(values) / len(values)), digits), "중앙값": round(float(median(values)), digits),
                      "최솟값": round(float(min(values)), digits), "최댓값": round(float(max(values)), digits)})
    return stats

def summarize(records):
    a1c = sorted((r for r in records if r["item"] == "HbA1c"), key=lambda r: r["measured_at"])
    return {"전체 기록": len(records), "혈당 기록": sum(r["item"] == "혈당" for r in records),
            "기록 일수": len({r['measured_at'][:10] for r in records}), "혈당 집계_mg_dL": unit_stats(records),
            "HbA1c 기록": len(a1c), "최근 HbA1c": a1c[-1]["value"] if a1c else None,
            "최근 HbA1c 날짜": a1c[-1]["measured_at"][:10] if a1c else None}

def display_rows(records):
    return [{"측정 시각(KST)": r["measured_at"][:16].replace("T", " "), "항목": r["item"],
             "원래 수치": r["value"], "단위": r["unit"], "조건": r["context"], "식후 경과(분)": r["minutes_after_meal"],
             "방법": r["method"], "메모": r["note"]} for r in sorted(records, key=lambda r: r['measured_at'], reverse=True)]

def report_html(records, start, end, questions="", language="ko", glucose_unit="mg/dL"):
    if language not in ("ko", "en"): raise ValueError("한국어와 영어 보고서를 지원합니다.")
    english = language == "en"
    summary = summarize(records)
    def pick(ko, en): return en if english else ko
    terms = {"공복(8시간 이상)":"Fasting (at least 8 h)", "식전":"Before meal (fasting not confirmed)",
             "식후":"After meal", "취침 전":"Bedtime", "기타":"Other", "손끝 채혈":"Finger-stick meter",
             "검사실 혈장검사":"Laboratory plasma", "검사실":"Laboratory", "CGM":"CGM (interstitial)", "혈당":"Glucose"}
    def translated(text):
        if not english: return text
        for ko, en in terms.items(): text = text.replace(ko, en)
        return text.replace("분", " min")
    def table(headers, rows):
        return '<table><thead><tr>' + ''.join('<th>'+escape(str(h))+'</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>'+''.join('<td>'+escape(str(c if c is not None else ""))+'</td>' for c in row)+'</tr>' for row in rows) + '</tbody></table>'
    stats = unit_stats(records, glucose_unit)
    stat_headers = ["Condition / method", "Readings", "Days recorded", "Mean", "Median", "Minimum", "Maximum"] if english else (list(stats[0]) if stats else [])
    stat_rows = [[translated(r["조건·방법"]), *list(r.values())[1:]] for r in stats]
    stat_table = table(stat_headers, stat_rows) if stats else '<p>'+pick('혈당 기록 없음','No glucose readings')+'</p>'
    recent = display_rows(records)[:50]
    headers = ["Measured at (UTC+09:00)", "Item", "Original value", "Unit", "Context", "Minutes after meal", "Method", "Original note (not translated)"] if english else (list(recent[0]) if recent else [])
    details = []
    for r in recent:
        values = list(r.values())
        for i in (1,4,6): values[i] = translated(str(values[i]))
        details.append(values)
    detail = table(headers, details) if recent else ''
    a1c = (f"{summary['최근 HbA1c']}% ({summary['최근 HbA1c 날짜']})" if summary['최근 HbA1c'] else pick('기록 없음','Not recorded'))
    title = pick('진료 전 기록 요약','Pre-visit record summary')
    line = pick(f"전체 {summary['전체 기록']}건 · 기록한 날 {summary['기록 일수']}일 · 혈당 {summary['혈당 기록']}건 · HbA1c {summary['HbA1c 기록']}건",
                f"Total {summary['전체 기록']} records · {summary['기록 일수']} days recorded · {summary['혈당 기록']} glucose readings · {summary['HbA1c 기록']} HbA1c results")
    caveat = pick('평균은 입력된 측정값의 산술평균입니다. 24시간 평균·TIR·GMI를 뜻하지 않습니다. 미기록 시간의 상태나 변화의 원인은 판단하지 않습니다. mmol/L와 mg/dL는 근사계수 18로 환산합니다. 측정 방법과 조건, 식후 경과 시간을 나누어 집계합니다.',
                  'Means describe the entered readings only, not a 24-hour mean, TIR or GMI. Unrecorded periods and causes of change are not inferred. Glucose unit conversions use the approximate factor 18. Context, measurement method and minutes after a meal are grouped separately.')
    footer = pick('전체 원본은 VITALOG CSV로 별도 보관할 수 있습니다. 사용자가 입력하거나 불러온 참고 자료이며, 병원 확인을 받은 검사 성적표·진단·치료 지시가 아닙니다.',
                  'The complete original records can be stored separately as VITALOG CSV. This user-entered/imported reference is not a verified laboratory report, diagnosis or treatment instruction. Free-text notes and questions are preserved as entered, without automatic translation.')
    return f'''<!DOCTYPE html><html lang="{language}"><meta charset="UTF-8"><title>VITALOG - {title}</title>
<style>body{{max-width:1100px;margin:35px auto;padding:0 20px;color:#253044;font:14px/1.7 Arial,"Malgun Gothic",sans-serif}}h1{{margin:0;font-size:30px}}h2{{font-size:19px;margin-top:30px}}.muted{{color:#596579}}.card{{padding:15px;background:#f2eff7;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0}}th,td{{border:1px solid #d8dce5;text-align:left;padding:7px;overflow-wrap:anywhere}}th{{background:#f4f5f8}}.questions{{white-space:pre-wrap}}@media print{{body{{margin:0;max-width:none;padding:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}@page{{size:A4 landscape;margin:14mm}}}}</style>
<h1>VITALOG</h1><p class="muted">{title} · {escape(str(start))} ~ {escape(str(end))} · UTC+09:00 (KST)</p>
<div class="card">{line}<br>{pick('최근 HbA1c','Latest HbA1c')}: {escape(a1c)}</div>
<h2>{pick('조건·측정 방법별 혈당 요약','Glucose summary by context and method')} ({glucose_unit})</h2>{stat_table}
<p class="muted">{caveat}</p><h2>{pick('의료진에게 확인할 질문','Questions for the clinician')}</h2><div class="questions">{escape(questions or pick('직접 작성한 질문 없음','No questions entered'))}</div>
<h2>{pick('기록 상세 (최근 최대 50건)','Record details (up to 50 most recent records)')}</h2>{detail}
<p class="muted">{footer}<br>{pick('작성','Generated')}: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} UTC+09:00</p></html>'''

def demo_records():
    now = datetime.now(KST).replace(hour=8, minute=0, second=0, microsecond=0)
    rows = []
    for day in range(14, 0, -1):
        at = now - timedelta(days=day)
        for after in (False, True):
            value = 102 + day % 6 * 4 + (35 if after else 0)
            stamp = at + timedelta(hours=5) if after else at
            rid = str(uuid5(NAMESPACE_URL, 'vitalog-demo-' + stamp.isoformat()))
            rows.append(make_record(stamp.isoformat(), '혈당', value, 'mg/dL', '식후' if after else '공복(8시간 이상)',
                                    '손끝 채혈', '가상 예시 기록', 120 if after else None, rid))
    stamp = now - timedelta(days=10)
    rows.append(make_record(stamp.isoformat(), 'HbA1c', '6.1', '%', '검사실', '검사실', '가상 예시 검사', record_id=str(uuid5(NAMESPACE_URL,'vitalog-demo-a1c-'+stamp.isoformat()))))
    return sorted(rows, key=lambda r: r['measured_at'])
