# -*- coding: utf-8 -*-
import os
import subprocess
from dotenv import load_dotenv
from google.cloud import texttospeech

load_dotenv()

def test_speaker():
    print("블루투스 스피커(버즈) 테스트 시작...")
    
    try:
        # 1. 구글 TTS로 파일 만들기
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text="테스트, 하나 둘 셋. 갤럭시 버즈로 소리가 잘 들립니다.")
        
        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR", name="ko-KR-Wavenet-A"
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            volume_gain_db=0.0
        )
        
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        filename = "test_output.wav"
        with open(filename, "wb") as f:
            f.write(response.audio_content)
            
        print("재생 중... (설정된 출력 장치로 소리가 나갑니다)")
        
        # [수정됨] paplay를 사용하여 현재 선택된 장치(버즈)로 재생
        subprocess.run(["paplay", filename])
        
        print("테스트 종료!")
        
    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == "__main__":
    test_speaker()