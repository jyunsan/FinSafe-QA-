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
DATASET = ROOT / "data" / "【v1.0】评测问题集.xlsx"
REPORTS = ROOT / "reports"


def clean_question(raw: object) -> str:
    text = str(raw or "").strip()
    match = re.search(r'"Q"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else text


def load_cases() -> list[dict]:
    wb = openpyxl.load_workbook(DATASET, data_only=True)
    ws = wb["SQL问题汇总"]
    rows = list(ws.iter_rows(values_only=True))
    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(row)]


def evaluate_case(case: dict) -> dict:
    """Run a single case through the full query engine and evaluate quality."""
    response = run_query(clean_question(case["问题"]))
    trust = response["trust"]

    sql_valid = bool(response.get("sql"))
    answer_valid = bool(response.get("answer"))
    trust_complete = bool(
        trust.get("confidence_score") is not None
        and trust.get("confidence_label")
        and trust.get("lineage", {}).get("source_fields")
        and response.get("query_id")
    )
    has_result = bool(response.get("results"))
    passed = sql_valid and answer_valid and trust_complete and has_result

    return {
        "id": case["编号"],
        "type": case["问题类型"],
        "difficulty": int(case["难度等级"]),
        "question": clean_question(case["问题"]),
        "passed": passed,
        "sql_valid": sql_valid,
        "answer_valid": answer_valid,
        "trust_complete": trust_complete,
        "has_result": has_result,
        "confidence": trust["confidence_score"],
        "confidence_label": trust["confidence_label"],
        "sql": response["sql"],
        "query_id": response["query_id"],
        "answer": response["answer"],
    }


def evaluate() -> tuple[list[dict], dict]:
    records = [evaluate_case(case) for case in load_cases()]

    by_difficulty = defaultdict(lambda: {"total": 0, "passed": 0})
    by_type = defaultdict(lambda: {"total": 0, "passed": 0})
    dimensions = {
        "sql_valid": {"total": 0, "passed": 0},
        "answer_valid": {"total": 0, "passed": 0},
        "trust_complete": {"total": 0, "passed": 0},
        "has_result": {"total": 0, "passed": 0},
    }
    for record in records:
        by_difficulty[record["difficulty"]]["total"] += 1
        by_difficulty[record["difficulty"]]["passed"] += int(record["passed"])
        by_type[record["type"]]["total"] += 1
        by_type[record["type"]]["passed"] += int(record["passed"])
        for key in dimensions:
            dimensions[key]["total"] += 1
            dimensions[key]["passed"] += int(record[key])

    summary = {
        "total": len(records),
        "passed": sum(int(r["passed"]) for r in records),
        "by_difficulty": dict(sorted(by_difficulty.items())),
        "by_type": dict(sorted(by_type.items())),
        "dimensions": dimensions,
        "confidence_labels": Counter(r["confidence_label"] for r in records),
    }
    return records, summary


def rate(passed: int, total: int) -> str:
    return f"{passed / total * 100:.1f}%" if total else "0.0%"


def write_reports(records: list[dict], summary: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "evaluation_results.json").write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# FinSafe-QA V1.0 评测运行结果",
        "",
        "> 本报告由 `evaluate.py` 基于 V1.0 评测问题集生成。3 级问题作为挑战集观察，不阻断 V1.0 核心能力判断。",
        "",
        "## 总览",
        "",
        f"- 总问题数：{summary['total']}",
        f"- 通过数量：{summary['passed']}",
        f"- 整体通过率：{rate(summary['passed'], summary['total'])}",
        "",
        "## 按难度等级",
        "",
        "| 难度等级 | 问题数 | 通过数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for difficulty, item in summary["by_difficulty"].items():
        lines.append(f"| {difficulty} 级 | {item['total']} | {item['passed']} | {rate(item['passed'], item['total'])} |")

    lines += [
        "",
        "## 按问题类型",
        "",
        "| 问题类型 | 问题数 | 通过数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for qtype, item in summary["by_type"].items():
        lines.append(f"| {qtype} | {item['total']} | {item['passed']} | {rate(item['passed'], item['total'])} |")

    lines += [
        "",
        "## 质量维度",
        "",
        "| 维度 | 样本数 | 通过数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, item in summary["dimensions"].items():
        lines.append(f"| {name} | {item['total']} | {item['passed']} | {rate(item['passed'], item['total'])} |")

    failed = [r for r in records if not r["passed"]][:12]
    lines += [
        "",
        "## 失败样例",
        "",
        "| 编号 | 类型 | 难度 | 问题 | 置信度 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for record in failed:
        q = record["question"].replace("|", " ")
        lines.append(f"| {record['id']} | {record['type']} | {record['difficulty']} | {q} | {record['confidence_label']} |")

    (REPORTS / "evaluation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    records, summary = evaluate()
    write_reports(records, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report written: {REPORTS / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()
