const MANIFEST_PATH = "./data/manifest.json";
const DAILY_PATH_PREFIX = "./data/daily/";

const STATUS_CLASSES = [
  "status-success",
  "status-stale",
  "status-loading",
  "status-empty",
  "status-error",
];
const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const ONE_YEAR_DAYS = 365;

let manifest = null;
let dailyPayload = null;
let filteredItems = [];
const dailyCache = new Map();
let trendRequestId = 0;

const compareState = {
  enabled: false,
  prevDate: null,
  prevPayload: null,
  diffMap: new Map(),
  stats: { up: 0, down: 0, same: 0, fresh: 0 },
};

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? "";
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  window.alert(message);
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

function parseSnapshotDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]) - 1;
  const day = Number(match[3]);
  const stamp = Date.UTC(year, month, day);
  const check = new Date(stamp);
  if (
    check.getUTCFullYear() !== year ||
    check.getUTCMonth() !== month ||
    check.getUTCDate() !== day
  ) {
    return null;
  }
  return stamp;
}

function getManifestDates() {
  if (!manifest || !Array.isArray(manifest.available_dates)) return [];
  return manifest.available_dates.filter((d) => typeof d === "string" && d.trim());
}

function normalizeSourceLabel(source) {
  const raw = String(source || "").trim().toLowerCase();
  if (raw === "auto") return "自动任务";
  if (raw === "manual") return "手动触发";
  return "未知";
}

function updateStatusBanner(status, message) {
  const banner = document.getElementById("statusBanner");
  if (!banner) return;

  STATUS_CLASSES.forEach((cls) => banner.classList.remove(cls));

  const normalized = ["success", "stale", "loading", "empty"].includes(status) ? status : "error";
  banner.classList.add(`status-${normalized}`);

  let text = "数据加载中";
  if (normalized === "success") text = "数据正常，可筛选和导出";
  if (normalized === "stale") text = "抓取失败，已回退到最近成功数据";
  if (normalized === "empty") text = "暂无可用数据";
  if (normalized === "error") text = "数据加载失败";

  if (message) {
    text = `${text}（${message}）`;
  }
  banner.textContent = text;
}

