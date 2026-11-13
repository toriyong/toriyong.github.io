# toriyong.github.io

보안 · 인프라 · 증시 현황 대시보드 (프로토타입)

- 사이트: https://toriyong.github.io/
- 구조: GitHub Actions가 공개 데이터를 수집해 JSON을 만들고, GitHub Pages가 정적 파일로 보여 줍니다.
- 열람 전용: 방문자는 볼 수만 있고, 수정은 레포 소유자만 할 수 있습니다.

> 이 사이트는 공개 데이터를 정리해 보여 주는 정보 사이트이며, 투자 권유나 매매 추천을 하지 않습니다.

## 폴더 구조

```
config/                 # 운영자가 직접 관리하는 설정
  grading.yml           #   공모주 등급 기준값
  ipo_manual.yml        #   API로 못 받는 값(경쟁률·확약률·상장일 등) 수동 입력
collect/market/         # 원천 데이터 수집 (DART)
process/market/         # 가공·등급 산정
site/                   # 배포되는 화면 (이 폴더가 그대로 사이트가 됨)
  index.html            #   허브
  security/ infra/      #   준비 중 탭
  market/               #   증시 탭 (공모주)
  assets/               #   공통 CSS·JS
.github/workflows/      # 자동 수집·배포
```

## 필요한 Secrets

| 이름 | 용도 |
| --- | --- |
| `DART_API_KEY` | OpenDART 인증키 (공모주 증권신고서) |

Settings → Secrets and variables → Actions 에서 등록합니다. 키는 코드에 절대 넣지 않습니다.

## 자동 실행 일정 (KST)

| 시각 | 작업 |
| --- | --- |
| 매일 07:00 | 공모주 수집 → 등급 산정 → 배포 |
| 평일 16:30 | 같은 작업 반복 (장 마감 후 갱신) |
| main에 push | 즉시 배포 |

## 로컬에서 실행

```bash
pip install -r requirements.txt
export DART_API_KEY="..."          # PowerShell: $env:DART_API_KEY="..."
python collect/market/dart_ipo.py --out site/market/data/raw_ipo.json
python process/market/grade_ipo.py --raw site/market/data/raw_ipo.json --out site/market/data/ipo.json
python -m http.server -d site 8000  # http://localhost:8000
```

키 없이 화면만 확인하려면 `--sample` 옵션으로 예시 데이터를 만들 수 있습니다.

```bash
python collect/market/dart_ipo.py --sample --out site/market/data/raw_ipo.json
```
