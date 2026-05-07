import os
import time
import threading
import subprocess
import socket
import hashlib
import RPi.GPIO as GPIO 
from dotenv import load_dotenv
from google import genai
from google.genai import types 
from ultralytics import YOLO
from picamera2 import Picamera2
import PIL.Image
import cv2
from google.cloud import texttospeech

# ==========================================
# 1. 환경 설정
# ==========================================
load_dotenv()
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL = "gemini-2.0-flash" 
GCP_CREDS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

BUTTON_PIN = 11
W, H, FPS = 640, 480, 30
CACHE_DIR = "/home/youngjun/Desktop/Smart_cane/tts_cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# 표준 모델 클래스 (필요한 것만 정의)
TARGET_CLASSES = [0, 1, 2, 3, 5, 7, 9, 10, 13, 56]
KO_NAMES = {
    0: "사람", 1: "자전거", 2: "자동차", 3: "오토바이", 5: "버스", 
    7: "트럭", 9: "신호등", 10: "소화전", 13: "벤치", 56: "의자"
}

current_audio_process = None
is_processing = False

# ==========================================
# 2. 오디오 시스템 (SSML 무음 적용)
# ==========================================
def stop_audio():
    global current_audio_process
    if current_audio_process:
        try:
            current_audio_process.terminate()
            current_audio_process.wait(timeout=0.5)
        except: pass
        current_audio_process = None

def play_audio_file(filename):
    global current_audio_process
    stop_audio()
    try:
        current_audio_process = subprocess.Popen(["paplay", filename])
        current_audio_process.wait()
    except Exception: pass
    finally: current_audio_process = None

def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError: return False

def smart_tts_engine(text):
    if not text: return

    # 파일명은 텍스트 내용으로 생성 (캐시용)
    filename_hash = hashlib.md5(text.encode()).hexdigest()
    cache_path = os.path.join(CACHE_DIR, f"{filename_hash}.wav")

    # 1. 캐시 있으면 바로 재생
    if os.path.exists(cache_path):
        play_audio_file(cache_path)
        return

    # 2. 인터넷 확인
    if not check_internet():
        print(f"[!] 인터넷 끊김.")
        return

    # 3. 구글 다운로드 (SSML 사용)
    try:
        client_tts = texttospeech.TextToSpeechClient()
        
        # -----------------------------------------------------------
        # [핵심 수정] 점(.) 대신 SSML 태그로 '1초 무음'을 넣음
        # <break time="1000ms"/> : 이 부분은 아예 소리가 안 남 (스피커 깨우기용)
        # -----------------------------------------------------------
        ssml_text = f'<speak><break time="1000ms"/>{text}</speak>'
        
        # input 타입을 text가 아니라 'ssml'로 설정해야 함
        synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
        
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR", name="ko-KR-Wavenet-A"
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16, 
            speaking_rate=0.90 
        )
        
        response = client_tts.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        with open(cache_path, "wb") as f:
            f.write(response.audio_content)
        play_audio_file(cache_path)
        
    except Exception as e:
        print(f"[!] TTS 오류: {e}")

def speak_cloud(text):
    smart_tts_engine(text)

def speak_instant(text):
    smart_tts_engine(text)

# ==========================================
# 3. 모델 및 카메라 준비
# ==========================================
print("AI 모델 로딩 중 (Standard)...")
yolo = YOLO("yolov8n.pt") 

print("카메라 연결 중...")
cam = Picamera2()
CAM_IS_BGR = False
try:
    cfg = cam.create_video_configuration(main={"size": (W, H), "format": "BGR888"})
    CAM_IS_BGR = True
except:
    cfg = cam.create_video_configuration(main={"size": (W, H), "format": "RGB888"})
cam.configure(cfg)
cam.start()
time.sleep(2)

def get_position_text(center_x):
    if center_x < W * 0.33: return "좌측"
    if center_x > W * 0.66: return "우측"
    return "정면"

