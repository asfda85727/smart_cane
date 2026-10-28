# Smart Cane — AI 스마트 지팡이

시각장애인을 위한 라즈베리파이 기반 보행 보조기기입니다. 지팡이에 달린 카메라가 본 장면을 한국어 음성으로 설명합니다.

버튼을 **한 번** 누르면 전방 위험을 한 문장으로 경고하고, **두 번** 누르면 주변 상황을 세 문장으로 묘사합니다.

> USG 공유대학 캡스톤 종합설계 경진대회 **우수상** (RISE 사업단, 2025.07–2026.02)

## 동작 구조

```
버튼 입력 → Picamera2 캡처 → YOLOv8n 로컬 탐지 → Gemini 2.0 Flash 장면 해석 → Google Cloud TTS → 음성 출력
```

로컬 탐지(YOLO)와 클라우드 해석(Gemini)의 역할을 나눴습니다. YOLO는 기기에서 "무엇이 어디에" 있는지를 빠르게 잡고, Gemini는 그 결과와 원본 이미지를 함께 받아 사람이 알아들을 문장을 만듭니다.

## 주요 기능

- **2단 폴백** — 네트워크가 없으면 로컬 YOLO 탐지 결과만으로 문장을 만들고, 네트워크가 있어도 Gemini 호출이 실패하면 탐지 결과로 되돌아갑니다.
- **SSML 무음 패딩** — 음성 합성 요청 앞에 1초짜리 무음 구간을 넣어, 스피커가 절전에서 깨어날 때 첫 음절이 잘리는 문제를 막습니다.
- **응답 캐시** — 같은 문장은 해시로 구분해 음성 파일을 캐시하므로, 반복되는 안내는 네트워크 호출 없이 즉시 재생됩니다.
- **버튼 중단** — 음성 재생 중 버튼을 다시 누르면 즉시 중단하고 새 요청을 받습니다.

## 탐지 대상

사람, 자전거, 자동차, 오토바이, 버스, 트럭, 신호등, 소화전, 벤치, 의자 — 보행 중 마주치는 대상 10종으로 좁혀 탐지 속도를 확보했습니다.

## 하드웨어

- Raspberry Pi (GPIO 버튼 1개, BOARD 핀 11)
- Picamera2 호환 카메라
- 블루투스 스피커 (PulseAudio `paplay` 출력)

## 설치

```bash
pip install -r requirements.txt
```

`.env` 파일에 아래 값을 설정합니다.

```
GOOGLE_API_KEY=<Gemini API 키>
GOOGLE_APPLICATION_CREDENTIALS=<Google Cloud 서비스 계정 JSON 경로>
```

TTS는 `google-cloud-texttospeech`가 `GOOGLE_APPLICATION_CREDENTIALS` 환경변수를 직접 읽으므로 서비스 계정 키가 별도로 필요합니다.

## 실행

```bash
python smart_cane.py
```

스피커 출력만 먼저 확인하려면:

```bash
python test_audio.py
```

## 스택

Python · YOLOv8 (Ultralytics) · Gemini 2.0 Flash API · Google Cloud Text-to-Speech · OpenCV · Picamera2 · RPi.GPIO
