import streamlit as st
from moviepy import VideoFileClip, ColorClip, CompositeVideoClip, TextClip, concatenate_videoclips
import os
import time
import traceback
import json

# 💡 [신규] 구글 AI 라이브러리 불러오기
import google.generativeai as genai

# --- 1. [핵심] 진짜 구글 Gemini AI 엔진 ---
def analyze_video_with_gemini(video_path, api_key, custom_prompt, status_box):
    try:
        status_box.info("🤖 AI가 영상을 시청하며 분석 중입니다... (약 10~30초 소요)")
        genai.configure(api_key=api_key)
        
        video_file = genai.upload_file(path=video_path)
        
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)
            
        if video_file.state.name == "FAILED":
            raise ValueError("영상 처리 실패")

        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        # 💡 [핵심] 파이썬이 에러 나지 않게 형식을 강제하면서, 사용자의 명령을 중간에 끼워 넣습니다!
        prompt = f"""
        당신은 전문 유튜브 숏츠 편집자입니다. 첨부된 영상을 끝까지 시청하세요.
        아래 [사용자 특별 요청사항]을 가장 우선적으로 반영하여 5초 이하의 하이라이트 구간을 찾고 자막을 작성하세요.
        
        [사용자 특별 요청사항]
        "{custom_prompt}"
        
        ---
        🚨 [절대 규칙] 반드시 아래의 JSON 형식으로만 대답하세요. 마크다운(```)이나 다른 인사말, 설명은 절대 쓰지 마세요.
        {{
            "start": 시작시간(초, 예: 2.5),
            "end": 종료시간(초, 예: 7.5),
            "subtitle": "여기에 요청사항을 반영한 추천 자막 작성"
        }}
        """
        
        response = model.generate_content([video_file, prompt])
        genai.delete_file(video_file.name)
        
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw_text)
        
        return result

    except Exception as e:
        error_msg = f"🚨 AI 통신 에러 발생: {e}"
        status_box.error(error_msg)
        print("===" * 10)
        print(error_msg)
        print("===" * 10)
        st.stop()

# --- 2. 개별 클립 '번개 미리보기' 생성 엔진 ---
def create_fast_preview(data, output_path, status_box, font_path, font_size, text_color, stroke_color, stroke_width, y_pos_percent):
    try:
        PREVIEW_W, PREVIEW_H = 270, 480 
        status_box.info("⚡ 빠른 미리보기 영상을 생성 중입니다...")
        
        clip = VideoFileClip(data['path']).subclipped(data['start'], data['end'])
        bg = ColorClip(size=(PREVIEW_W, PREVIEW_H), color=(0, 0, 0)).with_duration(clip.duration)
        w, h = clip.size
        resized = clip.resized(width=PREVIEW_W) if w > h else clip.resized(height=PREVIEW_H)
        
        # 💡 도화지가 작아졌으니, 글자 크기와 테두리도 그 비율에 맞춰 더 작게(0.5) 줄여줍니다.
        preview_font_size = int(font_size * 0.5)
        preview_stroke_width = max(1, int(stroke_width * 0.5)) if stroke_width > 0 else 0
        
        txt_kwargs = {
            "text": data['subtitle'] + "\n", # 💡 마법의 투명 방석 추가
            "font": font_path, "font_size": preview_font_size,
            "color": text_color, "size": (PREVIEW_W - 30, None), "method": "caption"
        }
        if stroke_width > 0:
            txt_kwargs["stroke_color"] = stroke_color
            txt_kwargs["stroke_width"] = preview_stroke_width

        txt = TextClip(**txt_kwargs).with_duration(clip.duration)
        
        # 💡 [핵심] 정중앙(0%)을 기준으로 픽셀 위치를 계산하는 공식
        final_y = (PREVIEW_H / 2) + (PREVIEW_H * (y_pos_percent / 100))
        
        # 💡 [수정] 기존에 PREVIEW_H - 100 으로 고정되어 있던 위치를 final_y 로 바꿉니다.
        final_clip = CompositeVideoClip([bg, resized.with_position("center"), txt.with_position(("center", final_y))])
        
        final_clip.write_videofile(
            output_path, fps=15, codec="libx264", audio_codec="aac", preset="ultrafast", logger=None, ffmpeg_params=["-pix_fmt", "yuv420p"]
        )
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
            status_box.info(f"⏳ [{i+1}/{len(clips_data)}] 고화질 클립 병합 중: {data['name']}")
            
            clip = VideoFileClip(data['path']).subclipped(data['start'], data['end']).with_fps(30)
            bg = ColorClip(size=(TARGET_W, TARGET_H), color=(0, 0, 0)).with_duration(clip.duration)
            w, h = clip.size
            resized = clip.resized(width=TARGET_W) if w / h > TARGET_W / TARGET_H else clip.resized(height=TARGET_H)
            
            txt_kwargs = {
            "text": data['subtitle'] + "\n", # 💡 마법의 투명 방석 추가
            "font": font_path, "font_size": hd_font_size,
            "color": text_color, "size": (TARGET_W - 100, None), "method": "caption"
        }
            if hd_stroke_width > 0:
                txt_kwargs["stroke_color"] = stroke_color
                txt_kwargs["stroke_width"] = hd_stroke_width

            txt = TextClip(**txt_kwargs).with_duration(clip.duration)
            
            # 💡 [핵심] 고화질(1920) 해상도에 맞춘 위치 계산
            final_y = (TARGET_H / 2) + (TARGET_H * (y_pos_percent / 100))
            
            # 💡 [수정] 기존 TARGET_H - 300 대신 final_y 로 바꿉니다.
            final_clip = CompositeVideoClip([bg, resized.with_position("center"), txt.with_position(("center", final_y))])
            processed_clips.append(final_clip)

        status_box.info("🚀 고화질 전체 영상 렌더링 중... (화질을 높여 시간이 조금 더 걸립니다)")
        final_video = concatenate_videoclips(processed_clips, method="compose")
        final_video.write_videofile(
            output_path, fps=30, codec="libx264", audio_codec="aac", preset="medium", bitrate="8000k", threads=4, logger=None,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709"]
        )
        final_video.close()
        for c in processed_clips: c.close()
        return True
    except Exception as e:
        st.error(f"렌더링 에러: {traceback.format_exc()}")
        return False

