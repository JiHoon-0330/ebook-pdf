# eBook PDF Generator

macOS에서 실행 중인 앱의 스크린샷을 자동으로 캡처하여 PDF로 변환하는 고급 CLI 프로그램입니다. 지능형 중복 감지와 완전 자동화된 워크플로우를 제공하며, PDF 페이지 분할 기능도 포함되어 있습니다.

## 주요 기능

### eBook PDF Generator (main.py)
- 🖥️ **앱 선택 및 포커스**: 실행 중인 앱 목록에서 선택하여 자동 포커스
- 📸 **자동 스크린샷 캡처**: 윈도우 기반 고품질 스크린샷 자동 캡처
- 🔍 **중복 페이지 감지**: 지능형 이미지 비교로 동일 페이지 자동 감지
- 🤖 **완전 자동화**: 방향키 자동 전송, 10회 연속 중복 시 자동 종료
- 📄 **PDF 자동 생성**: 캡처된 이미지들을 고품질 PDF로 변환

### PDF Splitter (pdf_splitter.py)
- ✂️ **PDF 페이지 분할**: 원하는 페이지 범위를 별도 PDF로 추출
- 💻 **CLI/대화형 모드**: 명령줄 또는 대화형 인터페이스 지원

## 설치 및 실행

### uv 설치 (macOS)
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

### 프로젝트 설정
```bash
# 의존성 설치
uv sync

# 프로그램 실행
uv run main.py
```

## 사용법

### eBook PDF Generator
1. **프로그램 실행**: `uv run main.py`
2. **앱 선택**: ↑/↓ 방향키로 앱 선택, Enter로 확인
3. **자동 캡처 시작**: 선택한 앱이 포커스되고 자동으로 스크린샷 캡처 시작
4. **자동 페이지 넘김**: 우측 방향키가 자동으로 전송되어 다음 페이지로 이동
5. **자동 종료 및 PDF 생성**: 10회 연속 동일 페이지 감지 시 자동으로 PDF 생성

### PDF Splitter
1. **대화형 모드**: `uv run pdf_splitter.py`
2. **CLI 모드**: `uv run pdf_splitter.py input.pdf -s 시작페이지 -e 끝페이지 -o 출력파일.pdf`

## 조작법

### eBook PDF Generator
- **↑/↓**: 앱 목록 이동
- **Enter**: 앱 선택 및 자동 캡처 시작
- **q**: 프로그램 종료

### PDF Splitter
- **대화형 모드**: 프롬프트에 따라 파일 선택 및 페이지 범위 입력
- **CLI 모드**: 명령줄 인수로 직접 실행

## 프로젝트 구조

```
ebook-pdf/
├── main.py              # eBook PDF Generator - 메인 프로그램
├── pdf_splitter.py      # PDF 페이지 분할 도구
├── pyproject.toml       # 프로젝트 설정 및 의존성
├── uv.lock             # 의존성 잠금 파일
├── screenshots/         # 스크린샷 저장 폴더 (자동 생성)
├── pdfs/               # 원본 PDF 파일 저장 폴더
│   ├── 함께_자라기.pdf
│   └── 함께_자라기_55-95.pdf
├── ebook.pdf           # 생성된 PDF 파일
└── README.md           # 이 파일
```

## 개발 환경

- Python 3.11+
- uv 패키지 매니저
- macOS 전용 (AppleScript, screencapture 명령어 사용)

## 의존성

핵심 의존성들은 `pyproject.toml`에 정의되어 있습니다:

- `rich`: 터미널 UI, 테이블 표시, 프로그레스 바
- `psutil`: 프로세스 정보 수집
- `Pillow`: 이미지 처리 및 퍼셉추얼 해시 계산
- `PyPDF2`: PDF 읽기 및 분할
- `reportlab`: 고해상도 PDF 생성
- `click`: CLI 인터페이스 (향후 확장용)
- `keyboard`: 키보드 이벤트 처리 (향후 확장용)
- `pyobjc-framework-Cocoa`: macOS Cocoa 프레임워크 (앱 목록, 포커스)
- `pyobjc-framework-Quartz`: macOS Quartz 프레임워크 (윈도우 캡처, 키 이벤트)

## 기술적 특징

### 고급 이미지 처리
- **퍼셉추얼 해시(pHash)**: DCT 기반 64비트 해시로 렌더링 노이즈에 강한 중복 감지
- **해밍거리 비교**: 미세한 UI 변화를 무시하고 실질적인 페이지 변경만 감지
- **ROI 기반 분석**: 페이지 하단 영역을 집중 분석하여 페이지 번호 변화 감지

### 자동화 워크플로우
- **CGWindowListCreateImage**: macOS 네이티브 API로 정확한 윈도우 캡처
- **자동 키 이벤트**: Quartz 이벤트로 우측 방향키 자동 전송
- **지능형 종료**: 10회 연속 동일 페이지 감지 시 자동 PDF 생성 및 종료

### PDF 최적화
- **고해상도 유지**: FHD 기준 최적화로 품질과 파일크기 균형
- **마지막 페이지 제외**: 중복된 마지막 페이지 자동 제거
- **ReportLab 기반**: 전문적인 PDF 생성 라이브러리 사용

## 주의사항 및 권한

- **macOS 전용**: AppleScript, Quartz, CGWindowListCreateImage 등 macOS 전용 API 사용
- **화면 녹화 권한 필요**: 
  > 시스템 설정 -> 개인정보 보호 및 보안 -> 화면 및 시스템 오디오 녹음 -> 실행환경 (터미널, VSCode, Cursor 등) 추가
- **접근성 권한 필요**: 
  > 시스템 설정 -> 개인정보 보호 및 보안 -> 손쉬운 사용 -> 실행환경 (터미널, VSCode, Cursor 등) 추가
- **Application 폴더 앱만 지원**: 보안상 `/Applications` 폴더의 앱만 목록에 표시
