import os
import io
import json
import base64
import html
from uuid import uuid4
from datetime import datetime, date, time, timedelta, timezone
from statistics import mean
from pathlib import Path

import pandas as pd
import altair as alt
import streamlit as st

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

# =========================================================
# 기본 설정
# =========================================================
KST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="GlucoBridge",
    page_icon="💗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# 유틸
# =========================================================
def now_kst():
    return datetime.now(KST)

def T(ko: str, en: str) -> str:
    return en if st.session_state.get("language", "한국어") == "English" else ko

def tr_context(value: str) -> str:
    mapping = {
        "공복(8시간 이상)": "Fasting (8+ hours)",
        "식전": "Before meal",
        "식후": "After meal",
        "취침 전": "Before bed",
        "기타": "Other",
        "검사실": "Laboratory",
    }
    return mapping.get(value, value)

def tr_method(value: str) -> str:
    mapping = {
        "손끝 채혈": "Finger-stick",
        "CGM": "CGM",
        "검사실 혈장검사": "Laboratory plasma",
        "검사실": "Laboratory",
    }
    return mapping.get(value, value)

def load_mascot_base64() -> str:
    candidates = [
        Path("assets/mascot.png"),
        Path("mascot.png"),
    ]
    for path in candidates:
        if path.exists():
            return base64.b64encode(path.read_bytes()).decode("utf-8")
    return ""

