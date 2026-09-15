import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

# [새로 추가된 에이전트용 라이브러리]
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import csv

# ==========================================
# 1. 파이어베이스 및 구글 시트 인증 설정
# ==========================================
@st.cache_resource
def init_firebase_and_google():
    db = None
    gspread_client = None
    
    # 1-1. 파이어베이스 열쇠 찾기
    try:
        if os.path.exists('firebase_key.json'):
            cred = credentials.Certificate('firebase_key.json')
            key_dict = json.load(open('firebase_key.json'))
        elif "firebase_json" in st.secrets:
            key_dict = json.loads(st.secrets["firebase_json"])
            cred = credentials.Certificate(key_dict)
        else:
            return None, None
            
        # 파이어베이스 DB 연결
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        # 1-2. 구글 시트 연결 (파이어베이스 열쇠를 그대로 재활용!)
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        gspread_creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        gspread_client = gspread.authorize(gspread_creds)
        
    except Exception as e:
        st.error(f"⚠️ 시스템 연결 오류: {e}")
        
    return db, gspread_client

db, gc = init_firebase_and_google()

if db:
    doc_ref = db.collection('japanese_app').document('my_progress')
else:
    doc_ref = None

def load_db_progress():
    if doc_ref:
        doc = doc_ref.get()
        if doc.exists: return doc.to_dict()
    return {'session_count': 1, 'studied_words': []}

def save_db_progress(session_count, studied_words):
    if doc_ref:
        doc_ref.set({'session_count': session_count, 'studied_words': studied_words})

# ==========================================
# 2. 팝 앤 게임 테마 CSS
# ==========================================
st.markdown("""
<style>
.stApp { background-color: #fff9e6; }
h1, h2, h3, p, span, div { color: #000; }
.flip-container { perspective: 1000px; width: 100%; margin: 10px auto 20px auto; }
.flip-toggle { display: none; }
.flipper { transition: 0.6s; transform-style: preserve-3d; position: relative; height: 350px; cursor: pointer; }
.flip-toggle:checked + .flipper { transform: rotateY(180deg); }
.front, .back { backface-visibility: hidden; position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 16px; border: 4px solid #000; box-shadow: 6px 6px 0 #000; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #fff; }
.back { transform: rotateY(180deg); }
.level-badge { background-color: #4ecdc4; padding: 6px 16px; border-radius: 20px; border: 3px solid #000; font-size: 14px; font-weight: 900; margin-bottom: 10px; box-shadow: 3px 3px 0 #000; }
.kanji-text { font-size: 85px; font-weight: 900; margin: 10px 0; }
.reading-text { font-size: 32px; font-weight: 900; margin: 5px 0; }
.meaning-text { font-size: 28px; font-weight: 900; color: #ff6b6b; margin: 5px 0; padding: 0 10px; }
.example-box { margin-top: 15px; padding: 12px; background-color: #feca57; border-radius: 12px; width: 85%; border: 3px solid #000; box-shadow: 3px 3px 0 #000; }
div[data-testid="stButton"] button { border: 3px solid #000 !important; box-shadow: 4px 4px 0 #000 !important; border-radius: 12px !important; font-weight: 900 !important; transition: all 0.1s !important; }
div[data-testid="stButton"] button:active { box-shadow: 0px 0px 0 #000 !important; transform: translateY(4px) translateX(4px) !important; }
div[data-testid="stButton"] button[kind="primary"] { background-color: #feca57 !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 데이터 로드 및 AI 에이전트 설정
# ==========================================
SHEET_ID = "1h-kcu7Xr0Mpwy-cGMqxv9mIlxVFFXRXVMpP9DqxyRDQ"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

@st.cache_data(ttl=60)
def load_data(level):
    try:
        df = pd.read_csv(CSV_URL)
        if 'kanji' in df.columns: df = df.dropna(subset=['kanji'])
        if 'example_ja' not in df.columns: df['example_ja'] = ""
        if 'example_ko' not in df.columns: df['example_ko'] = ""
        
        if 'level' in df.columns:
            df['level'] = df['level'].astype(str).str.strip().str.upper()
            df = df[df['level'] == level.upper()]
        else:
            df['level'] = level.upper()
        return df.reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame({'kanji': ['食べる'], 'reading': ['たべる'], 'meaning': ['먹다'], 'example_ja': [''], 'example_ko': [''], 'level': [level]})

# --- [비밀 관리자 에이전트 패널 (사이드바)] ---
with st.sidebar:
    st.header("🤖 AI 단어 생성 에이전트")
    st.write("비밀번호를 입력하여 조종실을 여세요.")
    admin_pw = st.text_input("비밀번호", type="password")
    
    if admin_pw == "0000": # 비밀번호는 '0000' 입니다. 원하시는 대로 바꾸셔도 됩니다!
        st.success("✅ 에이전트 접근 허가됨")
        gen_level = st.selectbox("생성할 급수", ["N5", "N4", "N3", "N2", "N1"])
        gen_count = st.number_input("생성할 단어 개수", min_value=5, max_value=30, value=10)
        
        if st.button("🚀 단어 생성 및 시트 업데이트"):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("스트림릿 Secrets에 GEMINI_API_KEY가 없습니다!")
            else:
                with st.spinner(f"AI가 {gen_level} 단어 {gen_count}개를 수집하고 있습니다. (약 10~20초 소요)"):
                    try:
                        # 1. 제미나이 호출
                        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = f"""
                        당신은 전문 일본어 강사입니다. JLPT {gen_level} 급수에 해당하는 필수 한자 단어 {gen_count}개를 만들어주세요.
                        반드시 아래의 규칙을 엄격하게 지켜서 CSV 형식으로만 출력하세요. 마크다운 기호(```csv 등)나 부가 설명은 절대 쓰지 마세요.
                        규칙:
                        1. 각 줄마다 level, kanji, reading, meaning, example_ja, example_ko 순서로 콤마(,)로 구분
                        2. level은 반드시 '{gen_level}' 로 작성
                        3. kanji가 없는 단어(히라가나만 있는 단어)는 제외
                        출력 예시:
                        {gen_level},勉強,べんきょう,공부,日本語の勉強をする。,일본어 공부를 한다.
                        """
                        response = model.generate_content(prompt)
                        # 이 아래 코드가 무조건 '한 줄'로 길게 이어져 있어야 합니다!
                        ai_text = response.text.strip().replace("```csv", "").replace("```", "").strip()
                        
                        # 2. 결과 파싱 및 시트 업데이트
                        new_rows = []