# ==========================================
# 4. 분석 파이프라인
# ==========================================
def process_ai_pipeline(mode):
    global GOOGLE_API_KEY
    
    frame = cam.capture_array()
    if CAM_IS_BGR:
        frame_bgr = frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        frame_rgb = frame

    detected_objects = []
    
    # YOLO 실행 (표준 모델)
    results = yolo.predict(frame_bgr, classes=TARGET_CLASSES, conf=0.5, verbose=False)
    
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            center_x = (x1 + x2) / 2
            pos = get_position_text(center_x)
            cls_id = int(box.cls[0])
            name = KO_NAMES.get(cls_id, "물체")
            
            # 모드 1: 위치 포함 / 모드 2: 이름만
            if mode == 1:
                detected_objects.append(f"{pos} {name}")
            else:
                detected_objects.append(name)
    
    yolo_summary = ", ".join(detected_objects) if detected_objects else "없음"
    print(f"[YOLO 감지] {yolo_summary}")

    if not check_internet():
        return f"인터넷 끊김. {yolo_summary}."

    # Gemini 프롬프트 설정
    if mode == 1:
        # [모드 1] 주행 안전
        prompt = (
            f"You are a 'Walking Assistant' for the visually impaired. "
            f"YOLO detected: {detected_objects}. "
            f"INSTRUCTION: "
            f"1. If YOLO detected objects, warn the user about them. "
            f"2. Even if YOLO detected NOTHING, look at the IMAGE directly. "
            f"Output a SHORT, DIRECT warning (1 sentence). "
            f"Speak ONLY in Korean. No English."
        )
    else:
        # [모드 2] 주변 묘사
        prompt = (
            f"You are a 'Walking Assistant'. "
            f"YOLO detected: {detected_objects}. "
            f"Look at the IMAGE and describe the scene in detail (must make 3 sentences). "
            f"Mention the atmosphere and surroundings. "  
            f"Speak ONLY in Korean. No English."
        )

    # Gemini 호출
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        # 안전 필터 해제
        safe_conf = types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            ]
        )

        resp = client.models.generate_content(
            model=GEMINI_MODEL, 
            contents=[prompt, PIL.Image.fromarray(frame_rgb)],
            config=safe_conf
        )
        return resp.text.strip()
        
    except Exception as e:
        print(f"\n[에러] {e}\n")
        if yolo_summary != "없음":
             return f"상세 분석 불가. 전방에 {yolo_summary}가 있습니다."
        else:
             return "전방 상황을 확인할 수 없습니다."

def main_thread_func(click_count):
    global is_processing
    is_processing = True
    
    # 여기도 speak_cloud(SSML)를 타므로 1초 무음 후 말함
    speak_cloud("촬영을 시작합니다.") 
    
    final_text = process_ai_pipeline(click_count)
    print(f"[Gemini] {final_text}")
    
    speak_cloud(final_text)
    is_processing = False

def monitor_buttons():
    global current_audio_process, is_processing
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    last_click_time = 0
    click_count = 0
    
    try:
        while True:
            if GPIO.input(BUTTON_PIN) == GPIO.LOW:
                time.sleep(0.05)
                if GPIO.input(BUTTON_PIN) == GPIO.LOW:
                    if current_audio_process is not None and current_audio_process.poll() is None:
                        stop_audio()
                        while GPIO.input(BUTTON_PIN) == GPIO.LOW: time.sleep(0.1)
                        continue
                    start_press = time.time()
                    while GPIO.input(BUTTON_PIN) == GPIO.LOW: time.sleep(0.01)
                    now = time.time()
                    if now - last_click_time < 0.5: click_count = 2
                    else: click_count = 1
                    last_click_time = now
            if click_count > 0 and (time.time() - last_click_time > 0.5):
                if not is_processing:
                    threading.Thread(target=main_thread_func, args=(click_count,), daemon=True).start()
                click_count = 0
            time.sleep(0.01)
    except KeyboardInterrupt:
        GPIO.cleanup()

if __name__ == "__main__":
    print("시스템 준비 중...")
    
    # 1. 미끼 던지기 (SSML로 무음 처리됨)
    speak_instant("시스템 준비.") 
    time.sleep(0.5) 

    # 2. 본 멘트
    if check_internet():
        speak_cloud("전원이 켜졌습니다. 인터넷이 연결 되었습니다.")
    else:
        speak_instant("전원이 켜졌습니다. 인터넷 연결 실패 .")

    monitor_buttons()