def parse_date_text(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except Exception:
        raise ValueError("날짜는 YYYY-MM-DD 형식으로 입력하세요.")

def parse_time_text(text: str) -> time:
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except Exception:
        raise ValueError("시간은 HH:MM 형식으로 입력하세요.")

def glucose_to_mgdl(value: float, unit: str) -> float:
    if unit == "mg/dL":
        return float(value)
    if unit == "mmol/L":
        return float(value) * 18.0
    return float(value)

def glucose_from_mgdl(value_mgdl: float, unit: str) -> float:
    if unit == "mg/dL":
        return float(value_mgdl)
    if unit == "mmol/L":
        return float(value_mgdl) / 18.0
    return float(value_mgdl)

def make_record(
    day_text: str,
    clock_text: str,
    item: str,
    value: float,
    input_unit: str,
    context: str,
    method: str,
    minutes_after_meal,
    note: str,
):
    day = parse_date_text(day_text)
    clock = parse_time_text(clock_text)
    measured_at = datetime.combine(day, clock).isoformat(timespec="minutes")

    if item == "혈당":
        stored_value = round(glucose_to_mgdl(value, input_unit), 2)
        stored_unit = "mg/dL"
    else:
        stored_value = round(float(value), 2)
        stored_unit = "%"

    return {
        "record_id": str(uuid4()),
        "measured_at": measured_at,
        "item": item,
        "value": stored_value,
        "unit": stored_unit,
        "context": context,
        "method": method,
        "minutes_after_meal": int(minutes_after_meal) if minutes_after_meal not in [None, ""] else None,
        "note": note.strip(),
    }

def get_glucose_display_value(record: dict, unit: str) -> float:
    return round(glucose_from_mgdl(record["value"], unit), 2)

def group_label(record: dict) -> str:
    if record["item"] == "HbA1c":
        return "HbA1c"
    if record["context"] == "식후" and record.get("minutes_after_meal"):
        return f"식후 ({record['minutes_after_meal']}분)"
    return record["context"]

def rows_for_table(records: list[dict], unit: str) -> pd.DataFrame:
    rows = []
    ordered = sorted(records, key=lambda r: r["measured_at"], reverse=True)
    for r in ordered:
        if r["item"] == "혈당":
            display_value = get_glucose_display_value(r, unit)
            display_unit = unit
        else:
            display_value = r["value"]
            display_unit = "%"
        rows.append({
            T("날짜", "Date"): r["measured_at"][:10],
            T("시간", "Time"): r["measured_at"][11:16],
            T("항목", "Item"): "Glucose" if (st.session_state.language == "English" and r["item"] == "혈당") else r["item"],
            T("값", "Value"): display_value,
            T("단위", "Unit"): display_unit,
            T("상황", "Context"): tr_context(r["context"]) if st.session_state.language == "English" else r["context"],
            T("방법", "Method"): tr_method(r["method"]) if st.session_state.language == "English" else r["method"],
            T("메모", "Note"): r["note"],
        })
    return pd.DataFrame(rows)

def stats_by_context(records: list[dict], unit: str) -> list[dict]:
    glucose_records = [r for r in records if r["item"] == "혈당"]
    grouped = {}

    for r in glucose_records:
        key = group_label(r)
        grouped.setdefault(key, []).append(get_glucose_display_value(r, unit))

    result = []
    for key, values in grouped.items():
        result.append({
            "context": key,
            "count": len(values),
            "avg": round(mean(values), 1),
            "min": round(min(values), 1),
            "max": round(max(values), 1),
        })

    return sorted(result, key=lambda x: x["count"], reverse=True)

def stats_df_for_display(records: list[dict], unit: str) -> pd.DataFrame:
    raw = stats_by_context(records, unit)
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    if st.session_state.language == "English":
        df["context"] = df["context"].apply(lambda x: tr_context(x.replace("식후 (", "식후")))
        return df.rename(columns={
            "context": "Context",
            "count": "Count",
            "avg": f"Average ({unit})",
            "min": f"Min ({unit})",
            "max": f"Max ({unit})",
        })
    else:
        return df.rename(columns={
            "context": "조건",
            "count": "건수",
            "avg": f"평균 ({unit})",
            "min": f"최소 ({unit})",
            "max": f"최대 ({unit})",
        })

def select_records(records: list[dict], period: str, begin_text: str = "", end_text: str = ""):
    if not records:
        today = now_kst().date()
        return [], today, today

    all_dates = [datetime.fromisoformat(r["measured_at"]).date() for r in records]
    min_day = min(all_dates)
    max_day = max(all_dates)

    if period == "7일":
        start = max_day - timedelta(days=6)
        end = max_day
    elif period == "30일":
        start = max_day - timedelta(days=29)
        end = max_day
    elif period == "전체":
        start = min_day
        end = max_day
    else:
        start = parse_date_text(begin_text)
        end = parse_date_text(end_text)
        if start > end:
            raise ValueError("시작일이 종료일보다 늦을 수 없어요.")

    selected = []
    for r in records:
        d = datetime.fromisoformat(r["measured_at"]).date()
        if start <= d <= end:
            selected.append(r)
    return selected, start, end

def export_csv(records: list[dict]) -> bytes:
    df = pd.DataFrame(records)
    return df.to_csv(index=False).encode("utf-8-sig")

def import_csv(uploaded_file):
    df = pd.read_csv(uploaded_file)
    required = [
        "record_id", "measured_at", "item", "value", "unit",
        "context", "method", "minutes_after_meal", "note"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV에 필요한 컬럼이 없어요: {', '.join(missing)}")

    records = []
    for _, row in df.iterrows():
        records.append({
            "record_id": str(row["record_id"]),
            "measured_at": str(row["measured_at"]),
            "item": str(row["item"]),
            "value": float(row["value"]),
            "unit": str(row["unit"]),
            "context": str(row["context"]),
            "method": str(row["method"]),
            "minutes_after_meal": None if pd.isna(row["minutes_after_meal"]) else int(row["minutes_after_meal"]),
            "note": "" if pd.isna(row["note"]) else str(row["note"]),
        })
    return records

def demo_data() -> list[dict]:
    today = now_kst().date()
    result = []

    for days_ago in range(14, 0, -1):
        day = today - timedelta(days=days_ago)
        fasting = 92 + (days_ago % 5) * 4
        post_meal = 126 + (days_ago % 6) * 7

        result.append(make_record(
            day.isoformat(), "08:00", "혈당", fasting, "mg/dL",
            "공복(8시간 이상)", "손끝 채혈", None, "가상 데이터"
        ))
        result.append(make_record(
            day.isoformat(), "13:00", "혈당", post_meal, "mg/dL",
            "식후", "손끝 채혈", 120, "가상 데이터"
        ))

    result.append(make_record(
        (today - timedelta(days=10)).isoformat(), "09:10", "HbA1c", 6.1, "%",
        "검사실", "검사실", None, "가상 데이터"
    ))
    return result

def build_report_html(records: list[dict], start: date, end: date, language: str, unit: str, questions: str, ai_text: str):
    original_lang = st.session_state.language
    st.session_state.language = language

    title = "GlucoBridge Visit Summary" if language == "English" else "GlucoBridge 진료 준비 리포트"
    subtitle = (
        f"Period: {start} ~ {end}"
        if language == "English"
        else f"기간: {start} ~ {end}"
    )

    stats_df = stats_df_for_display(records, unit)
    records_df = rows_for_table(records, unit).head(50)

    table_html = stats_df.to_html(index=False, border=0) if not stats_df.empty else "<p>No data</p>"
    detail_html = records_df.to_html(index=False, border=0)

    q_title = "Questions for clinician" if language == "English" else "의료진에게 확인할 질문"
    ai_title = "AI reference note" if language == "English" else "AI 참고 설명"
    detail_title = "Latest entries" if language == "English" else "최근 기록"

    report = f"""
    <html>
    <head>
      <meta charset="utf-8">
      <title>{title}</title>
      <style>
        body {{
          font-family: Arial, sans-serif;
          padding: 32px;
          color: #24365f;
          line-height: 1.6;
        }}
        h1 {{ margin-bottom: 8px; }}
        h2 {{
          margin-top: 28px;
          padding-bottom: 8px;
          border-bottom: 1px solid #dde5f2;
        }}
        .badge {{
          display: inline-block;
          padding: 6px 10px;
          border-radius: 999px;
          background: #eef4ff;
          color: #4d63bd;
          font-size: 12px;
          font-weight: bold;
        }}
        table {{
          width: 100%;
          border-collapse: collapse;
          margin-top: 12px;
        }}
        th, td {{
          border: 1px solid #dde5f2;
          padding: 8px 10px;
          text-align: left;
          font-size: 13px;
        }}
        th {{
          background: #f6f8fd;
        }}
        .box {{
          background: #f9fbff;
          border: 1px solid #dde5f2;
          border-radius: 12px;
          padding: 16px;
          margin-top: 12px;
        }}
      </style>
    </head>
    <body>
      <span class="badge">GlucoBridge</span>
      <h1>{title}</h1>
      <p>{subtitle}</p>

      <h2>{"Summary statistics" if language == "English" else "요약 통계"}</h2>
      {table_html}

      <h2>{detail_title}</h2>
      {detail_html}

      <h2>{q_title}</h2>
      <div class="box">{html.escape(questions).replace(chr(10), "<br>") if questions.strip() else ("None" if language == "English" else "없음")}</div>

      <h2>{ai_title}</h2>
      <div class="box">{html.escape(ai_text).replace(chr(10), "<br>") if ai_text.strip() else ("Not included" if language == "English" else "포함하지 않음")}</div>

      <p style="margin-top:32px; color:#6a7c99; font-size:12px;">
      {"User-generated reference only. Not automatically sent to any clinic." if language == "English" else "사용자 참고용 리포트이며 병원으로 자동 전송되지 않습니다."}
      </p>
    </body>
    </html>
    """
    st.session_state.language = original_lang
    return report

def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:
        return os.environ.get(name, default)

AI_SYSTEM_PROMPT = """
You explain self-recorded glucose and HbA1c logs for education only.
Do not diagnose, do not prescribe, and do not claim clinical certainty.
Use only the statistics and counts provided.
Do not infer continuous glucose monitoring metrics such as TIR, GMI, or 24-hour averages.
Keep the answer practical and easy to understand.
Suggest neutral questions the user can ask a clinician.
"""

def ask_gemini(records: list[dict], start: date, end: date, question: str, output_language: str):
    if genai is None or types is None:
        raise RuntimeError("google-genai 라이브러리를 불러올 수 없습니다.")

    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 없습니다.")

    model_name = get_secret("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)

    payload = {
        "period": [str(start), str(end)],
        "total_entries": len(records),
        "glucose_statistics_mg_dL": stats_by_context(records, "mg/dL"),
        "hba1c_entries": sum(1 for r in records if r["item"] == "HbA1c"),
        "question": question,
        "output_language": output_language,
    }

    response = client.models.generate_content(
        model=model_name,
        contents=json.dumps(payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=AI_SYSTEM_PROMPT,
            temperature=0.25,
        ),
    )

    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise RuntimeError("AI 응답이 비어 있습니다.")
    return text.strip()

def period_picker(key_prefix: str):
    choices = ["7일", "30일", "전체", "직접 입력"]
    choice = st.selectbox(
        T("분석 기간", "Analysis period"),
        choices,
        index=1,
        key=f"{key_prefix}_period",
        format_func=lambda x: {
            "7일": "7 days",
            "30일": "30 days",
            "전체": "All",
            "직접 입력": "Custom",
        }[x] if st.session_state.language == "English" else x,
    )

    begin = ""
    end = ""

    if choice == "직접 입력":
        c1, c2 = st.columns(2)
        begin = c1.text_input(
            T("시작일 (YYYY-MM-DD)", "Start (YYYY-MM-DD)"),
            value=str(now_kst().date() - timedelta(days=29)),
            key=f"{key_prefix}_begin"
        )
        end = c2.text_input(
            T("종료일 (YYYY-MM-DD)", "End (YYYY-MM-DD)"),
            value=str(now_kst().date()),
            key=f"{key_prefix}_end"
        )

    try:
        return select_records(st.session_state.records, choice, begin, end)
    except ValueError as e:
        st.warning(str(e))
        return [], now_kst().date(), now_kst().date()

def analytics_point_df(records: list[dict], unit: str) -> pd.DataFrame:
    rows = []
    for r in records:
        if r["item"] != "혈당":
            continue
        rows.append({
            "time": r["measured_at"],
            "date": r["measured_at"][:10],
            "value": get_glucose_display_value(r, unit),
            "context": tr_context(r["context"]) if st.session_state.language == "English" else r["context"],
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        df["date"] = pd.to_datetime(df["date"])
    return df

def render_message_html(posts: list[dict], category: str):
    blocks = []
    for idx, post in enumerate(posts):
        if category != "전체" and post["cat"] != category:
            continue

        mine = (idx % 2 == 1)
        who = "mine" if mine else ""
        avatar = "🧃" if post["cat"] == "식단" else ("🚶" if post["cat"] == "운동" else "🌿")
        cat_text = {
            "식단": "Food",
            "운동": "Activity",
            "생활습관": "Habits",
        }.get(post["cat"], post["cat"]) if st.session_state.language == "English" else post["cat"]

        title = post["en"] if st.session_state.language == "English" else post["title"]
        body = post["body_en"] if st.session_state.language == "English" else post["body"]

        left_avatar = "" if mine else f'<div class="gb-avatar">{avatar}</div>'
        right_avatar = '<div class="gb-avatar">💬</div>' if mine else ""

        block = f"""
        <div class="gb-message-row {who}">
          {left_avatar}
          <div class="gb-bubble {who}">
            <small>{cat_text}{" · DEMO" if post.get("demo") else ""}</small>
            <h4>{html.escape(title)}</h4>
            <div>{html.escape(body).replace(chr(10), "<br>")}</div>
          </div>
          {right_avatar}
        </div>
        """
        blocks.append(block)
    return "".join(blocks)

# =========================================================
# 세션 초기화
# =========================================================
def init_state():
    defaults = {
        "language": "한국어",
        "mode": "diabetes",
        "unit": "mg/dL",
        "menu": 0,
        "records": [],
        "ai_messages": [],
        "ai_last": None,
        "liked": set(),
        "community": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if not st.session_state.community:
        st.session_state.community = [
            {
                "id": "sample1",
                "cat": "운동",
                "title": "오늘도 가볍게 걷기",
                "en": "A gentle daily walk",
                "body": "일정표에 산책 시간을 체크하는 습관을 만들고 있어요.",
                "body_en": "I keep a small walking routine in my schedule every day.",
                "likes": 5,
                "comments": [],
                "demo": True,
            },
            {
                "id": "sample2",
                "cat": "식단",
                "title": "간편한 한 접시 식단",
                "en": "Easy balanced plate ideas",
                "body": "채소와 단백질 식품을 미리 준비했더니 식사 구성이 훨씬 편해졌어요.",
                "body_en": "Preparing vegetables and protein ahead of time made my meals much easier.",
                "likes": 7,
                "comments": [],
                "demo": True,
            },
        ]

init_state()
MASCOT_B64 = load_mascot_base64()

# =========================================================
# 스타일
# =========================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
  font-family: 'DM Sans', 'Noto Sans KR', sans-serif;
}
.stApp {
  background:
    radial-gradient(circle at 100% 0%, #e9fbf5 0, transparent 34%),
    #f6f8fd;
  color: #1f2f54;
}
.block-container {
  max-width: 1480px;
  padding-top: 2rem;
  padding-bottom: 4rem;
}
header[data-testid="stHeader"] {
  background: transparent;
}
.gb-logo {
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -1px;
  color: #22365a;
  margin-bottom: 4px;
}
.gb-logo b {
  color: #5266ee;
}
.gb-caption {
  font-size: 13px;
  color: #7587a4;
  letter-spacing: .06em;
}
.st-key-hero {
  border: 1px solid #dce6fa;
  background: linear-gradient(110deg, #eff4ff 0%, #f7fbff 56%, #f1fffb 100%);
  border-radius: 34px;
  padding: 28px 34px !important;
  box-shadow: 0 14px 38px rgba(69, 102, 181, 0.10);
  margin: 16px 0 24px;
}
.gb-mascot {
  width: 100%;
  max-width: 290px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gb-mascot img {
  width: 100%;
  height: auto;
  max-height: 290px;
  object-fit: contain;
  filter: drop-shadow(0 20px 24px rgba(68, 100, 170, 0.16));
}
.gb-pill {
  display: inline-block;
  border: 1px solid #bacaf8;
  background: rgba(255,255,255,.88);
  color: #4962bd;
  border-radius: 999px;
  padding: 8px 13px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .07em;
}
.gb-hero-title {
  font-size: clamp(31px, 3vw, 48px);
  font-weight: 800;
  color: #233971;
  line-height: 1.22;
  letter-spacing: -1.6px;
  margin: 14px 0 10px;
}
.gb-hero-sub {
  font-size: 16px;
  color: #587091;
  line-height: 1.85;
  margin: 0;
}
.gb-hero-badges {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 18px;
}
.gb-hero-badge {
  font-size: 13px;
  font-weight: 700;
  color: #3f5ca8;
  background: #fff;
  border: 1px solid #d9e4fb;
  padding: 8px 12px;
  border-radius: 999px;
}
.gb-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 26px;
}
.gb-kpi {
  background: #fff;
  border: 1px solid #dfe7f2;
  border-radius: 22px;
  padding: 20px 22px;
  min-height: 116px;
  box-shadow: 0 7px 22px rgba(81, 107, 153, 0.06);
}
.gb-kpi-label {
  font-size: 14px;
  color: #6e7f9b;
  font-weight: 700;
}
.gb-kpi-value {
  font-size: 31px;
  font-weight: 800;
  color: #24365f;
  margin-top: 10px;
}
.st-key-menu {
  border: 1px solid #dfe7f2;
  background: #fff;
  border-radius: 20px;
  padding: 12px !important;
  margin: 10px 0 24px;
}
.st-key-menu button {
  height: 58px !important;
  font-size: 15px !important;
}
.stButton button,
.stDownloadButton button {
  border-radius: 14px !important;
  min-height: 46px;
  font-weight: 700;
}
.stButton button[kind="primary"],
.stDownloadButton button[kind="primary"] {
  background: linear-gradient(110deg, #5368f0, #667ff5) !important;
  color: #fff !important;
  border: 0 !important;
  box-shadow: 0 8px 18px rgba(96, 115, 238, 0.18);
}
.st-key-entry_card,
.st-key-aside_card {
  border: 1px solid #dfe7f2;
  border-radius: 24px;
  background: #fff;
  padding: 25px 28px !important;
  box-shadow: 0 9px 29px rgba(60, 96, 154, 0.06);
}
.st-key-aside_card {
  background: linear-gradient(145deg, #edf3ff, #ecfcf6);
}
.gb-card-title {
  font-size: 20px;
  font-weight: 800;
  color: #223760;
  margin-bottom: 14px;
}
.gb-note {
  font-size: 14px;
  color: #617492;
  line-height: 1.9;
}
.gb-section {
  margin: 30px 0 16px;
}
.gb-section h2 {
  margin: 0;
  font-size: 27px;
  font-weight: 800;
  color: #21355d;
  letter-spacing: -.8px;
}
.gb-section p {
  margin: 7px 0 0;
  font-size: 14px;
  color: #697b98;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 22px !important;
  border-color: #dfe7f2 !important;
  background: #fff !important;
}
[data-testid="stMetric"] {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #dfe7f2;
  background: #fff;
}
[data-testid="stMetricValue"] {
  font-size: 28px;
  color: #21375e;
}
[data-baseweb="select"] > div,
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div {
  background: #f7f9fe;
  border-radius: 12px !important;
}
.gb-analytics-grid {
  display: grid;
  grid-template-columns: 1.2fr .8fr;
  gap: 16px;
  margin-bottom: 12px;
}
.gb-mini-card {
  background: linear-gradient(135deg, #fff, #f9fbff);
  border: 1px solid #dfe7f2;
  border-radius: 20px;
  padding: 18px 20px;
}
.gb-mini-title {
  font-size: 13px;
  color: #6b7d99;
  font-weight: 700;
  margin-bottom: 6px;
}
.gb-mini-value {
  font-size: 28px;
  font-weight: 800;
  color: #22385f;
}
.gb-mini-copy {
  font-size: 13px;
  color: #7587a5;
  line-height: 1.7;
}
.gb-community-board {
  background: linear-gradient(180deg, #fbfdff, #ffffff);
  border: 1px solid #dfe7f2;
  border-radius: 26px;
  padding: 18px;
}
.gb-message-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.gb-message-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
}
.gb-message-row.mine {
  justify-content: flex-end;
}
.gb-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: linear-gradient(135deg, #dde6ff, #ecfffa);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  border: 1px solid #d6e1f8;
}
.gb-bubble {
  max-width: 78%;
  padding: 14px 16px;
  border-radius: 22px;
  font-size: 15px;
  line-height: 1.7;
  border: 1px solid #e0e8f4;
  background: #fff;
  color: #273b61;
  box-shadow: 0 8px 20px rgba(71, 100, 167, 0.05);
}
.gb-bubble.mine {
  background: linear-gradient(135deg, #586ef0, #7a86f9);
  color: #fff;
  border: none;
}
.gb-bubble small {
  display: block;
  font-size: 11px;
  opacity: .78;
  margin-bottom: 6px;
  font-weight: 700;
}
.gb-bubble h4 {
  margin: 4px 0 6px;
  font-size: 16px;
}
.gb-compose-note {
  font-size: 12px;
  color: #7888a4;
  line-height: 1.6;
  margin-top: 10px;
}
.gb-footer {
  color: #8190a6;
  font-size: 12px;
  border-top: 1px solid #e5ebf5;
  padding-top: 20px;
  margin-top: 35px;
  line-height: 1.7;
}
@media (max-width: 920px) {
  .gb-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .gb-analytics-grid {
    grid-template-columns: 1fr;
  }
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 헤더
# =========================================================
header_left, header_right = st.columns([1.35, 1.3], gap="large")
with header_left:
    st.markdown(
        '<div class="gb-logo">Gluco<b>Bridge</b> ♡</div><div class="gb-caption">HEALTH DATA, MADE HUMAN</div>',
        unsafe_allow_html=True,
    )

with header_right:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.selectbox(
            "Mode / 사용자",
            ["diabetes", "wellness"],
            key="mode",
            format_func=lambda x: T("당뇨 관리", "Diabetes care") if x == "diabetes" else T("건강 관리", "Wellness"),
        )
    with c2:
        st.selectbox("Language / 언어", ["한국어", "English"], key="language")
    with c3:
        st.selectbox("Unit / 단위", ["mg/dL", "mmol/L"], key="unit")

# =========================================================
# 히어로
# =========================================================
with st.container(key="hero"):
    hero_left, hero_right = st.columns([0.9, 1.8], gap="large", vertical_alignment="center")

    with hero_left:
        if MASCOT_B64:
            st.markdown(
                f'<div class="gb-mascot"><img src="data:image/png;base64,{MASCOT_B64}" alt="mascot"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.warning("assets/mascot.png 파일을 넣어주세요.")

    with hero_right:
        st.markdown('<span class="gb-pill">GLUCOBRIDGE · YOUR WELLNESS COMPANION</span>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="gb-hero-title">{T("나의 혈당 기록, 더 쉽게 이해하기.", "Make sense of your glucose data.")}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="gb-hero-sub">{T("혈당을 기록하고 변화를 확인하세요. AI가 기록을 설명하고 진료 준비도 도와줘요.", "Track readings, understand trends, and prepare for care visits with AI support.")}</div>',
            unsafe_allow_html=True,
        )
        badges = [
            T("혈당 기록", "Glucose journal"),
            T("AI 요약", "AI summaries"),
            T("생활 습관 커뮤니티", "Wellness community"),
        ]
        badge_html = "".join([f'<span class="gb-hero-badge">{b}</span>' for b in badges])
        st.markdown(f'<div class="gb-hero-badges">{badge_html}</div>', unsafe_allow_html=True)

# =========================================================
# KPI
# =========================================================
all_records = st.session_state.records
glucose_records = [r for r in all_records if r["item"] == "혈당"]
a1c_records = [r for r in all_records if r["item"] == "HbA1c"]

last_glucose = (
    f"{get_glucose_display_value(sorted(glucose_records, key=lambda r: r['measured_at'])[-1], st.session_state.unit):.1f} {st.session_state.unit}"
    if glucose_records else "—"
)
last_a1c = (
    f"{sorted(a1c_records, key=lambda r: r['measured_at'])[-1]['value']}%"
    if a1c_records else "—"
)

kpis = [
    (T("전체 기록", "Total entries"), str(len(all_records))),
    (T("기록한 날짜", "Days logged"), str(len({r["measured_at"][:10] for r in all_records}))),
    (T("최근 혈당", "Latest glucose"), last_glucose),
    (T("최근 HbA1c", "Latest HbA1c"), last_a1c),
]

st.markdown(
    '<div class="gb-kpis">' + ''.join(
        [f'<div class="gb-kpi"><div class="gb-kpi-label">{label}</div><div class="gb-kpi-value">{value}</div></div>'
         for label, value in kpis]
    ) + '</div>',
    unsafe_allow_html=True,
)

# =========================================================
# 메뉴
# =========================================================
MENU_ITEMS = [
    ("🩸 기록", "🩸 Journal"),
    ("📊 분석", "📊 Analytics"),
    ("✨ AI 설명", "✨ AI insights"),
    ("📑 진료 리포트", "📑 Visit report"),
    ("💬 커뮤니티", "💬 Community"),
    ("📦 데이터", "📦 Data"),
]

with st.container(key="menu"):
    cols = st.columns(len(MENU_ITEMS), gap="small")
    for i, col in enumerate(cols):
        with col:
            if st.button(
                MENU_ITEMS[i][1] if st.session_state.language == "English" else MENU_ITEMS[i][0],
                key=f"menu_{i}",
                type="primary" if st.session_state.menu == i else "secondary",
                use_container_width=True,
            ):
                st.session_state.menu = i
                st.rerun()

# =========================================================
# 사이드바
# =========================================================
with st.sidebar:
    st.markdown("### GlucoBridge")
    st.caption(T("이 앱은 학습·시연용입니다. 기록은 접속 세션에만 저장돼요.", "Educational demo. Records stay only in this session."))
    if st.button(T("AI 대화 초기화", "Clear AI chat"), use_container_width=True):
        st.session_state.ai_messages = []
        st.session_state.ai_last = None
        st.rerun()

# =========================================================
# 빈 데이터 안내
# =========================================================
if not all_records:
    left, right = st.columns([3, 1], vertical_alignment="center")
    with left:
        st.info(T("처음이라면 가상 기록 29건으로 기능을 둘러보세요.", "New here? Explore the app with 29 fictional entries."))
    with right:
        if st.button(T("가상 데이터 불러오기", "Load demo data"), type="primary", use_container_width=True):
            st.session_state.records = demo_data()
            st.rerun()

# =========================================================
# 섹션 헤더
# =========================================================
def section_header(ko_title, en_title, ko_sub="", en_sub=""):
    st.markdown(
        f'<div class="gb-section"><h2>{T(ko_title, en_title)}</h2><p>{T(ko_sub, en_sub)}</p></div>',
        unsafe_allow_html=True
    )

# =========================================================
# 페이지 0 - 기록
# =========================================================
if st.session_state.menu == 0:
    section_header(
        "혈당 기록", "Your glucose journal",
        "측정값과 측정 상황을 함께 입력하세요.",
        "Log the value together with measurement context."
    )

    left, right = st.columns([1.6, 0.95], gap="large")

    with left:
        with st.container(key="entry_card"):
            st.markdown(f'<div class="gb-card-title">✍️ {T("새 기록 추가", "Add a new entry")}</div>', unsafe_allow_html=True)

            item = st.selectbox(T("기록 항목", "Reading type"), ["혈당", "HbA1c"])
            input_unit = st.selectbox(
                T("입력 단위", "Input unit"),
                ["mg/dL", "mmol/L"] if item == "혈당" else ["%"]
            )

            c1, c2 = st.columns(2)
            day_text = c1.text_input(T("측정 날짜 (YYYY-MM-DD)", "Date (YYYY-MM-DD)"), value=str(now_kst().date()))
            time_text = c2.text_input(T("측정 시간 (HH:MM)", "Time (HH:MM)"), value=now_kst().strftime("%H:%M"))

            default_val = 110.0 if input_unit == "mg/dL" else (6.1 if input_unit == "mmol/L" else 5.8)
            value = st.number_input(T("측정값", "Value"), min_value=0.1, value=float(default_val), step=0.1)

            if item == "혈당":
                c3, c4 = st.columns(2)
                context = c3.selectbox(T("측정 상황", "Context"), ["공복(8시간 이상)", "식전", "식후", "취침 전", "기타"])
                method = c4.selectbox(T("측정 방법", "Method"), ["손끝 채혈", "CGM", "검사실 혈장검사"])
                minutes_after_meal = st.number_input(
                    T("식후 경과 시간(분) — 식후 선택 시 사용", "Minutes after meal — use for post-meal"),
                    min_value=1,
                    max_value=480,
                    value=120,
                )
            else:
                context = "검사실"
                method = "검사실"
                minutes_after_meal = None

            note = st.text_area(T("식사·활동 메모 (선택)", "Meal / activity note (optional)"), max_chars=400)

            if st.button(T("기록 저장하기", "Save entry"), type="primary", use_container_width=True):
                try:
                    record = make_record(
                        day_text, time_text, item, value, input_unit,
                        context, method, minutes_after_meal, note
                    )
                    st.session_state.records.append(record)
                    st.success(T("기록이 저장됐어요!", "Entry saved!"))
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with right:
        with st.container(key="aside_card"):
            st.markdown(f'<div class="gb-card-title">💡 {T("더 좋은 기록을 위한 팁", "Tips for better logging")}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="gb-note">{T("① 실제로 측정한 수치만 입력하세요.<br>② 공복·식후 여부와 측정 방식을 구분하세요.<br>③ 빠진 시간을 임의로 추정해서 채우지 마세요.", "① Enter real measured values only.<br>② Distinguish fasting, pre-meal and post-meal context.<br>③ Do not guess missing readings.")}</div>',
                unsafe_allow_html=True,
            )

        st.write("")
        with st.container(border=True):
            st.subheader(T("최근 기록", "Recent entries"))
            if all_records:
                st.dataframe(rows_for_table(all_records, st.session_state.unit).head(5), hide_index=True, use_container_width=True)
            else:
                st.info(T("아직 기록이 없어요.", "No entries yet."))

# =========================================================
# 페이지 1 - 분석
# =========================================================
elif st.session_state.menu == 1:
    section_header(
        "혈당 데이터 분석", "Glucose analytics",
        "실제 기록이 없을 때도 데모 차트 예시를 보여줍니다.",
        "Even without records, demo charts are shown for presentation."
    )

    chosen, start, end = period_picker("analytics")
    source_records = chosen if chosen else demo_data()

    if not chosen:
        st.info(T("선택 기간 기록이 없어 예시 그래프로 보여드려요.", "No records were found, so demo charts are shown."))

    glucose_only = [r for r in source_records if r["item"] == "혈당"]
    avg_value = round(mean([get_glucose_display_value(r, st.session_state.unit) for r in glucose_only]), 1) if glucose_only else 0.0
    stats_list = stats_by_context(source_records, st.session_state.unit)
    top_context = stats_list[0]["context"] if stats_list else "-"

    st.markdown(
        f"""
        <div class="gb-analytics-grid">
          <div class="gb-mini-card">
            <div class="gb-mini-title">{T("요약 인사이트", "Summary insight")}</div>
            <div class="gb-mini-value">{avg_value} {st.session_state.unit}</div>
            <div class="gb-mini-copy">{T("선택 기간의 평균 혈당입니다. 데이터가 없으면 데모 예시를 사용합니다.", "Average glucose for the selected period. Demo data is used if no real data exists.")}</div>
          </div>
          <div class="gb-mini-card">
            <div class="gb-mini-title">{T("가장 많이 기록한 상황", "Most logged context")}</div>
            <div class="gb-mini-value" style="font-size:22px;">{top_context}</div>
            <div class="gb-mini-copy">{T("기록 패턴을 한눈에 볼 수 있도록 넣은 요약 카드입니다.", "A quick summary card that makes the logging pattern easy to understand.")}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric(T("기록 건수", "Entries"), len(source_records))
    m2.metric(T("기록한 날짜", "Days logged"), len({r["measured_at"][:10] for r in source_records}))
    m3.metric(T("혈당 기록", "Glucose readings"), len(glucose_only))

    chart_col, side_col = st.columns([1.35, 0.95], gap="large")
    point_df = analytics_point_df(source_records, st.session_state.unit)

    with chart_col:
        with st.container(border=True):
            st.subheader(T("혈당 변화 그래프", "Glucose trend"))
            if not point_df.empty:
                chart = alt.Chart(point_df).mark_line(point=True, interpolate="monotone").encode(
                    x=alt.X("time:T", title="KST"),
                    y=alt.Y("value:Q", title=f"Glucose ({st.session_state.unit})", scale=alt.Scale(zero=False)),
                    color=alt.Color("context:N", title=T("측정 조건", "Context")),
                    tooltip=[
                        alt.Tooltip("time:T", title=T("시간", "Time")),
                        alt.Tooltip("value:Q", title=T("값", "Value")),
                        alt.Tooltip("context:N", title=T("상황", "Context")),
                    ],
                ).properties(height=340)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info(T("혈당 기록이 없어요.", "No glucose readings."))

            st.caption(T("데모 화면에서는 가독성을 위해 선으로 연결했지만, 실제 해석은 측정 시점 중심으로 해야 합니다.", "The demo connects points for readability, but interpretation should remain point-in-time."))

        with st.container(border=True):
            st.subheader(T("측정 조건별 통계", "Statistics by context"))
            stats_df = stats_df_for_display(source_records, st.session_state.unit)
            if not stats_df.empty:
                st.dataframe(stats_df, hide_index=True, use_container_width=True)
            else:
                st.info(T("표시할 통계가 없어요.", "No statistics to display."))

    with side_col:
        with st.container(border=True):
            st.subheader(T("측정 상황 분포", "Context mix"))
            if stats_list:
                pie_source = pd.DataFrame(stats_list)
                if st.session_state.language == "English":
                    pie_source["context"] = pie_source["context"].apply(lambda x: tr_context(x.replace("식후 (", "식후")))
                arc = alt.Chart(pie_source).mark_arc(innerRadius=52).encode(
                    theta=alt.Theta("count:Q"),
                    color=alt.Color("context:N", title=T("상황", "Context")),
                    tooltip=[
                        alt.Tooltip("context:N", title=T("상황", "Context")),
                        alt.Tooltip("count:Q", title=T("건수", "Count")),
                    ],
                ).properties(height=260)
                st.altair_chart(arc, use_container_width=True)
            else:
                st.info(T("분포를 보여줄 데이터가 없어요.", "No distribution data available."))

        with st.container(border=True):
            st.subheader(T("주간 평균 예시", "Weekly average example"))
            if not point_df.empty:
                weekly = point_df.copy()
                weekly["week"] = weekly["date"].dt.strftime("%m/%d")
                weekly = weekly.groupby("week", as_index=False)["value"].mean()
                bars = alt.Chart(weekly).mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8).encode(
                    x=alt.X("week:N", title=T("주차", "Week")),
                    y=alt.Y("value:Q", title=f"Avg ({st.session_state.unit})"),
                    tooltip=[
                        alt.Tooltip("week:N", title=T("주차", "Week")),
                        alt.Tooltip("value:Q", title=T("평균", "Average"), format=".1f"),
                    ],
                ).properties(height=220)
                st.altair_chart(bars, use_container_width=True)
            st.caption(T("발표용 데모 시각화 예시입니다.", "A presentation-friendly demo visualization."))

    with st.expander(T("기록표 / 삭제", "Full table / delete")):
        st.dataframe(rows_for_table(chosen if chosen else source_records, st.session_state.unit), hide_index=True, use_container_width=True)

        if chosen:
            options = {r["record_id"]: f"{r['measured_at'][:16]} · {r['item']} {r['value']} {r['unit']}" for r in chosen}
            selected = st.selectbox(T("삭제할 기록", "Select an entry to delete"), list(options.keys()), format_func=lambda x: options[x])
            confirm = st.checkbox(T("선택한 기록을 삭제할게요.", "Confirm deletion"))
            if st.button(T("기록 삭제", "Delete"), disabled=not confirm):
                st.session_state.records = [r for r in st.session_state.records if r["record_id"] != selected]
                st.success(T("삭제했어요.", "Deleted."))
                st.rerun()

# =========================================================
# 페이지 2 - AI 설명
# =========================================================
elif st.session_state.menu == 2:
    section_header(
        "AI 기록 설명", "AI insights",
        "집계 통계를 먼저 만들고, AI가 쉽게 설명해줍니다.",
        "Aggregated statistics are computed first, then explained in plain language."
    )

    chosen, start, end = period_picker("ai")
    left, right = st.columns([0.95, 1.55], gap="large")

    with left:
        with st.container(border=True):
            st.subheader(T("분석 근거", "Evidence first"))
            st.metric(T("선택 기록", "Selected entries"), len(chosen))
            stats_df = stats_df_for_display(chosen, "mg/dL")
            if not stats_df.empty:
                st.dataframe(stats_df, hide_index=True, use_container_width=True)
            else:
                st.info(T("선택한 기간에 기록이 없어요.", "No entries in the selected period."))

            st.caption(
                T(
                    "Gemini에는 원본 메모 전체가 아니라 선택 기간의 통계와 질문만 전달하는 방식으로 설계했습니다.",
                    "Only statistics and the user's question are intended to be sent to Gemini."
                )
            )

    with right:
        consent = st.checkbox(
            T("선택 기간 통계와 질문을 Gemini로 전송하는 데 동의합니다.", "I consent to sending aggregated statistics and my question to Gemini.")
        )

        for msg in st.session_state.ai_messages[-8:]:
            with st.chat_message(msg["role"]):
                st.write(msg["text"])

        default_question = T(
            "측정 상황별 혈당 패턴을 설명하고, 진료 때 물어볼 질문 3가지를 제안해 주세요.",
            "Explain my glucose pattern by context and suggest three questions to ask a clinician."
        )

        quick = st.button(T("이 기간 AI 요약 생성 ✨", "Generate AI summary ✨"), type="primary", use_container_width=True)
        user_typed = st.chat_input(T("혈당 기록에 대해 질문하기", "Ask about your glucose journal"), max_chars=1000)

        final_question = default_question if quick else user_typed

        if final_question:
            if not consent:
                st.warning(T("먼저 동의에 체크해 주세요.", "Please check the consent box first."))
            elif not chosen:
                st.info(T("선택한 기간에 데이터가 없어요.", "There is no data for the selected period."))
            else:
                try:
                    with st.spinner(T("AI가 기록을 설명하고 있어요…", "AI is explaining your records…")):
                        answer = ask_gemini(chosen, start, end, final_question, st.session_state.language)
                    st.session_state.ai_messages.append({"role": "user", "text": final_question})
                    st.session_state.ai_messages.append({"role": "assistant", "text": answer})
                    st.session_state.ai_last = {
                        "text": answer,
                        "start": str(start),
                        "end": str(end),
                        "lang": st.session_state.language,
                    }
                    st.rerun()
                except Exception as e:
                    st.error(T("AI 요청에 실패했어요. Streamlit Secrets의 API 키를 확인하세요.", "AI request failed. Check your Streamlit Secrets API key."))
                    st.caption(str(e))

# =========================================================
# 페이지 3 - 진료 리포트
# =========================================================
elif st.session_state.menu == 3:
    section_header(
        "진료 준비 리포트", "Visit preparation report",
        "한국어 또는 영어로 정리해서 다운로드하세요.",
        "Download a bilingual summary before a clinic visit."
    )

    chosen, start, end = period_picker("report")

    if not chosen:
        st.info(T("선택한 기간에 기록이 없어요.", "No entries exist in this period."))
    else:
        c1, c2 = st.columns(2)
        report_lang = c1.selectbox(T("보고서 언어", "Report language"), ["한국어", "English"], index=1 if st.session_state.language == "English" else 0)
        report_unit = c2.selectbox(T("보고서 혈당 단위", "Report glucose unit"), ["mg/dL", "mmol/L"], index=1 if st.session_state.unit == "mmol/L" else 0)

        questions = st.text_area(
            T("의료진에게 확인할 질문 (선택)", "Questions for clinician (optional)"),
            max_chars=1200,
            placeholder=T("예: 식후 기록이 자주 높은 이유를 확인하고 싶어요.", "Ex: I'd like to ask why my post-meal values are often high.")
        )

        include_ai = st.checkbox(T("최근 AI 설명을 참고 자료로 포함", "Include the latest AI summary as reference"))
        ai_text = ""
        if include_ai and st.session_state.ai_last:
            ai_text = st.session_state.ai_last.get("text", "")

        preview_df = stats_df_for_display(chosen, report_unit)
        if not preview_df.empty:
            st.dataframe(preview_df, hide_index=True, use_container_width=True)

        report_html = build_report_html(chosen, start, end, report_lang, report_unit, questions, ai_text)
        st.download_button(
            T("진료 리포트 다운로드 (HTML)", "Download visit report (HTML)"),
            data=report_html.encode("utf-8"),
            file_name="GlucoBridge_visit_report.html",
            mime="text/html",
            type="primary",
            use_container_width=True,
        )

        st.caption(T("다운로드한 HTML 파일을 브라우저에서 열어 인쇄 → PDF 저장하면 됩니다.", "Open the HTML file in a browser, then Print → Save as PDF."))

# =========================================================
# 페이지 4 - 커뮤니티
# =========================================================
elif st.session_state.menu == 4:
    section_header(
        "건강 습관 커뮤니티", "Wellness community",
        "식단·운동·생활 루틴만 이야기해요.",
        "Share food, activity and daily habits — not medical advice."
    )

    st.info(
        T(
            "현재 커뮤니티는 내 세션에서만 작동하는 시연용입니다. 진단, 약물, 치료 조언은 다루지 않아요.",
            "This community works only in your current session. It does not allow diagnosis, medication or treatment advice."
        )
    )

    feed, compose = st.columns([1.35, 0.95], gap="large")

    with feed:
        category = st.radio(
            T("주제", "Topic"),
            ["전체", "식단", "운동", "생활습관"],
            horizontal=True,
            format_func=lambda x: {
                "전체": "All",
                "식단": "Food",
                "운동": "Activity",
                "생활습관": "Habits",
            }[x] if st.session_state.language == "English" else x
        )

        visible_posts = [p for p in reversed(st.session_state.community) if category == "전체" or p["cat"] == category]
        st.markdown(
            f'<div class="gb-community-board"><div class="gb-message-wrap">{render_message_html(visible_posts, "전체")}</div></div>',
            unsafe_allow_html=True,
        )

        for post in visible_posts:
            c1, c2 = st.columns([0.18, 0.82], gap="small")

            with c1:
                liked = post["id"] in st.session_state.liked
                if st.button(f"♡ {post['likes']}", key=f"like_{post['id']}", disabled=liked, use_container_width=True):
                    post["likes"] += 1
                    st.session_state.liked.add(post["id"])
                    st.rerun()

            with c2:
                if post["comments"]:
                    for comment in post["comments"][-2:]:
                        st.caption("💬 " + comment)

                with st.form(f"comment_form_{post['id']}", clear_on_submit=True):
                    reply = st.text_input(
                        T("응원 한마디", "Quick reply"),
                        placeholder=T("좋아요! 저도 해볼게요.", "Love this! I'll try it too."),
                        max_chars=180
                    )
                    submitted = st.form_submit_button(T("보내기", "Send"))
                    if submitted and reply.strip():
                        post["comments"].append(reply.strip())
                        st.rerun()

                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    with compose:
        with st.container(key="entry_card"):
            st.markdown(f'<div class="gb-card-title">🌱 {T("건강 습관 공유하기", "Share a healthy habit")}</div>', unsafe_allow_html=True)
            st.caption(T("아이폰 메시지처럼 가볍게 보이는 데모 커뮤니티 버전입니다.", "A lighter demo community inspired by messaging apps."))

            with st.form("new_post_form", clear_on_submit=True):
                cat = st.selectbox(T("카테고리", "Category"), ["식단", "운동", "생활습관"])
                title = st.text_input(T("짧은 제목", "Short title"), max_chars=70, placeholder=T("예: 저녁 산책 루틴", "Ex: Evening walk routine"))
                body = st.text_area(T("내용", "Message"), max_chars=700, placeholder=T("오늘 실천한 식단·운동·생활 루틴을 적어보세요.", "Share a practical food, movement or habit tip."))
                agree = st.checkbox(T("의료·약물 조언이나 개인정보를 작성하지 않았어요.", "I did not include medical advice or personal information."))
                post_submit = st.form_submit_button(T("시연 메시지 올리기", "Post demo message"), type="primary", use_container_width=True)

                if post_submit:
                    if not agree or len(title.strip()) < 2 or len(body.strip()) < 5:
                        st.warning(T("제목·내용과 운영 규칙 동의를 확인하세요.", "Please complete the fields and accept the rules."))
                    else:
                        st.session_state.community.append({
                            "id": str(uuid4()),
                            "cat": cat,
                            "title": title.strip(),
                            "en": title.strip(),
                            "body": body.strip(),
                            "body_en": body.strip(),
                            "likes": 0,
                            "comments": [],
                            "demo": False,
                        })
                        st.rerun()

            st.markdown(
                f'<div class="gb-compose-note">{T("실제 공개 전에는 게시글 신고·관리·개인정보 필터링 기능이 필요합니다.", "A public launch would require moderation, reporting and privacy filtering.")}</div>',
                unsafe_allow_html=True,
            )

# =========================================================
# 페이지 5 - 데이터
# =========================================================
else:
    section_header(
        "데이터 백업", "Your data, your control",
        "CSV로 저장하고 다시 불러올 수 있어요.",
        "Export to CSV and import it again later."
    )

    left, right = st.columns(2, gap="large")

    with left:
        with st.container(border=True):
            st.subheader(T("CSV 내려받기", "Export CSV"))
            if all_records:
                st.download_button(
                    T("전체 기록 다운로드", "Download all records"),
                    data=export_csv(all_records),
                    file_name="GlucoBridge_records.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.info(T("아직 기록이 없어요.", "No records yet."))

            st.download_button(
                T("예시 CSV 다운로드", "Download sample CSV"),
                data=export_csv(demo_data()),
                file_name="GlucoBridge_sample.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with right:
        with st.container(border=True):
            st.subheader(T("CSV 불러오기", "Import CSV"))
            uploaded = st.file_uploader(T("GlucoBridge CSV 파일", "GlucoBridge CSV file"), type=["csv"])

            if uploaded is not None:
                action = st.radio(
                    T("불러오기 방식", "Import mode"),
                    [T("기존 기록에 추가", "Append to current data"), T("기존 기록을 덮어쓰기", "Replace current data")]
                )
                if st.button(T("CSV 적용", "Apply CSV"), type="primary", use_container_width=True):
                    try:
                        imported = import_csv(uploaded)
                        if action == T("기존 기록을 덮어쓰기", "Replace current data"):
                            st.session_state.records = imported
                        else:
                            st.session_state.records.extend(imported)
                        st.success(T("CSV를 불러왔어요.", "CSV imported successfully."))
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

# =========================================================
# 하단
# =========================================================
st.markdown(
    f'<div class="gb-footer">GlucoBridge · {T("교육용 시연 프로토타입입니다. 기록 분석과 진료 준비 참고용이며 의료 진단·치료 지침을 제공하지 않습니다.", "Educational prototype. It is for journaling, analysis and visit preparation only, and does not provide diagnosis or treatment advice.")}</div>',
    unsafe_allow_html=True,
)
