const MANIFEST_PATH = "./data/manifest.json";
const DAILY_PATH_PREFIX = "./data/daily/";
const INSIGHTS_PATH_PREFIX = "./data/insights/";

const STATUS_CLASSES = [
  "status-success",
  "status-stale",
  "status-loading",
  "status-empty",
  "status-error",
];
const ONE_DAY_MS = 24 * 60 * 60 * 1000;
const ONE_YEAR_DAYS = 365;
const KEYWORD_STOPWORDS = new Set([
  "with",
  "for",
  "and",
  "the",
  "from",
  "pack",
  "set",
  "inch",
  "inches",
  "piece",
  "pieces",
  "amazon",
  "best",
  "seller",
  "sellers",
  "home",
  "kitchen",
  "new",
  "release",
  "releases",
]);

let manifest = null;
let dailyPayload = null;
let filteredItems = [];
let competitorMonthlyRows = [];
let styleTrendRows = [];
const dailyCache = new Map();
const officialInsightsCache = new Map();
let trendRequestId = 0;
let insightRequestId = 0;

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

async function loadOptionalJson(path) {
  const resp = await fetch(path, { cache: "no-store" });
  if (resp.status === 404) {
    return null;
  }
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

function monthKeyFromDate(date) {
  const match = String(date || "").match(/^(\d{4})-(\d{2})-\d{2}$/);
  if (!match) return "";
  return `${match[1]}-${match[2]}`;
}

function sortMonthAsc(left, right) {
  return String(left || "").localeCompare(String(right || ""));
}

function formatCompactNumber(value) {
  const parsed = parseNumber(value);
  if (parsed === null) return "-";
  return parsed.toLocaleString("en-US");
}

function avg(values) {
  if (!values.length) return null;
  return values.reduce((acc, item) => acc + item, 0) / values.length;
}

function extractKeywords(title) {
  const text = String(title || "").toLowerCase();
  const english = text.match(/[a-z0-9][a-z0-9-]{2,}/g) || [];
  const chinese = text.match(/[\u4e00-\u9fff]{2,}/g) || [];
  const combined = [...english, ...chinese];
  const unique = new Set();

  combined.forEach((rawToken) => {
    const token = rawToken.replace(/^-+|-+$/g, "");
    if (!token || token.length < 2) return;
    if (/^\d+$/.test(token)) return;
    if (KEYWORD_STOPWORDS.has(token)) return;
    unique.add(token);
  });

  return [...unique];
}

function renderInsightList(containerId, lines) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(lines)) {
    return;
  }

  if (!lines.length) {
    container.textContent = "暂无足够数据。";
    return;
  }

  const ul = document.createElement("ul");
  ul.className = "insight-list";
  lines.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    ul.appendChild(li);
  });
  container.appendChild(ul);
}

function renderKeywordMetrics(containerId, rows, metricLabel) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(rows)) {
    return;
  }

  if (!rows.length) {
    container.textContent = "样本不足，暂无关键词结果。";
    return;
  }

  const table = document.createElement("table");
  table.className = "mini-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr><th>关键词</th><th>${metricLabel}</th><th>样本数</th></tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.keyword}</td><td>${row.metric}</td><td>${row.itemCount}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function buildKeywordStats(items) {
  const stats = new Map();
  items.forEach((item) => {
    const keywords = extractKeywords(item.title);
    if (!keywords.length) return;

    const traffic = parseNumber(item.sales_month) ?? parseNumber(item.sales_day) ?? 1;
    const rating = parseNumber(item.rating);
    const reviewCount = parseNumber(item.review_count) ?? 0;

    keywords.forEach((keyword) => {
      const prev = stats.get(keyword) || {
        keyword,
        traffic: 0,
        itemCount: 0,
        ratingSum: 0,
        ratingCount: 0,
        reviewSum: 0,
      };
      prev.traffic += traffic;
      prev.itemCount += 1;
      prev.reviewSum += reviewCount;
      if (rating !== null) {
        prev.ratingSum += rating;
        prev.ratingCount += 1;
      }
      stats.set(keyword, prev);
    });
  });
  return [...stats.values()];
}

