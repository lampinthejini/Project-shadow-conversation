# 0단계 측정 도구

절차와 판단 기준은 `docs/그림자 대화 0단계 기술 검증 절차서 v0.1.md`를 따른다.

| 파일 | 용도 |
| --- | --- |
| `run_home.ps1` | 집 PC에서 S0-01·S0-03~05를 한 번에 실행(Ollama 병렬 슬롯 1·2개) |
| `env_info.py` | 측정 환경 기록(OS·CPU·RAM·GPU·엔진 버전) |
| `bench_llm.py` | LLM 지연 측정: `ctx`(컨텍스트 길이), `prefix`(프리픽스 캐시), `judge`(판정 병렬·순차) |
| `llm_client.py` | 스트리밍 클라이언트. OpenAI 호환 API와 Ollama 네이티브 API |
| `prompts/` | 측정용 대역 프롬프트. 제품 프롬프트가 아니다 |
| `results/` | 측정 결과(JSONL). 생성 문장은 저장하지 않는다 |

```
python tools/stage0/env_info.py
python tools/stage0/bench_llm.py --api ollama --model <모델 이름> --experiments ctx,prefix,judge
python -m pytest tools/stage0      # 스텁 서버로 도구 자체를 검사 (모델 불필요)
```

표준 라이브러리만 쓰고, localhost 서빙 엔진에만 요청한다.
