
import streamlit as st

st.set_page_config(
    page_title="점심 메뉴 고르기",
    page_icon="🍱",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ---------- 화면 디자인 ----------
st.markdown("""
<style>
    .stApp {
        background-color: #FAFBFE;
    }

    .block-container {
        max-width: 850px;
        padding-top: 3rem;
    }

    [data-testid="stSidebar"] {
        background-color: #F0F3FA;
    }

    .main-title {
        font-size: 34px;
        font-weight: 800;
        color: #26344A;
        margin-bottom: 5px;
    }

    .subtitle {
        color: #8591A3;
        font-size: 15px;
        margin-bottom: 30px;
    }

    .result-card {
        background: white;
        border: 1px solid #E5EAF2;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }

    .result-label {
        font-size: 14px;
        color: #8993A5;
        margin-bottom: 10px;
    }

    .result-value {
        font-size: 28px;
        font-weight: 800;
        color: #34445F;
    }

    .menu-card {
        background: white;
        border: 1px solid #E8ECF3;
        border-radius: 14px;
        padding: 18px 22px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .menu-name {
        font-size: 17px;
        font-weight: 700;
        color: #34445F;
    }

    .menu-tag {
        color: #95A0AF;
        font-size: 12px;
        margin-top: 5px;
    }

    .menu-price {
        color: #657BBD;
        font-size: 18px;
        font-weight: 700;
    }

    .counter-card {
        background: #EEF2FF;
        border: 1px solid #DEE5FF;
        border-radius: 18px;
        padding: 30px;
        text-align: center;
        margin-bottom: 20px;
    }

    .counter-label {
        color: #7483A3;
        font-size: 15px;
    }

    .counter-number {
        color: #5369BB;
        font-size: 52px;
        font-weight: 800;
        margin-top: 5px;
    }

    div.stButton > button {
        border-radius: 12px;
        font-weight: 700;
        width: 100%;
    }

    div.stButton > button[kind="primary"] {
        background-color: #697FD0;
        border-color: #697FD0;
        color: white;
    }
</style>
""", unsafe_allow_html=True)


# ---------- 사이드바 ----------
st.sidebar.header("⚙️ 조건 설정")

budget = st.sidebar.slider(
    "💰 오늘의 예산 (원)",
    min_value=5000,
    max_value=15000,
    value=10000,
    step=1000
)

spicy = st.sidebar.checkbox("🌶️ 매운 음식 괜찮음")

st.sidebar.caption("조건을 변경하면 추천 메뉴가 자동으로 바뀝니다.")


# ==========================================
# 실습 1-2 : 점심 메뉴 고르기
# ==========================================

st.markdown("""
<div class="main-title">🍱 오늘 점심 뭐 먹지?</div>
<div class="subtitle">
    예산과 취향에 맞는 점심 메뉴를 골라보세요.
</div>
""", unsafe_allow_html=True)

category = st.selectbox(
    "🍽️ 음식 종류",
    ["한식", "분식", "중식", "양식"]
)

menus = {
    "한식": [
        ("김치찌개", 8000, True),
        ("비빔밥", 9000, False),
        ("제육볶음", 9500, True)
    ],
    "분식": [
        ("떡볶이", 5000, True),
        ("김밥", 5000, False),
        ("라면", 6000, True)
    ],
    "중식": [
        ("짜장면", 7000, False),
        ("짬뽕", 8000, True),
        ("볶음밥", 8000, False)
    ],
    "양식": [
        ("토마토 파스타", 12000, False),
        ("돈가스", 10000, False),
        ("매운 크림 파스타", 13000, True)
    ]
}

# 조건에 맞는 메뉴 찾기
choices = [
    (name, price, is_spicy)
    for name, price, is_spicy in menus[category]
    if price <= budget and (spicy or not is_spicy)
]

# 결과 요약
st.markdown("### 📊 추천 결과")

left, right = st.columns(2)

with left:
    st.markdown(f"""
    <div class="result-card">
        <div class="result-label">🍽️ 조건에 맞는 메뉴</div>
        <div class="result-value">{len(choices)}개</div>
    </div>
    """, unsafe_allow_html=True)

with right:
    st.markdown(f"""
    <div class="result-card">
        <div class="result-label">💰 오늘의 예산</div>
        <div class="result-value">{budget:,}원</div>
    </div>
    """, unsafe_allow_html=True)


# 추천 메뉴 출력
st.markdown("### ✨ 추천 메뉴")

if choices:
    for name, price, is_spicy in choices:

        tag = "🌶️ 매콤한 메뉴" if is_spicy else "🥗 맵지 않은 메뉴"

        st.markdown(f"""
        <div class="menu-card">
            <div>
                <div class="menu-name">{name}</div>
                <div class="menu-tag">{tag}</div>
            </div>
            <div class="menu-price">{price:,}원</div>
        </div>
        """, unsafe_allow_html=True)

else:
    st.warning("조건에 맞는 메뉴가 없습니다. 예산이나 조건을 변경해 보세요.")


# ==========================================
# 실습 1-3 : 클릭 카운터
# ==========================================

st.divider()

st.markdown("### 🔢 클릭 카운터")
st.caption("버튼을 누를 때마다 숫자가 1씩 증가합니다.")

# 세션 상태에 카운터 저장
if "count" not in st.session_state:
    st.session_state.count = 0

# 버튼
col1, col2 = st.columns(2)

with col1:
    if st.button("➕ +1", type="primary"):
        st.session_state.count += 1

with col2:
    if st.button("🔄 초기화"):
        st.session_state.count = 0

# 카운터 결과
st.markdown(f"""
<div class="counter-card">
    <div class="counter-label">현재 누른 횟수</div>
    <div class="counter-number">{st.session_state.count}</div>
</div>
""", unsafe_allow_html=True)

st.caption("💡 session_state를 사용해 버튼을 눌러도 숫자가 유지됩니다.")