function buildReviewInsightLines(items) {
  if (!items.length) return ["当前筛选结果为空，无法分析口碑。"];

  const rated = items.map((item) => parseNumber(item.rating)).filter((value) => value !== null);
  if (!rated.length) return ["当前样本缺少评分信息。"];

  const highRated = items.filter((item) => {
    const rating = parseNumber(item.rating);
    return rating !== null && rating >= 4.4;
  });
  const lowRated = items.filter((item) => {
    const rating = parseNumber(item.rating);
    return rating !== null && rating < 4.1;
  });

  const avgRating = avg(rated) || 0;
  const highRatio = ((highRated.length / rated.length) * 100).toFixed(1);
  const lowRatio = ((lowRated.length / rated.length) * 100).toFixed(1);

  const positiveKeywords = buildKeywordStats(highRated)
    .sort((a, b) => b.traffic - a.traffic)
    .slice(0, 5)
    .map((item) => item.keyword);
  const painKeywords = buildKeywordStats(lowRated)
    .sort((a, b) => b.reviewSum - a.reviewSum)
    .slice(0, 5)
    .map((item) => item.keyword);

  return [
    `样本商品 ${items.length}，有评分商品 ${rated.length}，平均评分 ${avgRating.toFixed(2)}。`,
    `高口碑占比(>=4.4): ${highRatio}%；风险占比(<4.1): ${lowRatio}%。`,
    `好评优势关键词: ${positiveKeywords.length ? positiveKeywords.join("、") : "暂无明显集中词"}`,
    `差评潜在痛点词: ${painKeywords.length ? painKeywords.join("、") : "低评分样本不足，暂无法归纳"}`,
  ];
}

function buildKeywordInsightRows(items) {
  const stats = buildKeywordStats(items);
  if (!stats.length) {
    return { trafficRows: [], conversionRows: [] };
  }

  const scored = stats.map((item) => {
    const avgRating = item.ratingCount ? item.ratingSum / item.ratingCount : 4;
    const conversionScore = (item.traffic / Math.max(1, item.itemCount)) * avgRating * Math.log10(item.reviewSum + 10);
    return {
      ...item,
      conversionScore,
    };
  });

  const filtered = scored.filter((item) => item.itemCount >= 2);
  const candidates = filtered.length >= 5 ? filtered : scored;

  const trafficRows = [...candidates]
    .sort((a, b) => b.traffic - a.traffic)
    .slice(0, 8)
    .map((item) => ({
      keyword: item.keyword,
      metric: formatCompactNumber(Math.round(item.traffic)),
      itemCount: item.itemCount,
    }));

  const conversionRows = [...candidates]
    .sort((a, b) => b.conversionScore - a.conversionScore)
    .slice(0, 8)
    .map((item) => ({
      keyword: item.keyword,
      metric: item.conversionScore.toFixed(1),
      itemCount: item.itemCount,
    }));

  return { trafficRows, conversionRows };
}

