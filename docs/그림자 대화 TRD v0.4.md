# 그림자 대화 TRD v0.4

## 0. 문서 정보

| 항목 | 내용 |
| --- | --- |
| 문서명 | 그림자 대화(SHADOW) 기술 요구사항 정의서 |
| 버전 | v0.4 |
| 기준 문서 | docs/그림자 대화 PRD v0.9.1.md, docs/그림자 대화 화면정의서 v0.2.md, CLAUDE.md |
| 작성일 | 2026-11-26 (v0.4: 2026-11-27) |
| 상태 | 초안. 0단계(기술 검증) 실측 전 |
| 범위 | 사양과 무관한 부분(API, 데이터 모델, 오케스트레이터 처리 순서, 보안·보존 규칙)을 정한다. 서빙 엔진·모델·음성 모델·성능 수치는 "미검증"으로 남긴다 |

### 표기 규칙

| 표기 | 의미 |
| --- | --- |
| [기준] | PRD의 [확정] 사항이나 CLAUDE.md 4절의 확정 원칙을 기술 사양으로 옮긴 것. TRD에서 바꾸지 않는다 |
| [PRD] | PRD의 [제안]을 그대로 따른 것. PRD가 바뀌면 함께 바뀐다 |
| [설계] | 이 TRD가 정하는 사양 무관 설계. 사용자가 승인한 결정(12.1)도 여기에 든다 |
| [제안] | TRD가 안을 만들었고 사용자 확인이 남은 것. 12.2에 모은다 |
| [가설] | 수치 목표. 0단계 실측·테스트 후 조정 |
| 미검증 | 0단계 실측 전이라 값이나 기술을 정하지 않은 것 |

### 전제

- 이 문서의 수치는 PRD 값을 옮겼거나 [가설]·[제안] 값이다. 실측값은 없다.
- 이름 규칙(CLAUDE.md 8절)
  - 필드와 파라미터는 lowerCamelCase로 쓴다.
  - 엔터티는 PascalCase로 쓴다.
  - 오류 코드는 UPPER_SNAKE_CASE로 쓴다.
  - 이벤트 이름과 고정 문구 키(fixedTextKey)는 `영역.동작` 형식으로 쓴다.
  - 오류 코드·이벤트·고정 문구 키는 외부 계약이라 읽기 쉽게 하려고 예외를 둔다. 이 예외는 사용자 확인이 필요하다(12.2 D-T22).
- 기술 이름(SSE, WebSocket, argon2id 등)은 후보로만 적는다.

---

## 1. 시스템 구성 (논리 구성)

모든 LLM 호출은 오케스트레이터를 거치고, 클라이언트는 모델을 직접 부르지 않는다 [PRD 9절].

| 구성 요소 | 책임 | 기술 |
| --- | --- | --- |
| 웹 클라이언트 | 화면 SCR-01~08, 마이크·카메라 트랙 제어, 브라우저 안 표정 분석, 위기 카드·녹음 음성 표시(정적 자산 내장) | 미검증 |
| API 서버 + 오케스트레이터 | 인증, REST API, 사용자 이벤트 채널, 턴 처리(5절), 키워드 규칙, 출력 금지 사전 검사, 출력 확정, 세션 메모리 | Python 후보(CLAUDE.md 5절). 프레임워크는 미검증 |
| LLM 서빙 | 지배인·그림자·판정기 세 역할이 모델 인스턴스 하나를 공유 | 엔진은 미검증(prefix caching 필요). EXAONE 3.5 7.8B 후보. 양자화는 미검증 |
| 음성 서버 | VAD, 화자 확인, STT, 운율 분석, TTS, 에코 차단 | 모델 모두 미검증(4단계) |
| 요약 워커 | 롤링 요약 | 실행 방식 미검증 |
| 저장소 | 로컬 DB(필드 암호화), 키 저장소(6.2), 로컬 파일(콘텐츠) | DB 엔진과 암호화 라이브러리 미검증 |

**프로세스 경계** [기준]

- 음성 원본은 음성 서버의 메모리 안에서만 다룬다. 화자 확인에 실패한 발화는 음성 서버 밖으로 나가지 않는다.
- 카메라 영상은 브라우저 밖으로 나가지 않는다. 서버는 허용 목록 안의 표정 신호와 신뢰도만 받는다.
- 외부 네트워크 호출은 없다.

**GPU 요청 우선순위** [설계]: 위기 판정 > 그림자·지배인 생성 > 기분 추출 > 요약 순서다. 큐 구현은 미검증이다.

---

## 2. 데이터 모델

### 2.1 저장 엔터티 [설계]

🔒 표시는 필드 단위 암호화 대상이다. 어느 키로 암호화하는지는 6.2에 정한다.

| 엔터티 | 필드 | 비고 |
| --- | --- | --- |
| User | userId, loginId, passwordHash, mustChangePassword, passwordResetAt, isAdultVerified, accessExpiresAt, createdAt, voiceprint🔒(선택, 4단계) | 실명은 없다. isAdultVerified는 외부 공개 때부터 쓴다. 테스트 단계에서는 쓰지 않는다(3절). accessExpiresAt은 테스트 계정의 만료일이다 |
| Consent | userId, consentType(sensitive / innerVoice / expression), granted, updatedAt | 항목과 시각만 남긴다 |
| Interview | interviewId, userId, situation, status(active / held / confirmed / discarded), answers🔒, cardDraft🔒, maxCrisisLevel🔒, createdAt, lastActiveAt | 인터뷰 중 임시 데이터. 사용자 키로 암호화한다. 확정하면 Shadow로 옮기고 지운다. 위기로 판정된 답변은 answers에 넣지 않는다 |
| Shadow | shadowId, userId, situation, relationType🔒, timeAxis, card🔒, voicePreset(4단계), lastVisitedAt, createdAt | 선명도는 갈래별로 둔다. PRD 9절의 "상태"는 lastVisitedAt으로 대신한다("잠든 그림자" 연출용) |
| Branch | branchId, shadowId, parentBranchId, forkMessageId, forkSummarySnapshot🔒, clarity(1~4), createdAt, deletedAt | parentBranchId는 forkMessageId를 소유한 갈래다(2.3) |
| Message | messageId, branchId, sessionId, seq, speaker(user / shadow / host), content🔒, judgeLevel🔒, isFixedText, excludeFromContext, refCount, purgedAt, createdAt | seq는 계보 전체에서 이어진다(2.3). PRD 9절의 parent_id 대신 (계보, seq)로 순서를 정한다 |
| Session | sessionId, branchId, state(5.10), camOff, startedAt, endedAt, endReason(closure / userEnd / release / leave / crisis / harmEscalation / judgeFailed / deleted / consentWithdrawn), maxCrisisLevel🔒, lightState | lightState는 연출 값이고 사용 한도가 아니다 |
| OpenTurn | turnId, scope(session / interview), scopeId, clientTurnIds, failCount, status(pending / retryRequested / interrupted / closed), createdAt | 내용은 없다. 실패 횟수는 여기에만 둔다. 서버가 재시작해도 "같은 턴"의 실패 횟수가 유지된다. 키워드에 걸린 턴도 기록한다(멱등용) |
| Summary | summaryId, branchId, round, coveredUntilSeq, body🔒, nextHint🔒 | 기분·표정·위기 발화를 넣지 않는다 |
| SavePoint | branchId, lastMessageId, resumeSnapshot🔒 | 기분 블록은 넣지 않는다 |
| CrisisEvent | userId, scope, scopeId, level🔒, source(keyword / judge / inner), createdAt | 내용은 없다. source에 등급을 담지 않는다. L2에서 L3로 올라가면 한 건을 더 남긴다 |
| CrisisLock | userId, lockedUntil | L3이면 서버 시각으로 자정까지 잠근다 [기준, PRD v0.9 7절]. 만료된 행은 정리 작업이 지운다 |
| DistressCount | userId, sessionId, count, createdAt | 반복 고통 신호의 횟수만 둔다(F-15, P1). 내용은 없다. 안전 권유 말고 다른 곳(이용 제한, 통계, 지표)에는 쓰지 않는다 [기준, PRD 7절] |
| Settings | userId, autoDeleteEnabled(기본 false), autoDeleteDays(180 [가설]), camOffDefault(기본 true) | |
| OperatorAccessLog | operatorId, action(contentAccess / passwordReset / accountIssue / crisisNotice), targetId, reasonCode(열거형), createdAt | 사유는 자유 서술 대신 코드로 남긴다 |
| ErrorLog | errorId, code, requestId, createdAt | 내용은 없다 |

**PRD 9절과 다른 점**

- 새로 넣은 엔터티: Interview, OpenTurn, CrisisLock, DistressCount, Consent, Settings, OperatorAccessLog
- 필드를 더하거나 바꾼 엔터티
  - Message: seq, judgeLevel, isFixedText, excludeFromContext, refCount, purgedAt을 더했고 parent_id를 뺐다.
  - Session: endReason 값을 늘렸다.
  - Branch: forkSummarySnapshot을 더했다.
  - CrisisEvent: source를 더했다.
- F-20(고인 그림자)용 필드는 지금 두지 않는다. 나중에 Shadow에 유형 필드를 더할 수 있다.

### 2.2 세션 메모리 (DB에 저장하지 않는 것) [기준]

| 항목 | 지우는 때 |
| --- | --- |
| 생성 중인 응답 버퍼 | 출력 확정 뒤 저장할 때, 또는 폐기할 때 |
| 기분 라벨·강도, 표정 신호 | 세션 종료, 동의 철회·camOff 전환 즉시, 서버 재시작 |
| 속마음 전사 원문 | 판정 종료 즉시(등급과 관계없이). L0이면 기분을 추출한 직후 |
| 음성 원본(음성 서버) | STT·운율 분석 직후 |
| 진행 중인 속마음 수(innerPending) | 판정 종료, 화자 확인 실패 |
| 위기 held 플래그(scope별, 사용자별 L3) | DB에 반영되고 상태가 끝날 때 |
| 타해 구체 위협 연속 횟수(harmStreak). 횟수만 두고 내용은 두지 않는다 | 세션 종료, concrete가 아닌 판정이 나올 때 0으로 |
| 이벤트 재전송 버퍼 | 아래 규칙 |

**이벤트 재전송 버퍼**

- 짧은 TTL [가설]과 보관 개수 [가설] 안에서만 둔다.
- 다음 경우에는 해당 scope의 이벤트를 즉시 지운다.
  - 갈래·그림자·기록 삭제
  - 세션이 ended가 될 때
  - 동의 철회
  - 로그아웃
- mood.update와 interview.cardDraft는 재전송하지 않는다. 재연결하면 GET으로 현재 값만 받는다.

**공통 규칙**

- 세션 메모리 항목은 로그·오류 응답·요약·덤프 어디에도 넣지 않는다.
- 서버가 재시작하면 세션 메모리는 모두 사라진다.
  - 상태가 불확실한 OpenTurn은 재입력 요청(고정 문구)으로 처리한다. failCount는 유지한다.
  - 위기 held는 DB나 위기 표식(5.3)에서 되살린다.

### 2.3 갈래 계보·참조 카운트·삭제 [설계, CLAUDE.md 4.4 · PRD 9절]

**계보**

- 갈래 B의 대화는 두 부분으로 이루어진다.
  - 부모 계보에서 forkMessageId까지의 메시지
  - B가 소유한 메시지
