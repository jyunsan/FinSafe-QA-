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
DATASET = ROOT / "【v2.0】测试数据集.xlsx"
REPORTS = ROOT / "reports"


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
        for row in rows[1:]:
            if not any(row):
                continue
            item = dict(zip(headers, row))
            item["sheet"] = ws.title
            item["问题"] = clean_question(item.get("问题"))
            cases.append(item)
    return cases


def is_external_or_missing(question: str) -> bool:
    missing_terms = ["迈普医学", "百诚医药", "短期借款", "货币资金", "扣非净利润", "TIDES", "研报", "政策", "地缘政治", "业务量", "销售费用率"]
    return any(term in question for term in missing_terms)


def evaluate_case(case: dict) -> dict:
    response = run_query(case["问题"])
    plan = response["analysis_plan"]
    chart = response["chart"]
    trust = response["trust"]
    has_results = bool(response["results"])
    has_boundary_warning = bool(plan["limitations"])

    query_correct = has_results and plan["type"] not in {"unsupported", "partial_or_unsupported"}
    boundary_correct = is_external_or_missing(case["问题"]) and has_boundary_warning
    analysis_quality = query_correct or boundary_correct
    visual_quality = bool(chart.get("chart_type") and chart.get("title") and chart.get("unit") is not None and chart.get("sql_id"))
    traceability = bool(response["sql"] and response["query_id"] and trust["lineage"]["source_fields"])
    overall = (analysis_quality and visual_quality and traceability) and case.get("问题类型") != "开放性问题"

    return {
        "id": case.get("编号"),
        "sheet": case["sheet"],
        "type": case.get("问题类型"),
        "question": case["问题"],
        "analysis_type": plan["type"],
        "passed": overall,
        "query_correct": query_correct,
        "boundary_correct": boundary_correct,
        "analysis_quality": analysis_quality,
        "visual_quality": visual_quality,
        "traceability": traceability,
        "confidence": trust["confidence_score"],
        "confidence_label": trust["confidence_label"],
        "chart_type": chart.get("chart_type"),
        "answer": response["answer"],
        "limitations": plan["limitations"],
        "query_id": response["query_id"],
    }


def evaluate() -> tuple[list[dict], dict]:
    records = [evaluate_case(case) for case in load_cases()]

    by_sheet = defaultdict(lambda: {"total": 0, "passed": 0})
    by_type = defaultdict(lambda: {"total": 0, "passed": 0})
    dimensions = {
        "analysis_quality": {"total": 0, "passed": 0},
        "visual_quality": {"total": 0, "passed": 0},
        "traceability": {"total": 0, "passed": 0},
        "boundary_correct": {"total": 0, "passed": 0},
    }
    for record in records:
        by_sheet[record["sheet"]]["total"] += 1
        by_sheet[record["sheet"]]["passed"] += int(record["passed"])
        by_type[record["type"]]["total"] += 1
        by_type[record["type"]]["passed"] += int(record["passed"])
        for name in dimensions:
            if name == "boundary_correct" and not is_external_or_missing(record["question"]):
                continue
            dimensions[name]["total"] += 1
            dimensions[name]["passed"] += int(record[name])

    summary = {
        "total": len(records),
        "passed": sum(int(r["passed"]) for r in records),
        "by_sheet": dict(sorted(by_sheet.items())),
        "by_type": dict(sorted(by_type.items())),
        "dimensions": dimensions,
        "confidence_labels": Counter(r["confidence_label"] for r in records),
        "chart_types": Counter(r["chart_type"] for r in records),
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
        "# FinSafe-QA V2.0 评测运行结果",
        "",
        "> 本报告由 `evaluate.py` 基于 V2.0 测试数据集生成。",
        "",
        "## 总览",
        "",
        f"- 总问题数：{summary['total']}",
        f"- 通过数量：{summary['passed']}",
        f"- 整体通过率：{rate(summary['passed'], summary['total'])}",
        "",
        "## 按 Sheet",
        "",
        "| Sheet | 问题数 | 通过数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for sheet, item in summary["by_sheet"].items():
        lines.append(f"| {sheet} | {item['total']} | {item['passed']} | {rate(item['passed'], item['total'])} |")

    lines += [
        "",
        "## 质量维度",
        "",
        "| 维度 | 样本数 | 通过数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, item in summary["dimensions"].items():
        lines.append(f"| {name} | {item['total']} | {item['passed']} | {rate(item['passed'], item['total'])} |")

    failed = [r for r in records if not r["passed"]]
    lines += [
        "",
        "## 未通过样例",
        "",
        "| 编号 | Sheet | 类型 | 问题 | 主要限制 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in failed[:12]:
        q = record["question"].replace("|", " ")
        limitations = "；".join(record["limitations"]) or "分析质量或可视化质量未达门禁"
        lines.append(f"| {record['id']} | {record['sheet']} | {record['type']} | {q} | {limitations} |")

    (REPORTS / "evaluation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    records, summary = evaluate()
    write_reports(records, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Report written: {REPORTS / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()
