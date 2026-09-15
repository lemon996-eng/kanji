import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, firestore
import json

import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os # 파일이 있는지 확인하기 위해 추가된 모듈

# ==========================================
# 1. 파이어베이스 연동 (오류 해결 버전)
# ==========================================
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            # 1. 내 컴퓨터(로컬)에 'firebase_key.json' 파일이 있다면 이걸 사용
            if os.path.exists('firebase_key.json'):
                cred = credentials.Certificate('firebase_key.json')
            # 2. 파일이 없다면 스트림릿 클라우드(웹)라고 판단하고 비밀 금고에서 읽어옴
            else:
                key_dict = json.loads(st.secrets["firebase_json"])
                cred = credentials.Certificate(key_dict)
            
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"⚠️ 파이어베이스 연결 오류: {e}")
            
    return firestore.client() if firebase_admin._apps else None

db = init_firebase()

# 내 학습 기록이 저장될 DB 문서 위치 지정
if db:
    doc_ref = db.collection('japanese_app').document('my_progress')
else:
    doc_ref = None

# (이하 2번 CSS 설정부터는 기존 코드와 동일합니다)

# DB에서 기록 불러오기 함수
def load_db_progress():
    if doc_ref:
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
    return {'session_count': 1, 'studied_words': []}

# DB에 기록 저장하기 함수
def save_db_progress(session_count, studied_words):
    if doc_ref:
        doc_ref.set({
            'session_count': session_count,
            'studied_words': studied_words
        })