# --- 4. Streamlit UI 구성 ---
st.set_page_config(page_title="진짜 AI 숏츠 워크스테이션", layout="wide")

# 💡 화면에 그리지 않고, 파이썬이 뒤에서 조용히 열쇠만 꺼내옵니다.
user_api_key = st.secrets["GEMINI_API_KEY"]

with st.sidebar:
    # API 관련 UI는 전부 지우고 바로 자막 설정부터 시작합니다!
    st.header("🎨 자막 스타일 설정")
    # ... (생략) ...
    st.header("🎨 자막 스타일 설정")
    font_dict = {
        "기본 폰트": "myfont.ttf" # 👈 다운받아서 폴더에 넣은 폰트 이름
    }
    sel_font_name = st.selectbox("기본 폰트 선택", list(font_dict.keys()))
    global_font_path = font_dict[sel_font_name]
    
    st.subheader("🔠 나만의 폰트 추가")
    custom_font = st.file_uploader("폰트 파일(.ttf, .otf) 업로드", type=["ttf", "otf"])
    if custom_font is not None:
        global_font_path = os.path.abspath("temp_custom_font.ttf")
        with open(global_font_path, "wb") as f: f.write(custom_font.getbuffer())
        st.success(f"✅ '{custom_font.name}' 적용 완료!")
    
    st.markdown("---")
    color_dict = {"흰색": "white", "검정색": "black", "노란색": "yellow", "빨간색": "red", "파란색": "blue", "초록색": "green", "분홍색": "pink", "회색": "gray"}
    
    st.subheader("🎨 색상 및 크기")
    sel_text_color_kor = st.selectbox("글자 색상", list(color_dict.keys()), index=0) 
    sel_stroke_color_kor = st.selectbox("테두리 색상", list(color_dict.keys()), index=1) 
    global_text_color = color_dict[sel_text_color_kor]
    global_stroke_color = color_dict[sel_stroke_color_kor]
    
    # 기존에 있던 색상 및 크기 설정 코드 아래에 이어서 작성합니다.
    global_font_size = st.slider("글자 크기", 20, 80, 45, step=1)
    global_stroke_width = st.slider("테두리 두께", 0, 10, 3, step=1) 
    
    # 💡 [신규] 자막 세로 위치 조절 슬라이더 추가
    st.markdown("---")
    st.subheader("📍 자막 위치")
    global_y_pos_percent = st.slider("세로 위치 (정중앙 0%)", -45, 45, 30, step=1, format="%d%%")
    st.caption("음수(-)는 위로, 양수(+)는 아래로 이동합니다.")

if 'clips' not in st.session_state: st.session_state.clips = []
if 'analyzed' not in st.session_state: st.session_state.analyzed = False

st.title("🎬 숏츠 편집하기(Made by minorious)")

up_files = st.file_uploader("동영상 파일 업로드", type=["mp4", "mov"], accept_multiple_files=True)

