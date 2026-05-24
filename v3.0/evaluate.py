from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

os.environ.setdefault("FINSAFE_USE_LLM", "1")

from src.engine import run_query


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "【v3.0】测试数据集.xlsx"


def clean_question(raw: object) -> str:
    text = str(raw or "").strip()
    match = re.search(r'"Q"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else text


def load_cases() -> list[dict]:
    wb = openpyxl.load_workbook(DATASET, data_only=True)
    cases: list[dict] = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        headers = rows[0]
        question_key = "问题" if "问题" in headers else "问题内容"
        for row in rows[1:]:
            if not any(row):
                continue
            item = dict(zip(headers, row))
            item["sheet"] = ws.title
            item["question"] = clean_question(item.get(question_key))
            cases.append(item)
    return cases


def has_valid_dependencies(tasks: list[dict]) -> bool:
    ids = {task["id"] for task in tasks}
    return all(dep in ids for task in tasks for dep in task.get("depends_on", []))


def expected_task_types(question: str) -> set[str]:
    expected = {"query"}
    if any(word in question for word in ["①", "计算", "占比", "增长率", "效率", "评分", "ROE", "净利润率", "周转", "复合增长率"]):
        expected.add("calculation")
    if any(word in question for word in ["研报", "政策", "TIDES", "境外收入", "业务量", "在手订单", "客户集中度", "公允价值", "投资收益", "销售费用", "合同负债", "固定资产", "雇员人数", "流动比率", "营业外收入", "信用减值"]):
        expected.add("evidence_or_boundary")
    if any(word in question for word in ["画", "图", "折线图", "双轴图", "可视化"]):
        expected.add("visualization")
    if any(word in question for word in ["分析", "解释", "原因", "驱动", "风险", "关系"]):
        expected.add("analysis")
    return expected


def evaluate_case(case: dict, index: int) -> dict:
    session_id = f"eval-{case['sheet']}"
    response = run_query(case["question"], session_id=session_id)
    agent_plan = response["agent_plan"]
    context = response["context"]
    tasks = agent_plan["tasks"]
    actual_types = {task["type"] for task in tasks}
    expected_types = expected_task_types(case["question"])

    decomposition_pass = len(agent_plan["question_decomposition"]) >= 2 if "①" in case["question"] else len(tasks) >= 1
    task_type_pass = expected_types.issubset(actual_types | {"evidence_or_boundary"})
    dependency_pass = bool(tasks) and has_valid_dependencies(tasks) and bool(agent_plan["execution_batches"])
    context_record_pass = "session_id" in context and "inherited_slots" in context
    follow_up_pass = True
    if index > 0 and case["sheet"] == "多轮追问":
        follow_up_pass = bool(response.get("rewritten_question"))

    new_module_pass = decomposition_pass and task_type_pass and dependency_pass and context_record_pass and follow_up_pass

    return {
        "id": case.get("编号"),
        "sheet": case["sheet"],
        "type": case.get("问题类型"),
        "question": case["question"],
        "passed": new_module_pass,
        "decomposition_pass": decomposition_pass,
        "task_type_pass": task_type_pass,
        "dependency_pass": dependency_pass,
        "context_record_pass": context_record_pass,
        "follow_up_pass": follow_up_pass,
        "expected_types": sorted(expected_types),
        "actual_types": sorted(actual_types),
        "task_count": len(tasks),
        "batch_count": len(agent_plan["execution_batches"]),
        "context_used": context["is_follow_up"],
        "confidence": response["trust"]["confidence_score"],
    }


def evaluate() -> tuple[list[dict], dict]:
    records = [evaluate_case(case, index) for index, case in enumerate(load_cases())]
    by_sheet = defaultdict(lambda: {"total": 0, "passed": 0})
    by_type = defaultdict(lambda: {"total": 0, "passed": 0})
    dimensions = {
        "decomposition_pass": {"total": 0, "passed": 0},
        "task_type_pass": {"total": 0, "passed": 0},
        "dependency_pass": {"total": 0, "passed": 0},
        "context_record_pass": {"total": 0, "passed": 0},
        "follow_up_pass": {"total": 0, "passed": 0},
    }
    for record in records:
        by_sheet[record["sheet"]]["total"] += 1
        by_sheet[record["sheet"]]["passed"] += int(record["passed"])
        by_type[record["type"]]["total"] += 1
        by_type[record["type"]]["passed"] += int(record["passed"])
        for key in dimensions:
            dimensions[key]["total"] += 1
            dimensions[key]["passed"] += int(record[key])

    summary = {
        "total": len(records),
        "passed": sum(int(record["passed"]) for record in records),
        "by_sheet": dict(sorted(by_sheet.items())),
        "by_type": dict(sorted(by_type.items())),
        "dimensions": dimensions,
        "task_count_distribution": Counter(record["task_count"] for record in records),
    }
    return records, summary


def rate(passed: int, total: int) -> str:
    return f"{passed / total * 100:.1f}%" if total else "0.0%"


def main() -> None:
    records, summary = evaluate()
    print(json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
