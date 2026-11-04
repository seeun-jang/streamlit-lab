        data = data.rename(columns=renames)
        for col in ("Context / method", "Context", "Method", "Type"):
            if col in data.columns:
                data[col] = data[col].fillna("").map(context_in_english)
    return data


def glucose_chart(records, unit):
    items = []
    for record in records:
        if record["item"] != "혈당":
            continue
        items.append({
            "date": datetime.fromisoformat(record["measured_at"]).replace(tzinfo=None),
            "reading": round(float(normalized(record)) / (18 if unit == "mmol/L" else 1), 2),
            "category": context_in_english(group_label(record)) if T("ko", "en") == "en" else group_label(record),
        })
    if not items:
        return None
    data = pd.DataFrame(items)
    chart = alt.Chart(data).mark_circle(size=100, opacity=.85, stroke="white", strokeWidth=1.2).encode(
        x=alt.X("date:T", title=T("측정 시각 (KST)", "Measured at (KST)"), axis=alt.Axis(format="%m/%d", grid=False, labelColor="#7886a0")),
        y=alt.Y("reading:Q", title=f"Glucose ({unit})", scale=alt.Scale(zero=False), axis=alt.Axis(gridColor="#e9eff9", labelColor="#7886a0")),
        color=alt.Color("category:N", title=T("측정 조건·방법", "Context / method"), scale=alt.Scale(scheme="tableau10")),
        tooltip=[alt.Tooltip("date:T", title="KST", format="%Y-%m-%d %H:%M"), alt.Tooltip("reading:Q", title=unit), alt.Tooltip("category:N", title="Context")],
    ).properties(height=345, background="transparent").interactive()
    return chart


