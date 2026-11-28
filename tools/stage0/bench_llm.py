"""0단계 LLM 지연 측정 (TRD v0.4 13절, PRD 11절 0단계).

실험
- ctx:    컨텍스트 길이별 첫 토큰·전체 생성 시간 (매번 프리픽스 캐시를 비움)
- prefix: 같은 프리픽스를 다시 보낼 때 첫 토큰 시간이 줄어드는지 (캐시 냉·온)
- judge:  판정기와 그림자를 순차·병렬로 돌렸을 때 응답을 내보낼 수 있는 시점

입력은 모두 가상의 인물·상황으로 만든 대역 데이터다. 생성된 문장은 저장하지 않는다.
대상은 localhost 서빙 엔진뿐이다.

사용 예
    python bench_llm.py --api ollama --model exaone3.5:7.8b --experiments ctx,prefix,judge
"""

import argparse
import datetime
import json
import statistics
import threading
import time
import uuid
from pathlib import Path

import env_info
import llm_client

HERE = Path(__file__).resolve().parent

FILLER_LINES = [
    ("user", "오늘 오는 길에 비가 조금 왔어요. 우산을 챙길까 하다가 그냥 나왔는데 다행히 금방 그쳤네요."),
    ("assistant", "저도 창밖을 보면서 비가 오나 했어요. 젖지 않으셨다니 다행이에요. 여기 찾기는 어렵지 않으셨어요?"),
    ("user", "지도 보고 왔는데 골목이 좀 헷갈렸어요. 간판이 작아서 한 번 지나쳤다가 돌아왔어요."),
    ("assistant", "저도 처음엔 그랬어요. 그래도 안쪽은 조용해서 좋아요. 커피는 어떤 걸 좋아하세요?"),
    ("user", "보통은 따뜻한 라테를 마셔요. 쓴 건 잘 못 마셔서요. 윤서 씨는요?"),
    ("assistant", "저는 산미 있는 원두를 좋아해요. 일하다 보면 하루에 두 잔은 마시게 되더라고요."),
    ("user", "편집 일은 마감이 있어서 바쁘다고 들었어요. 요즘도 바쁘세요?"),
    ("assistant", "이번 달은 조금 숨 돌릴 틈이 있어요. 지난달에 책 한 권을 막 끝냈거든요. 요즘 어떻게 지내세요?"),
    ("user", "저는 주말마다 동네 천변을 걸어요. 생각이 정리되는 느낌이 들어서요."),
    ("assistant", "걷는 걸 좋아하시는구나. 어떤 생각을 주로 하면서 걸으세요?"),
    ("user", "그냥 그 주에 있었던 일이요. 잘한 것도 있고 아쉬운 것도 있고요."),
    ("assistant", "아쉬운 일을 떠올리면 걸음이 느려지기도 하겠네요. 저는 그럴 때 일부러 먼 길로 돌아가요."),
]

FINAL_USER_LINES = [
    "윤서 씨는 쉬는 날에 주로 뭐 하세요?",
    "책을 고를 때 제일 먼저 보는 게 뭐예요?",
    "처음 만나는 자리가 좀 긴장되네요. 윤서 씨도 그러세요?",
    "여기 디저트도 맛있어 보이는데 하나 시켜 볼까요?",
    "어릴 때는 어떤 일을 하고 싶으셨어요?",
]


