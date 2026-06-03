#!/usr/bin/env python3
"""Fetch NEC election counting data and write a GitHub Pages friendly JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://info.nec.go.kr"
ELECTION_ID = "0020260603"
SEOUL_TZ = timezone(timedelta(hours=9))
REQUEST_SLEEP_SECONDS = 0.18
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

TARGET_BALLOT_TYPES = ["관내사전투표", "선거일투표", "관외사전투표", "거소투표"]
CITY_GYEONGGI = "4100"
CITY_GYEONGGI_NAME = "경기도"
TOWN_SUJEONG = "4105"
TOWN_SUJEONG_NAME = "성남시수정구"
TOWN_JUNGWON = "4106"
TOWN_JUNGWON_NAME = "성남시중원구"
TOWN_BUNDANG = "4107"
TOWN_BUNDANG_NAME = "성남시분당구"
SEONGNAM_TOWNS = [
    {"CODE": TOWN_SUJEONG, "NAME": TOWN_SUJEONG_NAME},
    {"CODE": TOWN_JUNGWON, "NAME": TOWN_JUNGWON_NAME},
    {"CODE": TOWN_BUNDANG, "NAME": TOWN_BUNDANG_NAME},
]

VCCP09_STATEMENTS = {
    "2": "VCCP09_#2",
    "3": "VCCP09_#3",
    "4": "VCCP09_#4",
    "5": "VCCP09_#5_0",
    "6": "VCCP09_#6_0",
    "8": "VCCP09_#8",
    "9": "VCCP09_#9",
    "11": "VCCP09_#11",
}

SPECIAL_VCCP08_SGGTOWN = {
    "5290503",
    "5280501",
    "5280502",
    "5412606",
    "5412607",
    "5412608",
    "5430201",
    "5430202",
    "5430203",
    "5441702",
    "5441703",
}


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def to_int(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "&nbsp;"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def to_float(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "&nbsp;"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def add_number(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


class NecTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.current_cell_tag = ""
        self.current_cell_parts: list[str] = []
        self.current_row: list[dict[str, str]] = []
        self.rows: list[list[dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "table" and attr_map.get("id") == "table01":
            self.in_target_table = True
            self.table_depth = 1
            return

        if self.in_target_table and tag == "table":
            self.table_depth += 1

        if not self.in_target_table:
            return

        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in {"td", "th"} and self.in_row:
            self.in_cell = True
            self.current_cell_tag = tag
            self.current_cell_parts = []
        elif tag == "br" and self.in_cell:
            self.current_cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.in_target_table and self.in_cell:
            self.current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_target_table:
            return

        if tag in {"td", "th"} and self.in_cell:
            self.current_row.append(
                {
                    "tag": self.current_cell_tag,
                    "text": clean_text("".join(self.current_cell_parts)),
                }
            )
            self.in_cell = False
            self.current_cell_tag = ""
            self.current_cell_parts = []
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
            self.current_row = []
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth <= 0:
                self.in_target_table = False


def parse_table(html: str) -> list[list[dict[str, str]]]:
    parser = NecTableParser()
    parser.feed(html)
    return parser.rows


def split_header_body(rows: list[list[dict[str, str]]]) -> tuple[list[list[str]], list[list[str]]]:
    header: list[list[str]] = []
    body: list[list[str]] = []
    in_body = False
    for row in rows:
        tags = {cell["tag"] for cell in row}
        texts = [cell["text"] for cell in row]
        if not in_body and tags == {"th"}:
            header.append(texts)
        else:
            in_body = True
            body.append(texts)
    return header, body


def fetch_text(url: str, *, data: dict[str, str] | None = None) -> str:
    encoded_data = None
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": f"{BASE_URL}/main/showDocument.xhtml?electionId={ELECTION_ID}&topMenuId=VC",
    }
    if data is not None:
        encoded_data = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(url, data=encoded_data, headers=headers)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                raw = response.read()
                return raw.decode("utf-8-sig", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def fetch_json(path: str, params: dict[str, str]) -> list[dict[str, str]]:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    text = fetch_text(url)
    time.sleep(REQUEST_SLEEP_SECONDS)
    payload = json.loads(text)
    body = payload.get("jsonResult", {}).get("body", [])
    return [{"CODE": str(item["CODE"]), "NAME": str(item["NAME"])} for item in body]


def post_report(menu_id: str, statement_id: str, election_code: str, extra: dict[str, str]) -> str:
    data = {
        "electionId": ELECTION_ID,
        "requestURI": f"/electioninfo/{ELECTION_ID}/vc/{menu_id.lower()}.jsp",
        "topMenuId": "VC",
        "secondMenuId": menu_id,
        "menuId": menu_id,
        "statementId": statement_id,
        "electionCode": election_code,
        "cityCode": "-1",
        "townCode": "-1",
        "sggCityCode": "0" if menu_id == "VCCP09" else "-1",
        "townCodeFromSgg": "-1",
        "sggTownCode": "0" if menu_id == "VCCP09" else "-1",
        "searchType": "0",
    }
    data.update({key: str(value) for key, value in extra.items()})
    html = fetch_text(f"{BASE_URL}/electioninfo/electionInfo_report.xhtml", data=data)
    time.sleep(REQUEST_SLEEP_SECONDS)
    return html


def vccp08_statement(election_code: str, fields: dict[str, str]) -> str:
    sgg_city_code = str(fields.get("sggCityCode", ""))
    town_from_sgg = str(fields.get("townCodeFromSgg", ""))
    sgg_town_code = str(fields.get("sggTownCode", ""))

    if election_code == "2":
        if sgg_city_code == "2530301":
            return "VCCP08_#00_S"
        if sgg_city_code == "2530901" and town_from_sgg == "5303":
            return "VCCP08_#00_S"
    if election_code == "5" and sgg_town_code in SPECIAL_VCCP08_SGGTOWN:
        return "VCCP08_#00_S"
    return "VCCP08_#00"


def parse_vccp08(html: str) -> dict[str, Any]:
    rows = parse_table(html)
    header, body = split_header_body(rows)
    candidate_names = header[1] if len(header) > 1 else []

    data_rows: list[dict[str, Any]] = []
    for row in body:
        if not row or "검색된 결과가 없습니다" in " ".join(row):
            continue
        if len(row) < 4:
            continue
        candidate_count = max(0, min(len(candidate_names), len(row) - 6))
        candidates: list[dict[str, Any]] = []
        for idx, name in enumerate(candidate_names[:candidate_count]):
            candidates.append({"name": name, "votes": to_int(row[4 + idx])})
        total_candidate = next((candidate for candidate in candidates if candidate["name"] == "계"), None)
        extra_start = 4 + candidate_count
        valid_votes = total_candidate["votes"] if total_candidate else None
        if total_candidate is None and len(row) > extra_start:
            valid_votes = to_int(row[extra_start])
            extra_start += 1

        area_val = row[0]
        ballot_val = row[1]
        if not clean_text(ballot_val):
            normalized_area = normalize_ballot_type(area_val)
            if normalized_area:
                ballot_val = normalized_area

        data_rows.append(
            {
                "area": area_val,
                "ballotType": ballot_val,
                "electors": to_int(row[2]),
                "votes": to_int(row[3]),
                "candidateVotes": candidates,
                "validVotes": valid_votes,
                "invalidVotes": to_int(row[extra_start]) if len(row) > extra_start else None,
                "abstentions": to_int(row[extra_start + 1]) if len(row) > extra_start + 1 else None,
            }
        )

    return {
        "candidates": [name for name in candidate_names if name and name != "계"],
        "rows": data_rows,
    }


def parse_vccp09(html: str) -> dict[str, Any]:
    rows = parse_table(html)
    _, body = split_header_body(rows)
    if not body:
        return {"candidates": [], "rows": []}

    candidate_names: list[str] = []
    candidate_start = 3
    candidate_header_index = -1
    candidate_total_index = -1
    for idx, row in enumerate(body):
        if "계" in row:
            candidate_header_index = idx
            candidate_total_index = row.index("계")
            break

    if candidate_header_index >= 0:
        for row in body[candidate_header_index + 1 :]:
            if to_float(row[-1] if row else None) is None:
                continue
            numeric_indices = [index for index, cell in enumerate(row) if to_float(cell) is not None]
            if len(numeric_indices) >= 2:
                candidate_start = numeric_indices[1] + 1
                break
        if candidate_start <= candidate_total_index:
            candidate_names = body[candidate_header_index][candidate_start : candidate_total_index + 1]
        start_index = candidate_header_index + 1
    else:
        start_index = 0

    progress_rows: list[dict[str, Any]] = []
    index = start_index
    while index < len(body):
        row = body[index]
        joined = " ".join(row)
        if "검색된 결과가 없습니다" in joined:
            index += 1
            continue
        progress_rate = to_float(row[-1] if row else None)
        if progress_rate is None:
            index += 1
            continue
        numeric_indices = [cell_index for cell_index, cell in enumerate(row) if to_float(cell) is not None]
        if len(numeric_indices) < 2:
            index += 1
            continue

        area_cells = [clean_text(cell) for cell in row[: numeric_indices[0]] if clean_text(cell)]
        area = area_cells[-1] if area_cells else "합계"
        group_area = area_cells[0] if len(area_cells) > 1 else None
        full_area = " ".join(area_cells) if area_cells else area

        candidate_count = len(candidate_names)
        if candidate_count == 0:
            candidate_start = numeric_indices[1] + 1
            candidate_count = max(0, len(row) - candidate_start - 3)
            candidate_names = [f"후보 {i + 1}" for i in range(candidate_count)]

        rate_row: list[str] | None = None
        if index + 1 < len(body) and body[index + 1] and not clean_text(body[index + 1][0]):
            rate_row = body[index + 1]
            index += 1

        candidates: list[dict[str, Any]] = []
        for idx, name in enumerate(candidate_names[:candidate_count]):
            rate = None
            if rate_row and len(rate_row) > candidate_start + idx:
                rate = to_float(rate_row[candidate_start + idx])
            candidates.append(
                {
                    "name": name,
                    "votes": to_int(row[candidate_start + idx]) if len(row) > candidate_start + idx else None,
                    "rate": rate,
                }
            )
        total_candidate = next((candidate for candidate in candidates if candidate["name"] == "계"), None)
        extra_start = candidate_start + candidate_count
        valid_votes = total_candidate["votes"] if total_candidate else None
        if total_candidate is None and len(row) > extra_start:
            valid_votes = to_int(row[extra_start])
            extra_start += 1

        progress_rows.append(
            {
                "area": area,
                "groupArea": group_area,
                "fullArea": full_area,
                "electors": to_int(row[numeric_indices[0]]) if len(row) > numeric_indices[0] else None,
                "votes": to_int(row[numeric_indices[1]]) if len(row) > numeric_indices[1] else None,
                "candidateVotes": candidates,
                "validVotes": valid_votes,
                "invalidVotes": to_int(row[extra_start]) if len(row) > extra_start else None,
                "abstentions": to_int(row[extra_start + 1]) if len(row) > extra_start + 1 else None,
                "progressRate": progress_rate,
            }
        )
        index += 1

    return {
        "candidates": [name for name in candidate_names if name and name != "계"],
        "rows": progress_rows,
    }


def normalize_ballot_type(value: str) -> str:
    value = clean_text(value)
    if not value or value == "계":
        return ""
    if "관내" in value and "사전" in value:
        return "관내사전투표"
    if "관외" in value and "사전" in value:
        return "관외사전투표"
    if "선거일" in value:
        return "선거일투표"
    if "거소" in value:
        return "거소투표"
    if "선상" in value:
        return "선상투표"
    if "재외" in value:
        return "재외투표"
    if "잘못" in value or "투입" in value:
        return "별도분류"
    return value


def row_numeric_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "electors": row.get("electors"),
        "votes": row.get("votes"),
        "validVotes": row.get("validVotes"),
        "invalidVotes": row.get("invalidVotes"),
        "abstentions": row.get("abstentions"),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if row.get("area") == "합계":
            return row_numeric_summary(row)

    totals = {
        "electors": None,
        "votes": None,
        "validVotes": None,
        "invalidVotes": None,
        "abstentions": None,
    }
    source_rows = [row for row in rows if row.get("ballotType") == "계"] or rows
    for row in source_rows:
        for key in totals:
            totals[key] = add_number(totals[key], row.get(key))
    return totals


def aggregate_ballot_types(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for unit in units:
        for row in unit.get("rows", []):
            ballot_type = normalize_ballot_type(str(row.get("ballotType", "")))
            if not ballot_type:
                continue
            bucket = totals.setdefault(
                ballot_type,
                {
                    "type": ballot_type,
                    "electors": None,
                    "votes": None,
                    "validVotes": None,
                    "invalidVotes": None,
                    "abstentions": None,
                    "rowCount": 0,
                    "unitCount": 0,
                    "units": set(),
                },
            )
            for key in ["electors", "votes", "validVotes", "invalidVotes", "abstentions"]:
                bucket[key] = add_number(bucket[key], row.get(key))
            bucket["rowCount"] += 1
            bucket["units"].add(unit["id"])

    ordered = []
    for ballot_type in TARGET_BALLOT_TYPES:
        if ballot_type in totals:
            ordered.append(totals.pop(ballot_type))
        else:
            ordered.append(
                {
                    "type": ballot_type,
                    "electors": None,
                    "votes": 0,
                    "validVotes": None,
                    "invalidVotes": None,
                    "abstentions": None,
                    "rowCount": 0,
                    "unitCount": 0,
                    "units": set(),
                }
            )

    ordered.extend(sorted(totals.values(), key=lambda item: item["type"]))
    for item in ordered:
        item["unitCount"] = len(item["units"])
        item["units"] = sorted(item["units"])
        item["started"] = bool(item.get("votes"))
    return ordered


def aggregate_summaries(units: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "electors": None,
        "votes": None,
        "validVotes": None,
        "invalidVotes": None,
        "abstentions": None,
    }
    for unit in units:
        summary = unit.get("summary", {})
        for key in totals:
            totals[key] = add_number(totals[key], summary.get(key))
    return totals


def make_signal(ballot_types: list[dict[str, Any]]) -> dict[str, Any]:
    target = [item for item in ballot_types if item["type"] in TARGET_BALLOT_TYPES]
    active = [item for item in target if item.get("started")]
    leading = None
    if active:
        leading = max(active, key=lambda item: item.get("votes") or 0)["type"]
    return {
        "targetTypes": TARGET_BALLOT_TYPES,
        "activeTargetTypes": [item["type"] for item in active],
        "leadingTypeByVotes": leading,
        "hasAnyTargetTypeStarted": bool(active),
        "statusByType": {
            item["type"]: {
                "started": bool(item.get("started")),
                "votes": item.get("votes") or 0,
                "rows": item.get("rowCount") or 0,
            }
            for item in target
        },
    }


def progress_row_matches(row: dict[str, Any], name: str) -> bool:
    values = {
        clean_text(str(row.get("area") or "")),
        clean_text(str(row.get("groupArea") or "")),
        clean_text(str(row.get("fullArea") or "")),
    }
    values.discard("")
    return name in values


def find_progress_row(
    rows: list[dict[str, Any]],
    names: list[str],
    used_indexes: set[int] | None = None,
) -> dict[str, Any] | None:
    cleaned_names = [clean_text(name) for name in names if clean_text(name)]
    for name in cleaned_names:
        for index, row in enumerate(rows):
            if used_indexes and index in used_indexes:
                continue
            if progress_row_matches(row, name):
                return row
    for name in cleaned_names:
        for index, row in enumerate(rows):
            if used_indexes and index in used_indexes:
                continue
            full_area = clean_text(str(row.get("fullArea") or ""))
            if full_area.startswith(name + " "):
                return row
    return None


def choose_progress_summary(parsed: dict[str, Any], preferred_names: list[str]) -> dict[str, Any] | None:
    rows = parsed.get("rows", [])
    if not rows:
        return None
    for name in ["합계", *preferred_names]:
        match = find_progress_row(rows, [name])
        if match:
            return match

    totals = {
        "area": "합계",
        "electors": None,
        "votes": None,
        "candidateVotes": [],
        "validVotes": None,
        "invalidVotes": None,
        "abstentions": None,
        "progressRate": None,
    }
    rates: list[float] = []
    for row in rows:
        for key in ["electors", "votes", "validVotes", "invalidVotes", "abstentions"]:
            totals[key] = add_number(totals[key], row.get(key))
        if row.get("progressRate") is not None:
            rates.append(float(row["progressRate"]))
    if rates:
        totals["progressRate"] = round(sum(rates) / len(rates), 2)
    return totals


def attach_progress_to_units(units: list[dict[str, Any]], progress_rows: list[dict[str, Any]]) -> None:
    used_indexes: set[int] = set()
    for unit in units:
        names = [unit.get("name", ""), *(unit.get("progressNames") or [])]
        if " / " in unit.get("name", ""):
            names.append(unit["name"].split(" / ", 1)[0])
        match = find_progress_row(progress_rows, names, used_indexes)
        unit["progress"] = match
        if match is not None:
            used_indexes.add(progress_rows.index(match))


def aggregate_ballot_types_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unit = {"id": "rows", "rows": rows}
    return aggregate_ballot_types([unit])


def find_total_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    total = next((row for row in rows if row.get("area") == "합계"), None)
    if total: return total
    total = next((row for row in rows if row.get("ballotType") == "계"), None)
    if total: return total
    if len(rows) == 1:
        return rows[0]
    return None


def area_detail(name: str, rows: list[dict[str, Any]], progress_row: dict[str, Any] | None) -> dict[str, Any]:
    total_row = find_total_row(rows)
    source_row = total_row or progress_row or {}
    return {
        "name": name,
        "progress": progress_row,
        "summary": row_numeric_summary(source_row),
        "candidateVotes": source_row.get("candidateVotes", []),
        "ballotTypes": aggregate_ballot_types_from_rows(rows),
    }


def dong_details(unit: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_names: list[str] = []
    for row in unit.get("rows", []):
        area = row.get("area")
        if not area or area == "합계":
            continue
        if area not in ordered_names and (row.get("ballotType") == "계" or normalize_ballot_type(row.get("ballotType", ""))):
            ordered_names.append(area)

    details = []
    for name in ordered_names:
        rows = [row for row in unit.get("rows", []) if row.get("area") == name]
        details.append(area_detail(name, rows, None))
    return details


def build_local_breakdown(units: list[dict[str, Any]], progress_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_name = {unit["name"]: unit for unit in units}
    if not any(name in by_name for name in [TOWN_SUJEONG_NAME, TOWN_JUNGWON_NAME, TOWN_BUNDANG_NAME]):
        return None

    summary_regions = []
    for name in [TOWN_SUJEONG_NAME, TOWN_JUNGWON_NAME]:
        unit = by_name.get(name)
        progress_row = find_progress_row(progress_rows, [name])
        if unit:
            summary_regions.append(area_detail(name, unit.get("rows", []), progress_row))
        elif progress_row:
            summary_regions.append(area_detail(name, [], progress_row))

    bundang_unit = by_name.get(TOWN_BUNDANG_NAME)
    bundang_progress = find_progress_row(progress_rows, [TOWN_BUNDANG_NAME])
    bundang_summary = area_detail(TOWN_BUNDANG_NAME, bundang_unit.get("rows", []) if bundang_unit else [], bundang_progress)
    bundang_dongs = dong_details(bundang_unit) if bundang_unit else []

    return {
        "summaryRegions": summary_regions,
        "bundangSummary": bundang_summary,
        "bundangDongs": bundang_dongs,
    }


def fetch_vccp08_unit(
    *,
    unit_id: str,
    unit_name: str,
    election_code: str,
    fields: dict[str, str],
) -> dict[str, Any]:
    html = post_report("VCCP08", vccp08_statement(election_code, fields), election_code, fields)
    parsed = parse_vccp08(html)
    return {
        "id": unit_id,
        "name": unit_name,
        "query": fields,
        "candidates": parsed["candidates"],
        "rows": parsed["rows"],
        "summary": summarize_rows(parsed["rows"]),
    }


def with_unit_metadata(result: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key in ["cityName", "progressNames"]:
        if key in source:
            result[key] = source[key]
    return result


def fetch_progress(election_code: str, fields: dict[str, str], preferred_names: list[str]) -> dict[str, Any]:
    html = post_report("VCCP09", VCCP09_STATEMENTS[election_code], election_code, fields)
    parsed = parse_vccp09(html)
    return {
        "query": fields,
        "candidates": parsed["candidates"],
        "rows": parsed["rows"],
        "summary": choose_progress_summary(parsed, preferred_names),
    }


def get_town_codes(city_code: str) -> list[dict[str, str]]:
    return fetch_json(
        "/bizcommon/selectbox/selectbox_townCodeJson.json",
        {"electionId": ELECTION_ID, "cityCode": city_code},
    )


def get_sgg_city_codes(election_code: str, city_code: str) -> list[dict[str, str]]:
    return fetch_json(
        "/bizcommon/selectbox/selectbox_getSggCityCodeJson.json",
        {"electionId": ELECTION_ID, "electionCode": election_code, "cityCode": city_code},
    )


def get_town_codes_from_sgg(election_code: str, sgg_city_code: str) -> list[dict[str, str]]:
    return fetch_json(
        "/bizcommon/selectbox/selectbox_townCodeFromSggJson.json",
        {"electionId": ELECTION_ID, "electionCode": election_code, "sggCityCode": sgg_city_code},
    )


def get_sgg_town_codes(election_code: str, town_code: str) -> list[dict[str, str]]:
    return fetch_json(
        "/bizcommon/selectbox/selectbox_getSggTownCodeJson.json",
        {"electionId": ELECTION_ID, "electionCode": election_code, "townCode": town_code},
    )


def get_city_codes_by_election(election_code: str) -> list[dict[str, str]]:
    return fetch_json(
        "/bizcommon/selectbox/selectbox_cityCodeBySgJson.json",
        {"electionId": ELECTION_ID, "electionCode": election_code},
    )


@dataclass
class ScopeSpec:
    id: str
    election_code: str
    election_name: str
    scope_name: str
    focus_level: str
    progress_fields: dict[str, str]
    progress_preferred_names: list[str]
    units: list[dict[str, Any]] = field(default_factory=list)
    local_units: list[dict[str, Any]] = field(default_factory=list)
    include_local_breakdown: bool = False


def seongnam_town_units(prefix: str, election_code: str, *, sgg_city_code: str | None = None) -> list[dict[str, Any]]:
    units = []
    for town in SEONGNAM_TOWNS:
        if election_code in {"4", "9"}:
            fields = {
                "cityCode": CITY_GYEONGGI,
                "sggCityCode": sgg_city_code or "",
                "townCodeFromSgg": town["CODE"],
            }
        else:
            fields = {
                "cityCode": CITY_GYEONGGI,
                "townCode": town["CODE"],
            }
        units.append(
            {
                "id": f"{prefix}-{town['CODE']}",
                "name": town["NAME"],
                "fields": fields,
            }
        )
    return units


def static_scope_specs() -> list[ScopeSpec]:
    return [
        ScopeSpec(
            id="governor-gyeonggi",
            election_code="3",
            election_name="시·도지사선거",
            scope_name="경기도",
            focus_level="경기도",
            progress_fields={"cityCode": CITY_GYEONGGI, "sggCityCode": "0", "townCode": "-1", "sggTownCode": "0"},
            progress_preferred_names=["경기도", "합계"],
            units=[
                {
                    "id": "governor-gyeonggi",
                    "name": "경기도",
                    "fields": {"cityCode": CITY_GYEONGGI, "townCode": "0"},
                }
            ],
            local_units=seongnam_town_units("governor-seongnam", "3"),
            include_local_breakdown=True,
        ),
        ScopeSpec(
            id="metropolitan-pr-gyeonggi",
            election_code="8",
            election_name="광역의원비례대표선거",
            scope_name="경기도",
            focus_level="경기도",
            progress_fields={"cityCode": CITY_GYEONGGI, "sggCityCode": "0", "townCode": "-1", "sggTownCode": "0"},
            progress_preferred_names=["경기도", "합계"],
            units=[
                {
                    "id": "metropolitan-pr-gyeonggi",
                    "name": "경기도",
                    "fields": {"cityCode": CITY_GYEONGGI, "townCode": "0"},
                }
            ],
            local_units=seongnam_town_units("metropolitan-pr-seongnam", "8"),
            include_local_breakdown=True,
        ),
        ScopeSpec(
            id="education-gyeonggi",
            election_code="11",
            election_name="교육감선거",
            scope_name="경기도",
            focus_level="경기도",
            progress_fields={"cityCode": CITY_GYEONGGI, "sggCityCode": "0", "townCode": "-1", "sggTownCode": "0"},
            progress_preferred_names=["경기도", "합계"],
            units=[
                {
                    "id": "education-gyeonggi",
                    "name": "경기도",
                    "fields": {"cityCode": CITY_GYEONGGI, "townCode": "0"},
                }
            ],
            local_units=seongnam_town_units("education-seongnam", "11"),
            include_local_breakdown=True,
        ),
    ]


def dynamic_scope_specs() -> list[ScopeSpec]:
    specs: list[ScopeSpec] = []

    mayor_sgg = next(
        (item for item in get_sgg_city_codes("4", CITY_GYEONGGI) if item["NAME"] == "성남시"),
        {"CODE": "4410600", "NAME": "성남시"},
    )
    mayor_units = [
        {
            "id": f"mayor-seongnam-{town['CODE']}",
            "name": town["NAME"],
            "fields": {
                "cityCode": CITY_GYEONGGI,
                "sggCityCode": mayor_sgg["CODE"],
                "townCodeFromSgg": town["CODE"],
            },
        }
        for town in get_town_codes_from_sgg("4", mayor_sgg["CODE"])
    ]
    specs.append(
        ScopeSpec(
            id="mayor-seongnam",
            election_code="4",
            election_name="구·시·군의 장선거",
            scope_name="성남시",
            focus_level="성남시",
            progress_fields={"cityCode": CITY_GYEONGGI, "sggCityCode": mayor_sgg["CODE"]},
            progress_preferred_names=["성남시", "소계"],
            units=mayor_units,
            local_units=mayor_units,
            include_local_breakdown=True,
        )
    )

    provincial_units = [
        {
            "id": f"provincial-council-bundang-{sgg['CODE']}",
            "name": sgg["NAME"],
            "fields": {
                "cityCode": CITY_GYEONGGI,
                "townCode": TOWN_BUNDANG,
                "sggTownCode": sgg["CODE"],
            },
        }
        for sgg in get_sgg_town_codes("5", TOWN_BUNDANG)
    ]
    specs.append(
        ScopeSpec(
            id="provincial-council-bundang",
            election_code="5",
            election_name="시·도의회의원선거",
            scope_name="성남시 분당구",
            focus_level="성남시 분당구",
            progress_fields={
                "cityCode": CITY_GYEONGGI,
                "townCode": TOWN_BUNDANG,
                "sggTownCode": "0",
                "sggCityCode": "0",
            },
            progress_preferred_names=[TOWN_BUNDANG_NAME, "성남시 분당구"],
            units=provincial_units,
            local_units=provincial_units,
            include_local_breakdown=True,
        )
    )

    municipal_units = [
        {
            "id": f"municipal-council-bundang-{sgg['CODE']}",
            "name": sgg["NAME"],
            "fields": {
                "cityCode": CITY_GYEONGGI,
                "townCode": TOWN_BUNDANG,
                "sggTownCode": sgg["CODE"],
            },
        }
        for sgg in get_sgg_town_codes("6", TOWN_BUNDANG)
    ]
    specs.append(
        ScopeSpec(
            id="municipal-council-bundang",
            election_code="6",
            election_name="구·시·군의회의원선거",
            scope_name="성남시 분당구",
            focus_level="성남시 분당구",
            progress_fields={
                "cityCode": CITY_GYEONGGI,
                "townCode": TOWN_BUNDANG,
                "sggTownCode": "0",
                "sggCityCode": "0",
            },
            progress_preferred_names=[TOWN_BUNDANG_NAME, "성남시 분당구"],
            units=municipal_units,
            local_units=municipal_units,
            include_local_breakdown=True,
        )
    )

    basic_pr_sgg = next(
        (item for item in get_sgg_city_codes("9", CITY_GYEONGGI) if item["NAME"] == "성남시"),
        {"CODE": "9410600", "NAME": "성남시"},
    )
    basic_pr_units = [
        {
            "id": f"basic-pr-seongnam-{town['CODE']}",
            "name": town["NAME"],
            "fields": {
                "cityCode": CITY_GYEONGGI,
                "sggCityCode": basic_pr_sgg["CODE"],
                "townCodeFromSgg": town["CODE"],
            },
        }
        for town in get_town_codes_from_sgg("9", basic_pr_sgg["CODE"])
    ]
    specs.append(
        ScopeSpec(
            id="basic-pr-seongnam",
            election_code="9",
            election_name="기초의원비례대표선거",
            scope_name="성남시",
            focus_level="성남시",
            progress_fields={"cityCode": CITY_GYEONGGI, "sggCityCode": basic_pr_sgg["CODE"]},
            progress_preferred_names=["성남시", "소계"],
            units=basic_pr_units,
            local_units=basic_pr_units,
            include_local_breakdown=True,
        )
    )

    return specs


def national_assembly_scope() -> ScopeSpec:
    units: list[dict[str, Any]] = []
    for city in get_city_codes_by_election("2"):
        sggs = get_sgg_city_codes("2", city["CODE"])
        for sgg in sggs:
            towns = get_town_codes_from_sgg("2", sgg["CODE"])
            for town in towns:
                unit_name = sgg["NAME"] if len(towns) == 1 else f"{sgg['NAME']} / {town['NAME']}"
                units.append(
                    {
                        "id": f"national-assembly-{city['CODE']}-{sgg['CODE']}-{town['CODE']}",
                        "name": unit_name,
                        "cityName": city["NAME"],
                        "progressNames": [sgg["NAME"], town["NAME"], unit_name],
                        "fields": {
                            "cityCode": city["CODE"],
                            "sggCityCode": sgg["CODE"],
                            "townCodeFromSgg": town["CODE"],
                        },
                    }
                )

    return ScopeSpec(
        id="national-assembly-all",
        election_code="2",
        election_name="국회의원선거",
        scope_name="전체 선거구",
        focus_level="전국",
        progress_fields={"cityCode": "0", "sggCityCode": "0"},
        progress_preferred_names=["합계"],
        units=units,
    )


def build_scope(spec: ScopeSpec) -> dict[str, Any]:
    print(f"Fetching {spec.election_name} / {spec.scope_name} ({len(spec.units)} result unit(s))", file=sys.stderr)
    progress = fetch_progress(spec.election_code, spec.progress_fields, spec.progress_preferred_names)

    units: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    
    UNCONTESTED_UNITS = {"성남시사선거구", "성남시아선거구", "성남시자선거구", "성남시카선거구"}

    for unit in spec.units:
        if clean_text(unit["name"]) in UNCONTESTED_UNITS:
            continue
        try:
            units.append(
                with_unit_metadata(
                fetch_vccp08_unit(
                    unit_id=unit["id"],
                    unit_name=unit["name"],
                    election_code=spec.election_code,
                    fields=unit["fields"],
                ),
                    unit,
                )
            )
        except Exception as exc:  # noqa: BLE001 - collect partial scraper failures.
            errors.append({"unit": unit["name"], "message": str(exc)})

    attach_progress_to_units(units, progress.get("rows", []))
    local_units = units if spec.local_units == spec.units else []
    if spec.include_local_breakdown and not local_units:
        print(f"Fetching local Seongnam detail for {spec.election_name}", file=sys.stderr)
        for unit in spec.local_units:
            if clean_text(unit["name"]) in UNCONTESTED_UNITS:
                continue
            try:
                local_units.append(
                    with_unit_metadata(
                    fetch_vccp08_unit(
                        unit_id=unit["id"],
                        unit_name=unit["name"],
                        election_code=spec.election_code,
                        fields=unit["fields"],
                    ),
                        unit,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - collect partial scraper failures.
                errors.append({"unit": unit["name"], "message": str(exc)})
        attach_progress_to_units(local_units, progress.get("rows", []))

    ballot_types = aggregate_ballot_types(units)
    result_summary = aggregate_summaries(units)
    local_breakdown = build_local_breakdown(local_units, progress.get("rows", [])) if spec.include_local_breakdown else None

    scope = {
        "id": spec.id,
        "electionCode": spec.election_code,
        "electionName": spec.election_name,
        "scopeName": spec.scope_name,
        "focusLevel": spec.focus_level,
        "progress": progress,
        "resultSummary": result_summary,
        "ballotTypes": ballot_types,
        "signal": make_signal(ballot_types),
        "units": units,
        "errors": errors,
    }
    if local_breakdown:
        scope["localBreakdown"] = local_breakdown
    return scope


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"snapshots": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict) and isinstance(payload.get("snapshots"), list):
                return payload
    except json.JSONDecodeError:
        pass
    return {"snapshots": []}


def append_history(history: dict[str, Any], latest: dict[str, Any], limit: int) -> dict[str, Any]:
    snapshot = {
        "generatedAt": latest["generatedAt"],
        "scopes": [
            {
                "id": scope["id"],
                "electionName": scope["electionName"],
                "scopeName": scope["scopeName"],
                "progressRate": (scope.get("progress", {}).get("summary") or {}).get("progressRate"),
                "activeTargetTypes": scope.get("signal", {}).get("activeTargetTypes", []),
                "typeVotes": {
                    item["type"]: item.get("votes") or 0
                    for item in scope.get("ballotTypes", [])
                    if item["type"] in TARGET_BALLOT_TYPES
                },
            }
            for scope in latest.get("scopes", [])
        ],
    }

    snapshots = history.get("snapshots", [])
    snapshots = [item for item in snapshots if item.get("generatedAt") != snapshot["generatedAt"]]
    snapshots.append(snapshot)
    snapshots = snapshots[-limit:]
    return {"snapshots": snapshots}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_latest() -> dict[str, Any]:
    generated_at = datetime.now(SEOUL_TZ).replace(microsecond=0).isoformat()
    started_at_monotonic = time.monotonic()

    specs = [*static_scope_specs(), *dynamic_scope_specs(), national_assembly_scope()]
    scopes = [build_scope(spec) for spec in specs]

    any_errors = [error for scope in scopes for error in scope.get("errors", [])]
    return {
        "generatedAt": generated_at,
        "electionId": ELECTION_ID,
        "source": {
            "name": "중앙선거관리위원회 선거통계시스템",
            "documentUrl": (
                f"{BASE_URL}/main/showDocument.xhtml?"
                f"electionId={ELECTION_ID}&topMenuId=VC&secondMenuId=VCCP08"
            ),
            "progressUrl": (
                f"{BASE_URL}/main/showDocument.xhtml?"
                f"electionId={ELECTION_ID}&topMenuId=VC&secondMenuId=VCCP09"
            ),
        },
        "notes": [
            "개표율은 VCCP09 개표진행상황에서 가져옵니다.",
            "투표 구분별 신호는 VCCP08 개표단위별 개표결과의 관내사전투표/선거일투표/관외사전투표 행을 기준으로 합니다.",
            "VCCP08의 선거인수는 NEC 안내에 따라 전체 선거인수가 아니라 개표·집계 완료분의 선거인수입니다.",
        ],
        "targetBallotTypes": TARGET_BALLOT_TYPES,
        "scopes": scopes,
        "errorCount": len(any_errors),
        "durationSeconds": round(time.monotonic() - started_at_monotonic, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="public/data/latest.json", help="Path for latest JSON output.")
    parser.add_argument("--history", default="public/data/history.json", help="Path for history JSON output.")
    parser.add_argument("--history-limit", type=int, default=288, help="Maximum snapshots to retain.")
    args = parser.parse_args()

    latest = build_latest()
    output_path = Path(args.output)
    history_path = Path(args.history)
    history = append_history(load_history(history_path), latest, args.history_limit)

    write_json(output_path, latest)
    write_json(history_path, history)
    print(f"Wrote {output_path} and {history_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
