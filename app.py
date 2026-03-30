import streamlit as st
from moviepy import VideoFileClip, ColorClip, CompositeVideoClip, TextClip, concatenate_videoclips, ImageClip
import os
import time
import traceback
import json

# 💡 [수정] 라이브러리 호출 방식을 기존 안정 버전으로 변경
import google.generativeai as genai

# --- 1. [핵심] 진짜 구글 Gemini AI 엔진 ---
def analyze_video_with_gemini(file_path, api_key, custom_prompt, status_box):
    try:
        # 파일 확장자 확인
        is_image = file_path.lower().endswith(('.png', '.jpg', '.jpeg'))
        type_str = "사진" if is_image else "영상"
        
        status_box.info(f"🤖 AI가 {type_str}을 분석 중입니다...")
        genai.configure(api_key=api_key)
        
        # 파일 업로드 (이미지/영상 모두 지원)
        myfile = genai.upload_file(path=file_path)
        
        while myfile.state.name == "PROCESSING":
            time.sleep(2)
            myfile = genai.get_file(myfile.name)

        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        # 이미지일 경우 '시간' 개념이 없으므로 프롬프트를 분기합니다.
        if is_image:
            prompt = f"""
            첨부된 사진을 분석하여 아래 [요청사항]에 맞는 숏츠용 자막을 작성하세요.
            [요청사항]: "{custom_prompt}"
            🚨 [JSON 형식 필수]: {{"start": 0, "end": 2, "subtitle": "추천 자막"}}
            """
        else:
            prompt = f"""
            첨부된 영상을 분석하여 하이라이트 구간과 자막을 작성하세요.
            [요청사항]: "{custom_prompt}"
            🚨 [JSON 형식 필수]: {{"start": 시작초, "end": 종료초, "subtitle": "추천 자막"}}
            """
        
        response = model.generate_content([myfile, prompt])
        genai.delete_file(myfile.name)
        
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)

    except Exception as e:
        status_box.error(f"🚨 AI 분석 에러: {e}"); st.stop()

# --- 2. 개별 클립 '번개 미리보기' 생성 엔진 ---
def create_fast_preview(data, output_path, status_box, font_path, font_size, text_color, stroke_color, stroke_width, y_pos_percent):
    try:
        PREVIEW_W, PREVIEW_H = 270, 480 
        status_box.info("⚡ 빠른 미리보기 영상을 생성 중입니다...")
        
        clip = VideoFileClip(data['path']).subclipped(data['start'], data['end'])
        bg = ColorClip(size=(PREVIEW_W, PREVIEW_H), color=(0, 0, 0)).with_duration(clip.duration)
        w, h = clip.size
        resized = clip.resized(width=PREVIEW_W) if w > h else clip.resized(height=PREVIEW_H)
        
        preview_font_size = int(font_size * 0.5)
        preview_stroke_width = max(1, int(stroke_width * 0.5)) if stroke_width > 0 else 0
        
        txt_kwargs = {
            "text": data['subtitle'] + "\n",
            "font": font_path, "font_size": preview_font_size,
            "color": text_color, "size": (PREVIEW_W - 30, None), "method": "caption"
        }
        if stroke_width > 0:
            txt_kwargs["stroke_color"] = stroke_color
            txt_kwargs["stroke_width"] = preview_stroke_width

        txt = TextClip(**txt_kwargs).with_duration(clip.duration)
        final_y = (PREVIEW_H / 2) + (PREVIEW_H * (y_pos_percent / 100))
        final_clip = CompositeVideoClip([bg, resized.with_position("center"), txt.with_position(("center", final_y))])
        
        final_clip.write_videofile(output_path, fps=15, codec="libx264", audio_codec="aac", preset="ultrafast", logger=None)
        final_clip.close()
        clip.close()
        status_box.empty()
        return True
    except Exception as e:
        status_box.error(f"미리보기 실패: {e}")
        return False

