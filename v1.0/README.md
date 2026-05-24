# FinSafe-QA V1.0

面向金融投研场景的可信问数引擎，核心链路为：

```text
自然语言提问 -> SQL 自动生成 -> 公开财务数据查询 -> 可信层输出
```

## 数据源

项目通过 AkShare 调用同花顺公开财务数据接口，并落地为本地 SQLite 缓存：

- 数据源：AkShare / 同花顺公开财务数据
- 缓存文件：`data/finsafe_v1.db`
- 覆盖公司：10 家医药/CXO/创新药相关 A 股上市公司
- 覆盖期间：2022 年、2023 年、2024 年年度报告，2025 年三季报

重新同步公开数据：

```bash
python3 -m src.public_data
```

## 启动 Web 服务

```bash
python3 server.py
```

如果 8765 端口被占用，可以指定端口：

```bash
python3 server.py 8766
```

打开：

```text
http://127.0.0.1:8765
```

## 命令行查询

```bash
python3 -m src.engine "药明康德2025年第三季度营业总收入是多少"
```

## 大模型配置

项目支持硅基流动 OpenAI-compatible 接口。`.env` 示例：

```text
SILICONFLOW_API_KEY=你的 API Key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
```

大模型用于自然语言意图识别和结果表达，SQL 仍由系统基于白名单模板生成。若接口不可用，系统会自动回退到规则解析。

## 运行评测

```bash
python3 evaluate.py
```

脚本会在本地生成评测输出，正式结论已整理进 `【v1.0】项目评测.md`：

- `reports/evaluation_report.md`
- `reports/evaluation_results.json`

## 目录说明

| 目录/文件 | 说明 |
| --- | --- |
| `【v1.0】PRD.md` | V1.0 产品需求文档 |
| `【v1.0】项目评测.md` | 项目评测设计与本地运行结果 |
| `【v1.0】提示词工程.md` | 大模型提示词与兜底策略 |
| `data/【v1.0】评测问题集.xlsx` | 评测问题集 |
| `data/finsafe_v1.db` | 公开数据源同步后的本地 SQLite 缓存 |
| `src/public_data.py` | 公开数据源同步模块 |
| `src/engine.py` | NL2SQL 与可信层查询引擎 |
| `server.py` | 本地 Web/API 服务 |
| `web/` | Web 前端 |
| `evaluate.py` | 评测脚本 |