def percentile(values, pct):
    """선형 보간 백분위수. 값이 없으면 None."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    rank = (len(data) - 1) * pct / 100
    low = int(rank)
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (rank - low)


def loadPrompt(name):
    text = (HERE / "prompts" / name).read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.startswith("# ")).strip()


def buildFillerTurns(minChars):
    """minChars 글자 이상이 될 때까지 가상의 대화를 이어 붙인다. 결과는 항상 같다."""
    turns = []
    total = 0
    index = 0
    while total < minChars:
        role, content = FILLER_LINES[index % len(FILLER_LINES)]
        content = f"{content} ({index // len(FILLER_LINES) + 1})"
        turns.append({"role": role, "content": content})
        total += len(content)
        index += 1
    if turns and turns[-1]["role"] == "user":
        turns.pop()
    return turns


def shadowMessages(fillerChars, finalIndex, nonce):
    system = loadPrompt("shadow_system.txt").replace("{nonce}", nonce)
    finalLine = FINAL_USER_LINES[finalIndex % len(FINAL_USER_LINES)]
    return (
        [{"role": "system", "content": system}]
        + buildFillerTurns(fillerChars)
        + [{"role": "user", "content": finalLine}]
    )


def judgeMessages(finalIndex, nonce):
    system = loadPrompt("judge_system.txt")
    recent = [content for role, content in FILLER_LINES if role == "user"][-3:]
    finalLine = FINAL_USER_LINES[finalIndex % len(FINAL_USER_LINES)]
    userBlock = f"[{nonce}]\n최근 사용자 대사:\n" + "\n".join(recent) + f"\n현재 입력:\n{finalLine}"
    return [{"role": "system", "content": system}, {"role": "user", "content": userBlock}]


def runJudgeAndShadow(baseUrl, model, judgeMsgs, shadowMsgs, mode, api="openai", **options):
    """판정과 그림자 생성을 함께 돌린다.

    releaseMs: 그림자 응답을 내보낼 수 있게 되는 시점. 판정 통과와 출력 금지 사전 검사
    (전체 문장 필요)가 모두 끝나야 하므로 두 요청이 모두 끝난 시각이다(CLAUDE.md 4.1).
    """
    judgeOptions = dict(options, maxTokens=options.get("judgeMaxTokens", 120), temperature=0)
    judgeOptions.pop("judgeMaxTokens", None)
    shadowOptions = dict(options)
    shadowOptions.pop("judgeMaxTokens", None)
    results = {}
    start = time.perf_counter()

    if mode == "sequential":
        results["judge"] = llm_client.streamChat(baseUrl, model, judgeMsgs, api=api, **judgeOptions)
        if results["judge"]["ok"]:
            results["shadow"] = llm_client.streamChat(baseUrl, model, shadowMsgs, api=api, **shadowOptions)
        else:
            results["shadow"] = llm_client.emptyResult()
    elif mode == "parallel":
        def worker(key, messages, opts):
            results[key] = llm_client.streamChat(baseUrl, model, messages, api=api, **opts)

        threads = [
            threading.Thread(target=worker, args=("judge", judgeMsgs, judgeOptions)),
            threading.Thread(target=worker, args=("shadow", shadowMsgs, shadowOptions)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    else:
        raise ValueError(f"unknown mode: {mode}")

    elapsed = (time.perf_counter() - start) * 1000
    ok = results["judge"]["ok"] and results["shadow"]["ok"]
    return {"ok": ok, "mode": mode, "releaseMs": elapsed if ok else None, **results}


def isValidJudgeJson(text):
    try:
        parsed = json.loads(text.strip().strip("`").removeprefix("json").strip())
    except (json.JSONDecodeError, AttributeError):
        return False
    return isinstance(parsed, dict) and parsed.get("crisisLevel") in {"L0", "L1", "L2", "L3"}


def summarize(rows, metrics):
    groups = {}
    for row in rows:
        groups.setdefault((row["experiment"], row["label"]), []).append(row)
    summary = {}
    for key, items in groups.items():
        okItems = [item for item in items if item["ok"]]
        entry = {"n": len(okItems), "failed": len(items) - len(okItems)}
        for metric in metrics:
            values = [item.get(metric) for item in okItems if item.get(metric) is not None]
            entry[metric] = {
                "p50": percentile(values, 50),
                "p90": percentile(values, 90),
                "mean": statistics.fmean(values) if values else None,
            }
        summary[key] = entry
    return summary


def compactResult(result):
    """생성 문장은 버리고 수치만 남긴다."""
    kept = {k: v for k, v in result.items() if k != "text"}
    kept["textChars"] = len(result.get("text") or "")
    if result.get("completionTokens") and result.get("engineDecodeMs"):
        kept["decodeTokPerSec"] = result["completionTokens"] / (result["engineDecodeMs"] / 1000)
    return kept


def warmUp(args):
    """모델 적재 시간이 첫 측정에 섞이지 않도록 짧은 요청을 먼저 보낸다. 적재 시간 기록용(S0-02)."""
    messages = [{"role": "user", "content": "안녕하세요."}]
    result = llm_client.streamChat(
        args.baseUrl, args.model, messages, api=args.api, maxTokens=8,
        numCtx=args.numCtx, seed=args.seed, timeoutSec=args.timeout,
    )
    return {"experiment": "warmup", "label": "load", **compactResult(result)}


def experimentCtx(args, emit):
    for chars in args.ctxChars:
        for repeat in range(args.repeats):
            nonce = uuid.uuid4().hex[:8]  # 매번 새 프리픽스: 캐시 없는 값
            result = llm_client.streamChat(
                args.baseUrl, args.model, shadowMessages(chars, repeat, nonce), api=args.api,
                maxTokens=args.maxTokens, numCtx=args.numCtx, seed=args.seed, timeoutSec=args.timeout,
            )
            emit({"experiment": "ctx", "label": f"{chars}chars", **compactResult(result)})


def experimentPrefix(args, emit):
    chars = args.prefixChars
    for round_ in range(args.repeats):
        nonce = uuid.uuid4().hex[:8]
        for step in range(args.prefixWarmSteps + 1):
            label = "cold" if step == 0 else "warm"
            result = llm_client.streamChat(
                args.baseUrl, args.model, shadowMessages(chars, step, nonce), api=args.api,
                maxTokens=args.maxTokens, numCtx=args.numCtx, seed=args.seed, timeoutSec=args.timeout,
            )
            emit({"experiment": "prefix", "label": label, "round": round_, **compactResult(result)})


def experimentJudge(args, emit):
    for repeat in range(args.repeats):
        for mode in ("sequential", "parallel"):
            nonce = uuid.uuid4().hex[:8]
            outcome = runJudgeAndShadow(
                args.baseUrl, args.model, judgeMessages(repeat, nonce),
                shadowMessages(args.prefixChars, repeat, nonce), mode=mode, api=args.api,
                maxTokens=args.maxTokens, numCtx=args.numCtx, seed=args.seed,
                timeoutSec=args.timeout, judgeMaxTokens=args.judgeMaxTokens,
            )
            emit({
                "experiment": "judge",
                "label": mode,
                "ok": outcome["ok"],
                "releaseMs": outcome["releaseMs"],
                "judgeTotalMs": outcome["judge"]["totalMs"],
                "judgeJsonValid": isValidJudgeJson(outcome["judge"]["text"]),
                "shadowTtftMs": outcome["shadow"]["ttftMs"],
                "shadowTotalMs": outcome["shadow"]["totalMs"],
                "error": outcome["judge"]["error"] or outcome["shadow"]["error"],
            })


EXPERIMENTS = {"ctx": experimentCtx, "prefix": experimentPrefix, "judge": experimentJudge}
METRICS = ["ttftMs", "totalMs", "promptTokens", "completionTokens", "enginePromptMs",
           "decodeTokPerSec", "releaseMs", "judgeTotalMs", "shadowTtftMs", "shadowTotalMs"]


def formatSummary(summary):
    lines = ["| 실험 | 조건 | n | 실패 | 지표 | p50 | p90 |", "|---|---|---|---|---|---|---|"]
    for (experiment, label), entry in summary.items():
        for metric in METRICS:
            stats = entry.get(metric)
            if not stats or stats["p50"] is None:
                continue
            lines.append(
                f"| {experiment} | {label} | {entry['n']} | {entry['failed']} | {metric} "
                f"| {stats['p50']:.1f} | {stats['p90']:.1f} |"
            )
    return "\n".join(lines)


def parseArgs(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", dest="baseUrl", default="http://127.0.0.1:11434")
    parser.add_argument("--api", choices=["openai", "ollama"], default="ollama")
    parser.add_argument("--model", required=True)
    parser.add_argument("--experiments", default="ctx,prefix,judge")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--ctx-chars", dest="ctxChars", default="1000,6000,12000,24000",
                        help="대화 원문 글자 수 목록. 실제 토큰 수는 결과의 promptTokens로 확인한다")
    parser.add_argument("--prefix-chars", dest="prefixChars", type=int, default=6000)
    parser.add_argument("--prefix-warm-steps", dest="prefixWarmSteps", type=int, default=3)
    parser.add_argument("--max-tokens", dest="maxTokens", type=int, default=150)
    parser.add_argument("--judge-max-tokens", dest="judgeMaxTokens", type=int, default=120)
    parser.add_argument("--num-ctx", dest="numCtx", type=int, default=16384,
                        help="ollama API에서만 쓴다. 다른 엔진은 서버 실행 옵션으로 정한다")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--note", default="", help="엔진 설정 등 메모 (예: OLLAMA_NUM_PARALLEL=2)")
    parser.add_argument("--out-dir", dest="outDir", default=str(HERE / "results"))
    args = parser.parse_args(argv)
    args.ctxChars = [int(v) for v in args.ctxChars.split(",") if v]
    args.experiments = [v for v in args.experiments.split(",") if v]
    unknown = set(args.experiments) - EXPERIMENTS.keys()
    if unknown:
        parser.error(f"unknown experiments: {sorted(unknown)}")
    return args


def main(argv=None):
    args = parseArgs(argv)
    outDir = Path(args.outDir)
    outDir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outPath = outDir / f"llm-{stamp}.jsonl"
    rows = []

    with outPath.open("w", encoding="utf-8") as outFile:
        header = {
            "experiment": "meta",
            "startedAt": stamp,
            "args": {k: v for k, v in vars(args).items() if k != "outDir"},
            "env": env_info.collect(api=args.api),
        }
        outFile.write(json.dumps(header, ensure_ascii=False) + "\n")

        def emit(row):
            if row.get("ok") and row.get("promptTokens") and args.api == "ollama":
                if row["promptTokens"] >= args.numCtx - args.maxTokens:
                    row["warning"] = "프롬프트가 num_ctx에 닿음: 잘렸을 수 있다"
            rows.append(row)
            outFile.write(json.dumps(row, ensure_ascii=False) + "\n")
            outFile.flush()
            status = "ok" if row["ok"] else f"FAIL {row.get('error')}"
            print(f"[{row['experiment']}/{row['label']}] {status}", flush=True)

        emit(warmUp(args))
        for name in args.experiments:
            EXPERIMENTS[name](args, emit)

        vram = env_info.vramSnapshot()
        outFile.write(json.dumps({"experiment": "vram", **vram}, ensure_ascii=False) + "\n")

    print()
    print(formatSummary(summarize(rows, METRICS)))
    print()
    print("VRAM (측정 직후):", json.dumps(vram, ensure_ascii=False, indent=2))
    print(f"결과: {outPath}")


if __name__ == "__main__":
    main()