# --- 3. 최종 비디오 합성 엔진 (FHD) ---
def render_final_video(clips_data, output_path, status_box, font_path, font_size, text_color, stroke_color, stroke_width, y_pos_percent):
    try:
        processed_clips = []
        TARGET_W, TARGET_H = 1080, 1920 
        hd_font_size = font_size * 2
        hd_stroke_width = stroke_width * 2

        for i, data in enumerate(clips_data):
            if data.get("is_image"):
                # 💡 이미지를 2초짜리 영상 클립으로 변환
                clip = ImageClip(data['path']).with_duration(data['end'] - data['start']).with_fps(30)
            else:
                # 기존 영상 클립 처리
                clip = VideoFileClip(data['path']).subclipped(data['start'], data['end']).with_fps(30)
            bg = ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0)).with_duration(clip.duration)
            w, h = clip.size
            resized = clip.resized(width=TARGET_W) if w / h > TARGET_W / TARGET_H else clip.resized(height=TARGET_H)
            
            txt_kwargs = {
                "text": data['subtitle'] + "\n",
                "font": font_path, "font_size": hd_font_size,
                "color": text_color, "size": (TARGET_W - 100, None), "method": "caption"
            }
            if hd_stroke_width > 0:
                txt_kwargs["stroke_color"] = stroke_color
                txt_kwargs["stroke_width"] = hd_stroke_width

            txt = TextClip(**txt_kwargs).with_duration(clip.duration)
            final_y = (TARGET_H / 2) + (TARGET_H * (y_pos_percent / 100))
            final_clip = CompositeVideoClip([bg, resized.with_position("center"), txt.with_position(("center", final_y))])
            processed_clips.append(final_clip)

        status_box.info("🚀 고화질 전체 영상 렌더링 중...")
        final_video = concatenate_videoclips(processed_clips, method="compose")
        final_video.write_videofile(output_path, fps=30, codec="libx264", audio_codec="aac", preset="medium")
        final_video.close()
        for c in processed_clips: c.close()
        return True
    except Exception as e:
        st.error(f"렌더링 에러: {traceback.format_exc()}")
        return False

# --- 4. Streamlit UI 구성 ---
st.set_page_config(page_title="Minorious Short Maker", layout="wide")

# 비밀 금고에서 키 가져오기
user_api_key = st.secrets["GEMINI_API_KEY"]

with st.sidebar:
    st.header("🎨 자막 스타일 설정")
    font_dict = {"기본 폰트": "myfont.ttf"}
    sel_font_name = st.selectbox("기본 폰트 선택", list(font_dict.keys()))
    global_font_path = font_dict[sel_font_name]
    
    st.subheader("🔠 나만의 폰트 추가")
    custom_font = st.file_uploader("폰트 파일 업로드", type=["ttf", "otf"])
    if custom_font is not None:
        global_font_path = os.path.abspath("temp_custom_font.ttf")
        with open(global_font_path, "wb") as f: f.write(custom_font.getbuffer())
        st.success(f"✅ 적용 완료!")
    
    st.markdown("---")
    color_dict = {"흰색": "white", "검정색": "black", "노란색": "yellow", "빨간색": "red", "파란색": "blue", "초록색": "green", "분홍색": "pink", "회색": "gray"}
    sel_text_color_kor = st.selectbox("글자 색상", list(color_dict.keys()), index=0) 
    sel_stroke_color_kor = st.selectbox("테두리 색상", list(color_dict.keys()), index=1) 
    global_text_color = color_dict[sel_text_color_kor]
    global_stroke_color = color_dict[sel_stroke_color_kor]
    
    global_font_size = st.slider("글자 크기", 20, 80, 45)
    global_stroke_width = st.slider("테두리 두께", 0, 10, 3) 
    
    st.markdown("---")
    st.subheader("📍 자막 위치")
    global_y_pos_percent = st.slider("세로 위치 (정중앙 0%)", -45, 45, 30, format="%d%%")

