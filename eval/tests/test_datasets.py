"""위기 테스트 세트(PRD 6.4, TRD T-02), 타해 위협 세트(PRD 7절), 골든 시나리오(PRD 6.4)의 형식 검사.

내용의 옳고 그름은 사람이 검수한다. 이 테스트는 형식, 개수, 범주 구성만 본다.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

evalDir = Path(__file__).resolve().parent.parent
crisisPath = evalDir / "crisis" / "crisis_set.jsonl"
goldenPath = evalDir / "golden" / "golden_scenarios.jsonl"
harmPath = evalDir / "crisis" / "harm_others_set.jsonl"
goldenHarmPath = evalDir / "golden" / "harm_others_scenarios.jsonl"

levels = {"L0", "L1", "L2", "L3"}
roles = {"user", "shadow"}

crisisCategories = {
    "direct", "indirect", "slang", "obfuscated", "multi_turn", "short_answer",
    "inner", "boundary", "explicit_l3", "injection", "l1_elevated",
    "non_crisis_quote", "non_crisis_past", "non_crisis_anger",
    "non_crisis_hyperbole", "non_crisis_other",
}
crisisFields = {"id", "category", "channel", "scope", "context", "input", "expected", "notes", "reviewed"}
scopes = {"session", "interview", "checkin"}
harmLevels = {"none", "vented", "concrete"}
harmTargets = {"none", "shadowPerson", "other", "family"}
harmCategories = {
    "vented", "concrete_other", "concrete_shadow_person", "concrete_family",
    "extended_suicide", "escalating", "calmed", "non_harm", "inner", "obfuscated_injection",
}
harmFields = crisisFields | {"expectedHarm", "target"}

situations = {"date", "interview", "family", "free"}
rubricKeys = {
    "characterConsistency", "noAdvice", "noRealPersonClaim", "awarenessLine",
    "crisisProtocol", "situationRule", "moodHandling", "harmResponse",
}
goldenFields = {
    "id", "situation", "focus", "card", "clarity", "camOff", "mood", "history",
    "input", "expectedJudge", "expect", "mustNot", "rubric", "reviewed",
}
cardFields = {"relation", "timeAxis", "callName", "speechStyle", "wantToSay", "emotions"}
moodLabels = {"편안함", "설렘", "망설임", "긴장", "서운함", "슬픔", "화남", "미안함", "지침"}


def loadJsonl(path):
    rows = []
    for lineNo, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            pytest.fail(f"{path.name}:{lineNo} JSON 오류: {error}")
    return rows


def checkContext(caseId, context):
    assert isinstance(context, list), caseId
    for turn in context:
        assert set(turn) == {"role", "text"}, caseId
        assert turn["role"] in roles, caseId
        assert turn["text"].strip(), caseId


@pytest.fixture(scope="module")
def crisisCases():
    return loadJsonl(crisisPath)


@pytest.fixture(scope="module")
def goldenCases():
    return loadJsonl(goldenPath)


@pytest.fixture(scope="module")
def harmCases():
    return loadJsonl(harmPath)


@pytest.fixture(scope="module")
def goldenHarmCases():
    return loadJsonl(goldenHarmPath)


def checkGoldenCase(case, fields):
    caseId = case.get("id")
    assert set(case) == fields, caseId
    assert case["situation"] in situations, caseId
    assert set(case["card"]) == cardFields, caseId
    assert case["card"]["timeAxis"] in {"past", "future"}, caseId
    assert case["clarity"] in {1, 2, 3, 4}, caseId
    assert isinstance(case["camOff"], bool), caseId
    assert case["expectedJudge"] in {"L0", "L1"}, caseId
    assert case["input"].strip(), caseId
    assert case["expect"] and case["mustNot"], caseId
    assert case["rubric"] and set(case["rubric"]) <= rubricKeys, caseId
    assert isinstance(case["reviewed"], bool), caseId
    checkContext(caseId, case["history"])


def testCrisisSetHasAtLeast200Cases(crisisCases):
    assert len(crisisCases) >= 200


def testCrisisIdsAreUnique(crisisCases):
    counts = Counter(case["id"] for case in crisisCases)
    assert [caseId for caseId, n in counts.items() if n > 1] == []


def testCrisisCaseFields(crisisCases):
    for case in crisisCases:
        caseId = case.get("id")
        assert set(case) == crisisFields, caseId
        assert case["category"] in crisisCategories, caseId
        assert case["channel"] in {"dialogue", "inner"}, caseId
        assert case["scope"] in scopes, caseId
        assert case["expected"] in levels, caseId
        assert case["input"].strip(), caseId
        assert isinstance(case["reviewed"], bool), caseId
        checkContext(caseId, case["context"])


def testEveryCrisisCategoryHasAtLeastFiveCases(crisisCases):
    counts = Counter(case["category"] for case in crisisCases)
    assert {c: counts[c] for c in crisisCategories if counts[c] < 5} == {}


def testCrisisCategoryLevelsAreConsistent(crisisCases):
    for case in crisisCases:
        category, expected = case["category"], case["expected"]
        if category.startswith("non_crisis_"):
            assert expected in {"L0", "L1"}, case["id"]
        elif category == "l1_elevated":
            assert expected == "L1", case["id"]
        elif category == "explicit_l3":
            assert expected == "L3", case["id"]
        else:
            assert expected in {"L2", "L3"}, case["id"]


def testObfuscatedCasesKeepZeroWidthCharacters(crisisCases):
    zeroWidth = [case["id"] for case in crisisCases if "​" in case["input"]]
    assert {"CR-064", "CR-065"} <= set(zeroWidth)


def testInnerChannelOnlyInSessionScope(crisisCases):
    for case in crisisCases:
        if case["channel"] == "inner":
            assert case["scope"] == "session", case["id"]


def testCrisisContextCategoriesHaveContext(crisisCases):
    for case in crisisCases:
        if case["category"] in {"multi_turn", "short_answer"}:
            assert case["context"], case["id"]
        if case["category"] == "short_answer":
            assert case["context"][-1]["role"] == "shadow", case["id"]


def testInnerCategoryUsesInnerChannel(crisisCases):
    for case in crisisCases:
        if case["category"] == "inner":
            assert case["channel"] == "inner", case["id"]


def testGoldenHas40CasesTenPerSituation(goldenCases):
    assert len(goldenCases) == 40
    assert Counter(case["situation"] for case in goldenCases) == {s: 10 for s in situations}


def testGoldenIdsAreUnique(goldenCases):
    counts = Counter(case["id"] for case in goldenCases)
    assert [caseId for caseId, n in counts.items() if n > 1] == []


def testGoldenCaseFields(goldenCases):
    for case in goldenCases:
        checkGoldenCase(case, goldenFields)


def testGoldenMoodBlock(goldenCases):
    for case in goldenCases:
        mood = case["mood"]
        if mood is None:
            continue
        assert set(mood) == {"label", "strength", "source"}, case["id"]
        assert mood["label"] in moodLabels, case["id"]
        assert mood["strength"] in {"약", "중", "강"}, case["id"]
        assert mood["source"] in {"voice", "expression", "button"}, case["id"]
        if case["camOff"]:
            assert mood["source"] != "expression", case["id"]


def testGoldenL1CasesCheckAwarenessLine(goldenCases):
    for case in goldenCases:
        if case["expectedJudge"] == "L1":
            assert "awarenessLine" in case["rubric"], case["id"]
            assert "crisisProtocol" in case["rubric"], case["id"]


def testHarmSetFields(harmCases):
    assert len(harmCases) >= 30
    counts = Counter(case["id"] for case in harmCases)
    assert [caseId for caseId, n in counts.items() if n > 1] == []
    for case in harmCases:
        caseId = case.get("id")
        assert set(case) == harmFields, caseId
        assert case["category"] in harmCategories, caseId
        assert case["channel"] in {"dialogue", "inner"}, caseId
        assert case["scope"] in scopes, caseId
        assert case["expected"] in levels, caseId
        assert case["expectedHarm"] in harmLevels, caseId
        assert case["target"] in harmTargets, caseId
        assert isinstance(case["reviewed"], bool), caseId
        checkContext(caseId, case["context"])


def testHarmSetCoversEveryCategory(harmCases):
    counts = Counter(case["category"] for case in harmCases)
    assert {c for c in harmCategories if counts[c] < 2} == set()


def testHarmCategoryLevelsAreConsistent(harmCases):
    for case in harmCases:
        category, harm = case["category"], case["expectedHarm"]
        if category.startswith("concrete_") or category == "escalating":
            assert harm == "concrete", case["id"]
        elif category == "vented":
            assert harm == "vented", case["id"]
        elif category == "non_harm":
            assert harm == "none", case["id"]
        elif category == "extended_suicide":
            assert harm == "concrete" and case["expected"] == "L3", case["id"]
        if category == "concrete_shadow_person":
            assert case["target"] == "shadowPerson", case["id"]
        if category in {"escalating", "calmed"}:
            assert case["context"], case["id"]


def testGoldenHarmScenarios(goldenHarmCases):
    assert len(goldenHarmCases) >= 6
    counts = Counter(case["id"] for case in goldenHarmCases)
    assert [caseId for caseId, n in counts.items() if n > 1] == []
    for case in goldenHarmCases:
        checkGoldenCase(case, goldenFields | {"expectedHarm", "target"})
        assert case["expectedHarm"] in harmLevels, case["id"]
        assert case["target"] in harmTargets, case["id"]
        assert "harmResponse" in case["rubric"], case["id"]
    targets = {case["target"] for case in goldenHarmCases if case["expectedHarm"] == "concrete"}
    assert {"shadowPerson", "other"} <= targets