- 메시지는 처음 만든 갈래가 소유하고, 복사하지 않는다. Message를 수정하는 API는 없다(원본 불변).
- parentBranchId는 forkMessageId를 소유한 갈래다. 사용자가 보고 있던 갈래와 다를 수 있다.
- seq는 계보 전체에서 이어진다. 새 갈래의 첫 메시지는 분기 지점 seq + 1부터 시작한다. 그래서 같은 계보 안에서 seq와 coveredUntilSeq를 비교할 수 있다.

**참조 카운트**

- Message.refCount는 다음 둘을 더한 값이다.
  - 소유 갈래가 살아 있으면 1
  - 그 메시지를 계보에 포함하는 살아 있는 자손 갈래의 수
- 분기할 때는 계보에 포함되는 메시지의 refCount를 모두 1 올린다. 갈래 생성과 같은 트랜잭션에서 한다.

**분기 지점** [설계, D-T06]

- SCR-07에서 고른 "장면"이 사용자 대사면, forkMessageId는 그 바로 앞 메시지다. 새 갈래는 사용자의 새 답부터 시작한다.
- 그림자 대사를 골랐으면 그 대사가 forkMessageId다.
- 원문이 파기된 지점(purgedAt)에서는 분기할 수 없다(422 SOURCE_PURGED).

**분기 시점 요약**

- forkSummarySnapshot은 같은 계보에서 coveredUntilSeq가 분기 지점 seq 이하인 가장 최근 요약을 복사한 것이다.
- 그 요약 뒤부터 분기 지점까지는 원문 메시지를 계보로 참조한다.
- 새 갈래의 요약은 따로 쌓는다.

**갈래 삭제** (하나의 트랜잭션. 실패하면 전부 되돌린다)

1. 그림자 행을 잠근다. 대상 갈래에서 ended가 아닌 세션(active / paused / held / closing)을 모두 endReason=deleted로 닫고, 세션 메모리와 그 세션의 재전송 이벤트를 지운다.
2. deletedAt을 채운다. 목록에서 즉시 사라진다.
3. 계보 메시지의 refCount를 1씩 내리고, 0이 된 메시지를 지운다.
4. 그 갈래의 Summary·SavePoint는 자손이 있어도 바로 지운다. 자손은 forkSummarySnapshot이 있어 독립적으로 이어진다.
5. 정리 연쇄
   - 소유 메시지가 모두 지워졌고 살아 있는 자손도 없는 삭제 갈래 행을 지운다.
   - 그 부모가 같은 조건이면 이어서 지운다.
6. 살아 있는 갈래가 하나도 남지 않으면 그림자 삭제(아래)로 이어진다 [기준, PRD v0.9 9절 7].
7. 요약 워커의 대기 작업 가운데 지운 갈래의 것을 취소한다.

**그림자 삭제** (하나의 트랜잭션)

- 세션을 닫는다.
- 모든 갈래·메시지·요약·세이브 포인트를 지운다.
- 그 그림자의 데이터 키를 폐기한다(6.2).

**트리 표시**

- 지운 조상 갈래는 내용 없이 "지운 갈래" 자리 표시로만 그린다.
- GET /branches/{id}의 sharedPrefix는 refCount가 2 이상인 메시지가 있는지를 알려준다. 삭제 확인창 문구에 쓴다.

**동시성**

- 분기·삭제·세션 시작·세션 close는 같은 그림자 잠금 아래에서 차례로 처리한다. 각 처리는 잠금 안에서 deletedAt을 다시 확인한다.
- deletedAt이 있는 갈래에 분기·세션 시작·조회를 요청하면 404다.

---

## 3. 인증·권한·테스트 계정 [설계]