function renderMonthlySalesInsights(rows, asin) {
  const container = document.getElementById("monthlySalesInsights");
  if (!container) return;
  container.innerHTML = "";

  if (!Array.isArray(rows)) {
    return;
  }

  if (!asin) {
    container.textContent = "当前没有可分析的 ASIN。";
    return;
  }
  if (!rows.length) {
    container.textContent = "近一年暂无该商品的月度样本。";
    return;
  }

  const title = document.createElement("p");
  title.className = "muted";
  title.textContent = `ASIN: ${asin}`;
  container.appendChild(title);

  const table = document.createElement("table");
  table.className = "mini-table";
  table.innerHTML = "<thead><tr><th>月份</th><th>月销量(估)</th><th>采样日</th><th>月均排名</th></tr></thead>";

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.month}</td>
      <td>${formatCompactNumber(row.monthSales)}</td>
      <td>${row.sampleDays}</td>
      <td>${row.avgRank === null ? "-" : row.avgRank.toFixed(1)}</td>
    `;
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  container.appendChild(table);
}

function selectTrackedAsinsFromItems(items, limit = 10) {
  const seen = new Set();
  const sorted = [...(Array.isArray(items) ? items : [])].sort((left, right) => {
    const rankA = parseNumber(left.rank);
    const rankB = parseNumber(right.rank);
    if (rankA !== null && rankB !== null && rankA !== rankB) return rankA - rankB;
    if (rankA !== null && rankB === null) return -1;
    if (rankA === null && rankB !== null) return 1;

    const salesA = parseNumber(left.sales_month) ?? 0;
    const salesB = parseNumber(right.sales_month) ?? 0;
    if (salesA !== salesB) return salesB - salesA;
    return String(left.asin || "").localeCompare(String(right.asin || ""));
  });

  const picked = [];
  sorted.forEach((item) => {
    const asin = String(item.asin || "").trim();
    if (!asin || seen.has(asin)) return;
    seen.add(asin);
    picked.push(asin);
  });
  return picked.slice(0, Math.max(1, limit));
}

function buildCompetitorMonthlySalesRows(historyRows, items, maxAsins = 10) {
  const trackedAsins = selectTrackedAsinsFromItems(items, maxAsins);
  if (!trackedAsins.length) return [];
  const trackedSet = new Set(trackedAsins);

  const asinTitleMap = new Map();
  items.forEach((item) => {
    const asin = String(item.asin || "").trim();
    if (!asin || !trackedSet.has(asin)) return;
    if (!asinTitleMap.has(asin)) {
      asinTitleMap.set(asin, String(item.title || "").trim());
    }
  });

  const monthly = new Map();
  historyRows.forEach((entry) => {
    const month = monthKeyFromDate(entry.date);
    if (!month) return;

    entry.items.forEach((item) => {
      const asin = String(item.asin || "").trim();
      if (!trackedSet.has(asin)) return;

      const key = `${month}||${asin}`;
      const record = monthly.get(key) || {
        month,
        asin,
        title: asinTitleMap.get(asin) || "",
        monthSales: 0,
        sampleDays: 0,
        rankSum: 0,
        rankDays: 0,
      };
      record.monthSales += parseNumber(item.sales_day) ?? 0;
      record.sampleDays += 1;
      const rank = parseNumber(item.rank);
      if (rank !== null) {
        record.rankSum += rank;
        record.rankDays += 1;
      }
      monthly.set(key, record);
    });
  });

  return [...monthly.values()]
    .map((item) => ({
      month: item.month,
      asin: item.asin,
      title: item.title,
      monthSales: Math.round(item.monthSales),
      sampleDays: item.sampleDays,
      avgRank: item.rankDays ? item.rankSum / item.rankDays : null,
    }))
    .sort((left, right) => {
      const monthCompare = sortMonthAsc(right.month, left.month);
      if (monthCompare !== 0) return monthCompare;
      const salesDiff = (parseNumber(right.monthSales) || 0) - (parseNumber(left.monthSales) || 0);
      if (salesDiff !== 0) return salesDiff;
      return String(left.asin || "").localeCompare(String(right.asin || ""));
    });
}

function buildCompetitorMonthlySalesRowsFromOfficial(officialPayload, items, maxAsins = 10) {
  const rows = Array.isArray(officialPayload?.monthly_sales) ? officialPayload.monthly_sales : [];
  if (!rows.length) return [];

  const trackedAsins = selectTrackedAsinsFromItems(items, maxAsins);
  const trackedSet = trackedAsins.length ? new Set(trackedAsins) : null;

  const asinTitleMap = new Map();
  items.forEach((item) => {
    const asin = String(item.asin || "").trim();
    if (!asin) return;
    if (trackedSet && !trackedSet.has(asin)) return;
    if (!asinTitleMap.has(asin)) {
      asinTitleMap.set(asin, String(item.title || "").trim());
    }
  });

  return rows
    .filter((row) => {
      const asin = String(row.asin || "").trim();
      if (!asin) return false;
      if (trackedSet && !trackedSet.has(asin)) return false;
      return true;
    })
    .map((row) => ({
      month: String(row.month || "").trim(),
      asin: String(row.asin || "").trim(),
      title: asinTitleMap.get(String(row.asin || "").trim()) || "",
      monthSales: parseNumber(row.units) || 0,
      sampleDays: parseNumber(row.sample_days) || 0,
      avgRank: parseNumber(row.avg_rank),
    }))
    .filter((row) => row.month && row.asin)
    .sort((left, right) => {
      const monthCompare = sortMonthAsc(right.month, left.month);
      if (monthCompare !== 0) return monthCompare;
      const salesDiff = (parseNumber(right.monthSales) || 0) - (parseNumber(left.monthSales) || 0);
      if (salesDiff !== 0) return salesDiff;
      return String(left.asin || "").localeCompare(String(right.asin || ""));
    });
}

function renderMonthlySalesCompetitorTable(rows, sourceLabel) {
  const container = document.getElementById("monthlySalesCompetitor");
  if (!container) return;
  container.innerHTML = "";

  competitorMonthlyRows = Array.isArray(rows) ? rows : [];

  const exportButton = document.getElementById("downloadMonthlySalesCsv");
  if (exportButton) {
    exportButton.disabled = !competitorMonthlyRows.length;
  }

  if (!Array.isArray(rows) || !rows.length) {
    container.textContent = "近一年暂无竞品月销量明细。";
    return;
  }

  const caption = document.createElement("p");
  caption.className = "muted";
  caption.textContent = `竞品月销量明细（近12个月，${sourceLabel}）`;
  container.appendChild(caption);

  const table = document.createElement("table");
  table.className = "mini-table";
  table.innerHTML =
    "<thead><tr><th>月份</th><th>ASIN</th><th>商品名</th><th>月销量</th><th>采样日</th><th>月均排名</th></tr></thead>";

  const tbody = document.createElement("tbody");
  rows.slice(0, 160).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.month || "-"}</td>
      <td>${row.asin || "-"}</td>
      <td>${row.title || "-"}</td>
      <td>${formatCompactNumber(row.monthSales)}</td>
      <td>${row.sampleDays ?? "-"}</td>
      <td>${row.avgRank === null ? "-" : row.avgRank.toFixed(1)}</td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function buildStyleTrendRows(historyRows, topNPerMonth = 12) {
  if (!Array.isArray(historyRows) || !historyRows.length) return [];

  const monthStats = new Map();
  historyRows.forEach((entry) => {
    const month = monthKeyFromDate(entry.date);
    if (!month) return;
    const tokenMap = monthStats.get(month) || new Map();

    entry.items.forEach((item) => {
      const traffic = parseNumber(item.sales_month) ?? parseNumber(item.sales_day) ?? 1;
      extractKeywords(item.title).forEach((keyword) => {
        tokenMap.set(keyword, (tokenMap.get(keyword) || 0) + traffic);
      });
    });
    monthStats.set(month, tokenMap);
  });

  const months = [...monthStats.keys()].sort(sortMonthAsc);
  if (!months.length) return [];

  const rows = [];
  months.forEach((month, index) => {
    const current = monthStats.get(month) || new Map();
    const prev = index > 0 ? monthStats.get(months[index - 1]) || new Map() : new Map();
    [...current.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, Math.max(1, topNPerMonth))
      .forEach(([style, score]) => {
        rows.push({
          month,
          style,
          score: Math.round(score),
          delta: Math.round(score - (prev.get(style) || 0)),
        });
      });
  });

  return rows.sort((left, right) => {
    const monthCompare = sortMonthAsc(right.month, left.month);
    if (monthCompare !== 0) return monthCompare;
    const scoreDiff = (parseNumber(right.score) || 0) - (parseNumber(left.score) || 0);
    if (scoreDiff !== 0) return scoreDiff;
    return String(left.style || "").localeCompare(String(right.style || ""));
  });
}

function buildStyleTrendSummaryLines(rows, sourceLabel = "估算") {
  if (!Array.isArray(rows) || !rows.length) {
    return [`${sourceLabel}款式趋势样本不足。`];
  }

  const months = [...new Set(rows.map((row) => String(row.month || "").trim()).filter(Boolean))].sort(sortMonthAsc);
  if (!months.length) return [`${sourceLabel}款式趋势样本不足。`];

  const latestMonth = months[months.length - 1];
  const latestRows = rows
    .filter((row) => String(row.month) === latestMonth)
    .sort((a, b) => (parseNumber(b.score) || 0) - (parseNumber(a.score) || 0));
  const hotStyles = latestRows
    .slice(0, 6)
    .map((item) => `${item.style}(${Math.round(parseNumber(item.score) || 0)})`);

  if (months.length < 2) {
    return [
      `${sourceLabel}款式趋势样本月份: ${latestMonth}（当前只有单月样本）`,
      `当月热门款式: ${hotStyles.length ? hotStyles.join("、") : "暂无"}`,
    ];
  }

  const rising = latestRows
    .filter((item) => (parseNumber(item.delta) || 0) > 0)
    .sort((a, b) => (parseNumber(b.delta) || 0) - (parseNumber(a.delta) || 0))
    .slice(0, 6)
    .map((item) => `${item.style}(+${Math.round(parseNumber(item.delta) || 0)})`);

  return [
    `${sourceLabel}款式趋势样本: ${months[0]} ~ ${latestMonth}（共 ${months.length} 个月）`,
    `最新月热门款式: ${hotStyles.length ? hotStyles.join("、") : "暂无"}`,
    `相对上月上升款式: ${rising.length ? rising.join("、") : "暂无明显上升"}`,
  ];
}

function buildStyleTrendLines(historyRows) {
  const rows = buildStyleTrendRows(historyRows);
  return buildStyleTrendSummaryLines(rows, "估算");
}

function renderStyleTrendMonthlyTable(rows, sourceLabel) {
  const container = document.getElementById("styleTrendMonthlyTable");
  if (!container) return;
  container.innerHTML = "";
  styleTrendRows = Array.isArray(rows) ? rows : [];

  const exportButton = document.getElementById("downloadStyleTrendCsv");
  if (exportButton) {
    exportButton.disabled = !styleTrendRows.length;
  }

  if (!styleTrendRows.length) {
    container.textContent = "近一年暂无款式趋势明细。";
    return;
  }

  const caption = document.createElement("p");
  caption.className = "muted";
  caption.textContent = `款式趋势月度明细（${sourceLabel}）`;
  container.appendChild(caption);

  const table = document.createElement("table");
  table.className = "mini-table";
  table.innerHTML = "<thead><tr><th>月份</th><th>款式词</th><th>热度值</th><th>环比变化</th></tr></thead>";

  const tbody = document.createElement("tbody");
  styleTrendRows.slice(0, 180).forEach((row) => {
    const delta = parseNumber(row.delta) || 0;
    const deltaText = delta > 0 ? `+${Math.round(delta)}` : `${Math.round(delta)}`;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.month || "-"}</td>
      <td>${row.style || "-"}</td>
      <td>${formatCompactNumber(row.score)}</td>
      <td>${deltaText}</td>
    `;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function formatTopicLine(topics) {
  if (!Array.isArray(topics) || !topics.length) return "暂无";
  return topics
    .slice(0, 5)
    .map((topic) => {
      const name = String(topic.topic || "").trim() || "未命名";
      const mentions = parseNumber(topic.mentions);
      if (mentions === null) return name;
      return `${name}(${mentions})`;
    })
    .join("、");
}

