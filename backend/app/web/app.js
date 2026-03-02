const MANIFEST_PATH = "./data/manifest.json";
const DAILY_PATH_PREFIX = "./data/daily/";

let manifest = null;
let dailyPayload = null;
let filteredItems = [];

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? "";
}

async function loadJson(path) {
  const resp = await fetch(path, { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`加载失败 (${resp.status}): ${path}`);
  }
  return resp.json();
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function getManifestDates() {
  if (!manifest || !Array.isArray(manifest.available_dates)) return [];
  return manifest.available_dates.filter((d) => typeof d === "string" && d.trim());
}

function renderStatus() {
  const status = manifest?.status || "empty";
  const message = manifest?.message || "";
  const statusText = message ? `${status} (${message})` : status;
  setText("dataStatus", statusText);
  setText("lastSuccessDate", manifest?.last_success_date || "-");
  setText("lastAttemptAt", manifest?.last_attempt_at || "-");
}

function applyDefaultFilters() {
  const defaults = manifest?.default_filters || {};
  if (defaults.site) document.getElementById("site").value = defaults.site;
  if (defaults.board_type) document.getElementById("board_type").value = defaults.board_type;
  if (defaults.has_price !== undefined) document.getElementById("has_price").value = String(defaults.has_price);
  if (defaults.top_n !== undefined) document.getElementById("top_n").value = String(defaults.top_n);
  if (defaults.sort_by) document.getElementById("sort_by").value = defaults.sort_by;
  if (defaults.sort_order) document.getElementById("sort_order").value = defaults.sort_order;
}

function populateDateOptions() {
  const select = document.getElementById("snapshot_date");
  const dates = getManifestDates();
  select.innerHTML = "";

  if (!dates.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无可用数据";
    select.appendChild(option);
    return;
  }

  dates.forEach((date) => {
    const option = document.createElement("option");
    option.value = date;
    option.textContent = date;
    select.appendChild(option);
  });

  const preferred = manifest?.last_success_date || dates[0];
  if (dates.includes(preferred)) {
    select.value = preferred;
  } else {
    select.value = dates[0];
  }
}

function currentFilters() {
  return {
    site: document.getElementById("site").value,
    boardType: document.getElementById("board_type").value,
    categoryKey: document.getElementById("category_key").value,
    hasPrice: document.getElementById("has_price").value,
    topN: document.getElementById("top_n").value.trim(),
    sortBy: document.getElementById("sort_by").value,
    sortOrder: document.getElementById("sort_order").value,
    keyword: document.getElementById("keyword").value.trim().toLowerCase(),
  };
}

function rebuildCategoryOptions() {
  const select = document.getElementById("category_key");
  const previous = select.value;
  const site = document.getElementById("site").value;
  const boardType = document.getElementById("board_type").value;

  select.innerHTML = '<option value="">全部类目</option>';
  if (!dailyPayload) return;

  const categoryItems = (dailyPayload.categories || [])
    .filter((item) => item.site === site && item.board_type === boardType)
    .sort((a, b) => String(a.category_name || "").localeCompare(String(b.category_name || "")));

  categoryItems.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.category_key;
    option.textContent = `${item.category_name} (${item.item_count || 0})`;
    select.appendChild(option);
  });

  if (previous && [...select.options].some((opt) => opt.value === previous)) {
    select.value = previous;
  }
}

function sortFilteredItems(items, sortBy, sortOrder) {
  const direction = sortOrder === "desc" ? -1 : 1;
  const withIndex = items.map((item, index) => ({ item, index }));

  withIndex.sort((left, right) => {
    const a = parseNumber(left.item[sortBy]);
    const b = parseNumber(right.item[sortBy]);

    if (a === null && b === null) {
      // Keep stable order for all-null values.
      return left.index - right.index;
    }
    if (a === null) return 1;
    if (b === null) return -1;
    if (a !== b) return (a - b) * direction;

    const rankA = parseNumber(left.item.rank) ?? Number.MAX_SAFE_INTEGER;
    const rankB = parseNumber(right.item.rank) ?? Number.MAX_SAFE_INTEGER;
    if (rankA !== rankB) return rankA - rankB;
    return left.index - right.index;
  });

  return withIndex.map((entry) => entry.item);
}

