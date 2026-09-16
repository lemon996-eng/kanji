import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import random
from datetime import datetime

# [에이전트용 라이브러리]
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# ==========================================
# 1. 파이어베이스 및 구글 시트 인증 설정
# ==========================================
@st.cache_resource
def init_firebase_and_google():
    db = None
    gspread_client = None
    
    try:
        if os.path.exists('firebase_key.json'):
            cred = credentials.Certificate('firebase_key.json')
            key_dict = json.load(open('firebase_key.json'))
        elif "firebase_json" in st.secrets:
            key_dict = json.loads(st.secrets["firebase_json"])
            cred = credentials.Certificate(key_dict)
        else:
            return None, None
            
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        gspread_creds = Credentials.from_service_account_info(key_dict, scopes=scopes)
        gspread_client = gspread.authorize(gspread_creds)
        
    except Exception as e:
        st.error(f"⚠️ 시스템 연결 오류: {e}")
        
    return db, gspread_client

db, gc = init_firebase_and_google()

# --- [사용자 인증 및 데이터 관리 (접속 일수 기반 카운팅)] ---
def authenticate_and_load(user_name, password):
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    if not db:
        return {'status': 'success', 'session_count': 1, 'access_dates': [today_str], 'studied_words': []}
    
    try:
        doc_id = f"user_{user_name.strip()}"
        doc_ref = db.collection('japanese_app_users').document(doc_id)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            stored_pw = data.get('password', '')
            
            if stored_pw == '' or stored_pw == password.strip():
                if stored_pw == '' and password.strip() != '':
                    doc_ref.update({'password': password.strip()})
                
                # 접속 날짜 관리 및 접속 일수 카운트
                access_dates = data.get('access_dates', [])
                if today_str not in access_dates:
                    access_dates.append(today_str)
                    doc_ref.update({'access_dates': access_dates, 'session_count': len(access_dates)})
                
                session_count = len(access_dates) if access_dates else data.get('session_count', 1)
                
                return {
                    'status': 'success',
                    'session_count': session_count,
                    'access_dates': access_dates,
                    'studied_words': data.get('studied_words', [])
                }
            else:
                return {'status': 'wrong_password'}
        else:
            # 신규 사용자 등록 (첫 접속일 등록)
            access_dates = [today_str]
            doc_ref.set({
                'user_name': user_name.strip(),
                'password': password.strip(),
                'session_count': 1,
                'access_dates': access_dates,
                'studied_words': []
            })
            return {
                'status': 'success',
                'session_count': 1,
                'access_dates': access_dates,
                'studied_words': []
            }
            
    except Exception as e:
        st.error(f"DB 오류: {e}")
        return {'status': 'error', 'message': str(e)}

def save_db_progress(user_name, password, session_count, studied_words, access_dates=None):
    if db:
        try:
            doc_id = f"user_{user_name.strip()}"
            doc_ref = db.collection('japanese_app_users').document(doc_id)
            update_data = {
                'user_name': user_name.strip(),
                'password': password.strip(),
                'session_count': session_count,
                'studied_words': studied_words
            }
            if access_dates is not None:
                update_data['access_dates'] = access_dates
            doc_ref.set(update_data, merge=True)
        except Exception as e:
            st.error(f"진행도 저장 오류: {e}")

def get_all_users():
    users_list = []
    if db:
        try:
            docs = db.collection('japanese_app_users').stream()
            for doc in docs:
                data = doc.to_dict()
                users_list.append({
                    '이름': data.get('user_name', '알수없음'),
                    '접속 일수': data.get('session_count', len(data.get('access_dates', [1]))),
                    '학습완료 한자 수': len(data.get('studied_words', [])),
                    'doc_id': doc.id
                })
        except Exception as e:
            st.error(f"전체 목록 로드 오류: {e}")
    return users_list

def delete_user(doc_id):
    if db:
        try:
            db.collection('japanese_app_users').document(doc_id).delete()
            return True
        except Exception as e:
            st.error(f"삭제 오류: {e}")
    return False

# ==========================================
# 2. 프리미엄 팝 & 게임 UI 커스텀 CSS
# ==========================================
st.set_page_config(page_title="한자 마스터!", page_icon="🎮", layout="centered")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #fff9e6 0%, #f7f1e3 100%);
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
}