function buildReviewInsightLinesFromOfficial(officialPayload, asin) {
  const topics = Array.isArray(officialPayload?.review_topics) ? officialPayload.review_topics : [];
  if (!topics.length) return [];

  const selected =
    topics.find((item) => String(item.asin || "").trim() === String(asin || "").trim()) || topics[0];
  if (!selected) return [];
  const source = String(officialPayload?.source || "").trim();
  const sampleReviews = parseNumber(selected.sample_reviews);
  const sourceTags = parseInsightsSourceTags(source);
  const sourceLabel =
    sourceTags.has("public_reviews")
      ? "公开评论抓取"
      : "官方评论主题";
  const sampleLine =
    sampleReviews !== null && sampleReviews > 0 ? `评论样本: ${sampleReviews} 条（${sourceLabel}）` : "";

  return [
    sampleLine,
    `ASIN ${selected.asin || asin || "-"} 的${sourceLabel}洞察`,
    `好评主题: ${formatTopicLine(selected.positive_topics)}`,
    `差评痛点: ${formatTopicLine(selected.negative_topics)}`,
  ].filter(Boolean);
}

function parseInsightsSourceTags(source) {
  const value = String(source || "").trim();
  if (!value) return new Set();
  if (value === "mixed_reports_public_reviews") {
    return new Set(["official_reports", "public_reviews"]);
  }
  if (value.includes("+")) {
    return new Set(
      value
        .split("+")
        .map((part) => part.trim())
        .filter(Boolean),
    );
  }
  return new Set([value]);
}

