async function api(path, options) {
  const resp = await fetch(path, options);
  const contentType = resp.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return resp.json();
  }
  return resp.text();
}

function currentFilters() {
  const site = document.getElementById("site").value;
  const boardType = document.getElementById("board_type").value;
  const categoryKey = document.getElementById("category_key").value;
  const hasPrice = document.getElementById("has_price").value;
  const topN = document.getElementById("top_n").value.trim();
  const sortBy = document.getElementById("sort_by").value;
  const sortOrder = document.getElementById("sort_order").value;
  const keyword = document.getElementById("keyword").value.trim();
  const params = new URLSearchParams({ site: site, board_type: boardType });
  if (categoryKey) params.set("category_key", categoryKey);
  if (hasPrice) params.set("has_price", hasPrice);
  if (topN) params.set("top_n", topN);
  if (sortBy) params.set("sort_by", sortBy);
  if (sortOrder) params.set("sort_order", sortOrder);
  if (keyword) params.set("keyword", keyword);
  return params;
}

async function refreshJobs() {
  const data = await api("/api/jobs");
  document.getElementById("jobs").textContent = JSON.stringify(data.items || [], null, 2);
}

async function runJob() {
  const payload = {
    site: document.getElementById("site").value,
    board_type: document.getElementById("board_type").value,
  };

  const data = await api("/api/jobs/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });

  alert(`任务已创建: #${data.id}`);
  await refreshJobs();
}

async function loadCategories() {
  const site = document.getElementById("site").value;
  const boardType = document.getElementById("board_type").value;
  const data = await api(`/api/categories?site=${encodeURIComponent(site)}&board_type=${encodeURIComponent(boardType)}`);
  const select = document.getElementById("category_key");
  const previous = select.value;

  select.innerHTML = '<option value="">全部类目</option>';
  (data.items || []).forEach((item) => {
    const option = document.createElement("option");
    option.value = item.category_key;
    option.textContent = `${item.category_name} (${item.item_count})`;
    select.appendChild(option);
  });

  if (previous && [...select.options].some((opt) => opt.value === previous)) {
    select.value = previous;
  }
}

async function searchRanks() {
  const params = currentFilters();
  const data = await api(`/api/ranks?${params.toString()}`);
  const tbody = document.querySelector("#ranksTable tbody");
  tbody.innerHTML = "";
  document.getElementById("querySummary").textContent = `总数: ${data.total || 0} | 数据任务: ${data.job_id || "-"}`;

  (data.items || []).forEach((item) => {
    const tr = document.createElement("tr");
    const detailUrl = item.detail_url || "";
    const detailCell = detailUrl
      ? `<a href="${detailUrl}" target="_blank" rel="noreferrer">打开</a>`
      : "";
    tr.innerHTML = `
      <td>${item.snapshot_date || ""}</td>
      <td>${item.site || ""}</td>
      <td>${item.board_type || ""}</td>
      <td>${item.category_name || item.category_key || ""}</td>
      <td>${item.rank ?? ""}</td>
      <td>${item.asin || ""}</td>
      <td>${item.title || ""}</td>
      <td>${item.brand || ""}</td>
      <td>${item.price_text || ""}</td>
      <td>${item.rating ?? ""}</td>
      <td>${item.review_count ?? ""}</td>
      <td>${detailCell}</td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById("csvExport").href = `/api/export/ranks.csv?${params.toString()}`;
  document.getElementById("xlsxExport").href = `/api/export/ranks.xlsx?${params.toString()}`;
}

async function cleanupInvalid() {
  const site = document.getElementById("site").value;
  const boardType = document.getElementById("board_type").value;
  const confirmed = window.confirm(`清理 ${site} / ${boardType} 下历史无价格数据？`);
  if (!confirmed) return;

  const data = await api("/api/maintenance/cleanup-invalid", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      site: site,
      board_type: boardType,
    }),
  });

  alert(
    `清理完成\n删除排行: ${data.deleted_rank_records}\n删除商品: ${data.deleted_products}\n删除类目: ${data.deleted_categories}\n剩余无价格: ${data.remaining_invalid_rank_records}`,
  );
  await loadCategories();
  await searchRanks();
}

document.getElementById("runJob").addEventListener("click", runJob);
document.getElementById("refreshJobs").addEventListener("click", refreshJobs);
document.getElementById("searchRanks").addEventListener("click", searchRanks);
document.getElementById("cleanupInvalid").addEventListener("click", cleanupInvalid);
document.getElementById("site").addEventListener("change", async () => {
  await loadCategories();
  await searchRanks();
});
document.getElementById("board_type").addEventListener("change", async () => {
  await loadCategories();
  await searchRanks();
});
document.getElementById("category_key").addEventListener("change", searchRanks);
document.getElementById("has_price").addEventListener("change", searchRanks);
document.getElementById("top_n").addEventListener("change", searchRanks);
document.getElementById("sort_by").addEventListener("change", searchRanks);
document.getElementById("sort_order").addEventListener("change", searchRanks);

refreshJobs();
loadCategories().then(searchRanks);