function renderStatus() {
  const status = manifest?.status || "empty";
  const message = manifest?.message || "";
  const statusText = message ? `${status} (${message})` : status;

  setText("dataStatus", statusText);
  setText("dataSource", normalizeSourceLabel(manifest?.source));
  setText("lastSuccessDate", manifest?.last_success_date || "-");
  setText("lastAttemptAt", manifest?.last_attempt_at || "-");
  updateStatusBanner(status, message);
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

function renderRecentDateButtons() {
  const container = document.getElementById("recentDateButtons");
  if (!container) return;

  const dates = getManifestDates().slice(0, 7);
  const selectedDate = document.getElementById("snapshot_date").value;
  container.innerHTML = "";

  if (!dates.length) {
    return;
  }

  dates.forEach((date) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `date-chip${date === selectedDate ? " active" : ""}`;
    button.textContent = date;
    button.addEventListener("click", () => {
      document.getElementById("snapshot_date").value = date;
      handleDateChange(date).catch(showError);
    });
    container.appendChild(button);
  });
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

function sortFilteredItems(items, sortBy, sortOrder) {
  const direction = sortOrder === "desc" ? -1 : 1;
  const withIndex = items.map((item, index) => ({ item, index }));

  withIndex.sort((left, right) => {
    const a = parseNumber(left.item[sortBy]);
    const b = parseNumber(right.item[sortBy]);

    if (a === null && b === null) return left.index - right.index;
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

function filterItemsFromPayload(payload, filters) {
  if (!payload || !Array.isArray(payload.items)) return [];

  const topN = Math.max(1, parseInt(filters.topN || "100", 10));
  const requirePrice = !["0", "false", "no"].includes(String(filters.hasPrice).toLowerCase());

  const scoped = payload.items.filter((item) => {
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

function compareKey(item) {
  return `${item.site}||${item.board_type}||${item.category_key}||${item.asin}`;
}

function openTrendModal() {
  const modal = document.getElementById("trendModal");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
}

function closeTrendModal() {
  const modal = document.getElementById("trendModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

function renderTrendTable(points) {
  const tbody = document.querySelector("#trendTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";
  points.forEach((point) => {
    const tr = document.createElement("tr");
    const values = [
      point.snapshot_date || "",
      point.rank ?? "-",
      point.sales_day ?? "-",
      point.sales_month ?? "-",
      point.sales_year ?? "-",
    ];
    values.forEach((value) => {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function renderTrendChart(points) {
  const chart = document.getElementById("trendChart");
  if (!chart) return;

  chart.innerHTML = "";
  const usablePoints = points.filter((point) => point.sales_year !== null);
  if (!usablePoints.length) {
    const empty = document.createElement("p");
    empty.className = "trend-empty";
    empty.textContent = "近一年暂无销量估算数据。";
    chart.appendChild(empty);
    return;
  }

  const maxValue = Math.max(...usablePoints.map((point) => point.sales_year || 0), 1);
  usablePoints.forEach((point) => {
    const row = document.createElement("div");
    row.className = "trend-bar-row";

    const date = document.createElement("span");
    date.className = "trend-bar-date";
    date.textContent = point.snapshot_date;

    const track = document.createElement("div");
    track.className = "trend-bar-track";

    const fill = document.createElement("div");
    fill.className = "trend-bar-fill";
    const widthPercent = Math.max(4, Math.round(((point.sales_year || 0) / maxValue) * 100));
    fill.style.width = `${widthPercent}%`;
    track.appendChild(fill);

    const value = document.createElement("span");
    value.className = "trend-bar-value";
    value.textContent = String(point.sales_year ?? "-");

    row.appendChild(date);
    row.appendChild(track);
    row.appendChild(value);
    chart.appendChild(row);
  });
}

async function collectSalesTrendWithinOneYear(item) {
  const anchorDate = item.snapshot_date || document.getElementById("snapshot_date").value;
  const anchorStamp = parseSnapshotDate(anchorDate);
  if (anchorStamp === null) return [];

  const windowStartStamp = anchorStamp - ONE_YEAR_DAYS * ONE_DAY_MS;
  const candidateDates = new Set(getManifestDates());
  if (anchorDate) candidateDates.add(anchorDate);

  const dates = [...candidateDates]
    .filter((date) => {
      const stamp = parseSnapshotDate(date);
      return stamp !== null && stamp >= windowStartStamp && stamp <= anchorStamp;
    })
    .sort((left, right) => {
      const leftStamp = parseSnapshotDate(left) || 0;
      const rightStamp = parseSnapshotDate(right) || 0;
      return leftStamp - rightStamp;
    });

  const key = compareKey(item);
  const series = [];

  for (const date of dates) {
    try {
      const payload = await getDailyPayload(date);
      const found = (payload.items || []).find((entry) => compareKey(entry) === key);
      if (!found) continue;

      series.push({
        snapshot_date: date,
        rank: parseNumber(found.rank),
        sales_day: parseNumber(found.sales_day),
        sales_month: parseNumber(found.sales_month),
        sales_year: parseNumber(found.sales_year),
      });
    } catch (_error) {
      // Ignore partial daily payload failures so trend still works with remaining dates.
    }
  }

  return series;
}

async function showSalesTrendForItem(item) {
  trendRequestId += 1;
  const currentRequestId = trendRequestId;

  const asin = item.asin || "-";
  const title = item.title || "未知商品";
  setText("trendTitle", `近一年销量趋势：${title} (${asin})`);
  setText("trendInfo", "正在加载近一年走势...");
  renderTrendChart([]);
  renderTrendTable([]);
  openTrendModal();

  const points = await collectSalesTrendWithinOneYear(item);
  if (currentRequestId !== trendRequestId) return;

  if (!points.length) {
    setText("trendInfo", "近一年内未找到该商品的采样记录。");
    return;
  }

  renderTrendChart(points);
  renderTrendTable(points);

  const firstDate = points[0].snapshot_date;
  const lastDate = points[points.length - 1].snapshot_date;
  setText("trendInfo", `样本窗口：${firstDate} ~ ${lastDate}，共 ${points.length} 个采样日。`);
}

function buildCompareData(todayItems, prevPayload, filters) {
  const prevItems = filterItemsFromPayload(prevPayload, filters);
  const prevRankMap = new Map();
  prevItems.forEach((item) => {
    prevRankMap.set(compareKey(item), parseNumber(item.rank));
  });

  const diffMap = new Map();
  const stats = { up: 0, down: 0, same: 0, fresh: 0 };

  todayItems.forEach((item) => {
    const key = compareKey(item);
    const todayRank = parseNumber(item.rank);
    const prevRank = prevRankMap.get(key);

    if (prevRank === undefined || prevRank === null) {
      diffMap.set(key, "新上榜");
      stats.fresh += 1;
      return;
    }
    if (todayRank === null) {
      diffMap.set(key, "-");
      return;
    }

    const delta = prevRank - todayRank;
    if (delta > 0) {
      diffMap.set(key, `↑${delta}`);
      stats.up += 1;
      return;
    }
    if (delta < 0) {
      diffMap.set(key, `↓${Math.abs(delta)}`);
      stats.down += 1;
      return;
    }
    diffMap.set(key, "持平");
    stats.same += 1;
  });

  return { diffMap, stats };
}

function renderTable(items) {
  const tbody = document.querySelector("#ranksTable tbody");
  tbody.innerHTML = "";

  items.forEach((item) => {
    const tr = document.createElement("tr");
    const detailUrl = item.detail_url || "";
    const detailCell = detailUrl ? `<a href="${detailUrl}" target="_blank" rel="noreferrer">打开</a>` : "";
    const change = compareState.enabled ? compareState.diffMap.get(compareKey(item)) || "-" : "-";

    tr.innerHTML = `
      <td>${item.snapshot_date || ""}</td>
      <td>${item.site || ""}</td>
      <td>${item.board_type || ""}</td>
      <td>${item.category_name || item.category_key || ""}</td>
      <td>${item.rank ?? ""}</td>
      <td>${change}</td>
      <td>${item.sales_day ?? ""}</td>
      <td>${item.sales_month ?? ""}</td>
      <td>${item.sales_year ?? ""}</td>
      <td>${item.asin || ""}</td>
      <td>${item.title || ""}</td>
      <td>${item.brand || ""}</td>
      <td>${item.price_text || ""}</td>
      <td>${item.rating ?? ""}</td>
      <td>${item.review_count ?? ""}</td>
      <td>${detailCell}</td>
      <td></td>
    `;
    const trendButton = document.createElement("button");
    trendButton.type = "button";
    trendButton.className = "trend-btn";
    trendButton.textContent = "看近1年趋势";
    trendButton.addEventListener("click", () => {
      showSalesTrendForItem(item).catch(showError);
    });

    const trendCell = tr.lastElementChild;
    if (trendCell) {
      trendCell.appendChild(trendButton);
    }
    tbody.appendChild(tr);
  });
}

function renderSummary() {
  const date = document.getElementById("snapshot_date").value || "-";
  let summary = `日期: ${date} | 结果数: ${filteredItems.length}`;

  if (compareState.enabled && compareState.prevDate) {
    const stats = compareState.stats;
    summary += ` | 对比 ${compareState.prevDate}: 上升 ${stats.up} 下降 ${stats.down} 新上榜 ${stats.fresh} 持平 ${stats.same}`;
  }

  setText("querySummary", summary);
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
    "day_change",
    "sales_day",
    "sales_month",
    "sales_year",
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
    const record = {
      ...item,
      day_change: compareState.enabled ? compareState.diffMap.get(compareKey(item)) || "" : "",
    };
    lines.push(headers.map((key) => escapeCsv(record[key])).join(","));
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

function clearCompareState() {
  compareState.enabled = false;
  compareState.prevDate = null;
  compareState.prevPayload = null;
  compareState.diffMap = new Map();
  compareState.stats = { up: 0, down: 0, same: 0, fresh: 0 };
}

function applyFilters() {
  const filters = currentFilters();
  filteredItems = filterItemsFromPayload(dailyPayload, filters);

  if (compareState.enabled && compareState.prevPayload) {
    const compareData = buildCompareData(filteredItems, compareState.prevPayload, filters);
    compareState.diffMap = compareData.diffMap;
    compareState.stats = compareData.stats;
  } else {
    compareState.diffMap = new Map();
    compareState.stats = { up: 0, down: 0, same: 0, fresh: 0 };
  }

  renderTable(filteredItems);
  renderSummary();
}

async function getDailyPayload(date) {
  if (dailyCache.has(date)) {
    return dailyCache.get(date);
  }
  const path = `${DAILY_PATH_PREFIX}${encodeURIComponent(date)}.json`;
  const payload = await loadJson(path);
  dailyCache.set(date, payload);
  return payload;
}

async function loadDailyPayload(date) {
  if (!date) {
    dailyPayload = null;
    filteredItems = [];
    clearCompareState();
    renderTable([]);
    renderSummary();
    return;
  }

  dailyPayload = await getDailyPayload(date);
  clearCompareState();
  closeTrendModal();
  rebuildCategoryOptions();
  applyFilters();
}

async function handleDateChange(date) {
  await loadDailyPayload(date);
  renderRecentDateButtons();
}

async function compareWithPreviousDay() {
  const currentDate = document.getElementById("snapshot_date").value;
  const dates = getManifestDates();
  const currentIndex = dates.indexOf(currentDate);
  if (currentIndex < 0 || currentIndex === dates.length - 1) {
    window.alert("没有可对比的昨日数据。");
    return;
  }

  const prevDate = dates[currentIndex + 1];
  const prevPayload = await getDailyPayload(prevDate);
  compareState.enabled = true;
  compareState.prevDate = prevDate;
  compareState.prevPayload = prevPayload;
  applyFilters();
}

function clearCompare() {
  clearCompareState();
  applyFilters();
}

async function initialize() {
  try {
    manifest = await loadJson(MANIFEST_PATH);
  } catch (error) {
    manifest = {
      status: "empty",
      source: "unknown",
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
  renderRecentDateButtons();

  document.getElementById("snapshot_date").addEventListener("change", () => {
    handleDateChange(document.getElementById("snapshot_date").value).catch(showError);
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
  document.getElementById("compareYesterday").addEventListener("click", () => {
    compareWithPreviousDay().catch(showError);
  });
  document.getElementById("clearCompare").addEventListener("click", clearCompare);
  document.getElementById("trendClose").addEventListener("click", closeTrendModal);
  document.getElementById("trendModal").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) {
      closeTrendModal();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeTrendModal();
    }
  });

  await handleDateChange(document.getElementById("snapshot_date").value);
}

initialize().catch((error) => {
  setText("dataStatus", "error");
  updateStatusBanner("error", "");
  showError(error);
});