function formatInsightsSourceLabel(source) {
  const tags = parseInsightsSourceTags(source);
  if (!tags.size) return "估算模式";

  const labels = [];
  if (tags.has("official_reports")) labels.push("官方报表");
  if (tags.has("public_reviews")) labels.push("公开评论抓取");
  if (tags.has("public_search_keywords")) labels.push("公开搜索关键词");

  if (labels.length) return labels.join(" + ");
  return String(source || "").trim();
}

function isPublicSearchKeywordRows(payload) {
  const rows = Array.isArray(payload?.keywords) ? payload.keywords : [];
  if (!rows.length) return false;
  return rows.some((row) => {
    if (!row || typeof row !== "object") return false;
    return (
      Object.prototype.hasOwnProperty.call(row, "top_asin_overlap") ||
      Object.prototype.hasOwnProperty.call(row, "top_asin_count") ||
      Object.prototype.hasOwnProperty.call(row, "sponsored_count")
    );
  });
}

function buildKeywordInsightRowsFromOfficial(officialPayload) {
  const keywords = Array.isArray(officialPayload?.keywords) ? officialPayload.keywords : [];
  if (!keywords.length) {
    return { trafficRows: [], conversionRows: [] };
  }

  const trafficRows = [...keywords]
    .sort((a, b) => (parseNumber(b.impressions) || 0) - (parseNumber(a.impressions) || 0))
    .slice(0, 10)
    .map((item) => ({
      keyword: item.keyword || "-",
      metric: formatCompactNumber(parseNumber(item.impressions) || 0),
      itemCount: parseNumber(item.clicks) || 0,
    }));

  const conversionRows = [...keywords]
    .map((item) => {
      const explicitCvr = parseNumber(item.cvr);
      if (explicitCvr !== null) {
        return { ...item, cvrValue: explicitCvr };
      }
      const purchases = parseNumber(item.purchases) || 0;
      const clicks = parseNumber(item.clicks) || 0;
      return { ...item, cvrValue: clicks > 0 ? purchases / clicks : 0 };
    })
    .sort((a, b) => b.cvrValue - a.cvrValue)
    .slice(0, 10)
    .map((item) => ({
      keyword: item.keyword || "-",
      metric: `${(item.cvrValue * 100).toFixed(1)}%`,
      itemCount: parseNumber(item.purchases) || 0,
    }));

  return { trafficRows, conversionRows };
}

