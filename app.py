# 📋 app.py · 실습 1-1
import streamlit as st

st.title("VITALOG")
st.caption("혈당의 흐름을 읽다.")
st.write("당뇨 관련 기록 도우미의 첫 화면입니다.")

nickname = st.text_input("별명을 입력하세요")

if st.button("인사하기"):
    if nickname.strip():
        st.success(f"{nickname.strip()} 님, 반가워요!")
    else:
        st.warning("별명을 먼저 입력해 주세요.")