| 항목 | 규칙 |
| --- | --- |
| 테스트 단계 | 외부 공개 전에는 가입 API가 없다. 3단계 통과 전에는 운영자 본인만 쓰고, 지인 체험은 그 뒤에 한다 [기준, PRD v0.9 F-02] |
| 계정 발급 | 운영자 CLI로 만든다. 일회용 초기 비밀번호와 만료일을 넣는다. 첫 로그인 뒤 비밀번호를 바꾸기 전에는 다른 API를 쓸 수 없다(403 PASSWORD_CHANGE_REQUIRED) |
| 비밀번호 재설정 | 운영자가 재설정하면 mustChangePassword를 다시 켠다. 사용자가 비밀번호를 바꾸기 전에는 대화·기록 API를 쓸 수 없다. 운영자가 임시 비밀번호로 대화를 볼 수 없게 하려는 것이다. 다음 로그인 때 재설정 시각을 알린다. 발급·재설정은 OperatorAccessLog에 남긴다 |
| 발급 절차 | 한 사람에 계정 하나. 공유 금지를 고지한다. 테스트가 끝나면 계정을 모두 삭제한다고 고지한다. 성인 확인은 테스트 단계에서 시스템 기능으로 만들지 않는다 [기준, PRD v0.9 F-02]. 운영자가 발급할 때 구두로만 확인한다 [제안, D-T08] |
| 비밀번호 저장 | 느린 KDF(argon2id 후보)로 해시한다 |
| 세션 토큰 | HttpOnly·SameSite 쿠키. 무활동 만료는 기본 12시간 [제안]. 로그아웃하면 서버에서 무효화한다 |
| 권한 | 모든 리소스는 userId 범위로 제한한다. 다른 사용자의 리소스는 404 |
| 접근 게이트 | 로그인 전에는 /auth/*와 정적 자산만 쓸 수 있다. sensitive 동의 전에는 인터뷰·세션 API가 403 CONSENT_REQUIRED |
| 위기 잠금 | CrisisLock이 있으면 사용자 단위 미들웨어가 막는다. 대상은 인터뷰 생성·답변·카드·확정, 분기, 세션 시작·턴·resume·checkin이고 응답은 423 CRISIS_LOCK이다. 화면에서 버튼을 비활성하는 것만으로 막지 않는다. 단, 키워드 검사는 잠금 판정보다 먼저 한다(4.1) |
| 운영자 | 원문을 열람하는 운영 화면은 없다. 예외 접근은 사유 코드와 함께 기록한다. excludeFromContext 메시지(위기 문장)는 예외 접근 대상에서도 뺀다 [제안, D-T23] |

---

## 4. API

### 4.1 공통 규칙 [설계]

**전송 방식**

- 요청은 REST(JSON)로 보낸다.
- 결과와 알림은 **사용자 단위 이벤트 채널**(GET /events) 하나로 받는다. 전송 방식(SSE / WebSocket)은 미검증이다.
- 모든 이벤트에 공통으로 붙는 필드: scope(session / interview / user), scopeId, eventSeq, epoch
  - eventSeq는 사용자 단위 순번이다.
  - epoch는 서버가 시작할 때마다 바뀐다. 클라이언트는 epoch가 바뀌면 재전송을 기대하지 않고 GET으로 상태를 다시 받는다.
- 재연결하면 마지막으로 받은 eventSeq 뒤의 이벤트를 다시 보낸다. 재전송 버퍼 규칙은 2.2를 따른다.
- 재연결한 클라이언트는 GET /sessions/{id}, GET /interviews/{id}, GET /me로 상태를 다시 받는다.
  - state가 held(crisis)면 위기 카드를 다시 띄운다.
  - 등급은 응답의 crisisLevel과 GET /me의 crisisLock으로 정한다. 잠금이 있으면 L3 카드를 띄운다.

**응답과 캐시**

- 오류 본문은 `{ "error": { "code": "...", "messageKey": "..." } }` 형식이다. 입력·대화 내용·모델 출력은 넣지 않는다.
- 대화·기록·음성 응답에는 `Cache-Control: no-store`를 붙인다.

**입력 처리 순서** (텍스트를 받는 모든 API: turns, answers, card 수정, checkin)

1. 인증(401)
2. 멱등 처리: 이미 받은 clientTurnId면 처음 받은 turnId를 돌려준다.
3. **키워드 규칙**: 텍스트 전체에 적용한다. 길이 상한을 넘는 입력도 전체를 검사한다.
   - 걸리면 다른 검사보다 먼저 위기 경로(5.3)로 간다. 처리 중인 턴이 있어도 그 턴을 버린다.
   - 응답은 202이고 본문에 `crisisLevel`을 바로 담는다. 이벤트 채널이 끊겨 있어도 클라이언트가 카드를 띄울 수 있게 하려는 것이다.
   - 그 scope가 이미 held·ended·confirmed이거나 동의 전 상태여도 카드를 띄우고 CrisisEvent를 남긴다. L3면 잠금도 건다. 상태는 바꾸지 않는다.
4. 그 밖의 검사: 동의(403) → 위기 잠금(423) → 형식·길이(422) → 상태(409) → 처리 중인 턴(409)

**재입력과 길이 상한**

- 재입력은 새 clientTurnId에 retryOfTurnId를 붙여 보낸다.
- 그 scope에 retryRequested 상태의 OpenTurn이 있으면, retryOfTurnId가 없어도 서버가 다음 입력을 그 턴에 묶는다. 그래서 failCount가 처음부터 다시 세어지지 않는다.
- 입력 길이 상한은 한 턴 2,000자, 카드 항목 200자다 [제안, D-T12]. 넘으면 422다(키워드 검사 뒤).

**401일 때 위기 문장** [제안, D-T24]

- 클라이언트는 보내지 못한 입력을 메모리에 두었다가, 다시 로그인한 뒤 다시 보낸다.
- 로그인 화면에는 위기 연락처 열람 링크(정적 자산)를 둔다.

### 4.2 오류 코드

| code | HTTP | 의미 |
| --- | --- | --- |
| AUTH_REQUIRED | 401 | 로그인 필요, 토큰 만료 |
| PASSWORD_CHANGE_REQUIRED | 403 | 초기 비밀번호나 재설정된 비밀번호를 아직 바꾸지 않음 |
| CONSENT_REQUIRED | 403 | 민감정보 동의 전, 또는 동의 철회 뒤 |
| CHANNEL_CONSENT_REQUIRED | 403 | 속마음·표정 동의 없이 해당 채널을 씀, 또는 camOff=true인데 표정을 보냄 |
| NOT_FOUND | 404 | 없음, 다른 사용자 소유, 삭제된 갈래 |
| TURN_IN_PROGRESS | 409 | 처리 중인 턴이 있음 |
| SESSION_PAUSED | 409 | 설정 진입(paused) 중에 턴을 보냄 |
| SESSION_CLOSING | 409 | closing 상태에서 checkin이 아닌 턴을 보냄 |
| SESSION_HELD | 409 | 보류된 세션·인터뷰에 입력, 또는 held 상태에서 resume |
| SESSION_ENDED | 409 | 종료된 세션에 입력 |
| INTERVIEW_STATE | 409 | 확정·폐기된 인터뷰에 입력, 또는 판정을 거친 카드 초안 없이 확정 |
| VALIDATION_FAILED | 422 | 형식·길이 오류, 허용 목록 밖의 신호·기분 라벨, 이미지·음성 payload |
| SOURCE_PURGED | 422 | 원문이 파기된 지점에서 분기 |
| CRISIS_LOCK | 423 | L3 잠금 중. "잠김"이라는 뜻을 살려 403과 구분한다 |
| DELETE_FAILED | 500 | 삭제 트랜잭션 실패. 전부 되돌렸음 |
| INTERNAL_ERROR | 500 | 그 밖의 서버 오류 |
| SERVER_BUSY | 503 | 동시 처리 한도를 넘음. 인터뷰 시작·세션 시작에만 쓴다. 진행 중인 턴은 거절하지 않고 대기열에 넣는다 [설계, PRD 10절 "갑자기 끊지 않는다" 취지] |

### 4.3 엔드포인트

| 메서드 · 경로 | 요청 | 응답 | 관련 |
| --- | --- | --- | --- |
| POST /auth/login | loginId, password | 200 + 쿠키(mustChangePassword, passwordResetAt 포함) / 401 | F-02 |
| POST /auth/password | currentPassword, newPassword | 204 | 3절 |
| POST /auth/logout | — | 204 | SCR-08 |
| GET /me | — | 동의 상태, 설정, crisisLock, sameDayL2 | SCR-03 |
| GET /events | lastEventSeq, epoch | 사용자 이벤트 채널(4.4) | — |
| PUT /consents/{consentType} | granted | 200. 철회 처리는 5.12 | CMP-06 |
| POST /interviews | situation | 201 interviewId와 첫 질문(고정 문구) / 403 / 423 / 503 | F-03, F-04 |
| GET /interviews/{id} | — | status, heldReason, crisisLevel, 진행 중인 질문 번호, 판정을 거친 카드 초안 | 재연결 |
| POST /interviews/{id}/answers | questionKey, text, clientTurnId, retryOfTurnId? | 202 turnId(+crisisLevel). 같은 questionKey를 다시 보내면 답을 덮어쓰고 다시 판정한다 | F-04 |
| POST /interviews/{id}/card | — | 202. 카드 초안 생성(LLM) → 출력 검사·마스킹 → interview.cardDraft | 화면정의서 P-05 |
| PUT /interviews/{id}/card | 수정한 카드, clientTurnId | 202(+crisisLevel). 수정본은 키워드 규칙·판정·마스킹을 거쳐 interview.cardDraft로 돌아온다. 사용자는 마스킹된 결과를 미리보기에서 확인한다 | F-04 |
| POST /interviews/{id}/confirm | — | 201 shadowId, branchId. 마지막으로 판정을 거친 초안만 확정한다. 고인 감지 중이면 409 INTERVIEW_STATE(5.13) | F-04 |
| DELETE /interviews/{id} | — | 204 (인터뷰 취소, 보류 안내 확인) | SCR-04 |
| GET /shadows | — | 목록, 마지막 대화 한 줄 요약, 갈래 수 | F-12 |
| DELETE /shadows/{shadowId} | — | 204 / 500 | F-11 |
| GET /shadows/{shadowId}/branches | — | 갈래 트리, clarity, 요약, 생성 시각, 지운 갈래 자리 표시, 원문 파기 여부 | F-18 |
| GET /branches/{branchId} | — | 갈래 정보, sharedPrefix, isLastBranch | 삭제 확인창 |
| GET /branches/{branchId}/messages | cursor, limit | 계보 순서의 대사(읽기 전용) | F-18 |
| POST /branches/{branchId}/forks | sceneMessageId | 201 / 404 / 422 SOURCE_PURGED / 423 | F-18 |
| DELETE /branches/{branchId} | — | 204 / 500. 마지막 갈래면 그림자까지 지운다 | F-11 |
| POST /branches/{branchId}/sessions | camOff | 201 sessionId, 첫 대사(고정 문구. 새 갈래는 없음), sameDayL2 / 423 / 503 | F-05, F-06 |
| GET /sessions/{id} | — | state, heldReason, crisisLevel, camOff, openTurn | 재연결 |
| POST /sessions/{id}/turns | text, clientTurnId, retryOfTurnId? | 202 turnId(+crisisLevel) / 409 | F-07, F-10 |
| PUT /sessions/{id}/camera | camOff | 200. 다음 턴부터 적용한다. camOff=true면 표정 신호 메모리를 지운다 | PRD 6.7 |
| POST /sessions/{id}/pause | — | 200 (설정 진입, 5.6) | 화면정의서 6.4 |
| POST /sessions/{id}/resume | — | 200 / 409 SESSION_HELD | 화면정의서 6.4 |
| POST /sessions/{id}/mood | label, intensity | 200 ("지금 기분"). label은 허용 목록 안에서만 받는다 | PRD 6.5 |
| POST /sessions/{id}/expression | signals[{name, confidence}], at | 204. name은 허용 목록 [가설], confidence는 0~1 | F-19(4단계) |
| POST /sessions/{id}/end | reason(userEnd / closure) | 200 → closing(5.9) | F-08 |
| POST /sessions/{id}/release | — | 202. 그림자의 마지막 대사(LLM, 5.5 규칙) 뒤 closing | PRD 6.2 |
| POST /sessions/{id}/checkin | text, clientTurnId | 202(+crisisLevel). L1 안부에 대한 답. closing에서만 받는다 | PRD 7절 L1 |
| POST /sessions/{id}/close | — | 200 → ended | SCR-06 |
| PUT /settings | autoDeleteEnabled, camOffDefault | 200. camOffDefault는 다음 세션부터 적용 | SCR-08 |
| DELETE /me/records | — | 204 / 500 | F-11 |
| DELETE /me/voiceprint | — | 204 | PRD 6.5 |
| DELETE /me | — | 204 (탈퇴) | F-11 |

- **음성(4단계)**
  - 오디오는 클라이언트에서 음성 서버 채널(speech / inner)로 바로 간다.
  - 말하기 채널의 STT 결과는 음성 서버가 오케스트레이터를 내부 호출해 넘긴다. clientTurnId는 음성 서버가 발급하고, 이 턴도 5.2를 그대로 따른다.
  - 클라이언트는 전사 텍스트를 보내지 않는다.
  - TTS는 음성 참조를 메모리 Blob으로 받아 재생하고, 디스크 캐시에 남기지 않는다.
  - 문장 단위 TTS 스트리밍(PRD 6.5 참고 목표)을 할지는 미검증이다. 하더라도 응답 전체가 확정된 뒤에만 시작한다.
- **정적 자산**: 위기 카드 문구·연락처, 녹음 음성, 튜토리얼 스크립트는 인증 없이 받을 수 있고, 클라이언트에 미리 넣어 둔다.
- **F-15 로비 권유(P1)**: 1단계에는 API가 없다. 도입할 때 GET /me에 내용 없는 권유 플래그를 더한다.

### 4.4 이벤트

모든 이벤트에는 4.1의 공통 필드(scope, scopeId, eventSeq, epoch)가 붙는다.

| type | 데이터 | 언제 |
| --- | --- | --- |
| turn.accepted | turnId | 입력을 접수했을 때 |
| turn.waiting | turnId | 생성·판정 중일 때. 내용은 없다 |
| turn.output | turnId, speaker, text, clarity, lightState, saved | 출력이 확정된 뒤에만 보낸다. 응답 전체를 한 번에 보내고, 선명도도 같은 이벤트로 반영한다 |
| turn.ttsReady | turnId, 음성 참조 | 출력 확정 뒤 TTS 합성이 끝났을 때(4단계) |
| turn.retry | turnId, fixedTextKey | 판정 실패 1회, 중단된 턴, 재시작 뒤 상태 불명 |
| interview.question | text 또는 fixedTextKey | 인터뷰의 다음 질문(판정·출력 검사 뒤) |
| interview.cardDraft | cardDraft(마스킹됨) | 카드 초안 또는 수정본의 판정 결과 |
| crisis.card | level, hostFixedTextKey | 위기가 났을 때. scope.held보다 먼저 보낸다. 받은 클라이언트가 할 일: (1) 현재 화면 위에 카드를 띄운다. (2) 마이크·카메라 트랙과 그림자 오디오 재생을 멈춘다. (3) 같은 scope에서 이 eventSeq보다 큰 turn.output·turn.ttsReady는 무시한다 |
| crisis.upgrade | level=L3 | L2 처리 뒤 판정기가 L3로 올렸을 때 |
| scope.held | reason(crisis / harmEscalation / judgeFailed) | 세션이나 인터뷰가 보류됐을 때 |
| host.suggest | kind(closure / rest / awareness / noCamera / sameDayCare / harmStop), fixedTextKey | 마무리 제안, 쉬어 가기, 자각 환기, 카메라 없음 안내, 같은 날 L2 뒤 안내. 모두 고정 문구다. closure·rest·awareness는 state가 active일 때만 보낸다 |
| host.checkin | fixedTextKey | closing 상태에서 L1 안부를 물을 때 |
| mood.update | label, intensity | 기분 블록을 갱신할 때. 재전송하지 않는다 |
| voice.innerPaused | paused | 에코 차단을 위해 속마음 수집을 잠시 멈출 때 |

turn.output보다 앞서 응답의 일부(토큰, 부분 문장, 음성)를 보내는 이벤트는 없다 [기준, PRD 9절].

---

## 5. 오케스트레이터 처리 순서

### 5.1 원칙 [기준]

1. 판정과 출력 금지 사전 검사가 끝나기 전에는 그림자 응답과 LLM 지배인 응답을 내보내지 않는다. 병렬로 처리하든 순차로 처리하든 같다.
2. 처리 우선순위는 다음 순서다.
   1. 위기 키워드
   2. LLM 판정
   3. 판정이 실패하거나 시간을 넘기면 응답을 폐기하고 재입력을 요청한다.
   4. 같은 턴에서 두 번 실패하면 보류한다.
3. 위기 문구·연락처·음성, 위기 경로의 지배인 대사, 입력 없는 지배인 대사는 고정 문구와 녹음 음성만 쓴다.
4. 표정과 기분은 판정기 입력에 넣지 않는다.
5. scope가 held나 ended가 된 뒤에는 그 scope로 host 이벤트, turn.output, turn.ttsReady를 보내지 않는다. closing은 5.10의 허용 표를 따른다.

### 5.2 텍스트 턴

```
POST /sessions/{id}/turns   (인터뷰 답변·카드 수정·안부 답변도 같은 순서. 역할만 다르다)
 0. 4.1 입력 처리 순서(인증 → 멱등 → 키워드 → 그 밖의 검사)
      └ 키워드 적중 → 처리 중인 턴이 있어도 버리고 5.3
    → OpenTurn 생성 또는 연결 → turn.accepted
 1. [병렬] 판정기 ∥ 응답 생성(버퍼에만 담음)
    [순차] 판정기 → 통과하면 생성          (방식은 서버 설정. 기본값은 0단계 뒤에 정함)
    → turn.waiting
 2. 판정 결과 (시간 초과 3초 [가설]. 판정 호출을 시작한 때부터 잰다. 스키마가 맞지 않으면 실패)
    ├ 실패 → 버퍼 폐기, OpenTurn.failCount += 1
    │     1회 → turn.retry(fixedTextKey=judge.retry)
    │     2회 → 보류(judgeFailed), scope.held
    ├ L2·L3 → 버퍼 폐기 → 5.3
    ├ deceasedReference → 버퍼 폐기 → 5.13
    ├ harmToOthers=concrete (위기 등급 L0·L1) → harmStreak += 1
    │     harmStreak > harmStopTurns [가설] → 버퍼 폐기 → 5.14 (타해 중단)
    │     그 밖 → 버퍼 폐기, 말림 지시 블록을 붙여 다시 생성(L1과 같은 재생성 규칙)
    │            L1이 함께 나왔으면 자각 지시 블록도 붙이고 maxCrisisLevel = max(…, L1)
    │            다시 생성하다 실패하면 → 상황별 고정 말림 문구
    │     concrete가 아니면 harmStreak = 0
    ├ L1 → 버퍼 폐기, 자각 지시 블록을 붙여 다시 생성
    │      다시 생성하다 실패하거나 시간을 넘기면 → 상황별 고정 자각 문구(순환해 연속 반복을 피함)
    │      인터뷰·안부 scope에서는 → 지배인 고정 자각 문구
    │      maxCrisisLevel = max(…, L1)
    └ L0 → 다음 단계
 3. 출력 금지 사전 검사 (그림자·지배인 LLM 출력)
      └ 적중 → 버퍼 폐기, 고정 문구(자각 문구 또는 재입력 요청)로 대체. 위기 카드는 띄우지 않음 [기준]
         - 자해 수단 범주에 걸렸으면 같은 사용자 입력을 판정기에 한 번 더 보냄
           → L2 이상이면 5.3 [설계]
         - 적중 횟수는 내용 없이 센다
           → 한 세션에서 연속 적중 상한 [가설]을 넘으면 host.suggest(rest)
 4. 출력 확정 지점
    a. innerPending 대기
       - 기다리는 대상: 이 시점에 이미 진행 중인 속마음만(그 뒤에 들어온 속마음은 기다리지 않음)
       - scope 잠금 밖에서 기다린다. 상한은 judgeTimeoutMs [가설]
       - 상한을 넘기면 버퍼 폐기, turn.retry. failCount에는 넣지 않음
    b. scope 잠금을 잡고 다음 순서로 확인
       - 메모리 held 플래그(scope, 사용자 L3)
       - DB 상태(5.10 출력 허용 표)
       → 허용되지 않으면 폐기
    c. 마스킹(5.11) → 저장 트랜잭션: user 메시지 + 응답 메시지 + Branch.clarity + SavePoint
       저장 실패 → 한 번 다시 시도. 그래도 실패하면 saved=false로 출력(화면정의서 E-06 배지)
    d. turn.output → (음성 모드) TTS 합성 → turn.ttsReady
       turn.ttsReady를 보내기 전에 b를 다시 확인한다
 5. OpenTurn 닫기, 잠금 해제
 6. 후처리 (비동기. 보류·종료면 건너뜀. 세션 scope에서만)
    - 매듭 점수(10절)가 임계값 [가설] 이상 → host.suggest(closure)
      제안한 뒤로 사용자 턴이 closureResuggestTurns [가설]만큼 쌓이기 전에는 다시 제안하지 않음
      수락은 사용자가 end를 부르는 것으로 대신한다
    - ruminationSignal → host.suggest(rest)를 한 번 보낸다. 다시 권하려면 간격 [가설]을 지켜야 한다
      DistressCount += 1
    - 긴 세션의 자각 환기: 정해진 턴마다 [가설] host.suggest(awareness)를 보내거나,
      그림자의 고정 자각 문구를 순환해서 넣는다
    - 최근 12턴 [가설]을 넘은 원문은 요약 워커로 보낸다
```

- 서빙 엔진이 생성 취소(키워드 적중 때 진행 중인 생성 멈추기)를 지원하는지는 미검증이다. 취소하지 못해도 버퍼를 버리므로 출력은 0건이다.
- 모델 생성 실패(판정은 통과했는데 응답이 없음)도 재입력 요청으로 처리하고 failCount에 넣는다 [제안, D-08].
  - ErrorLog에는 GENERATION_FAILED 코드로 남겨 판정 실패와 구분한다.
  - 두 번째 실패로 보류하면 endReason은 judgeFailed다.
- 대기열에서 기다린 시간은 판정 시간 초과에 넣지 않는다. 대기열 대기가 상한 [가설]을 넘으면 turn.retry를 보내고 failCount에는 넣지 않는다.

**판정기 입력** [설계]

| 넣는 것 | 넣지 않는 것 |
| --- | --- |
| 현재 입력 | 기분 블록 |
| 최근 사용자 대사. excludeFromContext 메시지도 넣는다 | 표정 신호 |
| 직전 그림자 대사 1개. 넣을 때와 뺄 때를 0단계에서 위기 테스트 세트로 비교한 뒤 정한다 | |
| 카드 핵심 항목(관계, 하고 싶은 말) | |
| 최신 요약(선명도·매듭 판단용) | |
| 같은 날 L2가 있었는지(sameDayL2). 내용 없는 플래그다 | |

### 5.3 위기 경로 [기준 + 설계]

```
키워드 L2·L3 적중 또는 판정 L2·L3
 1. 메모리 held 플래그를 원자적으로 세운다 (scope. L3면 사용자 단위도)
    → 이 순간부터 5.2-4b가 모든 출력을 막는다
 2. 출력 차단
    - 버퍼 폐기, (가능하면) 생성 취소
    - TTS 합성 취소, 이 scope의 후처리 취소
 3. crisis.card(level, hostFixedTextKey) → scope.held
 4. 상태 기록 (하나의 트랜잭션. 시간 상한 [가설])
    - scope.state = held, endReason = crisis, maxCrisisLevel
    - CrisisEvent(level, source)
    - L3면: CrisisLock(서버 시각 자정까지)
            그 사용자의 다른 active·paused·closing 세션과 active 인터뷰를 모두 held(crisis)로 바꾸고,
            각 scope에 crisis.card를 보낸다
    - user 메시지 처리
      · 세션 대사: excludeFromContext=true로 저장(마스킹 적용)
      · 인터뷰 답변: answers에 넣지 않는다
      · 속마음(source=inner): 저장하지 않는다. 전사는 즉시 폐기
    - 실패하거나 상한을 넘기면 → 위기 표식 [제안, D-T25]을 남기고 저장을 다시 시도한다
      다시 시도하는 동안 그 scope의 입력은 409로 거절한다. 키워드 검사는 계속한다
 5. L2 사전에 적중했으면 판정기로 L3 여부를 계속 본다
    └ L3 → 4의 L3 처리, CrisisEvent 추가, crisis.upgrade
      판정이 실패하면 L2를 유지한다(재입력 요청 없음)
```

- 카드를 저장보다 먼저 보낸다. 그래서 DB 잠금을 기다리는 동안에도 카드가 늦어지지 않는다. 출력은 메모리 held 플래그가 막는다.
- **위기 표식** [제안, D-T25]: DB 저장에 실패했을 때 서버가 재시작해도 held와 잠금이 사라지지 않게 하려는 장치다.
  - DB와 별도인 로컬 파일 하나에 append 방식으로 남긴다.
  - 내용은 userId, scopeId, 등급, 시각뿐이다.
  - 서버가 시작할 때 이 파일을 읽어 DB에 반영한 뒤 지운다.
- 인터뷰에서 위기가 나면 Interview.status=held가 되고, 화면은 SCR-06 보류 변형으로 간다.
- **같은 날 L2** [기준, PRD v0.9 7절 + 설계]
  - L2 보류 뒤에도 같은 날 새 세션을 열 수 있다.
  - 새 세션을 시작할 때 host.suggest(sameDayCare)를 보낸다. 지배인 고정 문구와 위기 연락처 열람 링크다.
  - 그날 대화 화면에는 위기 연락처 링크를 상시 보여 준다.
  - 판정기에 sameDayL2를 넘긴다.
  - 같은 날 두 번째 L2가 나오면 쉬어 가기 고정 권유를 한 번 한다. 차단은 하지 않는다.
  - 문구는 공식 출처를 확인한 뒤 확정한다.
- L3면 잠금이 풀릴 때까지 3절의 모든 진입점이 423을 돌려준다.

### 5.4 세션 시작과 첫 대사

1. 그림자 잠금을 잡고 deletedAt을 다시 확인한다. CrisisLock(423)과 동시 처리 한도(503)를 확인한다.
2. Session을 만든다. state=active, camOff는 요청값이고 없으면 Settings.camOffDefault를 쓴다.
3. 첫 대사를 정한다.
   - 새 그림자와 이어하기: 상황별 고정 첫 대사에 카드 호칭을 넣어 shadow 메시지로 저장한다(isFixedText=true).
     - 호칭은 넣기 전에 키워드 규칙과 출력 금지 사전을 한 번 더 거친다. 걸리면 기본 호칭을 쓴다.
   - 새 갈래: 첫 대사 없이 시작한다.
4. sameDayL2면 host.suggest(sameDayCare)를 보낸다.
5. 카메라를 쓸 수 없으면 host.suggest(noCamera)를 보낸다.
6. Shadow.lastVisitedAt을 갱신한다.

### 5.5 지배인과 입력 없는 LLM 생성

- 입력 없는 지배인 대사는 고정 문구다 [기준, PRD v0.9 9절]. 로비 인사, 인터뷰 첫 질문, 마무리 제안, 쉬어 가기, 자각 환기, L1 안부, 인터뷰 자각 문구가 여기에 든다.
- 입력이 있는 지배인 응답은 5.2를 따른다. 인터뷰의 다음 질문, 안부 답변에 대한 응답이 여기에 든다.
- 새 사용자 입력 없이 LLM이 만드는 생성물: 카드 초안, 보내기의 마지막 대사, 요약 [설계]
  - 이미 판정을 통과한 입력만 쓴다. excludeFromContext 메시지는 쓰지 않는다.
  - 출력 금지 사전 검사를 거친다.
  - 요약은 여기에 더해 기분·표정 어휘 검사를 거친다.
  - 걸리면 한 번 다시 생성한다. 그래도 걸리면 다음으로 대신한다.
    - 카드 초안: 빈 칸
    - 마지막 대사: 고정 작별 문구
    - 요약: 직전 요약 유지
  - 출력 확정 지점(5.2-4b)은 같다.

### 5.6 설정 진입 (pause / resume) [설계, D-T02 · D-T20]

**pause**

- 클라이언트가 마이크·카메라 트랙과 그림자 오디오를 멈춘다.
- 서버는 state를 paused로 바꾸고 표정 신호 메모리를 지운다.
- 진행 중인 턴이 있으면 키워드 검사와 판정은 끝까지 한다.
  - L2·L3이면 5.3으로 간다. 이벤트는 사용자 채널로 가므로 설정 화면에서도 받는다.
  - 그 밖이면 버퍼를 버리고 OpenTurn.status를 interrupted로 둔다.
    - user 메시지는 저장하지 않는다. failCount에도 넣지 않는다.
    - L1이었으면 maxCrisisLevel은 갱신한다.
- paused 중에 새 턴이 오면 키워드 검사 뒤 409 SESSION_PAUSED다.

**resume**

- state를 active로 바꾼다. held 상태면 409 SESSION_HELD다.
- interrupted 턴이 있으면 turn.retry를 보낸다.
- 마이크는 꺼진 상태로 시작한다. 카메라도 자동으로 다시 켜지 않는다.

**종료할 때 진행 중인 턴**

- end·release를 부를 때 진행 중인 턴이 있으면 pause와 같이 처리한다. 판정은 끝까지 하고, 위기가 아니면 버퍼를 버리고 interrupted로 둔다.

### 5.7 그림자 프롬프트 조립 [PRD 6.1]

| 순서 | 블록 | 출처 |
| --- | --- | --- |
| 1 | 고정 규칙: 세계관, 실존 인물 주장 금지, 조언·정답 금지, 자각 대사 규칙, 상황별 규칙, "지난 세션의 기분을 다시 꺼내지 않는다", "카메라가 꺼진 세션에서는 얼굴·표정을 말하지 않는다" | contents/prompts/shadow, contents/rules. prefix caching 대상 |
| 2 | 그림자 카드 | Shadow.card |
| 3 | 관계 메모리: 지난 회차 요약, 선명도 | Summary, Branch.clarity |
| 4 | 롤링 요약 + 최근 12턴 원문 [가설] | excludeFromContext=true인 메시지는 뺀다 |
| 5 | 기분 블록: 라벨·강도, 표정 신호, 카메라 사용 여부 | 세션 메모리만 |
| 6 | (L1일 때) 자각 지시 블록 | contents/prompts/shadow |
| 7 | (harmToOthers=concrete일 때) 말림 지시 블록. 대상이 그림자가 연기하는 인물이면 "여기서는 쏟아내도 되지만 실제로는 그러지 말라"는 뉘앙스 [기준, PRD 7절] | contents/prompts/shadow |

- 전체를 16K 토큰 이하로 유지한다 [가설].
  - 턴 상한이 없으므로 길이는 롤링 요약으로만 묶는다.
  - 요약 길이 상한은 [가설]이다. 넘으면 오래된 요약끼리 다시 요약한다.
  - 고정 규칙 블록은 항상 맨 앞에 둔다.
- 원문이 파기된 갈래는 4블록의 원문 없이 요약만으로 조립한다.

### 5.8 속마음 파이프라인 (4단계) [기준, PRD 6.5]

```
음성 서버: VAD 발화 시작 → 오케스트레이터에 내용 없이 알림 (innerPending += 1)
  → 화자 확인 (실패하거나 확신이 낮으면 즉시 폐기, innerPending -= 1)
  → STT + 운율 → 원본 폐기
오케스트레이터: 키워드 규칙 → 판정기(위기만 판정, source=inner)
     ├ L2·L3 → 전사 즉시 폐기 → 5.3 (메시지를 저장하지 않음)
     ├ 실패·시간 초과 → 전사 폐기, 기분은 전하지 않음, failCount에 넣지 않음
     ├ L1 → 전사 폐기, maxCrisisLevel 갱신
     │      다음 그림자 응답에 자각 지시 블록을 붙인다
     │      (속마음 내용은 언급하지 않음. 대사의 L1과 같은 방식으로 처리) [기준, CLAUDE.md 4.1]
     └ L0 → 기분 추출(확신이 낮으면 전하지 않음) → 전사 폐기 → 기분 블록 → mood.update
  → innerPending -= 1
```

- TTS를 재생하는 동안에는 속마음 수집을 멈추거나 에코를 제거한다. 클라이언트가 재생 시작과 끝을 음성 서버에 알린다.
- innerVoice 동의를 철회하면 서버도 inner 채널을 닫고, 진행 중인 속마음을 버린다.

### 5.9 종료·안부·요약

- end나 release를 부르면 state가 closing이 된다.
  - maxCrisisLevel이 L1이면 host.checkin(고정 문구)을 보낸다.
  - checkin에 대한 답은 5.2 순서를 따른다.
- close를 부르면 다음 순서로 처리한다.
  1. 그림자 잠금 아래에서 deletedAt을 확인한다.
  2. state를 ended로 바꾼다.
  3. 요약 워커에 작업을 예약한다.
  4. 세션 메모리와 그 세션의 재전송 이벤트를 지운다.
  - SavePoint는 매 턴 저장 트랜잭션에서만 갱신하고, close에서는 다시 쓰지 않는다.
- 요약 워커
  - 쓰기 트랜잭션 안에서 갈래가 지워지지 않았는지 확인한다.
  - 요약 입력에서 excludeFromContext 메시지를 뺀다.
  - 요약 지시에 "기분·표정을 요약하지 않는다"를 넣는다.
  - 요약을 만든 뒤 사후 검사(5.5)를 한다.
  - 요약이 실패해도 대화 저장은 유지하고, 요약만 다시 시도한다.
- 무활동 타임아웃
  - 세션: 30분 [제안, D-T26]이 지나면 endReason=leave로 닫는다. 보류된 세션도 같다.
  - 인터뷰: 24시간 [제안, D-T26]이 지나면 discarded로 두고 answers와 cardDraft를 지운다. 보류된 인터뷰도 같다.

### 5.10 상태 전이와 출력 허용 [설계]

**세션**

| 지금 | 사건 | 다음 |
| --- | --- | --- |
| active | pause | paused |
| paused | resume | active |
| active / paused / closing | 위기, 판정 2회 실패 | held |
| active / paused | end, release | closing |
| held / closing | close | ended |
| active / paused / held / closing | 무활동 타임아웃 | ended(leave) |
| ended가 아닌 모든 상태 | 갈래·그림자 삭제 | ended(deleted) |
| ended가 아닌 모든 상태 | sensitive 동의 철회 | ended(consentWithdrawn) |

**세션 상태별 허용**

| 상태 | 받는 입력 | 내보내는 출력 |
| --- | --- | --- |
| active | turns, mood, expression, camera, pause, end, release | turn.output, host.suggest |
| paused | resume, end. turns는 409 SESSION_PAUSED | 없음. 위기 카드는 보낸다 |
| closing | checkin, close. 그 밖의 턴은 409 SESSION_CLOSING | checkin에 대한 turn.output, host.checkin |
| held | close. 그 밖은 409 SESSION_HELD | 위기 카드 재전송만 |
| ended | 없음(409 SESSION_ENDED) | 없음 |

모든 상태에서 위기 키워드 검사가 먼저 적용된다(4.1).

**인터뷰**

| 지금 | 사건 | 다음 |
| --- | --- | --- |
| active | 위기, 판정 2회 실패 | held |
| active | confirm | confirmed |
| active / held | DELETE, 무활동 타임아웃, sensitive 동의 철회 | discarded |

- 인터뷰가 confirmed나 discarded가 되면 answers와 cardDraft를 지운다.
- 인터뷰가 출력을 내보낼 수 있는 상태는 active뿐이다.

### 5.11 마스킹 [제안, D-T11]

- 위치: 모든 저장 직전에 한다.
  - 5.2-4c
  - 5.3 위기 메시지
  - 인터뷰 answers
  - 카드 수정본
  - checkin 답변
- 자동 마스킹: 전화번호, 이메일, 주소, 계좌번호·주민번호 형식을 정규식으로 찾아 `[연락처]`, `[주소]`처럼 바꾼다.
- 실명: 자동으로 가리면 호칭까지 지워질 수 있다.
  - 인터뷰에서 "실명 대신 호칭이나 별명을 써 주세요"라고 안내한다.
  - 카드 미리보기에서 사용자가 직접 확인한다.
- 화면에 보이는 사용자 대사와 저장된 대사를 일치시킨다. 다시 읽을 때는 마스킹된 대사가 보인다.
- 카드는 마스킹된 결과를 interview.cardDraft로 미리 보여 주고, 그 결과만 확정한다.

### 5.12 동의 철회

| 동의 | 서버 처리 |
| --- | --- |
| innerVoice | inner 채널을 닫는다. 진행 중인 속마음과 기분 메모리를 버린다. 목소리 특징값을 지울지 묻는다(voiceprintDeletePrompt=true) |
| expression | 표정 신호 메모리를 지운다. 이후 표정 신호는 403이다 |
| sensitive | 열린 세션을 닫는다(consentWithdrawn). 인터뷰는 discarded로 둔다. 기록을 지울지 고르는 안내(고정 문구)를 띄운다. 이후 인터뷰·세션 API는 403이다 |

### 5.13 고인 언급 (F-20 전까지) [설계]

- 감지 방법
  - 판정기의 deceasedReference를 쓴다.
  - 인터뷰에서 관계·대상을 묻는 답변에는 고인 표현 키워드 보조 사전도 쓴다.
- 인터뷰에서 감지하면
  - 고정 "준비 중" 안내를 보낸다. 위로 문구와 위기 연락처 열람 링크를 포함한다.
  - confirm을 막는다(409 INTERVIEW_STATE).
  - 사용자가 인터뷰를 고쳐 이어갈지 폐기할지 고른다.
- 자유 대화에서는 대화 상대를 고인으로 대하려 할 때만 안내한다. 예를 들면 그림자를 돌아가신 분 본인으로 부르는 경우다. 사별 이야기를 꺼내는 것만으로는 안내하지 않는다. 대화가 끊긴다고 느끼지 않게 하려는 것이다.
- 출력 금지 사전에 "고인 본인처럼 말하기" 범주를 둔다.

### 5.14 타해 중단 [기준 + 제안, PRD v0.9.1 7절]

```
harmStreak가 harmStopTurns [가설]를 넘음
 1. 메모리 held 플래그를 세운다(scope). 5.2-4b가 출력을 막는다
 2. 버퍼 폐기, TTS 합성 취소, 후처리 취소
 3. host.suggest(harmStop, fixedTextKey=host.harmStop) → scope.held(reason=harmEscalation)
    - 실행 시점이 임박했다고 판정되면(harmImminent) 112 고정 카드를 함께 보낸다 [제안]
 4. 상태 기록: state = held, endReason = harmEscalation. user 메시지는 excludeFromContext=true로 저장(마스킹 적용)
```

- 위기 경로(5.3)와 겹치면 위기 경로가 우선한다. 동반 자살 같은 말은 L3로 판정한다.
- 같은 날 새 세션은 열 수 있다. CrisisLock은 걸지 않는다 [제안].
- 문구·카드는 고정 텍스트다. LLM·TTS로 만들지 않는다.
- 속마음 채널의 concrete 판정도 harmStreak에 센다.

---

## 6. 보안 [설계]

### 6.1 규칙

| 영역 | 규칙 |
| --- | --- |
| 로그 | API 서버·서빙 엔진·음성 서버 모두 요청 본문·프롬프트·출력의 로깅을 끈다. 서빙 엔진의 디스크 캐시(KV·프롬프트 캐시 저장)도 끈다. 전역 예외 처리기가 예외 메시지에서 입력 문자열을 지운다. 크래시 덤프를 끈다. 실제 엔진 설정이 가능한지는 미검증이다 |
| 외부 전송 | 외부 API를 호출하지 않는다. 외부 송신 0건을 테스트로 확인한다 |
| 네트워크 | 로컬 시연에서는 로컬 주소에만 바인딩한다. 외부 공개(3단계 통과 후)에는 HTTPS·인증·접속 제한을 둔다 |
| 음성 | 음성 원본, 목소리 등록 원본, TTS 출력을 디스크나 임시 파일에 쓰지 않는다. Windows 페이지 파일·최대 절전 파일에 남는지는 확인이 필요하다(13절) |
| 브라우저 | 대화·음성 응답에는 no-store를 붙인다. TTS는 메모리 Blob으로 재생한다 |
| 영상 | 서버 API는 이미지·영상·랜드마크 원시값을 받지 않는다. 표정 신호는 허용 목록(PRD 6.7 예시: 미소, 찡그림, 눈썹 올림, 입술 꽉 다묾, 시선 피함, 고개 숙임)만 받는다. 목록은 [가설]이고 테스트로 정한다 |
| 스트림 | 마이크·카메라를 끄는 것은 브라우저 트랙 정지로 구현한다. 동의 철회나 camOff 때는 서버도 채널을 닫고 메모리를 지운다(이중 방어) |
| 판정 입력 | 위기 테스트 세트에 프롬프트 주입 문장을 넣는다. 판정기 출력은 스키마로만 해석한다 |
| 운영자 | 원문을 열람하는 운영 화면은 없다. 사유는 코드로 남긴다. OperatorAccessLog는 1년 보존한다 [제안]. 탈퇴 안내에 이 보존 사실을 적는다 |

### 6.2 암호화 키 구조 [제안, D-T13]

**키 종류**

- 그림자마다 데이터 키를 하나씩 둔다. 그림자 아래의 card, relationType, 대화 원문, 요약, 세이브 포인트, forkSummarySnapshot을 이 키로 암호화한다.
- 사용자마다 데이터 키를 하나씩 둔다. voiceprint, Interview 필드, CrisisEvent.level, Session.maxCrisisLevel, Message.judgeLevel처럼 사용자 단위 필드를 이 키로 암호화한다.
- 데이터 키는 마스터 키로 감싸서 **DB와 분리한 키 저장소**에 보관한다. 키 저장소는 일반 DB 백업에 넣지 않는다.

**폐기와 백업**

- 그림자를 지우면 그 그림자의 데이터 키를 폐기한다(crypto-shredding). 탈퇴하면 사용자 키와 그 사용자의 그림자 키를 모두 폐기한다.
- 키 저장소를 따로 백업할 때는 삭제 이력을 함께 둔다. 복원하면 삭제 이력을 다시 적용한다.
- 갈래만 지울 때는 키를 폐기하지 않는다. 백업에 남은 암호문은 백업 30일 파기 규칙으로 지운다.
- 따라서 보장 범위는 둘로 나뉜다. 그림자 삭제와 탈퇴는 키를 폐기하는 즉시 복호화할 수 없게 된다. 갈래 삭제는 백업 파기 기한 안에 지워진다. 도움말 문구도 이 범위에 맞춘다.

**마스터 키와 평문 필드**

- 마스터 키는 환경 파일과 분리한 비밀 파일에서 읽고, 백업에 넣지 않는다.
- 키를 교체할 때는 새 마스터 키로 데이터 키를 다시 감싼다. 데이터 자체는 다시 암호화하지 않는다.
- 평문으로 남는 위기 관련 값과 그 이유
  - CrisisLock.lockedUntil: 잠금 판단에 필요하다. 만료된 행은 지운다.
  - Session.endReason=crisis: 상태 판단에 필요하다.
  - CrisisEvent.source: 등급을 담지 않는다.

### 6.3 환경·의존성 [설계, CLAUDE.md 8절]

- 비밀값(마스터 키, 쿠키 서명 키)은 비밀 파일 하나에 두고 저장소에 커밋하지 않는다.
- 환경별 경로·포트·설정값은 환경 파일에서 읽는다. 저장소에는 예시 파일만 둔다.
- Python 의존성은 버전을 고정한 잠금 파일로 관리한다. 도구(pip-tools / uv / poetry 등)는 구현에 착수할 때 정한다.
- 모델 파일·패키지 버전·라이선스는 0단계 뒤에 기록한다.

### 6.4 설정 파라미터

| 이름 | 기본값 | 상태 |
| --- | --- | --- |
| judgeMode | parallel / sequential | 미검증 |
| harmStopTurns | 2 [가설, PRD 7절] | 테스트 후 조정 |
| judgeTimeoutMs | 3000 (판정 호출 시작부터) | [가설] |
| queueWaitCapMs | — | 미검증 |
| crisisPersistTimeoutMs | — | [가설] |
| recentTurnWindow | 12 | [가설] |
| promptTokenBudget | 16000 | [가설] |
| summaryTokenCap | — | 미검증 |
| closureThreshold, closureResuggestTurns | — | [가설]. 테스트로 정한다 |
| restSuggestCooldownTurns, awarenessIntervalTurns | — | [가설]. 테스트로 정한다 |
| blocklistConsecutiveCap | — | [가설] |
| sessionIdleTimeoutMin | 30 | [제안] |
| interviewIdleTimeoutHours | 24 | [제안] |
| authIdleTimeoutHours | 12 | [제안] |
| maxConcurrentGenerations, queueLength | — | 미검증 |
| eventReplayBufferSize, eventReplayTtlSec | — | [가설] |
| maxTurnChars, maxCardFieldChars | 2000, 200 | [제안] |
| autoDeleteDaysDefault | 180 | [가설] |
| errorLogRetentionDays | 30 | [PRD] |
| backupPurgeDays | 30 | [PRD] |
| operatorLogRetentionDays | 365 | [제안] |
| crisisLockTimezone | 서버 시각 | [기준] |

---

## 7. 보존·삭제 [PRD 8절 + 설계]

| 데이터 | 지우는 때 | 구현 |
| --- | --- | --- |
| 그림자 카드 | 그림자 삭제(마지막 갈래 삭제 포함), 탈퇴 | 트랜잭션 + 키 폐기 |
| 대화 원문 | 그림자·갈래·전체 삭제, 탈퇴, 자동 파기 | 2.3. 자동 파기는 content를 지우고 purgedAt을 표시한다 |
| 요약 | 그림자·갈래·전체 삭제, 탈퇴. 자동 파기 때는 남긴다 | 갈래를 지울 때는 자손이 있어도 즉시 지운다 |
| 세이브 포인트 | 갈래 삭제. 자동 파기 때는 resumeSnapshot만 지우고 lastMessageId는 남긴다 [제안, D-T27] | 이어하기는 요약으로 한다 |
| Session 행 | 소속 갈래·그림자 삭제, 전체 삭제, 탈퇴 | 갈래 삭제 트랜잭션에 포함한다 |
| OpenTurn | 턴이 닫힌 뒤 정리 작업, scope 삭제 | 내용 없음 |
| 인터뷰 임시 데이터 | confirm·취소·무활동 타임아웃·동의 철회 | Interview 행 정리 |
| 속마음 전사 | 판정 종료 즉시 | 저장하지 않음 |
| 기분·표정 | 세션 종료, 철회·camOff 즉시, 재시작 | 메모리 |
| 이벤트 재전송 버퍼 | TTL, 삭제·종료·철회·로그아웃 | 메모리 |
| 화자 확인 실패 발화, 음성 원본 | 즉시 | 음성 서버 메모리 |
| 목소리 특징값 | 설정에서 삭제, 탈퇴 | innerVoice를 철회할 때 지울지 묻는다 |
| 동의 기록, 설정, 위기 이벤트, 고통 신호 횟수 | 탈퇴. DistressCount·CrisisEvent의 sessionId는 세션이 지워지면 비운다 | — |
| CrisisLock | 만료 뒤 정리 작업, 탈퇴 | — |
| 위기 표식 파일 | 시작할 때 DB에 반영한 뒤 | 내용 없음 |
| OperatorAccessLog | 1년 뒤 [제안] | 정리 작업 |
| 오류 로그 | 30일 뒤 | 정리 작업 |
| 백업 | 삭제 요청 후 30일 안 | 범위는 6.2. 복원할 때 삭제 이력을 다시 적용한다 |
| 카메라 영상 | 브라우저 안에서 분석 직후 | 서버에 오지 않음 |

- 자동 파기 [기준, PRD v0.9 8절]
  - 조건: autoDeleteEnabled=true이고, Shadow.lastVisitedAt으로부터 autoDeleteDays가 지났다.
  - 원문을 파기하되 요약은 남긴다. 그래서 이어하기만 된다.
  - 원문이 파기된 지점에서는 분기할 수 없다(422 SOURCE_PURGED).
- 삭제가 성공하면 목록 API에서 즉시 빠진다.

---

## 8. 자원과 상한 [설계 + 미검증]

| 항목 | 내용 |
| --- | --- |
| 상한 | 세션 턴 상한과 일일 토큰 상한은 없다 [기준, PRD v0.9]. 예전 D-T09(긴 세션 대비)는 아래 장치로 정리했다 |
| 긴 세션 장치 | 마무리 재제안 간격, 쉬어 가기 권유(한 번, 이후 간격), 자각 환기, 요약 길이 상한(5.2-6, 5.7) |
| 한 계정의 GPU 독점 | 동시 처리 한도와 대기열로만 다룬다. 사용자별 한도는 두지 않는다 |
| 동시성 | 한 scope에는 열린 턴이 하나뿐이다. 서버 전체 한도와 대기열 값은 미검증 |
| 지연·VRAM·KV 캐시·100턴 세션 품질 | 미검증(0단계) |

---

## 9. 콘텐츠 파일 [설계]

콘텐츠 파일을 바꿀 때마다 위기 테스트 세트와 골든 시나리오를 다시 돌린다 [기준, CLAUDE.md 8절]. 파일 형식은 구현할 때 정한다. 고정 문구는 `영역.용도` 형식의 fixedTextKey로 부른다. 예: judge.retry, host.sameDayCare.

| 경로 | 내용 |
| --- | --- |
| contents/prompts/shadow/ | 그림자 고정 규칙, 자각 지시 블록 |
| contents/prompts/host/ | 인터뷰 다음 질문, 안부 답변에 대한 응답, 카드 초안 생성 |
| contents/prompts/judge/ | 판정기 프롬프트, 출력 스키마 |
| contents/prompts/summary/ | 요약 지시(기분·표정·위기 발화 제외) |
| contents/rules/ | 상황별 행동 규칙(PRD 6.6), rhythm |
| contents/safety/ | 위기 키워드 사전(L2·L3), 정규화 규칙, 고인 표현 보조 사전, 출력 금지 사전, 위기 카드 문구·연락처, 위기 경로 지배인 문구, 녹음 음성, 기분·표정 어휘 목록(요약 검사, camOff 검사), 타해 중단 112 카드 |
| contents/fixed/ | 첫 대사(상황별), 자각 문구(순환), 지배인 자각 문구(인터뷰·안부), 재입력 요청, 판정 실패 보류 안내, 로비 인사, 인터뷰 첫 질문, 마무리 제안, 쉬어 가기, 자각 환기, L1 안부, 같은 날 L2 안내, 고인 "준비 중" 안내(위로 문구와 위기 연락처 열람 링크 포함), "얼굴 없이 목소리로만" 안내, 고정 작별 문구, 상황별 고정 말림 문구, 타해 중단 안내(host.harmStop), 동의 철회 안내, 비밀번호 재설정 고지, 서버 오류 안내 |
| contents/ui/ | 튜토리얼 스크립트, 동의·도움말 문구, 기분 라벨 세트(9개 [가설], mood API 허용 목록) |

**출력 금지 사전의 범주**

- 자해 수단
- 점수·합격 판정
- 실존 인물이라는 주장
- 실제 연락 권유
- 고인 본인처럼 말하기
- (camOff 세션에서만) 얼굴·표정 언급
- 위기 연락처·상담기관(전화번호, 기관명) 생성 [제안, PRD v0.9.1 7절]

**키워드 정규화**

- 사전은 원문과 정규화한 문장 양쪽에 적용한다.
- 정규화 방법
  - NFKC 정규화, 영폭 문자 제거
  - 공백 제거, 반복 문자 줄이기
  - 자모 분리 결합
  - 전각·반각 통일
  - 이모지·기호 제거
- 초성만 쓴 은어와 한영 혼용 표현은 사전 항목으로 다룬다.
- 사전 내용은 공식 출처와 전문가 검수를 거친다.

---

## 10. 판정기 출력 스키마 [설계]

```json
{
  "crisisLevel": "L0 | L1 | L2 | L3",
  "closureSignals": { "coreMessageDelivered": false, "resolutionExpressed": false, "looping": false },
  "clarityStage": 1,
  "ruminationSignal": false,
  "deceasedReference": false,
  "harmToOthers": "none | vented | concrete",
  "harmImminent": false
}
```

- 스키마와 맞지 않으면 판정 실패다.
- 매듭 점수는 최근 몇 턴 [가설] 동안 참이 된 closureSignals의 개수다. closureThreshold와 비교한다.
- clarityStage는 같은 턴의 turn.output에 반영하고, 같은 트랜잭션에서 Branch.clarity에 저장한다. 감정이 격해진다고 자동으로 오르지 않도록 판정기 지시에 넣는다 [PRD 6.2].
- harmToOthers는 위기 등급과 따로 판정한다. vented는 관용적 분노, concrete는 대상·수단·장소·시점이 드러난 위협이다. harmImminent는 concrete일 때 실행 시점이 임박했는지다. 처리는 5.2·5.14를 따른다.
- deceasedReference는 5.13의 기준으로 판정한다. 대화 상대를 고인으로 대하려는 경우만 참이다.
- 판정기 출력은 저장하지 않는다. Message.judgeLevel만 남긴다.
- 기분 추출은 위기 판정과 별도로 호출한다.
- 판정기 입력은 5.2의 표를 따른다.

---

## 11. 검증 항목 (테스트 계획서 입력)

| 번호 | 검증 | 기대 결과 |
| --- | --- | --- |
| T-01 | 판정 지연을 늘린 상태에서 이벤트 관찰 | turn.output 전에 응답의 일부가 나간 건수 0 |
| T-02 | 위기 테스트 세트, 사람 검수. 세트 구성: 직접·우회·은어 표현, 여러 턴에 나뉜 위기, 그림자 질문에 대한 짧은 답, STT 오류·구두점 없는 속마음체, 초성·한영 혼용·영폭 문자, 비위기 유사 표현(인용, 과거 회고, 타인을 향한 분노), L2/L3 경계 문장, 주입 문장 | 누락 0건(3단계 게이트), 오탐률 기록 |
| T-03 | L2 키워드 / L3 키워드 / L2 키워드 + 판정 L3 | 즉시 카드·보류 / L3 카드·잠금 / crisis.upgrade·잠금·CrisisEvent 2건 |
| T-04 | 처리 중(409 상황)에 위기 입력 | 위기 카드, 진행 중인 턴의 출력 0 |
| T-05 | 판정 실패 → 재입력(retryOfTurnId 있음/없음) → 실패, 중간에 서버 재시작 | 두 번째 실패에서 보류, failCount 유지 |
| T-06 | 이벤트 채널을 끊고 위기 발생 → 재연결, epoch 변경 | POST 응답의 crisisLevel로 카드, 재연결 때 카드·upgrade 재수신, GET 상태 held |
| T-07 | 위기 처리 중 서버 재시작, DB 잠금 대기 중 위기, DB 저장 실패 | 카드 지연 없음, held·CrisisLock 유지(위기 표식) |
| T-08 | TTS 재생·합성 중 위기 | 재생 즉시 정지, 카드 뒤 turn.ttsReady 0건 |
| T-09 | 보류 뒤 host 이벤트·turn.output | 0건 |
| T-10 | pause 중 위기 입력 / 진행 중인 일반 턴 / 새 턴 | 설정 화면에서 카드 / interrupted, resume 때 retry / 409 SESSION_PAUSED |
| T-11 | 인터뷰 답변·카드 수정본·안부 답변에 위기 입력 | 카드, 보류, answers에 위기 답변 0건 |
| T-12 | 출력 금지 사전 범주별(자해 수단, 점수·합격, 실존 주장, 연락 권유, 고인 행세, camOff 표정) 적중 응답 주입 | 출력 0건, 고정 문구로 대체(1단계 게이트), 자해 수단이면 재판정 |
| T-13 | L1 판정, L1 재생성 실패, 인터뷰 L1 | 자각 대사 / 고정 자각 문구 / 지배인 자각 문구, 안부 표시 |
| T-14 | 속마음 위기, 속마음 판정 실패, 속마음 판정 대기 중 텍스트 턴, STT 진행 중 텍스트 턴, 속마음이 계속 들어오는 중 출력, 속마음 L2와 출력 확정 경합 | 카드·Message 행 0건 / 폐기·기분 미전달 / 출력 대기 / 출력 대기 / 상한 안에 출력 또는 retry / 교착 없음, 출력 0 |
| T-15 | 판정기 프롬프트 검사 | 기분·표정 블록 0건 |
| T-16 | 요약·resumeSnapshot·한 줄 요약 검사(어휘 목록 + 사람 검수) | 기분·표정·위기 발화 0건 |
| T-17 | 갈래 A→B·C, B→D. A 삭제, B 삭제, 삭제 중 강제 실패, 요약 워커 경쟁 | 남은 갈래 전체 재생, 삭제 갈래 요약·세이브 포인트 0, 롤백하면 변화 0 |
| T-18 | 마지막 갈래 삭제, 그림자 삭제 | 그림자 포함 관련 행 0, 키 폐기 |
| T-19 | 활성·held·closing 세션이 있는 갈래 삭제, 삭제와 세션 시작·close 경합 | 세션 ended(deleted), 고아 행 0 |
| T-20 | 분기 시점 요약, 조상 소유 메시지에서 분기(parentBranchId), seq 연속성 | 분기 이후 내용 0, 부모 = 소유 갈래 |
| T-21 | 자동 파기 뒤 이어하기·분기 | 이어하기 가능, 분기 422, resumeSnapshot 없음 |
| T-22 | 오류 로그·응답 본문, 강제 예외 뒤 로그, 서빙 엔진·음성 서버 로그 | 대화 내용 0건 |
| T-23 | 외부 송신 감시 | 0건 |
| T-24 | 음성 처리 중 파일 시스템 감시(원본·등록 원본·TTS), 브라우저 디스크 캐시 | 음성 파일 0건, 대화·음성 응답 캐시 0건 |
| T-25 | 화자 확인 실패 발화 | 오케스트레이터·서빙 엔진 전달 0건 |
| T-26 | 그림자 음성이 속마음으로 전사된 건수 | 0건(4단계 게이트) |
| T-27 | "캠 없이 진행" 체크, 카메라 끄기, 카메라 없는 PC에서 완주 | 카메라 권한 요청 0건, 브라우저 트랙 정지, 완주 |
| T-28 | expression API에 이미지·허용 목록 밖 신호, mood API에 목록 밖 라벨 | 422 |
| T-29 | 동의 전 인터뷰·세션, innerVoice·expression·sensitive 동의 철회 | 403, 채널 닫힘·메모리 삭제, 세션 consentWithdrawn |
| T-30 | L3 잠금 중 인터뷰(생성·답변·확정)·분기·세션 시작·턴·resume·checkin, 다른 탭 세션 | 423, 다른 탭 세션 held + 카드 |
| T-31 | 다른 사용자의 리소스, 삭제된 갈래 | 404 |
| T-32 | 초기 비밀번호 미변경 접근, 운영자 재설정 뒤 대화 API | 403, OperatorAccessLog 기록, 재설정 고지 |
| T-33 | 세션 대사·위기 메시지·인터뷰 답변·카드 수정본·안부 답변에 연락처 입력 | 저장된 값 마스킹, 미리보기 일치 |
| T-34 | 고인 언급: 인터뷰 / 자유 대화(사별 이야기) / 자유 대화(그림자를 고인으로 부름) / 판정 누락 케이스 | 안내·confirm 차단 / 안내 없음 / 안내 / 보조 사전·출력 금지 사전으로 차단 |
| T-35 | 100턴 이상 세션(0단계) | 지연·VRAM·요약 품질·루브릭 점수 기록 |
| T-36 | 콘텐츠 파일 변경 | T-02와 골든 시나리오 회귀 |
| T-37 | 종료·보류·확정된 scope와 2,000자 초과 입력에 위기 문장 | 카드 표시, CrisisEvent 기록, 409·422 전에 처리 |
| T-38 | 재전송 버퍼: 삭제·동의 철회·종료·로그아웃 뒤 재연결 | 해당 scope 이벤트 재전송 0건, mood.update 재전송 0건 |
| T-39 | 인터뷰 L3 승격 뒤 재연결, closing에서 안부 답변 위기, closing에서 안부 답변 정상 응답, held 인터뷰 타임아웃 | L3 카드 / 카드·held / 응답 출력 / discarded·answers 삭제 |
| T-40 | 위기 경로의 LLM·TTS 호출 | 0건. 카드 문구·음성은 정적 자산에서만 |
| T-41 | 같은 clientTurnId 재전송(키워드 적중 턴 포함) | 같은 turnId, 중복 처리 0 |
| T-42 | 원본·갈래 보존: 분기한 뒤 원본과 각 갈래를 다시 열어 전체 재생 | 원본·갈래 보존 100%(2단계 게이트) |
| T-43 | 마지막 턴까지 보존(F-09): 저장 직후 강제 종료 → 이어하기 | 마지막 턴부터 이어짐 |
| T-44 | 401 상태에서 위기 문장 | 입력 보존 → 재로그인 뒤 재전송 → 카드 |
| T-45 | 같은 날 L2 뒤 새 세션, 같은 날 두 번째 L2 | sameDayCare 안내·연락처 링크 / 쉬어 가기 권유 1회 |
| T-46 | 타해 위협: eval/crisis/harm_others_set.jsonl 판정, concrete 1회 / 연속 harmStopTurns 초과 / 진정 후 계속 / 속마음 concrete / 동반 자살 | 판정 기록 / 말림 응답 / host.harmStop·held(harmEscalation), LLM 출력 0건 / 대화 계속, harmStreak 0 / harmStreak 증가 / 위기 경로(L3) 우선 |
| T-47 | 그림자·지배인 출력에 위기 연락처 주입 | 출력 0건, 고정 문구로 대체 |

---

## 12. 결정 기록

### 12.1 정한 것

v0.2에서 정한 것(사용자가 권장안을 승인, 2026-11-26):

| 번호 | 결정 |
| --- | --- |
| D-T01 | 키워드 사전을 L2·L3로 나눈다. L2 적중 뒤에도 판정기로 L3 승격 여부를 본다 |
| D-T02 | 설정 진입 중에도 판정은 끝까지 한다. 응답만 버리고, 실패 횟수에 넣지 않는다 |
| D-T03 | L1이면 자각 지시를 붙여 다시 생성하고, 실패하면 고정 자각 문구를 쓴다 |
| D-T04 | 위기 발화는 대사로 저장하되 요약·프롬프트에서 뺀다. 오탐 개선은 가상 테스트 세트로만 한다 |
| D-T05 | L2 보류 뒤 같은 날 새 세션을 허용한다. L3는 서버 시각 자정까지 잠근다 |
| D-T06 | 분기 지점 규칙(2.3) |
| D-T07 | 입력 없는 지배인 대사는 모두 고정 문구다 |
| D-T10 | 그림자·지배인 LLM 출력에 출력 금지 사전 검사를 한다. 1단계 완료 조건이다 |
| D-T14 | 마지막 갈래를 지우면 그림자도 지운다 |
| D-T15 | 자동 파기 때 요약은 남긴다 |
| D-T16 | 그림자 대사에서 기분·표정을 언급하는 것은 허용하고, 요약에서는 뺀다 |
| D-T17 | 반복 고통 신호는 세션별 횟수만 저장한다(DistressCount) |
| D-T18 | 속마음 판정이 실패하면 그 발화를 버리고 기분을 전하지 않는다. 실패 횟수에 넣지 않는다 |
| D-T19 | 지인 체험은 3단계 통과 뒤에 한다. 테스트 계정은 일회용 초기 비밀번호를 쓴다 |
| D-T20 | 설정에서 돌아올 때 카메라를 자동으로 다시 켜지 않는다 |

D-T09(긴 세션 대비)는 8절의 장치로 정리했고, 번호는 비워 둔다.

v0.3에서 정한 것(v0.2 재검토의 권장안을 사용자가 승인, 2026-11-26):

| 번호 | 결정 |
| --- | --- |
| D-T28 | 키워드 검사는 인증을 뺀 모든 거절보다 먼저 한다. POST 응답에 crisisLevel을 직접 담는다 |
| D-T29 | 위기 처리: 메모리 held 플래그 → 카드 → 저장 순서로 한다. 출력 확정 지점은 메모리 플래그를 먼저 본다 |
| D-T30 | L3면 같은 사용자의 열린 세션·인터뷰를 모두 보류한다. 잠금은 모든 진입점에 적용한다 |
| D-T31 | 속마음 위기 발화와 인터뷰 위기 답변은 저장하지 않는다 |
| D-T32 | 속마음 L1은 대사의 L1과 같이 처리한다. 다음 그림자 응답에 자각 지시를 붙이고, 속마음 내용은 언급하지 않는다. PRD·CLAUDE.md의 "똑같이 처리" 원칙을 따른 것이다 |
| D-T33 | 판정기 입력에 카드 핵심 항목, 최신 요약, 사용자 위기 발화, sameDayL2를 넣는다. 직전 그림자 대사는 0단계에서 비교한 뒤 정한다 |
| D-T34 | 새 입력 없는 LLM 생성물(카드 초안, 마지막 대사, 요약)은 판정된 입력만 쓰고, 출력 검사를 거친다 |
| D-T35 | 출력 금지 사전에서 자해 수단 범주에 걸리면 입력을 다시 판정한다. 범주를 확장한다(9절) |
| D-T36 | 고인 안내는 인터뷰와 "대화 상대를 고인으로 대할 때"에만 한다. 보조 키워드 사전을 둔다 |
| D-T37 | 같은 날 L2 뒤에는 안내·연락처 링크를 보이고, 두 번째 L2에는 쉬어 가기를 한 번 권한다 |
| D-T38 | 재전송 버퍼를 세션 메모리 규칙에 넣는다. 기분은 재전송하지 않는다 |
| D-T39 | 운영자가 비밀번호를 재설정하면 다시 바꾸기 전까지 대화 API를 막는다. 사유는 코드로 남긴다 |
| D-T40 | 데이터 키 저장소를 DB 백업과 분리한다. 삭제 보장 범위를 문서에 맞게 바로잡는다 |
| D-T41 | 마스킹은 모든 저장 직전에 한다 |
| D-T42 | 상태별 허용 표(5.10)와 closing 안부, seq 연속, parentBranchId 정의, 응답 no-store |
| D-T43 | 타해 위협(PRD v0.9.1 7절): 판정기에 harmToOthers를 두고, concrete면 그림자가 말린다. 말린 뒤에도 연속되면 중단한다(5.14) |

### 12.2 확인이 남은 것

| 번호 | 내용 | TRD에 넣은 안 |
| --- | --- | --- |
| D-T08 | 테스트 계정 발급 절차(3절), 지인에게 L3가 생겼을 때 운영자의 대응 | 기본은 운영자에게 알리지 않는다. 지인이 발급 때 원하면 "L3 발생 사실과 시각만" 내용 없이 한 번 알리는 옵트인을 둔다. 알릴 때는 OperatorAccessLog action=crisisNotice로 남긴다. 운영자는 미리 정한 연락 수단으로 안부를 묻고 공식 창구를 안내하는 데까지만 한다. 거절해도 불이익이 없다고 밝힌다. **운영자가 대신 신고하는 것이 맞는지는 사용자 판단과 전문가 확인이 필요하다** |
| D-T11 | 마스킹 방식(5.11) | 연락처는 자동으로 가리고, 실명은 안내한 뒤 사용자가 직접 확인 |
| D-T12 | 입력 길이 상한 | 한 턴 2,000자, 카드 항목 200자 |
| D-T13 | 키 구조와 위기 등급 암호화(6.2) | 그림자별·사용자별 데이터 키, 키 저장소 분리 |
| D-T21 | 운영자 로그 보존 기간, 세션 토큰 만료 | 1년, 무활동 12시간 |
| D-T22 | 이름 규칙 예외(오류 코드는 UPPER_SNAKE_CASE, 이벤트·fixedTextKey는 `영역.동작`) | 예외 유지 |
| D-T23 | 운영자 예외 접근에서 위기 문장(excludeFromContext)을 뺄지. PRD 8절의 "위기 검수" 예외 접근과 관계됨 | 뺀다. 위기 검수는 가상 테스트 세트로 한다(D-T04와 같은 방향). PRD 8절 수정이 필요하다 |
| D-T24 | 401 상태에서 위기 문장 | 클라이언트가 입력을 보존했다가 다시 로그인한 뒤 재전송. 로그인 화면에 연락처 링크 |
| D-T25 | DB 저장이 실패할 때 위기 표식 파일 | 내용 없는 별도 로컬 파일에 남기고, 시작할 때 반영 |
| D-T26 | 무활동 타임아웃 | 세션 30분, 인터뷰 24시간 |
| D-T27 | 자동 파기 때 SavePoint | resumeSnapshot은 지우고 lastMessageId는 남긴다. PRD 8절("세이브 포인트는 갈래 삭제 때만")과 다르므로 PRD 수정이 필요하다 |
| D-T44 | 타해 중단 방식(5.14) | 지배인 고정 문구 + 세션 보류, 같은 날 새 세션 허용, 임박하면 112 고정 카드. 연속 기준 harmStopTurns=2 [가설] |
| D-T45 | 출력 금지 사전에 위기 연락처 생성 범주 추가 | 추가한다 |
| D-08 | (화면정의서 번호) 모델 생성 실패를 판정 실패 횟수에 셀지 | 센다. 오류 코드로 구분한다 |
| D-20 | (화면정의서 번호) 운영자 예외 접근을 도움말에 알릴지, 튜토리얼의 "아무도 닿지 않는다" 문구 수정(PRD 8절) | 알린다. 튜토리얼 문구는 운영 원칙에 맞게 고친다. 위기 문장이 기록에 남는다는 점, 화자 확인에 실패한 발화의 위기 신호는 볼 수 없다는 한계도 함께 적는다 |

---

## 13. 미검증 항목 (0단계)

| 항목 |
| --- |
| 집 PC의 GPU·VRAM·RAM·CPU, OS |
| 서빙 엔진: prefix caching, 생성 취소, 로깅·디스크 캐시 끄기. 양자화, 컨텍스트 길이, KV 캐시 |
| 판정 병렬 vs 순차, 판정 시간 초과 값, 대기열 대기 상한, 지배인 응답 판정·출력 검사로 늘어나는 지연 |
| 판정기 입력에 직전 그림자 대사를 넣을 때와 뺄 때의 위기 누락률 비교 |
| 첫 토큰·전체 생성 시간, 버튼을 뗀 뒤 목소리가 나올 때까지의 시간(p90 3초 참고 목표), 문장 단위 TTS 스트리밍 |
| STT·TTS·VAD·화자 확인·운율 모델, 동시 적재 VRAM, 에코 차단 방식 |
| 표정 분석 모델과 GPU 공유 지연 |
| 웹·API 프레임워크, 이벤트 전송 방식, DB 엔진, 암호화 라이브러리, 키 저장소 방식, 의존성 도구 |
| 동시 처리 한도, 대기열, 요약 길이 상한 |
| Windows 페이지 파일·최대 절전 파일에 메모리 속 음성·전사가 남는지 |
| 100턴 이상 세션의 품질과 지연 |
| EXAONE 3.5 라이선스 원문 |

---

## 변경 이력

| 버전 | 일자 | 내용 |
| --- | --- | --- |
| v0.1 | 2026-11-26 | 초안. PRD v0.9·화면정의서 v0.2 기준 |
| v0.2 | 2026-11-26 | document-reviewer·safety-reviewer 검토와 사용자 결정 반영. 사용자 이벤트 채널, Interview·OpenTurn, 상태 전이, 출력 금지 사전, 마스킹, 키 폐기 등 |
| v0.3 | 2026-11-26 | v0.2 재검토(문서 25건, 안전 27건)의 권장안 반영 |
| v0.4 | 2026-11-27 | PRD v0.9.1의 타해 위협 정책 반영: 판정기 harmToOthers·harmImminent, 말림 지시 블록, 타해 중단(5.14), harmStopTurns, endReason·이벤트 값, 출력 금지 사전 위기 연락처 범주, T-46·T-47, D-T43~45 |

v0.3에서 바뀐 내용:

- **위기 대응**
  - 키워드 검사를 모든 거절보다 먼저 하고, POST 응답에 crisisLevel을 직접 담는다.
  - 메모리 held 플래그 → 카드 → 저장 순서로 바꾸고, 위기 표식을 둔다.
  - L3면 사용자 전체를 보류하고, 잠금을 모든 진입점에 적용한다.
  - 같은 날 L2 뒤 안내를 넣었다.
  - 카드 뒤에 오는 TTS를 차단한다.
- **동시성**
  - innerPending을 잠금 밖에서, 상한을 두고 기다린다.
  - 갈래 삭제 때 모든 비종료 세션을 닫는다.
  - 세션 시작·close 때 deletedAt을 다시 확인한다.
- **상태**
  - 세션·인터뷰 상태별 허용 표를 넣었다. closing에서 안부 출력을 허용한다.
  - paused·closing용 오류 코드를 넣었다.
  - 종료 시점의 진행 중 턴 처리를 정했다.
- **데이터**
  - seq를 계보 전체에서 잇는다. parentBranchId를 forkMessageId의 소유 갈래로 정의했다.
  - OpenTurn에 clientTurnIds를 넣고, 실패 횟수는 OpenTurn 한 곳에만 둔다.
  - clarity를 저장 트랜잭션에 넣었다.
  - 보존 표에 행을 추가하고, 이벤트 공통 필드와 epoch를 넣었다.
- **개인정보**
  - 속마음·인터뷰 위기 발화를 저장하지 않는다.
  - 마스킹을 모든 저장 지점으로 넓혔다.
  - 재전송 버퍼를 세션 메모리 규칙에 넣었다.
  - no-store와 메모리 Blob을 쓴다.
  - 키 저장소를 분리하고 보장 범위를 바로잡았다.
  - CrisisEvent.source에서 등급을 뺐다.
  - sensitive 동의 철회 처리를 정했다.
  - 운영자 재설정 보호와 사유 코드를 넣었다.
- **판정**
  - 판정기 입력 표를 넣었다.
  - 입력 없는 LLM 생성물을 검사한다.
  - 요약을 사후 검사한다.
  - 출력 금지 사전 범주를 넓히고, 자해 수단이 걸리면 재판정한다.
  - 속마음 L1을 대사와 같이 처리한다.
  - 고인 감지 처리(5.13)를 넣었다.
- **표기**
  - [기준] 표기 오류를 고쳤다(SERVER_BUSY, 5.6).
  - 이름 규칙 예외를 12.2로 옮겼다.
  - D-T09가 비어 있는 이유를 적었다.
  - 테스트를 T-45까지 늘렸다.
