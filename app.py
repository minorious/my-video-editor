import streamlit as st
from moviepy import VideoFileClip, ColorClip, CompositeVideoClip, TextClip, concatenate_videoclips, ImageClip
import os
import time
import traceback
import json
import google.generativeai as genai

# 💡 [여기 추가됨] 사진 방향을 잡아주기 위한 새로운 준비물 2개
from PIL import Image, ImageOps
import numpy as np

# --- 1. [핵심] 진짜 구글 Gemini AI 엔진 ---
def analyze_video_with_gemini(file_path, api_key, custom_prompt, status_box, progress_bar):
    try:
        is_image = file_path.lower().endswith(('.png', '.jpg', '.jpeg'))
        
        progress_bar.progress(10, text="📡 구글 AI 서버에 연결 중...")
        genai.configure(api_key=api_key)
        
        progress_bar.progress(30, text="📤 파일을 업로드하고 있습니다...")
        myfile = genai.upload_file(path=file_path)
        
        p_val = 50
        while myfile.state.name == "PROCESSING":
            if p_val < 85: p_val += 5
            progress_bar.progress(p_val, text=f"🤖 AI가 내용을 파악 중입니다... ({p_val}%)")
            time.sleep(3)
            myfile = genai.get_file(myfile.name)
            
        progress_bar.progress(90, text="📝 자막과 하이라이트를 작성하는 중...")
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")

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
            🚨 [JSON 형식 필수]: {{"start": 1.0, "end": 6.0, "subtitle": "요약 자막"}}
            """
        
        response = model.generate_content([myfile, prompt])
        genai.delete_file(myfile.name)
        
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw_text)
        
        progress_bar.progress(100, text="✅ 분석 완료!")
        return result

    except Exception as e:
        status_box.error(f"🚨 AI 분석 에러: {e}")
        st.stop()

# --- 2. 개별 클립 '번개 미리보기' 생성 엔진 ---
def create_fast_preview(data, output_path, status_box, font_path, font_size, text_color, stroke_color, stroke_width, y_pos_percent):
    try:
        PREVIEW_W, PREVIEW_H = 270, 480 
        status_box.info("⚡ 빠른 미리보기 생성 중...")
        
        if data.get("is_image"):
            # 💡 [여기 추가됨] 스마트폰 사진이 눕지 않게 똑바로 세워주는 마법의 코드
            img = Image.open(data['path'])
            img = ImageOps.exif_transpose(img) # 사진의 원래 방향(세로)을 찾아줍니다!
            clip = ImageClip(np.array(img)).with_duration(data['end'] - data['start'])
        else:
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
                # 💡 [여기 추가됨] 최종 완성본을 만들 때도 사진을 똑바로 세워줍니다!
                img = Image.open(data['path'])
                img = ImageOps.exif_transpose(img)
                clip = ImageClip(np.array(img)).with_duration(data['end'] - data['start']).with_fps(30)
            else:
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

        status_box.info("🚀 최종 렌더링 중...")
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
user_api_key = st.secrets["GEMINI_API_KEY"]

with st.sidebar:
    st.header("🎨 자막 스타일 설정")
    font_dict = {"기본 폰트": "myfont.ttf"}
    sel_font_name = st.selectbox("기본 폰트 선택", list(font_dict.keys()))
    global_font_path = font_dict[sel_font_name]
    
    custom_font = st.file_uploader("폰트 파일 업로드", type=["ttf", "otf"])
    if custom_font is not None:
        global_font_path = os.path.abspath("temp_custom_font.ttf")
        with open(global_font_path, "wb") as f: f.write(custom_font.getbuffer())
        st.success(f"✅ 적용 완료!")
    
    st.markdown("---")
    color_dict = {"흰색": "white", "검정색": "black", "노란색": "yellow", "빨간색": "red", "파란색": "blue", "초록색": "green", "분홍색": "pink", "회색": "gray"}
    global_text_color = color_dict[st.selectbox("글자 색상", list(color_dict.keys()), index=0)]
    global_stroke_color = color_dict[st.selectbox("테두리 색상", list(color_dict.keys()), index=1)]
    global_font_size = st.slider("글자 크기", 20, 80, 45)
    global_stroke_width = st.slider("테두리 두께", 0, 10, 3) 
    global_y_pos_percent = st.slider("세로 위치 (정중앙 0%)", -45, 45, 0, step=1, format="%d%%")

if 'clips' not in st.session_state: st.session_state.clips = []
if 'analyzed' not in st.session_state: st.session_state.analyzed = False

st.title("🎬 숏츠 쉽게만들기(Made by minorious)")
up_files = st.file_uploader("동영상 및 사진 업로드", type=["mp4", "mov", "jpg", "jpeg", "png"], accept_multiple_files=True)
user_custom_prompt = st.text_area("🧠 AI 지시사항", value="이 영상에서 핵심 정보가 잘 전달되는 5초 이하의 구간을 찾고 요약 자막을 써줘.", height=80)

if st.button("🔍 1단계: AI 자동 분석 시작"):
    if up_files:
        st.session_state.clips = []
        uid = int(time.time())
        status_box = st.empty()
        my_bar = st.progress(0)
        
        for i, f in enumerate(up_files):
            tmp_p = f"temp_{uid}_{i}_{f.name}"
            with open(tmp_p, "wb") as out: out.write(f.getbuffer())
            
            ai_res = analyze_video_with_gemini(tmp_p, user_api_key, user_custom_prompt, status_box, my_bar)
            
            is_img = tmp_p.lower().endswith(('.png', '.jpg', '.jpeg'))
            if is_img:
                st.session_state.clips.append({
                    "path": tmp_p, "name": f.name, "total": 2.0, "start": 0.0, "end": 2.0, 
                    "subtitle": ai_res['subtitle'], "preview_path": None, "is_image": True
                })
            else:
                with VideoFileClip(tmp_p) as v:
                    st.session_state.clips.append({
                        "path": tmp_p, "name": f.name, "total": v.duration, 
                        "start": ai_res['start'], "end": ai_res['end'], 
                        "subtitle": ai_res['subtitle'], "preview_path": None, "is_image": False
                    })
        
        my_bar.empty()
        st.session_state.analyzed = True
        st.rerun()

# --- 편집 화면 ---
if st.session_state.analyzed:
    col_left, col_right = st.columns([1.5, 1])
    with col_right:
        st.subheader("✂️ 순서 및 편집")
        for i, c in enumerate(st.session_state.clips):
            cols = st.columns([0.1, 0.1, 0.1, 0.7])
            if cols[0].button("🔼", key=f"up_{i}") and i > 0:
                st.session_state.clips[i], st.session_state.clips[i-1] = st.session_state.clips[i-1], st.session_state.clips[i]
                st.rerun()
            if cols[1].button("🔽", key=f"down_{i}") and i < len(st.session_state.clips) - 1:
                st.session_state.clips[i], st.session_state.clips[i+1] = st.session_state.clips[i+1], st.session_state.clips[i]
                st.rerun()
            if cols[2].button("🗑️", key=f"del_{i}"):
                st.session_state.clips.pop(i)
                st.rerun()
            cols[3].write(f"**{i+1}:** {c['name']}")

            with st.expander(f"⚙️ 상세 설정", expanded=False):
                if not c.get('is_image'):
                    s, e = st.slider(f"구간", 0.0, c['total'], (c['start'], c['end']), key=f"range_{i}")
                    st.session_state.clips[i]['start'], st.session_state.clips[i]['end'] = s, e
                sub = st.text_area("자막", value=c['subtitle'], key=f"sub_{i}")
                st.session_state.clips[i]['subtitle'] = sub
                if st.button(f"▶️ 미리보기", key=f"btn_{i}"):
                    p_path = f"prev_{int(time.time())}_{i}.mp4"
                    create_fast_preview(st.session_state.clips[i], p_path, st.empty(), global_font_path, global_font_size, global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent)
                    st.session_state.clips[i]['preview_path'] = p_path
                if st.session_state.clips[i].get('preview_path'):
                    # 💡 [핵심] 양옆에 1만큼의 빈 공간, 가운데에 3만큼의 영상 공간을 할당합니다.
                    # 숫자를 조절해서 [1, 2, 1]로 하면 영상이 더 작아집니다!
                    space_left, video_col, space_right = st.columns([1, 3, 1])
                    with video_col:
                        st.video(st.session_state.clips[i]['preview_path'])

        if st.button("🚀 최종 숏츠 완성하기", use_container_width=True):
            out_p = f"final_{int(time.time())}.mp4"
            if render_final_video(st.session_state.clips, out_p, st.empty(), global_font_path, global_font_size, global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent):
                st.session_state.final_video_path = out_p; st.rerun()

    with col_left:
        st.subheader("📺 전체 미리보기")
        if 'final_video_path' in st.session_state and os.path.exists(st.session_state.final_video_path):
            st.video(st.session_state.final_video_path)
            with open(st.session_state.final_video_path, "rb") as f:
                st.download_button("💾 다운로드", f, file_name="ai_shorts.mp4")
