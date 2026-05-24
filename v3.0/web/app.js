const form = document.querySelector("#queryForm");
const input = document.querySelector("#question");
const answer = document.querySelector("#answer");
const sql = document.querySelector("#sql");
const table = document.querySelector("#table");
const trust = document.querySelector("#trust");
const confidence = document.querySelector("#confidence");
const queryId = document.querySelector("#queryId");
const score = document.querySelector("#score");
const plan = document.querySelector("#plan");
const chart = document.querySelector("#chart");
const chartType = document.querySelector("#chartType");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTable(rows) {
  if (!rows || rows.length === 0) {
    table.innerHTML = "<p class=\"empty\">无结构化结果</p>";
    return;
  }
  const columns = Object.keys(rows[0]);
  const head = columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${columns.map((c) => `<td>${escapeHtml(row[c])}</td>`).join("")}</tr>`)
    .join("");
  table.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderPlan(payload) {
  const context = window.latestPayload?.context || {};
  const agentPlan = window.latestPayload?.agent_plan || {};
  const items = [
    `是否追问：${context.is_follow_up ? "是" : "否"}`,
    `继承槽位：${JSON.stringify(context.inherited_slots || {})}`,
    `子任务数：${(agentPlan.tasks || []).length}`,
    `分析类型：${payload.type}`,
    `指标：${payload.metric}`,
    `推荐图表：${payload.chart_type}`,
    ...payload.steps,
    ...(agentPlan.tasks || []).map((task) => `${task.id} / ${task.type}：${task.goal}`),
    ...payload.limitations.map((item) => `限制：${item}`),
  ];
  plan.innerHTML = `<ul class="info-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderTrust(payload) {
  const items = [
    `数据源：${payload.lineage.data_provider}`,
    `源表字段：${payload.lineage.source_fields.join("、")}`,
    `快照版本：${payload.lineage.snapshot_version}`,
    ...payload.checks,
  ];
  trust.innerHTML = `<ul class="info-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function getValue(row, key) {
  const value = Number(row[key]);
  return Number.isFinite(value) ? value : 0;
}

function renderChart(config) {
  chartType.textContent = config.chart_type || "-";
  const rows = config.data || [];
  if (!rows.length || config.chart_type === "table") {
    chart.innerHTML = `<p class="empty">${escapeHtml(config.insight || "暂无图表")}</p>`;
    return;
  }

  const yKey = config.y_axis || "value";
  const xKey = config.x_axis || "short_name";
  const maxValue = Math.max(...rows.map((row) => Math.abs(getValue(row, yKey))), 1);

  if (config.chart_type === "line") {
    const points = rows.map((row, index) => {
      const x = rows.length === 1 ? 50 : (index / (rows.length - 1)) * 100;
      const y = 92 - (Math.max(getValue(row, yKey), 0) / maxValue) * 78;
      return `${x},${y}`;
    });
    const labels = rows
      .map((row, index) => {
        const x = rows.length === 1 ? 50 : (index / (rows.length - 1)) * 100;
        return `<span style="left:${x}%">${escapeHtml(row.report_period)}</span>`;
      })
      .join("");
    chart.innerHTML = `
      <div class="chart-title">${escapeHtml(config.title)}</div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="${escapeHtml(config.title)}">
        <polyline points="${points.join(" ")}" fill="none" stroke="#2166a5" stroke-width="2.5" vector-effect="non-scaling-stroke"></polyline>
        ${points.map((point) => `<circle cx="${point.split(",")[0]}" cy="${point.split(",")[1]}" r="1.8" fill="#2166a5"></circle>`).join("")}
      </svg>
      <div class="axis-labels">${labels}</div>
      <p class="chart-note">${escapeHtml(config.insight)}</p>
    `;
    return;
  }

  const bars = rows
    .map((row) => {
      const value = getValue(row, yKey);
      const width = Math.max(4, (Math.abs(value) / maxValue) * 100);
      return `
        <div class="bar-row">
          <span>${escapeHtml(row[xKey] || row.short_name || row.name)}</span>
          <div class="bar-track"><i style="width:${width}%"></i></div>
          <strong>${escapeHtml(value.toFixed(2).replace(/\.00$/, ""))}</strong>
        </div>
      `;
    })
    .join("");
  chart.innerHTML = `
    <div class="chart-title">${escapeHtml(config.title)}</div>
    <div class="bars">${bars}</div>
    <p class="chart-note">${escapeHtml(config.insight)}</p>
  `;
}

async function query(question) {
  answer.textContent = "分析中...";
  const res = await fetch(`/api/query?q=${encodeURIComponent(question)}`);
  const data = await res.json();
  if (!res.ok) {
    answer.textContent = data.error || "分析失败";
    return;
  }
  window.latestPayload = data;
  answer.textContent = data.answer;
  sql.textContent = data.sql;
  confidence.textContent = data.trust.confidence_label;
  queryId.textContent = `Query ID: ${data.query_id}`;
  score.textContent = `Score: ${data.trust.confidence_score}`;
  renderTable(data.results);
  renderPlan(data.analysis_plan);
  renderTrust(data.trust);
  renderChart(data.chart);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (question) query(question);
});

document.querySelectorAll("[data-q]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.q;
    query(input.value);
  });
});

query(input.value);
