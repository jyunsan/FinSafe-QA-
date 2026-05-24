const form = document.querySelector("#queryForm");
const input = document.querySelector("#question");
const answer = document.querySelector("#answer");
const sql = document.querySelector("#sql");
const table = document.querySelector("#table");
const trust = document.querySelector("#trust");
const confidence = document.querySelector("#confidence");
const queryId = document.querySelector("#queryId");
const score = document.querySelector("#score");

function renderTable(rows) {
  if (!rows || rows.length === 0) {
    table.innerHTML = "<p>无结构化结果</p>";
    return;
  }
  const columns = Object.keys(rows[0]);
  const head = columns.map((c) => `<th>${c}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${columns.map((c) => `<td>${row[c] ?? ""}</td>`).join("")}</tr>`)
    .join("");
  table.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderTrust(payload) {
  const items = [
    `数据源：${payload.lineage.data_provider}`,
    `源表字段：${payload.lineage.source_fields.join("、")}`,
    `快照版本：${payload.lineage.snapshot_version}`,
    ...payload.checks,
  ];
  trust.innerHTML = `<ul class="trust-list">${items.map((item) => `<li>${item}</li>`).join("")}</ul>`;
}

async function query(question) {
  answer.textContent = "查询中...";
  const res = await fetch(`/api/query?q=${encodeURIComponent(question)}`);
  const data = await res.json();
  if (!res.ok) {
    answer.textContent = data.error || "查询失败";
    return;
  }
  answer.textContent = data.answer;
  sql.textContent = data.sql;
  confidence.textContent = data.trust.confidence_label;
  queryId.textContent = `Query ID: ${data.query_id}`;
  score.textContent = `Score: ${data.trust.confidence_score}`;
  renderTable(data.results);
  renderTrust(data.trust);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  query(input.value.trim());
});

document.querySelectorAll("[data-q]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.q;
    query(input.value);
  });
});

query(input.value);