function filterItems() {
  if (!dailyPayload || !Array.isArray(dailyPayload.items)) {
    return [];
  }

  const filters = currentFilters();
  const topN = Math.max(1, parseInt(filters.topN || "100", 10));
  const requirePrice = !["0", "false", "no"].includes(String(filters.hasPrice).toLowerCase());

  const scoped = dailyPayload.items.filter((item) => {
    if (item.site !== filters.site) return false;
    if (item.board_type !== filters.boardType) return false;
    if (filters.categoryKey && item.category_key !== filters.categoryKey) return false;

    const rank = parseNumber(item.rank);
    if (rank !== null && rank > topN) return false;

    if (requirePrice) {
      const priceText = String(item.price_text || "").trim();
      if (!priceText) return false;
    }

    if (filters.keyword) {
      const title = String(item.title || "").toLowerCase();
      const asin = String(item.asin || "").toLowerCase();
      if (!title.includes(filters.keyword) && !asin.includes(filters.keyword)) return false;
    }

    return true;
  });

  return sortFilteredItems(scoped, filters.sortBy, filters.sortOrder);
}

function renderTable(items) {
  const tbody = document.querySelector("#ranksTable tbody");
  tbody.innerHTML = "";

  items.forEach((item) => {
    const tr = document.createElement("tr");
    const detailUrl = item.detail_url || "";
    const detailCell = detailUrl ? `<a href="${detailUrl}" target="_blank" rel="noreferrer">打开</a>` : "";
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
}

function renderSummary() {
  const date = document.getElementById("snapshot_date").value || "-";
  setText("querySummary", `日期: ${date} | 结果数: ${filteredItems.length}`);
}

function escapeCsv(value) {
  const text = String(value ?? "");
  if (text.includes('"') || text.includes(",") || text.includes("\n")) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function buildCsv(items) {
  const headers = [
    "snapshot_date",
    "site",
    "board_type",
    "category_name",
    "rank",
    "asin",
    "title",
    "brand",
    "price_text",
    "rating",
    "review_count",
    "detail_url",
  ];
  const lines = [headers.join(",")];
  items.forEach((item) => {
    lines.push(headers.map((key) => escapeCsv(item[key])).join(","));
  });
  return lines.join("\n");
}

function downloadCsv() {
  if (!filteredItems.length) {
    window.alert("当前筛选结果为空，无法导出。");
    return;
  }

  const date = document.getElementById("snapshot_date").value || "unknown";
  const csv = buildCsv(filteredItems);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ranks-${date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function applyFilters() {
  filteredItems = filterItems();
  renderTable(filteredItems);
  renderSummary();
}

async function loadDailyPayload(date) {
  if (!date) {
    dailyPayload = null;
    filteredItems = [];
    renderTable([]);
    renderSummary();
    return;
  }

  const path = `${DAILY_PATH_PREFIX}${encodeURIComponent(date)}.json`;
  dailyPayload = await loadJson(path);
  rebuildCategoryOptions();
  applyFilters();
}

async function initialize() {
  try {
    manifest = await loadJson(MANIFEST_PATH);
  } catch (error) {
    manifest = {
      status: "empty",
      message: error instanceof Error ? error.message : String(error),
      available_dates: [],
      default_filters: {},
      last_success_date: null,
      last_attempt_at: null,
    };
  }

  renderStatus();
  applyDefaultFilters();
  populateDateOptions();

  document.getElementById("snapshot_date").addEventListener("change", () => {
    loadDailyPayload(document.getElementById("snapshot_date").value).catch((error) => {
      window.alert(error instanceof Error ? error.message : String(error));
    });
  });
  document.getElementById("site").addEventListener("change", () => {
    rebuildCategoryOptions();
    applyFilters();
  });
  document.getElementById("board_type").addEventListener("change", () => {
    rebuildCategoryOptions();
    applyFilters();
  });
  document.getElementById("category_key").addEventListener("change", applyFilters);
  document.getElementById("has_price").addEventListener("change", applyFilters);
  document.getElementById("top_n").addEventListener("change", applyFilters);
  document.getElementById("sort_by").addEventListener("change", applyFilters);
  document.getElementById("sort_order").addEventListener("change", applyFilters);
  document.getElementById("searchRanks").addEventListener("click", applyFilters);
  document.getElementById("downloadCsv").addEventListener("click", downloadCsv);

  await loadDailyPayload(document.getElementById("snapshot_date").value);
}

initialize().catch((error) => {
  setText("dataStatus", "error");
  const message = error instanceof Error ? error.message : String(error);
  window.alert(message);
});

