const TARGET_TYPES = ["관내사전투표", "선거일투표", "관외사전투표", "거소투표"];
const FOCUS_SCOPE_IDS = [
  "provincial-council-bundang",
  "municipal-council-bundang",
  "mayor-seongnam",
  "governor-gyeonggi",
  "metropolitan-pr-gyeonggi",
  "basic-pr-seongnam",
  "education-gyeonggi",
];
const PARTY_COLOR_RULES = [
  { keyword: "더불어민주당", color: "#3b82f6", soft: "rgba(59, 130, 246, 0.12)" },
  { keyword: "국민의힘", color: "#ef4444", soft: "rgba(239, 68, 68, 0.12)" },
  { keyword: "조국혁신당", color: "#4338ca", soft: "rgba(67, 56, 202, 0.12)" },
  { keyword: "개혁신당", color: "#f97316", soft: "rgba(249, 115, 22, 0.12)" },
  { keyword: "진보당", color: "#f87171", soft: "rgba(248, 113, 113, 0.12)" },
  { keyword: "안민석", color: "#60a5fa", soft: "rgba(96, 165, 250, 0.12)" },
  { keyword: "임태희", color: "#f87171", soft: "rgba(248, 113, 113, 0.12)" },
];
const NEUTRAL_CANDIDATE_COLORS = [
  { color: "#64748b", soft: "rgba(100, 116, 139, 0.12)" },
  { color: "#94a3b8", soft: "rgba(148, 163, 184, 0.12)" },
  { color: "#475569", soft: "rgba(71, 85, 105, 0.12)" },
  { color: "#cbd5e1", soft: "rgba(203, 213, 225, 0.12)" },
  { color: "#334155", soft: "rgba(51, 65, 85, 0.12)" },
];