def init_state():
    defaults = {
        "page": 0, "records": [], "ai_history": [], "ai_messages": [],
        "last_export": "", "post_list": [], "liked_posts": set(),
        "period_start": datetime.now(KST).date() - timedelta(days=30),
        "period_end": datetime.now(KST).date(),
        "user_mode": "diabetes", "ui_language": "한국어", "display_unit": "mg/dL",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.post_list:
        st.session_state.post_list = [
            {"id":"demo-walk", "kind":"운동", "title_ko":"식사 후 가볍게 걷는 습관", "title_en":"A gentle walk after meals", "body_ko":"산책 시간을 캘린더에 표시하면서 꾸준히 실천 중이에요. 작은 습관부터 시작해보세요!", "body_en":"I mark my walks on a calendar. Small habits are easier to keep!", "likes":8, "comments":[], "demo":True},
            {"id":"demo-food", "kind":"식단", "title_ko":"한 접시 식단 준비 아이디어", "title_en":"Easy balanced plate inspiration", "body_ko":"채소와 단백질 식품을 먼저 준비하면 식사 구성이 편해지더라고요.", "body_en":"Preparing veggies and protein foods first makes my meals easier to plan.", "likes":5, "comments":[], "demo":True},
        ]


init_state()

# Simple bilingual labels; health records remain local to this browser session.
NAV_KO = ["기록하기", "데이터 분석", "AI 인사이트", "진료 준비", "커뮤니티", "데이터 보관"]
NAV_EN = ["Journal", "Analytics", "AI insights", "Visit report", "Community", "Data & backup"]
NAV_ICONS = ["🩸", "📈", "✨", "📑", "💬", "📦"]

head, controls = st.columns([2.6, 1.45], vertical_alignment="center")
with head:
    st.markdown('<div class="gb-topline"><div class="gb-topicon">✦</div><div class="gb-word">Gluco<span>Bridge</span></div><div class="gb-tag">HEALTH DATA, MADE HUMAN</div></div>', unsafe_allow_html=True)
with controls:
    mode_col, lang_col = st.columns([1.25, .9])
    mode_col.selectbox(
        "Mode / 사용자", ["diabetes", "wellness"], key="user_mode",
        format_func=lambda x: ("Diabetes" if x == "diabetes" else "Wellness") if T("ko", "en") == "en" else ("당뇨 관리" if x == "diabetes" else "일반 관리"),
    )
    lang_col.selectbox("Language / 언어", ["한국어", "English"], key="ui_language")

hero_title = T("나의 혈당 기록, 더 똑똑하게.", "Better insights, healthier routines.")
hero_sub = (T(
    "혈당 측정 기록을 한눈에 정리하고 AI 설명과 진료 준비 자료로 연결해요.",
    "Organize readings, understand patterns and prepare for your next care visit.",
) if st.session_state.user_mode == "diabetes" else T(
    "식사·운동과 생활습관 기록을 쉽게 남기고 건강한 일상을 이어가요.",
    "Track readings and everyday routines to build sustainable wellness habits.",
))
mascot_b64 = base64.b64encode(ASSET_PATH.read_bytes()).decode("ascii") if ASSET_PATH.is_file() else ""
hero_img = f'<img alt="GlucoBridge heart-hugging blood drop mascot" src="data:image/png;base64,{mascot_b64}">' if mascot_b64 else ""
st.markdown(f'''<div class="gb-hero"><div class="gb-hero-copy"><div class="gb-eyebrow">PERSONAL HEALTH COMPANION · {date_title()}</div><h1>{hero_title}</h1><p>{hero_sub}</p><div class="gb-hero-pills"><span class="gb-pill">✦ {T('나만의 기록','Personal journal')}</span><span class="gb-pill">◈ {T('설명 가능한 AI','Explainable insights')}</span><span class="gb-pill">♡ {T('따뜻한 커뮤니티','Wellness community')}</span></div></div>{hero_img}</div>''', unsafe_allow_html=True)

# Top summary cards (explicitly user-entered readings, not CGM-derived metrics).
current = st.session_state.records
sum_all = summarize(current)
last_glucose = sorted([r for r in current if r["item"] == "혈당"], key=lambda r: r["measured_at"])
last_value = (f"{float(normalized(last_glucose[-1])) / (18 if st.session_state.display_unit == 'mmol/L' else 1):.1f} {st.session_state.display_unit}" if last_glucose else "—")
m1, m2, m3, m4 = st.columns(4)
m1.metric(T("전체 기록", "Total records"), f"{sum_all['전체 기록']}" + T("건", ""))
m2.metric(T("기록한 날짜", "Days recorded"), f"{sum_all['기록 일수']}" + T("일", ""))
m3.metric(T("최근 혈당 측정값", "Latest glucose reading"), last_value)
m4.metric(T("최근 HbA1c 기록", "Latest HbA1c entry"), f"{sum_all['최근 HbA1c']}%" if sum_all["최근 HbA1c"] else "—")

with st.container(key="nav"):
    menu_cols = st.columns(6)
    for idx, col in enumerate(menu_cols):
        label = (NAV_EN if T("ko", "en") == "en" else NAV_KO)[idx]
        col.button(f"{NAV_ICONS[idx]} {label}", type="primary" if st.session_state.page == idx else "secondary", key=f"menu_{idx}", on_click=set_page, args=(idx,), width="stretch")

if not current:
    with st.container(border=True):
        left_intro, right_intro = st.columns([4, 1.2], vertical_alignment="center")
        left_intro.markdown(T("**처음이라면 가상 데이터로 기능을 둘러보세요.** 14일치 가상 측정값과 HbA1c 기록을 즉시 추가할 수 있어요.", "**New here? Explore with demo data.** Load 14 days of fictional readings and an HbA1c entry."))
        if right_intro.button(T("가상 기록 불러오기", "Load demo data"), type="primary", key="demo_load", width="stretch"):
            st.session_state.records = demo_records()
            st.session_state.flash = T("가상 데이터를 불러왔습니다.", "Demo data loaded.")
            st.rerun()
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

with st.sidebar:
    st.header("⚙️ GlucoBridge")
    st.selectbox(T("그래프 혈당 단위", "Glucose display unit"), ["mg/dL", "mmol/L"], key="display_unit")
    st.slider(T("AI 대화 기억 턴 수", "AI history turns"), 1, 10, 5, key="ai_turns")
    st.button(T("AI 대화 초기화", "Reset AI chat"), on_click=reset_chat, width="stretch")
    st.markdown("---")
    st.caption(T("⚠️ 학습·시연용 앱입니다. 실제 환자 계정, 의료진 자동 전송, 서버 장기 저장은 지원하지 않습니다.", "⚠️ Educational prototype. No patient accounts, clinical transmission, or persistent server storage."))
    st.caption(T("혈당 측정값은 기기나 검사 결과를 직접 확인하고 입력하세요.", "Enter readings confirmed by a meter or lab result."))

page = st.session_state.page
now = datetime.now(KST)

# Shared selection for analytics, AI and visit report.
if page in (1, 2, 3):
    with st.container(border=True):
        d1, d2, d3 = st.columns([1, 1, 1.5], vertical_alignment="bottom")
        d1.date_input(T("시작일 (KST)", "Start date (KST)"), key="period_start")
        d2.date_input(T("종료일 (KST)", "End date (KST)"), key="period_end")
        d3.caption(T("이 기간을 그래프 · AI 요약 · 진료 보고서에 공통 적용합니다.", "The same period is used for charts, AI and visit reports."))
    if st.session_state.period_start > st.session_state.period_end:
        st.warning(T("시작일이 종료일보다 늦습니다.", "Start date must not be later than end date."))
        st.stop()
selected = select_period(st.session_state.records, st.session_state.period_start, st.session_state.period_end)
summary = summarize(selected)


if page == 0:  # Journal
    st.markdown(f'<div class="gb-section"><strong>{T("새로운 기록 남기기", "Add a new reading")}</strong><small>{T("정확한 측정 조건을 함께 기록해요", "A reading makes sense with its context")}</small></div>', unsafe_allow_html=True)
    lcol, rcol = st.columns([1.65, 1], gap="large")
    with lcol:
        item = st.selectbox(T("기록 유형", "Reading type"), ["혈당", "HbA1c"], format_func=lambda v: ("Glucose" if v == "혈당" else "HbA1c") if T("ko", "en") == "en" else v)
        unit = st.selectbox(T("입력 단위", "Input unit"), (["mg/dL", "mmol/L"] if item == "혈당" else ["%"]), key=f"unit_{item}")
        with st.form("add_record_form", clear_on_submit=False):
            dc, tc = st.columns(2)
            day = dc.date_input(T("측정 날짜", "Date"), now.date(), max_value=now.date())
            clock = tc.time_input(T("측정 시간", "Time"), now.time().replace(second=0, microsecond=0, tzinfo=None))
            initial = 110.0 if item == "혈당" and unit == "mg/dL" else (6.1 if item == "혈당" else 5.8)
            value = st.number_input(T("수치", "Value") + f" ({unit})", min_value=0.1, value=initial, step=0.1, key=f"reading_{item}_{unit}")
            if item == "혈당":
                context = st.selectbox(T("측정 시점", "Measurement context"), CONTEXTS, format_func=lambda value: context_in_english(value) if T("ko", "en") == "en" else value)
                method = st.selectbox(T("측정 방법", "Measurement method"), METHODS, format_func=lambda value: context_in_english(value) if T("ko", "en") == "en" else value)
                mins = st.number_input(T("식후 경과 시간(분) · 식후인 경우", "Minutes after meal · if applicable"), min_value=1, max_value=480, value=120)
            else:
                context, method, mins = "검사실", "검사실", None
            note = st.text_area(T("생활습관 메모 (선택)", "Lifestyle notes (optional)"), max_chars=500, placeholder=T("예: 식사, 운동, 수면", "e.g. meals, movement, sleep"))
            saved = st.form_submit_button(T("＋ 기록 저장", "＋ Save reading"), type="primary", width="stretch")
        if saved:
            try:
                record = make_record(datetime.combine(day, clock, KST).isoformat(), item, value, unit, context, method, note, mins)
                st.session_state.records, _, _ = merge_records(st.session_state.records, [record])
                st.session_state.flash = T("기록이 저장됐습니다. 데이터 보관에서 CSV 백업을 권장합니다.", "Reading saved. We recommend downloading a CSV backup.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    with rcol:
        st.markdown(f'<div class="gb-gradient-card"><b>💡 {T("기록이 정확할수록 분석도 좋아져요", "Better context, clearer insights")}</b><p>{T("혈당 숫자뿐 아니라 언제, 어떤 방법으로 측정했는지를 함께 남겨주세요. 식후 기록은 경과 시간을 구분해 분석합니다.", "Keep the date, method and meal context with each reading. Post-meal elapsed times are analyzed separately.")}</p></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="gb-section"><strong>{T("최근 기록", "Recent entries")}</strong></div>', unsafe_allow_html=True)
        if st.session_state.records:
            st.dataframe(friendly_labels(display_rows(st.session_state.records)[:5]), hide_index=True, width="stretch", height=260)
        else:
            st.info(T("아직 입력한 기록이 없습니다.", "No entries yet."))
        st.caption(T("HI/LO 표시 등을 임의의 숫자로 바꾸지 마세요. HbA1c와 혈당은 별도의 지표입니다.", "Do not convert HI/LO symbols into guessed numbers. HbA1c and glucose are different metrics."))

elif page == 1:  # Analytics
    st.markdown(f'<div class="gb-section"><strong>{T("나의 혈당 데이터 분석", "Your glucose analytics")}</strong><small>{T("기록된 시점의 값만 시각화합니다", "Only recorded values are displayed")}</small></div>', unsafe_allow_html=True)
    if not selected:
        st.info(T("선택한 기간에 기록이 없습니다. 기간을 바꾸거나 기록을 추가하세요.", "No entries in this period. Change dates or add a reading."))
    else:
        a, b, c = st.columns(3)
        a.metric(T("기간 내 기록", "Entries in range"), f"{summary['전체 기록']}")
        b.metric(T("기록 일수", "Days recorded"), f"{summary['기록 일수']}")
        c.metric(T("혈당 측정", "Glucose readings"), f"{summary['혈당 기록']}")
        with st.container(border=True):
            st.subheader(T("측정 시점별 분포", "Reading timeline"))
            chart = glucose_chart(selected, st.session_state.display_unit)
            if chart is not None:
                st.altair_chart(chart, width="stretch")
            else:
                st.info(T("이 기간에 혈당 기록은 없습니다.", "No glucose readings in this range."))
            st.caption(T("각 점은 하나의 측정값입니다. 측정하지 않은 시간의 혈당 변화를 연결선으로 추정하지 않습니다.", "Each dot is one reading. The app does not infer glucose between readings."))
        with st.container(border=True):
            st.subheader(T("측정 조건별 통계", "Statistics by context"))
            statistics = unit_stats(selected, st.session_state.display_unit)
            if statistics:
                st.dataframe(friendly_labels(statistics), hide_index=True, width="stretch")
                st.caption(T("평균은 사용자가 기록한 값의 산술평균이며, 하루 전체 평균이나 TIR·GMI가 아닙니다.", "These are arithmetic means of entered readings, not 24-hour means, TIR or GMI."))
            else:
                st.info(T("혈당 측정 기록 없음", "No glucose data"))
        with st.expander(T("전체 기록표 · 기록 삭제", "Full table · delete an entry")):
            st.dataframe(friendly_labels(display_rows(selected)), hide_index=True, width="stretch")
            choices = {r["record_id"]: f"{r['measured_at'][:16].replace('T', ' ')} · {r['item']} {r['value']} {r['unit']}" for r in selected}
            target = st.selectbox(T("삭제할 기록", "Entry to delete"), list(choices), format_func=choices.get)
            sure = st.checkbox(T("이 기록을 삭제하겠습니다.", "I want to delete this entry."))
            if st.button(T("선택 기록 삭제", "Delete selected"), disabled=not sure, type="secondary"):
                st.session_state.records = [r for r in st.session_state.records if r["record_id"] != target]
                st.session_state.pop("prepared_report", None)
                reset_chat()
                st.session_state.flash = T("선택한 기록이 삭제됐습니다.", "Entry deleted.")
                st.rerun()

elif page == 2:  # AI insight
    st.markdown(f'<div class="gb-section"><strong>{T("AI가 정리하는 기록 인사이트", "Explainable AI insights")}</strong><small>{T("의학적 진단이 아닌 기록 요약", "Record explanations, not a diagnosis")}</small></div>', unsafe_allow_html=True)
    lc, rc = st.columns([.9, 1.5], gap="large")
    with lc:
        st.markdown(f'<div class="gb-gradient-card"><b>✨ {T("AI에게 무엇을 맡기나요?", "What the AI can do")}</b><p>{T("Python이 먼저 조건별 통계를 계산하고 Gemini가 그 결과를 쉬운 말로 풀어줍니다. 수치에 없는 정보를 추정하거나 치료 지침을 생성하지 않도록 제한합니다.", "Python computes context-specific statistics first. Gemini explains the calculations in plain language without making treatment decisions.")}</p></div>', unsafe_allow_html=True)
        st.markdown(" ")
        st.metric(T("분석 대상 기록", "Selected entries"), f"{summary['전체 기록']}")
        if summary["혈당 집계_mg_dL"]:
            st.dataframe(friendly_labels(summary["혈당 집계_mg_dL"]), hide_index=True, width="stretch")
        st.caption(T("메모·원본 기록은 자동으로 AI에 전달되지 않습니다.", "Raw entries and free-text notes are not sent automatically."))
    with rc:
        ai_language = st.selectbox(T("AI 응답 언어", "Response language"), ["한국어", "English"], index=1 if T("ko", "en") == "en" else 0)
        consent = st.checkbox(T("선택 기간의 통계(기간·건수·평균 등)를 Gemini에 전달하는 데 동의합니다.", "I consent to sending the selected period's statistics to Gemini."), value=False, key="ai_consent", on_change=reset_chat)
        st.caption(T("질문 내용도 Gemini 서버로 전달됩니다. 이름·연락처·진료 기록 등의 민감한 개인정보는 입력하지 마세요.", "Your question is also sent to Gemini. Do not enter names, contacts or sensitive personal health details."))
        for msg in st.session_state.ai_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["text"])
        request_demo = st.button(T("선택 기간 요약받기 ✨", "Explain this period ✨"), type="primary", disabled=not consent or not selected, width="stretch")
        prompt = (T("선택 기간의 기록을 조건별로 설명하고 진료 때 확인할 질문 3개를 제안해 주세요.", "Explain the recorded trends by context and suggest three neutral questions for my clinician.") if st.session_state.user_mode == "diabetes" else T("선택 기간의 기록을 측정 조건별로 설명하고 생활습관 기록을 더 일관되게 남기는 팁을 알려주세요. 질병 위험도를 판단하지 마세요.", "Explain the journal by measurement context and suggest better habits for consistent logging, without estimating disease risk.")) if request_demo else None
