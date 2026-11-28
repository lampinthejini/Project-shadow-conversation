"""0단계 측정 도구 테스트. 실제 모델 없이 로컬 스텁 서버로 검사한다."""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_client  # noqa: E402
import bench_llm  # noqa: E402


class StubHandler(BaseHTTPRequestHandler):
    """OpenAI 호환(SSE)과 Ollama 네이티브(NDJSON) 스트리밍을 흉내 낸다."""

    delayFirstChunk = 0.05
    failStatus = None
    chunks = ["안", "녕", "하세요"]

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.server.lastBodies.append(body)
        if self.failStatus:
            self.send_response(self.failStatus)
            self.end_headers()
            self.wfile.write(b"error")
            return
        # 판정기 역할처럼 보이면 지연을 다르게 준다
        isJudge = "JUDGE" in json.dumps(body, ensure_ascii=False)
        delay = self.server.judgeDelay if isJudge else self.delayFirstChunk
        self.send_response(200)
        if self.path.startswith("/v1/"):
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            time.sleep(delay)
            for text in self.chunks:
                payload = {"choices": [{"delta": {"content": text}}]}
                self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.01)
            usage = {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 3}}
            self.wfile.write(f"data: {json.dumps(usage)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            time.sleep(delay)
            for text in self.chunks:
                line = {"message": {"content": text}, "done": False}
                self.wfile.write((json.dumps(line) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.01)
            final = {
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 120,
                "prompt_eval_duration": 40_000_000,
                "eval_count": 3,
                "eval_duration": 30_000_000,
            }
            self.wfile.write((json.dumps(final) + "\n").encode())


@pytest.fixture
def stubServer():
    StubHandler.failStatus = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    server.lastBodies = []
    server.judgeDelay = 0.05
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def baseUrl(server):
    return f"http://127.0.0.1:{server.server_address[1]}"


MESSAGES = [{"role": "user", "content": "테스트"}]


@pytest.mark.parametrize("api", ["openai", "ollama"])
def test_streamChat_measuresTtftAndTokens(stubServer, api):
    result = llm_client.streamChat(baseUrl(stubServer), "m", MESSAGES, api=api, maxTokens=10)
    assert result["ok"] is True
    assert result["text"] == "안녕하세요"
    assert result["promptTokens"] == 120
    assert result["completionTokens"] == 3
    assert 40 <= result["ttftMs"] <= result["totalMs"]


def test_streamChat_ollamaReportsEngineTimings(stubServer):
    result = llm_client.streamChat(baseUrl(stubServer), "m", MESSAGES, api="ollama")
    assert result["enginePromptMs"] == pytest.approx(40.0)
    assert result["engineDecodeMs"] == pytest.approx(30.0)


def test_streamChat_ollamaSendsNumCtx(stubServer):
    llm_client.streamChat(baseUrl(stubServer), "m", MESSAGES, api="ollama", numCtx=16384)
    assert stubServer.lastBodies[-1]["options"]["num_ctx"] == 16384


def test_streamChat_openaiRequestsUsage(stubServer):
    llm_client.streamChat(baseUrl(stubServer), "m", MESSAGES, api="openai")
    assert stubServer.lastBodies[-1]["stream_options"] == {"include_usage": True}


def test_streamChat_httpErrorIsReportedNotRaised(stubServer):
    StubHandler.failStatus = 500
    result = llm_client.streamChat(baseUrl(stubServer), "m", MESSAGES)
    assert result["ok"] is False
    assert "500" in result["error"]


def test_streamChat_timeoutIsReportedNotRaised(stubServer):
    stubServer.judgeDelay = 1.0
    judgeMessages = [{"role": "user", "content": "JUDGE"}]
    result = llm_client.streamChat(baseUrl(stubServer), "m", judgeMessages, timeoutSec=0.2)
    assert result["ok"] is False
    assert result["error"]


def test_streamChat_connectionRefused():
    result = llm_client.streamChat("http://127.0.0.1:1", "m", MESSAGES, timeoutSec=1)
    assert result["ok"] is False


def test_percentile():
    values = list(range(1, 11))
    assert bench_llm.percentile(values, 50) == pytest.approx(5.5)
    assert bench_llm.percentile(values, 90) == pytest.approx(9.1)
    assert bench_llm.percentile([7], 90) == 7
    assert bench_llm.percentile([], 90) is None


def test_buildFiller_reachesTargetSizeAndIsDeterministic():
    first = bench_llm.buildFillerTurns(4000)
    second = bench_llm.buildFillerTurns(4000)
    assert first == second
    totalChars = sum(len(m["content"]) for m in first)
    assert totalChars >= 4000
    assert [m["role"] for m in first[:2]] == ["user", "assistant"]


def test_releaseLatency_parallelUsesMaxSequentialUsesSum(stubServer):
    """판정 통과 전에는 내보내지 않으므로 공개 시점은 둘 다 끝난 시점이다."""
    stubServer.judgeDelay = 0.3
    url = baseUrl(stubServer)
    judgeMsgs = [{"role": "user", "content": "JUDGE"}]
    shadowMsgs = [{"role": "user", "content": "SHADOW"}]
    seq = bench_llm.runJudgeAndShadow(url, "m", judgeMsgs, shadowMsgs, mode="sequential", api="openai")
    par = bench_llm.runJudgeAndShadow(url, "m", judgeMsgs, shadowMsgs, mode="parallel", api="openai")
    assert seq["ok"] and par["ok"]
    assert seq["releaseMs"] >= seq["judge"]["totalMs"] + seq["shadow"]["totalMs"] - 5
    assert par["releaseMs"] >= max(par["judge"]["totalMs"], par["shadow"]["totalMs"]) - 5
    assert par["releaseMs"] < seq["releaseMs"]


def test_releaseLatency_failedJudgeMeansNoRelease(stubServer):
    StubHandler.failStatus = 500
    url = baseUrl(stubServer)
    result = bench_llm.runJudgeAndShadow(url, "m", MESSAGES, MESSAGES, mode="parallel")
    assert result["ok"] is False
    assert result["releaseMs"] is None


def test_summarize_groupsAndComputesStats():
    rows = [
        {"experiment": "ctx", "label": "1k", "ok": True, "ttftMs": v, "totalMs": v * 2}
        for v in (100, 200, 300)
    ] + [{"experiment": "ctx", "label": "1k", "ok": False, "ttftMs": None, "totalMs": None}]
    summary = bench_llm.summarize(rows, ["ttftMs", "totalMs"])
    entry = summary[("ctx", "1k")]
    assert entry["n"] == 3
    assert entry["failed"] == 1
    assert entry["ttftMs"]["p50"] == 200