const numberFormatter = new Intl.NumberFormat("ko-KR");
const timeFormatter = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const $ = (selector) => document.querySelector(selector);

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return numberFormatter.format(Number(value));
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(2)}%`;
}

function safePercent(value, max = 100) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 0;
  return Math.max(0, Math.min(max, Number(value)));
}

function parseDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

async function fetchJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  } catch (error) {
    console.warn(`Failed to load ${path}`, error);
    return fallback;
  }
}

function getProgressSummary(scope) {
  return scope?.progress?.summary || null;
}

function getProgressRate(scope) {
  return getProgressSummary(scope)?.progressRate ?? null;
}

function getLeadingCandidate(scope) {
  const candidates = (getProgressSummary(scope)?.candidateVotes || [])
    .filter((candidate) => candidate.name !== "계" && candidate.votes)
    .sort((a, b) => (b.votes || 0) - (a.votes || 0));
  return candidates[0] || null;
}

function getCandidateRate(candidate, totalVotes) {
  if (candidate.rate !== null && candidate.rate !== undefined) return Number(candidate.rate);
  if (!totalVotes || !candidate.votes) return null;
  return (Number(candidate.votes) / Number(totalVotes)) * 100;
}

function hashText(value) {
  return [...String(value || "")].reduce((hash, char) => {
    return (hash * 31 + char.charCodeAt(0)) >>> 0;
  }, 0);
}

function getCandidateAccent(candidate, fallbackIndex = 0) {
  const name = candidate?.name || "";
  const partyMatch = PARTY_COLOR_RULES.find((rule) => name.includes(rule.keyword));
  if (partyMatch) return partyMatch;
  return NEUTRAL_CANDIDATE_COLORS[
    (Number.isInteger(fallbackIndex) ? fallbackIndex : hashText(name)) % NEUTRAL_CANDIDATE_COLORS.length
  ];
}

function applyCandidateAccent(element, candidate, fallbackIndex = 0) {
  const accent = getCandidateAccent(candidate, fallbackIndex);
  element.style.setProperty("--candidate-color", accent.color);
  element.style.setProperty("--candidate-soft", accent.soft);
}

function getMaxBallotVotes(scope) {
  return Math.max(1, ...scope.ballotTypes.map((item) => item.votes || 0));
}

function shouldShowDistrictBreakdown(scope) {
  return ["provincial-council-bundang", "municipal-council-bundang"].includes(scope.id);
}

function shouldShowLocalBreakdown(scope) {
  return Boolean(scope.localBreakdown);
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderTopStatus(data) {
  const updated = parseDate(data.generatedAt);
  $("#updatedAt").textContent = updated ? `${timeFormatter.format(updated)} 갱신` : "갱신 시각 없음";
  $("#sourceLink").href = data.source?.documentUrl || $("#sourceLink").href;

  const scopesById = new Map(data.scopes.map((scope) => [scope.id, scope]));
  const bundangScopes = [
    scopesById.get("provincial-council-bundang"),
    scopesById.get("municipal-council-bundang"),
  ].filter(Boolean);
  const bundangRates = bundangScopes
    .map((scope) => getProgressRate(scope))
    .filter((rate) => rate !== null && rate !== undefined);
  const averageBundangRate = bundangRates.length
    ? bundangRates.reduce((sum, rate) => sum + Number(rate), 0) / bundangRates.length
    : null;

  $("#bundangRateInline").textContent = averageBundangRate !== null ? `(${formatPercent(averageBundangRate)})` : "";
}

function renderSummaryItems(container, scope) {
  const progress = getProgressSummary(scope) || {};
  const leading = getLeadingCandidate(scope);
  const leadingRate = leading ? getCandidateRate(leading, progress.validVotes || progress.votes) : null;
  const items = [
    ["선거인수", formatNumber(progress.electors)],
    ["투표수", formatNumber(progress.votes)],
    ["선두", leading ? `${leading.name} ${formatPercent(leadingRate)} · ${formatNumber(leading.votes)}표` : "-"],
  ];
  container.replaceChildren();
  items.forEach(([label, value]) => {
    const item = makeElement("div", "summary-item");
    item.append(makeElement("span", "", label));
    item.append(makeElement("strong", "", value));
    container.append(item);
  });
}

function renderChips(container, scope) {
  container.replaceChildren();
  TARGET_TYPES.forEach((type) => {
    const status = scope.signal?.statusByType?.[type];
    const chip = makeElement("span", `chip ${status?.started ? "chip--active" : ""}`);
    const statusText = status?.rows ? (status.started ? "반영" : "대기") : "상세없음";
    chip.textContent = `${type} ${statusText}`;
    container.append(chip);
  });
}

function renderBallotBars(container, scope) {
  container.replaceChildren();
  const maxVotes = getMaxBallotVotes(scope);
  scope.ballotTypes
    .filter((item) => TARGET_TYPES.includes(item.type) || item.votes)
    .forEach((item) => {
      const row = makeElement("div", "bar-row");
      row.dataset.type = item.type;
      const label = makeElement("b", "", item.type);
      const track = makeElement("div", "bar-track");
      const fill = makeElement("span");
      fill.style.width = `${((item.votes || 0) / maxVotes) * 100}%`;
      track.append(fill);
      row.append(label, track, makeElement("span", "", formatNumber(item.votes || 0)));
      container.append(row);
    });
}

function renderCandidateRows(container, scope) {
  const summary = getProgressSummary(scope) || {};
  const totalVotes = summary.validVotes || summary.votes;
  const candidates = (summary.candidateVotes || [])
    .filter((candidate) => candidate.name !== "계" && candidate.votes)
    .sort((a, b) => (b.votes || 0) - (a.votes || 0))
    .slice(0, 4);
  container.replaceChildren();
  if (!candidates.length) {
    const message = shouldShowDistrictBreakdown(scope)
      ? "선거구별 후보 득표율은 아래 선거구별 보기에서 확인"
      : "후보 득표 데이터 대기";
    container.append(makeElement("p", "muted", message));
    return;
  }
  const maxVotes = Math.max(1, ...candidates.map((candidate) => candidate.votes || 0));
  candidates.forEach((candidate, index) => {
    const isLeader = candidate === candidates[0];
    const row = makeElement("div", `candidate-row ${isLeader ? "candidate-row--leader" : ""}`);
    applyCandidateAccent(row, candidate, index);
    const track = makeElement("div", "bar-track");
    const fill = makeElement("span");
    fill.style.width = `${((candidate.votes || 0) / maxVotes) * 100}%`;
    track.append(fill);
    row.append(
      makeElement("b", "", candidate.name),
      track,
      makeElement(
        "span",
        "",
        `${formatNumber(candidate.votes)}표 · ${formatPercent(getCandidateRate(candidate, totalVotes))}`
      )
    );
    container.append(row);
  });
}

function getUnitProgress(scope, unit) {
  return unit.progress || (scope.progress?.rows || []).find((row) => row.area === unit.name) || null;
}

function getUnitTotalRow(unit) {
  return unit.rows.find((row) => row.area === "합계") || unit.rows.find((row) => row.ballotType === "계") || null;
}

function getUnitCandidates(unit) {
  return (getUnitTotalRow(unit)?.candidateVotes || [])
    .filter((candidate) => candidate.name !== "계" && candidate.votes)
    .sort((a, b) => (b.votes || 0) - (a.votes || 0));
}

function getUnitLeadingCandidate(unit) {
  return getUnitCandidates(unit)[0] || null;
}

function getUnitBallotTypeVotes(unit, type) {
  return unit.rows
    .filter((row) => row.ballotType === type)
    .reduce((sum, row) => sum + (row.votes || 0), 0);
}

function renderUnitBallotBreakdown(unit) {
  const wrapper = makeElement("div", "district-ballots");
  const values = TARGET_TYPES.map((type) => ({ type, votes: getUnitBallotTypeVotes(unit, type) }));
  const maxVotes = Math.max(1, ...values.map((item) => item.votes));
  values.forEach((item) => {
    const row = makeElement("div", `district-ballot ${item.votes ? "district-ballot--active" : ""}`);
    row.dataset.type = item.type;
    const label = makeElement("span", "", item.type);
    const track = makeElement("div", "bar-track");
    const fill = makeElement("span");
    fill.style.width = `${(item.votes / maxVotes) * 100}%`;
    track.append(fill);
    row.append(label, track, makeElement("strong", "", `${formatNumber(item.votes)}표`));
    wrapper.append(row);
  });
  return wrapper;
}

function renderUnitCandidateBreakdown(unit) {
  const candidates = getUnitCandidates(unit).slice(0, 3);
  const wrapper = makeElement("div", "district-candidates");
  if (!candidates.length) return wrapper;
  const totalVotes = getUnitTotalRow(unit)?.validVotes || getUnitTotalRow(unit)?.votes;
  const maxVotes = Math.max(1, ...candidates.map((candidate) => candidate.votes || 0));
  candidates.forEach((candidate, index) => {
    const row = makeElement("div", `district-candidate ${candidate === candidates[0] ? "district-candidate--leader" : ""}`);
    applyCandidateAccent(row, candidate, index);
    const track = makeElement("div", "bar-track");
    const fill = makeElement("span");
    fill.style.width = `${((candidate.votes || 0) / maxVotes) * 100}%`;
    track.append(fill);
    row.append(
      makeElement("b", "", candidate.name),
      track,
      makeElement(
        "span",
        "",
        `${formatNumber(candidate.votes)}표 · ${formatPercent(getCandidateRate(candidate, totalVotes))}`
      )
    );
    wrapper.append(row);
  });
  return wrapper;
}

function getUnitLeadingText(unit) {
  const totalRow = unit.rows.find((row) => row.area === "합계") || unit.rows.find((row) => row.ballotType === "계");
  const leading = getUnitLeadingCandidate(unit);
  if (!leading) return "후보 득표 대기";
  const rate = getCandidateRate(leading, totalRow?.validVotes || totalRow?.votes);
  return `선두 ${leading.name} ${formatPercent(rate)}`;
}

function getUnitActiveTypes(unit) {
  return TARGET_TYPES.filter((type) => unit.rows.some((row) => row.ballotType === type && row.votes));
}

const UNCONTESTED_UNITS = new Set([
  "성남시사선거구",
  "성남시아선거구",
  "성남시자선거구",
  "성남시카선거구",
]);

function renderDistrictBreakdown(scope) {
  const section = makeElement("section", "district-breakdown");
  const header = makeElement("div", "district-breakdown__head");

  const visibleUnits = scope.units.filter((u) => !UNCONTESTED_UNITS.has(u.name));

  header.append(makeElement("strong", "", "선거구별 보기"));
  header.append(makeElement("span", "muted", `${visibleUnits.length}개 선거구`));
  section.append(header);

  const list = makeElement("div", "district-list");
  const maxVotes = Math.max(1, ...visibleUnits.map((unit) => unit.summary?.votes || 0));

  visibleUnits.forEach((unit) => {
    const progress = getUnitProgress(scope, unit);
    const activeTypes = getUnitActiveTypes(unit);
    const votes = unit.summary?.votes || progress?.votes || 0;
    const rate = progress?.progressRate;

    const row = makeElement("article", "district-card");
    const top = makeElement("div", "district-card__top");
    top.append(makeElement("strong", "", unit.name));
    top.append(makeElement("span", "district-card__rate", formatPercent(rate)));

    const meta = makeElement("div", "district-card__meta");
    meta.append(makeElement("span", "", `투표수 ${formatNumber(votes)}`));
    meta.append(makeElement("span", "", activeTypes.length ? `반영 ${activeTypes.length}/${TARGET_TYPES.length}` : "투표구분 대기"));
    meta.append(makeElement("span", "", getUnitLeadingText(unit)));

    const track = makeElement("div", "bar-track district-card__track");
    const fill = makeElement("span");
    fill.style.width = `${((votes || 0) / maxVotes) * 100}%`;
    track.append(fill);

    row.append(top, meta, track, renderUnitBallotBreakdown(unit), renderUnitCandidateBreakdown(unit));
    list.append(row);
  });

  section.append(list);
  return section;
}

function getDetailVotes(detail) {
  return detail?.summary?.votes ?? detail?.progress?.votes ?? 0;
}

function getDetailTotalVotes(detail) {
  return detail?.summary?.validVotes || detail?.summary?.votes || detail?.progress?.validVotes || detail?.progress?.votes;
}

function getDetailCandidates(detail) {
  return (detail?.candidateVotes || [])
    .filter((candidate) => candidate.name !== "계" && (candidate.votes || candidate.rate !== null && candidate.rate !== undefined))
    .sort((a, b) => (b.votes || 0) - (a.votes || 0));
}

function getDetailActiveTypes(detail) {
  return TARGET_TYPES.filter((type) => {
    const item = (detail?.ballotTypes || []).find((ballot) => ballot.type === type);
    return item?.started;
  });
}

function getDetailLeadingText(detail) {
  const leading = getDetailCandidates(detail)[0];
  if (!leading) return "후보 득표 대기";
  return `선두 ${leading.name} ${formatPercent(getCandidateRate(leading, getDetailTotalVotes(detail)))}`;
}

function renderDetailBallotBreakdown(detail) {
  const wrapper = makeElement("div", "local-ballots");
  const values = TARGET_TYPES.map((type) => {
    return (detail?.ballotTypes || []).find((ballot) => ballot.type === type) || { type, votes: 0, rowCount: 0 };
  });
  const maxVotes = Math.max(1, ...values.map((item) => item.votes || 0));
  values.forEach((item) => {
    const hasRows = Boolean(item.rowCount);
    const row = makeElement("div", `local-ballot ${item.started ? "local-ballot--active" : ""} ${hasRows ? "" : "local-ballot--empty"}`);
    row.dataset.type = item.type;
    const track = makeElement("div", "bar-track");
    const fill = makeElement("span");
    fill.style.width = `${((item.votes || 0) / maxVotes) * 100}%`;
    track.append(fill);
    row.append(
      makeElement("span", "", item.type),
      track,
      makeElement("strong", "", hasRows ? `${formatNumber(item.votes || 0)}표` : "상세없음")
    );
    wrapper.append(row);
  });
  return wrapper;
}

function renderDetailCandidateBreakdown(detail) {
  const candidates = getDetailCandidates(detail).slice(0, 3);
  const wrapper = makeElement("div", "local-candidates");
  if (!candidates.length) {
    wrapper.append(makeElement("p", "muted", "후보 득표 데이터 대기"));
    return wrapper;
  }
  const totalVotes = getDetailTotalVotes(detail);
  const maxVotes = Math.max(1, ...candidates.map((candidate) => candidate.votes || 0));
  candidates.forEach((candidate, index) => {
    const row = makeElement("div", `local-candidate ${index === 0 ? "local-candidate--leader" : ""}`);
    applyCandidateAccent(row, candidate, index);
    const track = makeElement("div", "bar-track");
    const fill = makeElement("span");
    fill.style.width = `${((candidate.votes || 0) / maxVotes) * 100}%`;
    track.append(fill);
    row.append(
      makeElement("b", "", candidate.name),
      track,
      makeElement(
        "span",
        "",
        `${formatNumber(candidate.votes || 0)}표 · ${formatPercent(getCandidateRate(candidate, totalVotes))}`
      )
    );
    wrapper.append(row);
  });
  return wrapper;
}

function renderLocalAreaCard(detail, extraClass = "") {
  const card = makeElement("article", `local-card ${extraClass}`.trim());
  const activeTypes = getDetailActiveTypes(detail);
  const rate = detail?.progress?.progressRate;
  const votes = getDetailVotes(detail);

  const top = makeElement("div", "local-card__top");
  top.append(makeElement("strong", "", detail.name));
  top.append(makeElement("span", "local-card__rate", rate === null || rate === undefined ? `${formatNumber(votes)}표` : formatPercent(rate)));

  const meta = makeElement("div", "local-card__meta");
  meta.append(makeElement("span", "", `투표수 ${formatNumber(votes)}`));
  meta.append(makeElement("span", "", activeTypes.length ? `반영 ${activeTypes.length}/${TARGET_TYPES.length}` : "투표구분 상세없음"));
  meta.append(makeElement("span", "", getDetailLeadingText(detail)));

  card.append(top, meta, renderDetailBallotBreakdown(detail), renderDetailCandidateBreakdown(detail));
  return card;
}

function renderLocalBreakdown(scope) {
  const breakdown = scope.localBreakdown;
  const section = makeElement("section", "local-breakdown");
  const header = makeElement("div", "local-breakdown__head");
  header.append(makeElement("strong", "", "수정·중원 전체 / 분당 동별"));
  header.append(makeElement("span", "muted", "후보 득표율과 투표 종류 반영 상태"));
  section.append(header);

  // 수정/중원구 카드는 기존 그리드에 표시
  if (breakdown.summaryRegions?.length) {
    const summaryGrid = makeElement("div", "local-grid local-grid--summary");
    breakdown.summaryRegions.forEach((detail) => {
      summaryGrid.append(renderLocalAreaCard(detail));
    });
    section.append(summaryGrid);
  }

  // 분당구 요약 + 동별 아코디언
  if (breakdown.bundangSummary) {
    const details = makeElement("details", "local-breakdown__accordion");
    const summary = makeElement("summary", "local-breakdown__summary");
    const bundangCard = renderLocalAreaCard(breakdown.bundangSummary);
    bundangCard.append(makeElement("p", "unit-group__hint muted", "▸ 분당구 동별 개표 현황 보기"));
    summary.append(bundangCard);
    details.append(summary);

    const dongWrap = makeElement("div", "local-breakdown__dongs");
    const dongHeader = makeElement("div", "local-breakdown__subhead");
    dongHeader.append(makeElement("strong", "", "분당구 동별 보기"));
    dongHeader.append(makeElement("span", "muted", `${(breakdown.bundangDongs || []).length}개 동`));
    dongWrap.append(dongHeader);

    if (breakdown.bundangDongs?.length) {
      const dongGrid = makeElement("div", "local-grid local-grid--dongs");
      breakdown.bundangDongs.forEach((detail) => {
        dongGrid.append(renderLocalAreaCard(detail, "local-card--dong"));
      });
      dongWrap.append(dongGrid);
    } else {
      dongWrap.append(makeElement("p", "empty-state", "분당구 동별 개표 상세 행은 아직 NEC에 올라오지 않았습니다."));
    }
    details.append(dongWrap);
    section.append(details);
  }

  return section;
}

function renderRaceCard(scope) {
  const template = $("#raceCardTemplate");
  const card = template.content.firstElementChild.cloneNode(true);
  const rate = getProgressRate(scope);
  card.querySelector(".race-card__scope").textContent = scope.scopeName;
  card.querySelector("h3").textContent = scope.electionName;
  card.querySelector(".race-card__rate").textContent = formatPercent(rate);
  card.querySelector(".progress span").style.width = `${safePercent(rate)}%`;
  renderSummaryItems(card.querySelector(".race-card__summary"), scope);
  renderChips(card.querySelector(".chips"), scope);
  renderBallotBars(card.querySelector(".ballot-bars"), scope);
  renderCandidateRows(card.querySelector(".candidate-list"), scope);
  
  const content = card.querySelector(".race-card__content");
  if (shouldShowLocalBreakdown(scope)) {
    content.append(renderLocalBreakdown(scope));
  }
  if (shouldShowDistrictBreakdown(scope)) {
    content.append(renderDistrictBreakdown(scope));
  }
  
  // 모바일에선 접어놓고, 데스크탑(800px 초과)에서는 기본으로 열려있게 설정
  if (window.innerWidth > 800) {
    card.setAttribute("open", "");
  }
  
  return card;
}

function renderRaces(data) {
  const grid = $("#raceGrid");
  grid.replaceChildren();
  const ordered = [...data.scopes].sort((a, b) => {
    const ai = FOCUS_SCOPE_IDS.indexOf(a.id);
    const bi = FOCUS_SCOPE_IDS.indexOf(b.id);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });
  ordered.forEach((scope) => {
    if (scope.id === "national-assembly-all") return;
    // 무투표 선거구를 scope 레벨에서 완전히 제거
    const renderScope = scope.id === "municipal-council-bundang"
      ? { ...scope, units: scope.units.filter((u) => !UNCONTESTED_UNITS.has(u.name)) }
      : scope;
    grid.append(renderRaceCard(renderScope));
  });
}

// " / " 구분자가 있는 유닛들을 앞부분(선거구명) 기준으로 그룹화.
// 예: "군산시김제시부안군을 / 군산시" → 그룹키 "군산시김제시부안군을", 서브명 "군산시"
function groupedNationalUnits(units) {
  const groups = []; // { key, cityName, items: [unit,...] } or { key: null, unit }
  const groupMap = new Map();
  units.forEach((unit) => {
    const sepIdx = unit.name.indexOf(" / ");
    if (sepIdx !== -1) {
      const groupKey = unit.name.slice(0, sepIdx);
      if (!groupMap.has(groupKey)) {
        const entry = { key: groupKey, cityName: unit.cityName, items: [] };
        groupMap.set(groupKey, entry);
        groups.push(entry);
      }
      groupMap.get(groupKey).items.push({ ...unit, subName: unit.name.slice(sepIdx + 3) });
    } else {
      groups.push({ key: null, unit });
    }
  });
  return groups;
}

function renderNationalUnitCard(unit, scope) {
  const progress = unit.progress || getUnitProgress(scope, unit);
  const totalRow = getUnitTotalRow(unit);
  const totalValidVotes = totalRow?.validVotes || totalRow?.votes;
  const totalVotes = unit.summary?.votes || progress?.votes || 0;
  const candidates = (totalRow?.candidateVotes || [])
    .filter((c) => c.name && c.name !== "계" && c.votes)
    .sort((a, b) => (b.votes || 0) - (a.votes || 0))
    .slice(0, 2);
  const activeTypes = TARGET_TYPES.filter((t) =>
    unit.rows.some((r) => r.ballotType === t && r.votes)
  );

  const details = makeElement("details", "unit-card");
  const summary = makeElement("summary", "unit-card__summary");

  // 제목 + 개표율
  const top = makeElement("div", "unit-card__top");
  top.append(makeElement("strong", "", unit.name));
  top.append(makeElement("span", "unit-card__rate", formatPercent(progress?.progressRate)));
  summary.append(top);

  // 메타
  summary.append(makeElement("p", "muted",
    `${unit.cityName ? `${unit.cityName} · ` : ""}${formatNumber(totalVotes)}표 · ` +
    (activeTypes.length ? activeTypes.join(" · ") : "개표구분 대기")
  ));

  // 후보 득표 바
  if (candidates.length) {
    const maxV = candidates[0].votes || 1;
    const candList = makeElement("div", "unit-group__merged-candidates");
    candidates.forEach((c, i) => {
      const row = makeElement("div", `candidate-row ${i === 0 ? "candidate-row--leader" : ""}`);
      applyCandidateAccent(row, c, i);
      const track = makeElement("div", "bar-track");
      const fill = makeElement("span");
      fill.style.width = `${((c.votes || 0) / maxV) * 100}%`;
      track.append(fill);
      row.append(
        makeElement("b", "", c.name),
        track,
        makeElement("span", "", `${formatNumber(c.votes)}표 · ${formatPercent(getCandidateRate(c, totalValidVotes))}`)
      );
      candList.append(row);
    });
    summary.append(candList);
  }

  summary.append(makeElement("p", "unit-group__hint muted", "▸ 투표 종류별 상세 보기"));
  details.append(summary);

  // 펼쳐진 영역: 투표 종류별 상세
  details.append(makeElement("div", "unit-group__divider"));
  const ballotWrap = makeElement("div", "unit-card__ballot-detail");
  ballotWrap.append(renderUnitBallotBreakdown(unit));
  details.append(ballotWrap);

  return details;
}

function renderNationalGroupCard(group) {
  // ── 합산 계산 ──────────────────────────────────────
  let totalElectors = 0;
  let totalVotes = 0;
  let totalValidVotes = 0;
  const candidateTotals = new Map(); // name → votes
  const activeSet = new Set();

  group.items.forEach((unit) => {
    const s = unit.summary || {};
    totalElectors += s.electors || 0;
    totalVotes    += s.votes    || 0;
    totalValidVotes += s.validVotes || s.votes || 0;

    // totalRow에서 후보별 득표 합산
    const totalRow = getUnitTotalRow(unit);
    (totalRow?.candidateVotes || []).forEach((c) => {
      if (!c.name || c.name === "계" || !c.votes) return;
      candidateTotals.set(c.name, (candidateTotals.get(c.name) || 0) + c.votes);
    });

    // 반영된 투표 종류
    TARGET_TYPES.forEach((t) => {
      if (unit.rows.some((r) => r.ballotType === t && r.votes)) activeSet.add(t);
    });
  });

  const progressRate = totalElectors > 0 ? (totalVotes / totalElectors) * 100 : null;
  const sortedCandidates = [...candidateTotals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([name, votes]) => ({ name, votes }));

  // ── 카드 구조 (details/summary 아코디언) ───────────
  const details = makeElement("details", "unit-card unit-card--group");
  const summary = makeElement("summary", "unit-card__summary");

  // 헤더 행
  const top = makeElement("div", "unit-card__top");
  top.append(makeElement("strong", "", group.key));
  const rateSpan = makeElement("span", "unit-card__rate",
    progressRate !== null ? `${progressRate.toFixed(2)}%` : "-");
  top.append(rateSpan);
  summary.append(top);

  // 메타
  summary.append(
    makeElement("p", "muted",
      `${group.cityName ? `${group.cityName} · ` : ""}분리선거구 ${group.items.length}개 지역 · ` +
      `${formatNumber(totalVotes)}표 / ${formatNumber(totalElectors)}명 · ` +
      (activeSet.size ? [...activeSet].join(" · ") : "개표구분 대기")
    )
  );

  // 합산 후보 득표
  if (sortedCandidates.length) {
    const candList = makeElement("div", "unit-group__merged-candidates");
    const maxV = sortedCandidates[0].votes || 1;
    sortedCandidates.forEach((c, i) => {
      const row = makeElement("div", `candidate-row ${i === 0 ? "candidate-row--leader" : ""}`);
      applyCandidateAccent(row, c, i);
      const track = makeElement("div", "bar-track");
      const fill = makeElement("span");
      fill.style.width = `${((c.votes || 0) / maxV) * 100}%`;
      track.append(fill);
      const rate = totalValidVotes ? (c.votes / totalValidVotes) * 100 : null;
      row.append(
        makeElement("b", "", c.name),
        track,
        makeElement("span", "", `${formatNumber(c.votes)}표 · ${formatPercent(rate)}`)
      );
      candList.append(row);
    });
    summary.append(candList);
  }

  // 펼치기 힌트
  summary.append(makeElement("p", "unit-group__hint muted", "▸ 지역별 상세 보기"));

  details.append(summary);

  // ── 펼쳐진 영역: 지역별 세부 ──────────────────────
  const subList = makeElement("div", "unit-group__list");
  group.items.forEach((unit) => {
    const sub = makeElement("div", "unit-group__item");

    const subTop = makeElement("div", "unit-group__item-top");
    const progress = unit.progress || null;
    subTop.append(makeElement("span", "unit-group__item-name", unit.subName));
    subTop.append(makeElement("span", "unit-group__item-rate", formatPercent(progress?.progressRate)));
    sub.append(subTop);

    const votes = unit.summary?.votes || progress?.votes || 0;
    const electors = unit.summary?.electors || progress?.electors || 0;
    sub.append(makeElement("p", "muted",
      `${formatNumber(votes)}표 / ${formatNumber(electors)}명`
    ));

    const totalRow = getUnitTotalRow(unit);
    const cands = (totalRow?.candidateVotes || [])
      .filter((c) => c.name && c.name !== "계" && c.votes)
      .sort((a, b) => (b.votes || 0) - (a.votes || 0))
      .slice(0, 2);
    const subValidVotes = totalRow?.validVotes || totalRow?.votes;
    cands.forEach((candidate, index) => {
      const line = makeElement("p", `unit-candidate unit-group__candidate ${index === 0 ? "unit-candidate--leader" : ""}`);
      applyCandidateAccent(line, candidate, index);
      line.textContent = `${candidate.name} ${formatNumber(candidate.votes)}표 · ${formatPercent(getCandidateRate(candidate, subValidVotes))}`;
      sub.append(line);
    });
    subList.append(sub);
  });
  details.append(subList);

  return details;
}

function renderNational(data) {
  const scope = data.scopes.find((item) => item.id === "national-assembly-all");
  const list = $("#nationalList");
  list.replaceChildren();
  if (!scope) {
    list.append(makeElement("p", "empty-state", "국회의원선거 데이터가 없습니다."));
    return;
  }

  const units = [...scope.units].sort((a, b) => {
    const av = a.summary?.votes || 0;
    const bv = b.summary?.votes || 0;
    return bv - av;
  });
  if (!units.length) {
    list.append(makeElement("p", "empty-state", "조회 가능한 국회의원선거 선거구가 아직 없습니다."));
    return;
  }

  const groups = groupedNationalUnits(units);
  groups.forEach((group) => {
    if (group.key === null) {
      list.append(renderNationalUnitCard(group.unit, scope));
    } else {
      list.append(renderNationalGroupCard(group));
    }
  });
}

function renderError(message) {
  document.body.replaceChildren();
  const main = makeElement("main");
  main.append(makeElement("p", "empty-state", message));
  document.body.append(main);
}

async function boot() {
  const data = await fetchJson("./data/latest.json", null);
  if (!data || !Array.isArray(data.scopes)) {
    renderError("아직 수집된 데이터가 없습니다. GitHub Actions 또는 scripts/fetch_nec.py를 먼저 실행해 주세요.");
    return;
  }
  renderTopStatus(data);
  renderRaces(data);
  renderNational(data);
}

boot();
