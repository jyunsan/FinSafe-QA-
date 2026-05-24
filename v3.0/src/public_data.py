from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "finsafe_v3.db"


@dataclass(frozen=True)
class Company:
    stock_code: str
    short_name: str
    industry: str


COMPANIES = [
    Company("603259", "药明康德", "CXO"),
    Company("002821", "凯莱英", "CXO"),
    Company("300347", "泰格医药", "CXO"),
    Company("603127", "昭衍新药", "CXO"),
    Company("688276", "百克生物", "疫苗"),
    Company("300244", "迪安诊断", "医学检验"),
    Company("300759", "康龙化成", "CXO"),
    Company("688202", "美迪西", "CXO"),
    Company("300558", "贝达药业", "创新药"),
    Company("688520", "神州细胞", "创新药"),
]


def parse_amount(value: Any) -> float | None:
    if value is None or value is False:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"False", "--", "nan", "None"}:
        return None
    try:
        if text.endswith("亿"):
            return round(float(text[:-1]) * 100, 4)
        if text.endswith("万"):
            return round(float(text[:-1]) / 100, 4)
        return round(float(text), 4)
    except ValueError:
        return None


def parse_percent(value: Any) -> float | None:
    if value is None or value is False:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"False", "--", "nan", "None"}:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 4)
    except ValueError:
        return None


def period_key(report_date: str) -> str:
    if report_date.endswith("-09-30"):
        return report_date[:4] + "Q3"
    if report_date.endswith("-12-31"):
        return report_date[:4] + "A"
    return report_date


def pick_row(df: pd.DataFrame, report_date: str) -> dict[str, Any] | None:
    if df.empty or "报告期" not in df.columns:
        return None
    matched = df[df["报告期"].astype(str) == report_date]
    if matched.empty:
        return None
    return matched.iloc[0].to_dict()


def get_value(row: dict[str, Any] | None, *columns: str, parser=parse_amount) -> float | None:
    if not row:
        return None
    for col in columns:
        if col in row:
            parsed = parser(row.get(col))
            if parsed is not None:
                return parsed
    return None


def fetch_company_frames(stock_code: str) -> dict[str, pd.DataFrame]:
    return {
        "abstract": ak.stock_financial_abstract_ths(symbol=stock_code, indicator="按报告期"),
        "benefit": ak.stock_financial_benefit_ths(symbol=stock_code, indicator="按报告期"),
        "debt": ak.stock_financial_debt_ths(symbol=stock_code, indicator="按报告期"),
        "cash": ak.stock_financial_cash_ths(symbol=stock_code, indicator="按报告期"),
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS financial_metrics;
        DROP TABLE IF EXISTS companies;
        DROP TABLE IF EXISTS data_sources;

        CREATE TABLE companies (
            stock_code TEXT PRIMARY KEY,
            short_name TEXT NOT NULL,
            industry TEXT NOT NULL
        );

        CREATE TABLE financial_metrics (
            stock_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            report_period TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            revenue REAL,
            net_profit REAL,
            rd_expense REAL,
            operating_cash_flow REAL,
            gross_margin REAL,
            total_assets REAL,
            total_liabilities REAL,
            accounts_receivable REAL,
            inventory REAL,
            currency_unit TEXT NOT NULL DEFAULT '百万元',
            data_provider TEXT NOT NULL,
            source_url TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            PRIMARY KEY (stock_code, report_period),
            FOREIGN KEY (stock_code) REFERENCES companies(stock_code)
        );

        CREATE TABLE data_sources (
            provider TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            source_url TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        """
    )


def sync_public_database(limit: int | None = None, sleep_seconds: float = 0.2) -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    now = datetime.now().isoformat(timespec="seconds")
    snapshot = f"akshare-ths-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    conn.executemany(
        "INSERT INTO companies(stock_code, short_name, industry) VALUES (?, ?, ?)",
        [(c.stock_code, c.short_name, c.industry) for c in COMPANIES],
    )
    conn.execute(
        "INSERT INTO data_sources VALUES (?, ?, ?, ?)",
        (
            "AkShare/同花顺公开财务数据",
            "通过 AkShare 调用同花顺公开财务报表接口，落地为本地 SQLite 缓存用于可复现查询。",
            "https://basic.10jqka.com.cn/",
            now,
        ),
    )

    report_dates = ["2025-09-30", "2024-12-31", "2023-12-31", "2022-12-31"]
    rows = []
    for idx, company in enumerate(COMPANIES[:limit] if limit else COMPANIES, start=1):
        frames = fetch_company_frames(company.stock_code)
        for report_date in report_dates:
            abstract = pick_row(frames["abstract"], report_date)
            benefit = pick_row(frames["benefit"], report_date)
            debt = pick_row(frames["debt"], report_date)
            cash = pick_row(frames["cash"], report_date)

            revenue = get_value(benefit, "营业总收入", "一、营业总收入")
            net_profit = get_value(benefit, "五、净利润", "*净利润", "净利润")
            rd_expense = get_value(benefit, "研发费用")
            operating_cash_flow = get_value(cash, "经营活动产生的现金流量净额", "*经营活动产生的现金流量净额")
            gross_margin = get_value(abstract, "销售毛利率", parser=parse_percent)
            total_assets = get_value(debt, "资产合计", "*资产合计")
            total_liabilities = get_value(debt, "负债合计", "*负债合计")
            accounts_receivable = get_value(debt, "应收账款", "应收票据及应收账款")
            inventory = get_value(debt, "存货")

            rows.append(
                (
                    company.stock_code,
                    report_date,
                    period_key(report_date),
                    int(report_date[:4]),
                    "Q3" if report_date.endswith("-09-30") else "A",
                    revenue,
                    net_profit,
                    rd_expense,
                    operating_cash_flow,
                    gross_margin,
                    total_assets,
                    total_liabilities,
                    accounts_receivable,
                    inventory,
                    "AkShare/同花顺公开财务数据",
                    f"https://basic.10jqka.com.cn/new/{company.stock_code}/finance.html",
                    snapshot,
                    now,
                )
            )
        if sleep_seconds and idx < len(COMPANIES):
            time.sleep(sleep_seconds)

    conn.executemany(
        """
        INSERT INTO financial_metrics (
            stock_code, report_date, report_period, year, quarter, revenue, net_profit,
            rd_expense, operating_cash_flow, gross_margin, total_assets, total_liabilities,
            accounts_receivable, inventory, data_provider, source_url, snapshot_version, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return DB_PATH


if __name__ == "__main__":
    path = sync_public_database()
    print(f"Public data cache created: {path}")
