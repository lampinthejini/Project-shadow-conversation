"""0단계 측정용 스트리밍 클라이언트 (표준 라이브러리만 사용).

두 가지 API를 지원한다. 둘 다 localhost 서빙 엔진만 대상으로 한다.
- openai: OpenAI 호환 /v1/chat/completions (llama.cpp server, Ollama, vLLM 등)
- ollama: Ollama 네이티브 /api/chat. num_ctx 지정과 엔진 쪽 시간 측정을 받을 수 있다.

예외를 던지지 않고 결과 dict의 ok/error로 실패를 알린다.
"""

import json
import time
import urllib.error
import urllib.request


def emptyResult():
    return {
        "ok": False,
        "error": None,
        "text": "",
        "ttftMs": None,
        "totalMs": None,
        "promptTokens": None,
        "completionTokens": None,
        "enginePromptMs": None,
        "engineDecodeMs": None,
    }


def buildRequest(baseUrl, model, messages, api, maxTokens, temperature, numCtx, seed):
    if api == "openai":
        url = baseUrl.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": maxTokens,
            "temperature": temperature,
        }
        if seed is not None:
            body["seed"] = seed
    elif api == "ollama":
        url = baseUrl.rstrip("/") + "/api/chat"
        options = {"num_predict": maxTokens, "temperature": temperature}
        if numCtx:
            options["num_ctx"] = numCtx
        if seed is not None:
            options["seed"] = seed
        body = {"model": model, "messages": messages, "stream": True, "options": options}
    else:
        raise ValueError(f"unknown api: {api}")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})


def parseOpenaiLine(line, result):
    """SSE 한 줄을 읽어 result를 갱신한다. 본문 조각이 있으면 그 문자열을 돌려준다."""
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    chunk = json.loads(payload)
    usage = chunk.get("usage")
    if usage:
        result["promptTokens"] = usage.get("prompt_tokens")
        result["completionTokens"] = usage.get("completion_tokens")
    timings = chunk.get("timings")  # llama.cpp server가 주는 엔진 측 시간
    if timings:
        result["enginePromptMs"] = timings.get("prompt_ms")
        result["engineDecodeMs"] = timings.get("predicted_ms")
    for choice in chunk.get("choices") or []:
        content = (choice.get("delta") or {}).get("content")
        if content:
            return content
    return None


def parseOllamaLine(line, result):
    if not line.strip():
        return None
    chunk = json.loads(line)
    if chunk.get("error"):
        raise RuntimeError(chunk["error"])
    if chunk.get("done"):
        result["promptTokens"] = chunk.get("prompt_eval_count")
        result["completionTokens"] = chunk.get("eval_count")
        if chunk.get("prompt_eval_duration") is not None:
            result["enginePromptMs"] = chunk["prompt_eval_duration"] / 1e6
        if chunk.get("eval_duration") is not None:
            result["engineDecodeMs"] = chunk["eval_duration"] / 1e6
    content = (chunk.get("message") or {}).get("content")
    return content or None


def streamChat(
    baseUrl,
    model,
    messages,
    api="openai",
    maxTokens=200,
    temperature=0.7,
    numCtx=None,
    seed=None,
    timeoutSec=120,
):
    """한 번 생성하고 첫 토큰 시간(ttftMs)과 전체 시간(totalMs)을 잰다.

    시간은 요청을 보내기 직전부터 클라이언트 쪽에서 잰다.
    """
    result = emptyResult()
    request = buildRequest(baseUrl, model, messages, api, maxTokens, temperature, numCtx, seed)
    parseLine = parseOpenaiLine if api == "openai" else parseOllamaLine
    pieces = []
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeoutSec) as response:
            for rawLine in response:
                content = parseLine(rawLine.decode("utf-8").rstrip("\r\n"), result)
                if content:
                    if result["ttftMs"] is None:
                        result["ttftMs"] = (time.perf_counter() - start) * 1000
                    pieces.append(content)
        result["totalMs"] = (time.perf_counter() - start) * 1000
        result["text"] = "".join(pieces)
        result["ok"] = bool(pieces)
        if not pieces:
            result["error"] = "empty response"
    except urllib.error.HTTPError as error:
        result["error"] = f"HTTP {error.code}"
    except Exception as error:  # 측정 도구라 모든 실패를 기록하고 계속한다
        result["error"] = f"{type(error).__name__}: {error}"
    return result