function buildMonthlySalesRowsFromOfficial(officialPayload, asin) {
  const rows = Array.isArray(officialPayload?.monthly_sales) ? officialPayload.monthly_sales : [];
  if (!rows.length) return [];

  return rows
    .filter((row) => !asin || String(row.asin || "").trim() === String(asin || "").trim())
    .map((row) => ({
      month: row.month || "",
      monthSales: parseNumber(row.units) || 0,
      sampleDays: parseNumber(row.sample_days) || 0,
      avgRank: parseNumber(row.avg_rank),
    }))
    .filter((row) => row.month)
    .sort((left, right) => sortMonthAsc(left.month, right.month));
}

function buildStyleTrendRowsFromOfficial(officialPayload, topNPerMonth = 12) {
  const rows = Array.isArray(officialPayload?.style_trends) ? officialPayload.style_trends : [];
  if (!rows.length) return [];

  const grouped = new Map();
  rows.forEach((row) => {
    const month = String(row.month || "").trim();
    const style = String(row.style || "").trim();
    if (!month || !style) return;
    const score = parseNumber(row.score) || 0;
    const monthMap = grouped.get(month) || new Map();
    monthMap.set(style, (monthMap.get(style) || 0) + score);
    grouped.set(month, monthMap);
  });

  const months = [...grouped.keys()].sort(sortMonthAsc);
  if (!months.length) return [];

  const trendRows = [];
  months.forEach((month, index) => {
    const current = grouped.get(month) || new Map();
    const prev = index > 0 ? grouped.get(months[index - 1]) || new Map() : new Map();
    [...current.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, Math.max(1, topNPerMonth))
      .forEach(([style, score]) => {
        trendRows.push({
          month,
          style,
          score: Math.round(score),
          delta: Math.round(score - (prev.get(style) || 0)),
        });
      });
  });

  return trendRows.sort((left, right) => {
    const monthCompare = sortMonthAsc(right.month, left.month);
    if (monthCompare !== 0) return monthCompare;
    const scoreDiff = (parseNumber(right.score) || 0) - (parseNumber(left.score) || 0);
    if (scoreDiff !== 0) return scoreDiff;
    return String(left.style || "").localeCompare(String(right.style || ""));
  });
}

function buildStyleTrendLinesFromOfficial(officialPayload) {
  const rows = buildStyleTrendRowsFromOfficial(officialPayload);
  return buildStyleTrendSummaryLines(rows, "官方");
}

function populateAnalysisAsinOptions() {
  const select = document.getElementById("analysisAsin");
  if (!select) return;

  const previous = select.value;
  const unique = [];
  const seen = new Set();
  filteredItems.forEach((item) => {
    const asin = String(item.asin || "").trim();
    if (!asin || seen.has(asin)) return;
    seen.add(asin);
    unique.push(item);
  });

  select.innerHTML = '<option value="">自动选择当前Top1</option>';
  unique.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.asin;
    const title = String(item.title || "").slice(0, 42);
    option.textContent = `${item.asin} | #${item.rank ?? "-"} | ${title}`;
    select.appendChild(option);
  });

  if (previous && [...select.options].some((opt) => opt.value === previous)) {
    select.value = previous;
  }
}

function buildMonthlySalesRows(historyRows, asin) {
  if (!asin) return [];
  const monthly = new Map();

  historyRows.forEach((entry) => {
    const month = monthKeyFromDate(entry.date);
    if (!month) return;

    let daySales = 0;
    const ranks = [];
    entry.items.forEach((item) => {
      if (item.asin !== asin) return;
      daySales += parseNumber(item.sales_day) ?? 0;
      const rank = parseNumber(item.rank);
      if (rank !== null) ranks.push(rank);
    });

    if (daySales === 0 && !ranks.length) return;
    const record = monthly.get(month) || { month, monthSales: 0, sampleDays: 0, rankSum: 0, rankDays: 0 };
    record.monthSales += daySales;
    record.sampleDays += 1;
    if (ranks.length) {
      record.rankSum += avg(ranks) || 0;
      record.rankDays += 1;
    }
    monthly.set(month, record);
  });

  return [...monthly.values()]
    .sort((a, b) => sortMonthAsc(a.month, b.month))
    .map((item) => ({
      month: item.month,
      monthSales: Math.round(item.monthSales),
      sampleDays: item.sampleDays,
      avgRank: item.rankDays ? item.rankSum / item.rankDays : null,
    }));
}