# 💡 [신규] 사용자가 프롬프트를 마음대로 수정할 수 있는 입력창 추가!
default_prompt = "이 영상에서 핵심 정보가 가장 잘 전달되는 5초 이하의 중요한 구간을 찾고, 시청자가 내용을 쉽게 이해할 수 있도록 차분하고 명확한 요약 자막(15자 내외)을 하나 작성해 줘."
user_custom_prompt = st.text_area("🧠 AI에게 내릴 특별한 지시사항 (프롬프트 커스텀)", value=default_prompt, height=80)

if st.button("🔍 1단계: AI 자동 분석 시작"):
    if up_files:
        st.session_state.clips = []
        uid = int(time.time())
        status_box = st.empty() 
        
        for i, f in enumerate(up_files):
            tmp_p = f"temp_{uid}_{i}.mp4"
            with open(tmp_p, "wb") as out: out.write(f.getbuffer())
            
            # 💡 [핵심] 아까 만든 입력창의 내용(user_custom_prompt)을 AI 함수로 전달합니다!
            ai_res = analyze_video_with_gemini(tmp_p, user_api_key, user_custom_prompt, status_box)
            
            with VideoFileClip(tmp_p) as v:
                dur = v.duration
                safe_start = min(ai_res['start'], dur - 1.0)
                safe_end = min(ai_res['end'], dur)
                if safe_start >= safe_end: safe_start = 0.0; safe_end = min(5.0, dur)
                
                st.session_state.clips.append({
                    "path": tmp_p, "name": f.name, "total": dur,
                    "start": safe_start, "end": safe_end, 
                    "subtitle": ai_res['subtitle'], "preview_path": None
                })
                
        status_box.success("✅ AI 분석이 모두 완료되었습니다!")
        st.session_state.analyzed = True
        st.rerun()

if st.session_state.analyzed:
    col_left, col_right = st.columns([1, 1.2])

    with col_right:
        st.subheader("✂️ 개별 클립 정밀 편집")
        total_final_dur = 0
        for i, c in enumerate(st.session_state.clips):
            with st.expander(f"클립 #{i+1}: {c['name']} (AI 추천)", expanded=True):
                s, e = st.slider(f"구간 (초)", 0.0, c['total'], (c['start'], c['end']), key=f"range_{i}")
                st.session_state.clips[i]['start'], st.session_state.clips[i]['end'] = s, e
                sub = st.text_area("AI 자막 수정", value=c['subtitle'], key=f"sub_{i}", height=70)
                st.session_state.clips[i]['subtitle'] = sub
                total_final_dur += (e - s)
                
                preview_status = st.empty()
                # [미리보기 버튼 부분 수정]
                if st.button(f"▶️ 이 클립만 미리보기 생성", key=f"prev_btn_{i}"):
                    prev_path = f"fast_preview_{int(time.time())}_{i}.mp4"
                    # 맨 끝에 global_y_pos_percent 추가!
                    if create_fast_preview(st.session_state.clips[i], prev_path, preview_status, 
                                           global_font_path, global_font_size, 
                                           global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent):
                        st.session_state.clips[i]['preview_path'] = prev_path
                
                if st.session_state.clips[i].get('preview_path') and os.path.exists(st.session_state.clips[i]['preview_path']):
                    st.video(st.session_state.clips[i]['preview_path'])
        
        st.divider()
        st.write(f"📊 **예상 총 재생 시간:** {total_final_dur:.2f}초")
        
        # [최종 완성 버튼 부분 수정]
        if st.button("🚀 2단계: 최종 숏츠 완성하기", use_container_width=True):
            s_box = st.empty()
            out_p = f"final_output_{int(time.time())}.mp4"
            # 맨 끝에 global_y_pos_percent 추가!
            if render_final_video(st.session_state.clips, out_p, s_box, 
                                  global_font_path, global_font_size, 
                                  global_text_color, global_stroke_color, global_stroke_width, global_y_pos_percent):
                st.session_state.final_video_path = out_p
                st.success("완성되었습니다! 왼쪽 미리보기를 확인하세요.")
                st.rerun()

    with col_left:
        st.subheader("📺 결과물 전체 미리보기")
        if 'final_video_path' in st.session_state and os.path.exists(st.session_state.final_video_path):
            st.video(st.session_state.final_video_path)
            with open(st.session_state.final_video_path, "rb") as f:
                st.download_button("💾 고화질 숏츠 다운로드", f, file_name="ai_shorts.mp4")
        else:
            st.info("오른쪽에서 개별 클립을 편집하고 '최종 숏츠 완성하기'를 눌러주세요.")