h1, h2, h3, p, span, div { color: #2c3e50; }

.player-card {
    background: #ffffff;
    border: 3px solid #2d3436;
    border-radius: 18px;
    padding: 16px 20px;
    box-shadow: 5px 5px 0px #2d3436;
    margin-bottom: 20px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
}

.player-info-title {
    font-size: 13px;
    font-weight: 800;
    color: #636e72;
    margin: 0;
}

.player-badge {
    display: inline-block;
    background: #ffeaa7;
    border: 2px solid #2d3436;
    padding: 4px 12px;
    border-radius: 12px;
    font-weight: 900;
    font-size: 13px;
    color: #2d3436;
    box-shadow: 2px 2px 0px #2d3436;
    margin-left: 4px;
}

.flip-container {
    perspective: 1000px;
    width: 100%;
    margin: 15px auto 25px auto;
}

.flip-toggle { display: none; }

.flipper {
    transition: transform 0.6s cubic-bezier(0.4, 0.2, 0.2, 1);
    transform-style: preserve-3d;
    position: relative;
    height: 380px;
    cursor: pointer;
}

.flip-toggle:checked + .flipper { transform: rotateY(180deg); }

.front, .back {
    backface-visibility: hidden;
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    border-radius: 24px;
    border: 4px solid #2d3436;
    box-shadow: 8px 8px 0px #2d3436;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    background-color: #ffffff;
    padding: 20px;
    box-sizing: border-box;
}

.back {
    transform: rotateY(180deg);
    background: linear-gradient(180deg, #ffffff 0%, #fffdf9 100%);
}

.level-badge {
    background-color: #4ecdc4;
    color: #ffffff;
    padding: 6px 18px;
    border-radius: 20px;
    border: 3px solid #2d3436;
    font-size: 15px;
    font-weight: 900;
    margin-bottom: 12px;
    box-shadow: 3px 3px 0px #2d3436;
    letter-spacing: 1px;
}

.kanji-text {
    font-size: 90px;
    font-weight: 900;
    margin: 5px 0;
    color: #2d3436;
    text-shadow: 2px 2px 0px #dfe6e9;
}

.reading-text {
    font-size: 32px;
    font-weight: 900;
    margin: 8px 0;
    color: #0984e3;
}

.meaning-text {
    font-size: 28px;
    font-weight: 900;
    color: #d63031;
    margin: 5px 0;
    padding: 0 10px;
    text-align: center;
}

.example-box {
    margin-top: 15px;
    padding: 14px 18px;
    background-color: #ffeaa7;
    border-radius: 16px;
    width: 90%;
    border: 3px solid #2d3436;
    box-shadow: 4px 4px 0px #2d3436;
    text-align: center;
}

div[data-testid="stButton"] button {
    border: 3px solid #2d3436 !important;
    box-shadow: 4px 4px 0px #2d3436 !important;
    border-radius: 14px !important;
    font-weight: 900 !important;
    font-size: 16px !important;
    padding: 12px 20px !important;
    transition: all 0.15s ease !important;
}

div[data-testid="stButton"] button:hover {
    transform: translateY(-2px);
    box-shadow: 6px 6px 0px #2d3436 !important;
}

div[data-testid="stButton"] button:active {
    box-shadow: 0px 0px 0px #2d3436 !important;
    transform: translateY(4px) translateX(4px) !important;
}

div[data-testid="stButton"] button[kind="primary"] {
    background-color: #55efc4 !important;
    color: #2d3436 !important;
}

.stProgress > div > div > div > div {
    background-color: #ff7675;
    border-radius: 10px;
}
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

# --- [비밀 관리자 조종실 (사이드바)] ---
with st.sidebar:
    st.header("🤖 관리자 조종실")
    admin_pw = st.text_input("관리자 비밀번호", type="password")
    
    if admin_pw == "0000":
        st.success("✅ 관리자 인증 완료")
        
        tab1, tab2 = st.tabs(["🤖 AI 단어 생성", "👥 전체 사용자 관리"])
        
        with tab1:
            gen_level = st.selectbox("생성할 급수", ["N5", "N4", "N3", "N2", "N1"])
            gen_count = st.number_input("생성할 단어 개수", min_value=5, max_value=30, value=10)
            
            if st.button("🚀 단어 생성 및 시트 업데이트"):
                if "GEMINI_API_KEY" not in st.secrets:
                    st.error("스트림릿 Secrets에 GEMINI_API_KEY가 없습니다!")
                else:
                    with st.spinner(f"AI가 {gen_level} 단어 {gen_count}개를 수집하고 있습니다..."):
                        try:
                            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                            model = genai.GenerativeModel('gemini-3.6-flash')
                            
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
                            ai_text = response.text.strip().replace("```csv", "").replace("```", "").strip()
                            
                            new_rows = []
                            for line in ai_text.split('\n'):
                                if line.strip():
                                    row_data = [item.strip() for item in line.split(',')]
                                    if len(row_data) == 6:
                                        new_rows.append(row_data)
                            
                            if new_rows and gc:
                                sheet = gc.open_by_key(SHEET_ID).sheet1
                                sheet.append_rows(new_rows)
                                st.success(f"🎉 성공적으로 {len(new_rows)}개의 단어를 구글 시트에 추가했습니다!")
                                st.cache_data.clear()
                            else:
                                st.error("데이터 추가 실패: 형식을 확인하세요.")
                                
                        except Exception as e:
                            st.error(f"오류 발생: {e}")
        
        with tab2:
            st.subheader("📊 등록된 플레이어 현황")
            all_users = get_all_users()
            if all_users:
                df_users = pd.DataFrame(all_users)
                st.dataframe(df_users[['이름', '접속 일수(회차)', '학습완료 한자 수']], use_container_width=True)
                
                st.markdown("---")
                st.subheader("🗑️ 특정 사용자 데이터 삭제")
                user_to_delete = st.selectbox("삭제할 사용자 선택", [u['이름'] for u in all_users])
                if st.button("❌ 선택한 사용자 삭제", type="primary"):
                    target = next((u for u in all_users if u['이름'] == user_to_delete), None)
                    if target and delete_user(target['doc_id']):
                        st.success(f"'{user_to_delete}' 유저 삭제 완료!")
                        st.rerun()
            else:
                st.info("등록된 사용자가 없습니다.")

# ==========================================
# 4. 메인 화면 UI 및 사용자별 학습 로직
# ==========================================
st.markdown("<h1 style='text-align: center; font-size: 40px; font-weight: 900; margin-bottom: 20px;'>🎮 JLPT 한자 마스터!</h1>", unsafe_allow_html=True)

# 4-1. 로그인 및 프로필 설정 영역
col_user, col_pw, col_level = st.columns(3)

with col_user:
    user_name = st.text_input("👤 플레이어 이름", value="홍길동", help="처음 입력 시 자동으로 새 계정이 생성됩니다.").strip()

with col_pw:
    user_pw = st.text_input("🔑 비밀번호", type="password", help="계정보호를 위한 비밀번호를 입력하세요.").strip()

with col_level:
    selected_level = st.selectbox("🎯 학습 급수", ["N5", "N4", "N3", "N2", "N1"])

if not user_name:
    st.info("👋 플레이어 이름을 입력하고 로그인해 주세요!")
    st.stop()

if not user_pw:
    st.warning("🔒 계정 보호를 위해 비밀번호를 입력해 주세요. (신규 생성 시 해당 비밀번호로 설정됩니다)")
    st.stop()

# 사용자 로그인/인증 검사
auth_result = authenticate_and_load(user_name, user_pw)

if auth_result['status'] == 'wrong_password':
    st.error("❌ 비밀번호가 일치하지 않습니다! 정확한 비밀번호를 입력해 주세요.")
    st.stop()
elif auth_result['status'] == 'error':
    st.error("⚠️ 데이터베이스 연결 중 오류가 발생했습니다.")
    st.stop()

# 로그인 성공 처리
if 'current_user' not in st.session_state or st.session_state.current_user != user_name:
    st.session_state.current_user = user_name
    st.session_state.db_progress = auth_result
    st.session_state.session_count = auth_result['session_count']
    st.session_state.current_index = 0
    for key in list(st.session_state.keys()):
        if key.startswith('vocab_'):
            del st.session_state[key]
else:
    st.session_state.db_progress = auth_result

if 'current_level' not in st.session_state or st.session_state.current_level != selected_level:
    st.session_state.current_level = selected_level
    st.session_state.current_index = 0

# 4-2. 사용자 대시보드 상태 바
total_studied = len(st.session_state.db_progress.get('studied_words', []))
session_cnt = st.session_state.session_count

st.markdown(f"""
<div class="player-card">
    <div>
        <span class="player-info-title">LOGGED IN PLAYER</span><br>
        <span style="font-size: 19px; font-weight: 900; color: #2d3436;">👤 {user_name} 님</span>
    </div>
    <div>
        <span class="player-badge">🔥 {session_cnt}일차 접속</span>
        <span class="player-badge" style="background-color: #74b9ff; color: white;">⭐ 학습완료: {total_studied}개</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 사용자별 + 급수별 단어 세션 (랜덤 셔플 로직 적용)
session_key = f'vocab_{selected_level}_{user_name}'
if session_key not in st.session_state:
    df = load_data(selected_level)
    df['studied'] = df['kanji'].isin(st.session_state.db_progress['studied_words'])
    
    # [1] 단어 무작위 셔플 (Unstudied 단어를 무작위로 섞음)
    unstudied_df = df[df['studied'] == False].sample(frac=1).reset_index(drop=True)
    studied_df = df[df['studied'] == True]
    st.session_state[session_key] = pd.concat([unstudied_df, studied_df]).reset_index(drop=True)

df = st.session_state[session_key]
todays_words = df[df['studied'] == False].head(15)

# 4-3. 카드 학습 화면
if not todays_words.empty and st.session_state.current_index < len(todays_words):
    current_word = todays_words.iloc[st.session_state.current_index]
    
    # 프로그레스 바
    progress_val = st.session_state.current_index / len(todays_words)
    st.progress(progress_val)
    st.markdown(f"<div style='text-align: right; font-weight: 900; font-size: 14px; color: #636e72; margin-top: -10px;'>오늘의 {selected_level} 달성도: {st.session_state.current_index + 1} / {len(todays_words)}</div>", unsafe_allow_html=True)
    
    example_html = ""
    if pd.notna(current_word.get('example_ja')) and current_word.get('example_ja') != "":
        example_html = f"""<div class="example-box">
<p style="font-size: 16px; margin: 0 0 4px 0; font-weight: 900; color: #2d3436;">{current_word['example_ja']}</p>
<p style="font-size: 13px; margin: 0; font-weight: 700; color: #636e72;">{current_word['example_ko']}</p></div>"""

    front_reading_html = ""
    if current_word['level'] in ['N5', 'N4', 'N3']:
        front_reading_html = f'<h3 style="font-size: 14px; font-weight: 900; color: #ff7675; margin: 0 0 -5px 0;">{current_word["reading"]}</h3>'

    card_html = f"""
<div class="flip-container"><label>
<input type="checkbox" class="flip-toggle" id="toggle-{selected_level}-{st.session_state.current_index}">
<div class="flipper"><div class="front">
<span class="level-badge">JLPT {current_word['level']}</span>
{front_reading_html}
<h1 class="kanji-text">{current_word['kanji']}</h1>
<p style="font-size: 14px; font-weight: 900; color: #b2bec3; margin-top: 15px;">카드 터치 ➔ 정답 확인 👆</p>
</div><div class="back">
<span class="level-badge" style="background-color: #ff7675;">JLPT {current_word['level']}</span>
<h2 class="reading-text">📖 {current_word['reading']}</h2>
<h1 class="meaning-text">💡 {current_word['meaning']}</h1>
{example_html}
</div></div></label></div>
"""
    st.markdown(card_html, unsafe_allow_html=True)
    
    try:
        tts = gTTS(text=current_word['reading'], lang='ja')
        audio_bytes = io.BytesIO()
        tts.write_to_fp(audio_bytes)
        st.audio(audio_bytes, format='audio/mp3')
    except Exception: pass
        
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("❌ 다시 복습하기", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()
    with col2:
        if st.button("⭕ 학습 완료!", type="primary", use_container_width=True):
            word_index = current_word.name 
            st.session_state[session_key].at[word_index, 'studied'] = True
            if current_word['kanji'] not in st.session_state.db_progress['studied_words']:
                st.session_state.db_progress['studied_words'].append(current_word['kanji'])
                save_db_progress(
                    user_name,
                    user_pw,
                    st.session_state.session_count,
                    st.session_state.db_progress['studied_words'],
                    st.session_state.db_progress.get('access_dates')
                )
            st.session_state.current_index += 1
            st.rerun()
else:
    st.success(f"🎉 축하합니다! {user_name}님의 {selected_level} 학습을 완료했습니다!")
    if st.button("다음 단어 계속 학습하기 🚀", type="primary", use_container_width=True):
        st.session_state.current_index = 0
        # 다음 세트를 위한 셔플 재실행
        if session_key in st.session_state:
            df_temp = st.session_state[session_key]
            unstudied_temp = df_temp[df_temp['studied'] == False].sample(frac=1).reset_index(drop=True)
            studied_temp = df_temp[df_temp['studied'] == True]
            st.session_state[session_key] = pd.concat([unstudied_temp, studied_temp]).reset_index(drop=True)
            
        save_db_progress(
            user_name,
            user_pw,
            st.session_state.session_count,
            st.session_state.db_progress['studied_words'],
            st.session_state.db_progress.get('access_dates')
        )
        st.rerun()