async function collectScopeHistoryWithinOneYear(filters, anchorDate) {
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

  const historyRows = [];
  for (const date of dates) {
    try {
      const payload = await getDailyPayload(date);
      const scoped = filterItemsFromPayload(payload, filters);
      if (!scoped.length) continue;
      historyRows.push({ date, items: scoped });
    } catch (_error) {
      // Skip single-day failures and keep available samples.
    }
  }
  return historyRows;
}

async function getOfficialInsights(date) {
  if (!date) return null;
  if (officialInsightsCache.has(date)) {
    return officialInsightsCache.get(date);
  }

  const path = `${INSIGHTS_PATH_PREFIX}${encodeURIComponent(date)}.json`;
  const payload = await loadOptionalJson(path);
  officialInsightsCache.set(date, payload);
  return payload;
}

function resetInsightsView(message) {
  setText("insightStatus", message || "点击“分析当前竞品”生成结果");
  renderInsightList("reviewInsights", null);
  renderKeywordMetrics("trafficKeywords", null, "估算流量");
  renderKeywordMetrics("conversionKeywords", null, "转化分");
  renderMonthlySalesInsights(null, "");
  renderMonthlySalesCompetitorTable(null, "");
  renderInsightList("styleTrendInsights", null);
  renderStyleTrendMonthlyTable(null, "");
}