# ==========================================
# 2. 팝 앤 게임 (Pop & Playful) 테마 CSS
# ==========================================
st.markdown("""
<style>
.stApp { background-color: #fff9e6; }
h1, h2, h3, p, span, div { color: #000; }
.flip-container { perspective: 1000px; width: 100%; margin: 10px auto 20px auto; }
.flip-toggle { display: none; }
.flipper { transition: 0.6s; transform-style: preserve-3d; position: relative; height: 350px; cursor: pointer; }
.flip-toggle:checked + .flipper { transform: rotateY(180deg); }
.front, .back { backface-visibility: hidden; -webkit-backface-visibility: hidden; position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 16px; border: 4px solid #000; box-shadow: 6px 6px 0 #000; display: flex; flex-direction: column; justify-content: center; align-items: center; background-color: #fff; }
.back { transform: rotateY(180deg); }
.level-badge { background-color: #4ecdc4; color: #000; padding: 6px 16px; border-radius: 20px; border: 3px solid #000; font-size: 14px; font-weight: 900; margin-bottom: 10px; box-shadow: 3px 3px 0 #000; }
.kanji-text { font-size: 85px; font-weight: 900; color: #000; margin: 10px 0; }
.reading-text { font-size: 32px; font-weight: 900; color: #000; margin: 5px 0; }
.meaning-text { font-size: 28px; font-weight: 900; color: #ff6b6b; margin: 5px 0; padding: 0 10px; }
.example-box { margin-top: 15px; padding: 12px; background-color: #feca57; border-radius: 12px; width: 85%; border: 3px solid #000; box-shadow: 3px 3px 0 #000; }
div[data-testid="stButton"] button { border: 3px solid #000 !important; box-shadow: 4px 4px 0 #000 !important; border-radius: 12px !important; font-weight: 900 !important; color: #000 !important; padding: 10px !important; transition: all 0.1s !important; }
div[data-testid="stButton"] button:active { box-shadow: 0px 0px 0 #000 !important; transform: translateY(4px) translateX(4px) !important; }
div[data-testid="stButton"] button[kind="secondary"] { background-color: #fff !important; }
div[data-testid="stButton"] button[kind="primary"] { background-color: #feca57 !important; }
div[data-testid="stLinkButton"] a { border: 3px solid #000 !important; box-shadow: 4px 4px 0 #000 !important; border-radius: 12px !important; font-weight: 900 !important; color: #000 !important; background-color: #4ecdc4 !important; transition: all 0.1s !important; }
div[data-testid="stLinkButton"] a:active { box-shadow: 0px 0px 0 #000 !important; transform: translateY(4px) translateX(4px) !important; }
.stProgress > div > div > div { background-color: #ff6b6b !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. 단어 데이터 가져오기 및 DB 기록 병합
# ==========================================
@st.cache_data
def load_data(level):
    url = f"https://raw.githubusercontent.com/jamsinclair/open-anki-jlpt-decks/main/src/{level.lower()}.csv"
    try:
        df = pd.read_csv(url)
        if 'kana' in df.columns: df = df.rename(columns={'kana': 'reading'})
        if 'english' in df.columns: df = df.rename(columns={'english': 'meaning'})
        if 'kanji' not in df.columns and len(df.columns) >= 3:
             df = df.rename(columns={df.columns[0]: 'kanji', df.columns[1]: 'reading', df.columns[2]: 'meaning'})
        if 'kanji' in df.columns:
            df = df.dropna(subset=['kanji'])
        
        if 'example_ja' not in df.columns: df['example_ja'] = ""
        if 'example_ko' not in df.columns: df['example_ko'] = ""
        
        df['level'] = level.upper()
        return df.reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame({'kanji': ['食べる'], 'reading': ['たべる'], 'meaning': ['먹다'], 'example_ja': [''], 'example_ko': [''], 'level': [level]})

# ==========================================
# 4. 화면 UI 및 전역 상태 관리
# ==========================================
st.title("🎮 한자 마스터!")

if 'db_progress' not in st.session_state:
    st.session_state.db_progress = load_db_progress()
if 'session_count' not in st.session_state:
    st.session_state.session_count = st.session_state.db_progress['session_count']

selected_level = st.selectbox("학습할 JLPT 급수를 선택하세요:", ["N5", "N4", "N3", "N2", "N1"])

if 'current_level' not in st.session_state:
    st.session_state.current_level = selected_level
    st.session_state.current_index = 0
if st.session_state.current_level != selected_level:
    st.session_state.current_level = selected_level
    st.session_state.current_index = 0

session_key = f'vocab_{selected_level}'
if session_key not in st.session_state:
    df = load_data(selected_level)
    df['studied'] = df['kanji'].isin(st.session_state.db_progress['studied_words'])
    st.session_state[session_key] = df

# ==========================================
# 5. 카드 렌더링 및 학습 로직
# ==========================================
df = st.session_state[session_key]
todays_words = df[df['studied'] == False].head(15)

if not todays_words.empty and st.session_state.current_index < len(todays_words):
    current_word = todays_words.iloc[st.session_state.current_index]
    
    st.progress(st.session_state.current_index / len(todays_words))
    st.markdown(f"**🔄 학습 횟수: {st.session_state.session_count}회차 | 오늘의 {selected_level} 진행: {st.session_state.current_index + 1} / {len(todays_words)}**")
    
    example_html = ""
    if pd.notna(current_word.get('example_ja')) and current_word.get('example_ja') != "":
        example_html = f"""
<div class="example-box">
<p style="font-size: 15px; color: #000; margin: 0 0 5px 0; font-weight: 900;">{current_word['example_ja']}</p>
<p style="font-size: 13px; color: #333; margin: 0; font-weight: bold;">{current_word['example_ko']}</p>
</div>
"""

    card_html = f"""
<div class="flip-container">
<label>
<input type="checkbox" class="flip-toggle" id="toggle-{selected_level}-{st.session_state.current_index}">
<div class="flipper">
<div class="front">
<span class="level-badge">JLPT {current_word['level']}</span>
<h1 class="kanji-text">{current_word['kanji']}</h1>
<p style="font-size: 15px; font-weight: 900; color: #666; margin-top: 20px;">터치해서 정답 보기 👆</p>
</div>
<div class="back">
<span class="level-badge">JLPT {current_word['level']}</span>
<h2 class="reading-text">📖 {current_word['reading']}</h2>
<h1 class="meaning-text">💡 {current_word['meaning']}</h1>
{example_html}
</div>
</div>
</label>
</div>
"""
    st.markdown(card_html, unsafe_allow_html=True)
    
    st.link_button(f"🔍 '{current_word['kanji']}' 네이버 사전에서 보기", f"https://ja.dict.naver.com/#/search?query={current_word['kanji']}", use_container_width=True)
    
    try:
        tts = gTTS(text=current_word['reading'], lang='ja')
        audio_bytes = io.BytesIO()
        tts.write_to_fp(audio_bytes)
        st.audio(audio_bytes, format='audio/mp3')
    except Exception:
        pass
        
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("❌ 다시 복습", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()
    with col2:
        if st.button("⭕ 학습 완료", type="primary", use_container_width=True):
            word_index = current_word.name 
            st.session_state[session_key].at[word_index, 'studied'] = True
            
            kanji = current_word['kanji']
            if kanji not in st.session_state.db_progress['studied_words']:
                st.session_state.db_progress['studied_words'].append(kanji)
                save_db_progress(st.session_state.session_count, st.session_state.db_progress['studied_words'])
            
            st.session_state.current_index += 1
            st.rerun()

else:
    st.success(f"🎉 {st.session_state.session_count}회차 ({selected_level} 급수 15개) 학습을 모두 완료했습니다!")
    st.balloons()
    
    if st.button("다음 15개 단어 계속 학습하기 🚀", type="primary", use_container_width=True):
        st.session_state.current_index = 0
        st.session_state.session_count += 1
        
        save_db_progress(st.session_state.session_count, st.session_state.db_progress['studied_words'])
        
        if st.session_state.session_count % 30 == 0:
            current_df = st.session_state[session_key]
            studied_words = current_df[current_df['studied'] == True]
            
            if not studied_words.empty:
                random_idx = studied_words.sample(n=1).index[0]
                kanji_to_review = current_df.at[random_idx, 'kanji']
                
                current_df.at[random_idx, 'studied'] = False
                if kanji_to_review in st.session_state.db_progress['studied_words']:
                    st.session_state.db_progress['studied_words'].remove(kanji_to_review)
                    save_db_progress(st.session_state.session_count, st.session_state.db_progress['studied_words'])
                
                row_to_move = current_df.iloc[[random_idx]]
                current_df = current_df.drop(random_idx)
                current_df = pd.concat([row_to_move, current_df]).reset_index(drop=True)
                st.session_state[session_key] = current_df
                st.toast("🔄 세션 30회 달성! 과거에 외웠던 단어가 복습용으로 등장합니다.", icon="🎁")
        
        st.rerun()