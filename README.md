# 분당구 개표 흐름 대시보드

중앙선거관리위원회 선거통계시스템의 `개표진행상황(VCCP09)`과 `개표단위별 개표결과(VCCP08)`를 수집해 GitHub Pages로 보여주는 정적 대시보드입니다.

## 수집 범위

- 시·도지사선거: 경기도
- 구·시·군의 장선거: 성남시
- 시·도의회의원선거: 성남시 분당구, 성남시제5선거구부터 제8선거구까지 선거구별 표시
- 구·시·군의회의원선거: 성남시 분당구, 성남시바선거구부터 타선거구까지 선거구별 표시
- 광역의원비례대표선거: 경기도
- 기초의원비례대표선거: 성남시
- 교육감선거: 경기도
- 국회의원선거: NEC에 등록된 전체 선거구

시·도지사선거, 구·시·군의 장선거, 광역의원비례대표선거, 교육감선거, 기초의원비례대표선거는 성남시 수정구·중원구 전체와 분당구 동별 상세를 함께 보여줍니다. NEC가 아직 동별 개표 상세 행을 내려주지 않는 범위는 화면에서 `상세없음`으로 표시됩니다.

## 로컬 실행

```bash
python3 scripts/fetch_nec.py
python3 -m http.server 5173 --directory public
```

브라우저에서 `http://127.0.0.1:5173/`을 열면 됩니다.

## GitHub Pages

`.github/workflows/pages.yml`은 5분마다 `scripts/fetch_nec.py`를 실행하고 `public/data/latest.json`, `public/data/history.json`을 갱신한 뒤 GitHub Pages에 배포합니다. 저장소 설정에서 Pages source를 `GitHub Actions`로 선택해 주세요.