async function runCompetitiveInsights() {
  if (!dailyPayload) {
    setText("insightStatus", "当前无可分析数据。");
    return;
  }

  insightRequestId += 1;
  const currentRequestId = insightRequestId;

  const filters = currentFilters();
  const anchorDate = document.getElementById("snapshot_date").value;
  const selectedAsin = document.getElementById("analysisAsin").value || (filteredItems[0]?.asin || "");

  resetInsightsView("分析中，请稍候...");
  const officialPayload = await getOfficialInsights(anchorDate);
  if (currentRequestId !== insightRequestId) return;

  const historyRows = await collectScopeHistoryWithinOneYear(filters, anchorDate);
  if (currentRequestId !== insightRequestId) return;

  const officialKeywordRows = Array.isArray(officialPayload?.keywords) ? officialPayload.keywords.length : 0;
  const officialReviewRows = Array.isArray(officialPayload?.review_topics) ? officialPayload.review_topics.length : 0;
  const officialSalesRows = Array.isArray(officialPayload?.monthly_sales) ? officialPayload.monthly_sales.length : 0;
  const officialStyleRows = Array.isArray(officialPayload?.style_trends) ? officialPayload.style_trends.length : 0;
  const hasOfficialData = officialKeywordRows + officialReviewRows + officialSalesRows + officialStyleRows > 0;

  if (hasOfficialData) {
    const estimatedKeywordInsights = buildKeywordInsightRows(filteredItems);
    const officialKeywordInsights = buildKeywordInsightRowsFromOfficial(officialPayload);
    const officialReviewLines = buildReviewInsightLinesFromOfficial(officialPayload, selectedAsin);
    const officialMonthlyRows = buildMonthlySalesRowsFromOfficial(officialPayload, selectedAsin);
    const officialCompetitorMonthlyRows = buildCompetitorMonthlySalesRowsFromOfficial(officialPayload, filteredItems, 12);
    const estimatedCompetitorMonthlyRows = buildCompetitorMonthlySalesRows(historyRows, filteredItems, 12);
    const officialStyleTrendRows = buildStyleTrendRowsFromOfficial(officialPayload, 12);
    const estimatedStyleTrendRows = buildStyleTrendRows(historyRows, 12);
    const officialStyleLines = buildStyleTrendLinesFromOfficial(officialPayload);

    const keywordFromPublicSearch = isPublicSearchKeywordRows(officialPayload);

    renderInsightList(
      "reviewInsights",
      officialReviewLines.length ? officialReviewLines : buildReviewInsightLines(filteredItems),
    );
    renderKeywordMetrics(
      "trafficKeywords",
      officialKeywordInsights.trafficRows.length
        ? officialKeywordInsights.trafficRows
        : estimatedKeywordInsights.trafficRows,
      officialKeywordInsights.trafficRows.length
        ? keywordFromPublicSearch
          ? "搜索结果量"
          : "官方曝光"
        : "估算流量",
    );
    renderKeywordMetrics(
      "conversionKeywords",
      officialKeywordInsights.conversionRows.length
        ? officialKeywordInsights.conversionRows
        : estimatedKeywordInsights.conversionRows,
      officialKeywordInsights.conversionRows.length
        ? keywordFromPublicSearch
          ? "匹配率"
          : "官方转化率"
        : "转化分",
    );
    renderMonthlySalesInsights(
      officialMonthlyRows.length ? officialMonthlyRows : buildMonthlySalesRows(historyRows, selectedAsin),
      selectedAsin,
    );
    renderMonthlySalesCompetitorTable(
      officialCompetitorMonthlyRows.length ? officialCompetitorMonthlyRows : estimatedCompetitorMonthlyRows,
      officialCompetitorMonthlyRows.length ? "官方月销量" : "估算月销量",
    );
    renderInsightList(
      "styleTrendInsights",
      officialStyleLines.length ? officialStyleLines : buildStyleTrendLines(historyRows),
    );
    renderStyleTrendMonthlyTable(
      officialStyleTrendRows.length ? officialStyleTrendRows : estimatedStyleTrendRows,
      officialStyleTrendRows.length ? "官方款式趋势" : "估算款式趋势",
    );

    setText(
      "insightStatus",
      `已完成分析：数据源 ${formatInsightsSourceLabel(officialPayload?.source)}（关键词 ${officialKeywordRows}，月销量 ${officialSalesRows}，评论主题 ${officialReviewRows}，款式趋势 ${officialStyleRows}）。`,
    );
    return;
  }

  renderInsightList("reviewInsights", buildReviewInsightLines(filteredItems));
  const keywordInsights = buildKeywordInsightRows(filteredItems);
  renderKeywordMetrics("trafficKeywords", keywordInsights.trafficRows, "估算流量");
  renderKeywordMetrics("conversionKeywords", keywordInsights.conversionRows, "转化分");
  renderMonthlySalesInsights(buildMonthlySalesRows(historyRows, selectedAsin), selectedAsin);
  renderMonthlySalesCompetitorTable(buildCompetitorMonthlySalesRows(historyRows, filteredItems, 12), "估算月销量");
  renderInsightList("styleTrendInsights", buildStyleTrendLines(historyRows));
  renderStyleTrendMonthlyTable(buildStyleTrendRows(historyRows, 12), "估算款式趋势");

  setText(
    "insightStatus",
    `已完成分析：当前样本 ${filteredItems.length} 条，历史采样日 ${historyRows.length} 天（近一年，估算模式）。`,
  );
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

function buildMonthlySalesCsv(rows) {
  const headers = ["month", "asin", "title", "month_sales", "sample_days", "avg_rank"];
  const lines = [headers.join(",")];
  rows.forEach((row) => {
    lines.push(
      [
        escapeCsv(row.month),
        escapeCsv(row.asin),
        escapeCsv(row.title),
        escapeCsv(row.monthSales),
        escapeCsv(row.sampleDays),
        escapeCsv(row.avgRank === null ? "" : row.avgRank.toFixed(2)),
      ].join(","),
    );
  });
  return lines.join("\n");
}

function buildStyleTrendCsv(rows) {
  const headers = ["month", "style", "score", "delta"];
  const lines = [headers.join(",")];
  rows.forEach((row) => {
    lines.push(
      [
        escapeCsv(row.month),
        escapeCsv(row.style),
        escapeCsv(row.score),
        escapeCsv(row.delta),
      ].join(","),
    );
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

function downloadMonthlySalesCsv() {
  if (!competitorMonthlyRows.length) {
    window.alert("当前无可导出的月销量明细。");
    return;
  }

  const date = document.getElementById("snapshot_date").value || "unknown";
  const csv = buildMonthlySalesCsv(competitorMonthlyRows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `monthly-sales-${date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadStyleTrendCsv() {
  if (!styleTrendRows.length) {
    window.alert("当前无可导出的款式趋势明细。");
    return;
  }

  const date = document.getElementById("snapshot_date").value || "unknown";
  const csv = buildStyleTrendCsv(styleTrendRows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `style-trend-${date}.csv`;
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
  populateAnalysisAsinOptions();
  resetInsightsView("筛选条件已更新，请点击“分析当前竞品”刷新洞察");
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
    populateAnalysisAsinOptions();
    resetInsightsView("暂无可分析数据。");
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
  document.getElementById("downloadMonthlySalesCsv").addEventListener("click", downloadMonthlySalesCsv);
  document.getElementById("downloadStyleTrendCsv").addEventListener("click", downloadStyleTrendCsv);
  document.getElementById("runInsights").addEventListener("click", () => {
    runCompetitiveInsights().catch(showError);
  });
  document.getElementById("analysisAsin").addEventListener("change", () => {
    resetInsightsView("已切换 ASIN，请点击“分析当前竞品”更新结果");
  });
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

  resetInsightsView("点击“分析当前竞品”生成结果");
  await handleDateChange(document.getElementById("snapshot_date").value);
}

initialize().catch((error) => {
  setText("dataStatus", "error");
  updateStatusBanner("error", "");
  showError(error);
});