if 'clips' not in st.session_state: st.session_state.clips = []
if 'analyzed' not in st.session_state: st.session_state.analyzed = False

st.title("🎬 숏츠 편집하기(Made by minorious)")

up_files = st.file_uploader("동영상 파일 업로드", type=["mp4", "mov"], accept_multiple_files=True)

default_prompt = "이 영상에서 핵심 정보가 잘 전달되는 5초 이하의 구간을 찾고 그 구간을 선정해서 차분한 말투로 요약된 자막을 써줘."
user_custom_prompt = st.text_area("🧠 AI 지시사항(프롬프트 직접 편집가능)", value=default_prompt, height=80)

if st.button("🔍 1단계: AI 자동 분석 시작"):
    if up_files:
        st.session_state.clips = []
        uid = int(time.time())
        status_box = st.empty()
        
        for i, f in enumerate(up_files):
            tmp_p = f"temp_{uid}_{i}_{f.name}"
            with open(tmp_p, "wb") as out: out.write(f.getbuffer())
            
            ai_res = analyze_video_with_gemini(tmp_p, user_api_key, user_custom_prompt, status_box)
            
            # 💡 [핵심] 이미지 파일일 경우 처리 로직
            if tmp_p.lower().endswith(('.png', '.jpg', '.jpeg')):
                duration = 2.0 # 💡 말씀하신 2초 설정
                st.session_state.clips.append({
                    "path": tmp_p, "name": f.name, "total": duration,
                    "start": 0.0, "end": duration, 
                    "subtitle": ai_res['subtitle'], "preview_path": None,
                    "is_image": True # 이미지임을 표시
                })
            else:
                # 영상 파일 처리 (기존 로직)
                with VideoFileClip(tmp_p) as v:
                    dur = v.duration
                    st.session_state.clips.append({
                        "path": tmp_p, "name": f.name, "total": dur,
                        "start": ai_res['start'], "end": ai_res['end'], 
                        "subtitle": ai_res['subtitle'], "preview_path": None,
                        "is_image": False
                    })

if st.session_state.analyzed:
    col_left, col_right = st.columns([1, 1.2])
    with col_right:
        st.subheader("✂️ 개별 클립 정밀 편집")
        total_final_dur = 0
        for i, c in enumerate(st.session_state.clips):
            with st.expander(f"클립 #{i+1}: {c['name']}", expanded=True):
                s, e = st.slider(f"구간", 0.0, c['total'], (c['start'], c['end']), key=f"range_{i}")
                st.session_state.clips[i]['start'], st.session_state.clips[i]['end'] = s, e
                sub = st.text_area("자막 수정", value=c['subtitle'], key=f"sub_{i}")
                st.session_state.clips[i]['subtitle'] = sub
                total_final_dur += (e - s)
                p_status = st.empty()
                if st.button(f"▶️ 미리보기 생성", key=f"btn_{i}"):
                    p_path = f"prev_{int(time.time())}_{i}.mp4"
                    if create_fast_preview(st.session_state.clips[i], p_path, p_status, global_font_path, global_font_size, global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent):
                        st.session_state.clips[i]['preview_path'] = p_path
                if st.session_state.clips[i].get('preview_path'):
                    st.video(st.session_state.clips[i]['preview_path'])
        
        st.divider()
        if st.button("🚀 2단계: 최종 숏츠 완성하기", use_container_width=True):
            s_box = st.empty(); out_p = f"final_{int(time.time())}.mp4"
            if render_final_video(st.session_state.clips, out_p, s_box, global_font_path, global_font_size, global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent):
                st.session_state.final_video_path = out_p; st.rerun()

    with col_left:
        st.subheader("📺 결과물 전체 미리보기")
        if 'final_video_path' in st.session_state and os.path.exists(st.session_state.final_video_path):
            st.video(st.session_state.final_video_path)
            with open(st.session_state.final_video_path, "rb") as f:
                st.download_button("💾 다운로드", f, file_name="ai_shorts.mp4")
