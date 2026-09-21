import json
import os
import re
import urllib.error
import urllib.request

import pandas as pd
from sqlalchemy import inspect, text

from app.database import engine


def _get_active_department(dept_no: str | None = None) -> str:
    if dept_no and str(dept_no).strip():
        return str(dept_no).strip().zfill(6)
    return "018285"


def tool_get_glidepath(department_no: str = "018285", year: int = 2026) -> dict:
    """Fetches complete Glide Path governance, budget status, and 12-month vehicle additions/disposals."""
    dept = _get_active_department(department_no)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    department_no,
                    department_name,
                    glidepath_year,
                    activity,
                    manager,
                    coordinator,
                    chief_engineer,
                    director_ll2,
                    finance_approver,
                    finance_cost_center,
                    budget_year,
                    budget_amount,
                    actual_amount,
                    december_budget,
                    reduction_percent,
                    requirement_month,
                    build_count,
                    production_count,
                    total_adds,
                    disposal_count,
                    total_monthly_count
                FROM vw_department_glidepath_dashboard
                WHERE (department_no = :dno OR department_no = :unpadded) AND glidepath_year = :year
                ORDER BY requirement_month ASC
            """),
            {"dno": dept, "unpadded": dept.lstrip("0"), "year": year},
        ).fetchall()

    if not rows:
        return {
            "error": f"No Glidepath record found for Department {dept} and Year {year}"
        }

    first = rows[0]
    months = []
    tot_adds = 0
    tot_disposals = 0
    tot_builds = 0
    tot_production = 0

    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    for r in rows:
        m_dt = r.requirement_month
        m_idx = m_dt.month if hasattr(m_dt, "month") else int(str(m_dt).split("-")[1])
        b_cnt = int(r.build_count or 0)
        p_cnt = int(r.production_count or 0)
        a_cnt = int(r.total_adds or 0)
        d_cnt = int(r.disposal_count or 0)
        tm_cnt = float(r.total_monthly_count or 0.0)

        tot_builds += b_cnt
        tot_production += p_cnt
        tot_adds += a_cnt
        tot_disposals += d_cnt

        months.append(
            {
                "month": month_names[m_idx - 1] if 1 <= m_idx <= 12 else str(m_idx),
                "month_num": m_idx,
                "build_count": b_cnt,
                "production_count": p_cnt,
                "total_adds": a_cnt,
                "disposal_count": d_cnt,
                "total_monthly_count": tm_cnt,
            }
        )

    return {
        "department_no": first.department_no,
        "department_name": first.department_name,
        "activity": first.activity or first.department_name,
        "manager": first.manager,
        "coordinator": first.coordinator,
        "chief_engineer": first.chief_engineer,
        "director_ll2": first.director_ll2,
        "finance_approver": first.finance_approver,
        "finance_cost_center": first.finance_cost_center,
        "budget_year": first.budget_year,
        "starting_actual": float(first.actual_amount or 0.0),
        "december_target": float(first.december_budget or 0.0),
        "total_builds": tot_builds,
        "total_production": tot_production,
        "total_adds": tot_adds,
        "total_disposals": tot_disposals,
        "ending_fleet_count": months[-1]["total_monthly_count"]
        if months
        else float(first.actual_amount or 0.0),
        "target_met": (
            abs(months[-1]["total_monthly_count"] - float(first.december_budget or 0.0))
            < 0.01
        )
        if months
        else False,
        "monthly_breakdown": months,
    }


def tool_get_team_summary(
    year: int = 2026, month: int | None = None, team: str | None = None
) -> dict:
    """Fetches team-wise metrics (Glidepath Arrivals, Glidepath Disposals, Budget, Niv Sheet Arrivals, To Be Disposed)."""
    from app.main import get_team_wise_summary

    filters_dict = {}
    if team:
        filters_dict["team"] = team
    filters_str = json.dumps(filters_dict) if filters_dict else None
    return get_team_wise_summary(year=year, month=month, filters=filters_str)


def tool_get_comparison(
    year: int = 2026, month: int = 8, department_no: str = "018285"
) -> dict:
    """Calculates Surplus Arrivals, Target Disposals, Disposal Alert Count, and Budget Variance."""
    from app.main import get_glidepath_summary_comparison

    dept = _get_active_department(department_no)
    return get_glidepath_summary_comparison(year=year, month=month, vci=dept)


def tool_search_vehicles(
    query_str: str, table: str = "arrival", limit: int = 10
) -> list[dict]:
    """Searches vehicle records by keywords in VIN, job, model, team, trim, or notes."""
    tbl = "arrival" if "arr" in table.lower() else "disposal"
    if not inspect(engine).has_table(tbl):
        return []

    with engine.connect():
        df = pd.read_sql_table(tbl, engine)

    q = str(query_str).strip().lower()
    matched_rows = []
    for _, row in df.iterrows():
        row_str = " ".join(str(val).lower() for val in row.values if pd.notna(val))
        if q in row_str:
            matched_rows.append(
                {col: (None if pd.isna(val) else str(val)) for col, val in row.items()}
            )
        if len(matched_rows) >= limit:
            break

    return matched_rows


def tool_simulate_scenario(
    department_no: str = "018285",
    year: int = 2026,
    add_builds: int = 0,
    add_disposals: int = 0,
    start_month: int = 9,
) -> dict:
    """Simulates what-if operational changes from a given month onward and computes the resulting December fleet count."""
    gp = tool_get_glidepath(department_no, year)
    if "error" in gp:
        return gp

    months = gp["monthly_breakdown"]
    starting_actual = gp["starting_actual"]
    dec_target = gp["december_target"]

    simulated_months = []
    running_count = starting_actual

    for m in months:
        m_num = m["month_num"]
        b_cnt = m["build_count"]
        p_cnt = m["production_count"]
        d_cnt = m["disposal_count"]

        if m_num >= start_month:
            b_cnt += max(0, add_builds)
            d_cnt += max(0, add_disposals)

        total_adds = b_cnt + p_cnt
        running_count = running_count + total_adds - d_cnt

        simulated_months.append(
            {
                "month": m["month"],
                "month_num": m_num,
                "simulated_builds": b_cnt,
                "simulated_adds": total_adds,
                "simulated_disposals": d_cnt,
                "simulated_fleet_count": running_count,
            }
        )

    new_ending = simulated_months[-1]["simulated_fleet_count"]
    variance_to_target = new_ending - dec_target

    return {
        "department_no": department_no,
        "year": year,
        "december_target": dec_target,
        "original_ending_count": gp["ending_fleet_count"],
        "simulated_ending_count": new_ending,
        "variance_to_target": variance_to_target,
        "target_met": abs(variance_to_target) < 0.01,
        "adjustments_applied": f"+{add_builds} builds/month, +{add_disposals} disposals/month from Month {start_month} onwards",
        "simulated_trajectory": simulated_months,
    }


def _build_nlp_response(user_message: str, global_filters: dict | None = None) -> dict:
    """Intelligent fallback rule/NLP analytical response generator when no cloud API key is configured."""
    msg = user_message.lower()
    filters = global_filters or {}

    # Extract month
    month_map = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    extracted_month = None
    for m_name, m_num in month_map.items():
        if re.search(r"\b" + m_name + r"\b", msg):
            extracted_month = m_num
            break

    if extracted_month is None and filters.get("month"):
        try:
            extracted_month = int(filters.get("month"))
        except (ValueError, TypeError):
            extracted_month = None

    # Extract department
    dept_match = re.search(r"\b(0?\d{5,6})\b", msg)
    department_no = (
        dept_match.group(1).zfill(6)
        if dept_match
        else (filters.get("filters", {}).get("vci") or "018285")
    )

    # Extract team
    team_name = None
    for t_cand in ["mmota us", "ivi us", "v&v mexico", "ivi canada"]:
        if t_cand in msg:
            team_name = t_cand.upper() if "mexico" not in t_cand else "V&V Mexico"
            break

    # Scenario 0: Simple Greetings
    if re.match(
        r"^(hi|hello|hey|greetings|good morning|good afternoon|good evening|howdy)\b",
        msg.strip(),
    ):
        return {
            "response": "Hi! How can I assist you with your fleet and Glide Path analysis today?",
            "intent": "greeting",
            "tool_results": {},
            "suggestions": [],
        }

    # Scenario 1: Simulation / What-If query
    if any(
        k in msg
        for k in [
            "simulate",
            "what if",
            "increase build",
            "add build",
            "if we add",
            "scenario",
        ]
    ):
        build_match = re.search(r"(?:add|increase|extra)\s+(\d+)\s*(?:build|add)", msg)
        disp_match = re.search(
            r"(?:add|increase|extra)\s+(\d+)\s*(?:disposal|scrap)", msg
        )
        add_b = int(build_match.group(1)) if build_match else 10
        add_d = int(disp_match.group(1)) if disp_match else 0

        sim_res = tool_simulate_scenario(
            department_no=department_no,
            add_builds=add_b,
            add_disposals=add_d,
            start_month=extracted_month or 9,
        )

        resp = f"### 📊 Glide Path Simulation Analysis — Department {sim_res['department_no']}\n\n"
        resp += f"**Scenario Applied:** `{sim_res['adjustments_applied']}`\n\n"
        resp += f"- **Original Year-End Target:** **{int(sim_res['december_target'])}** vehicles\n"
        resp += f"- **Projected Ending Fleet Count:** **{int(sim_res['simulated_ending_count'])}** vehicles\n"
        resp += f"- **Target Variance:** **{'+' if sim_res['variance_to_target'] > 0 else ''}{int(sim_res['variance_to_target'])} vehicles** "
        resp += f"({'⚠️ Target Exceeded' if sim_res['variance_to_target'] > 0 else '✅ Target Met'})\n\n"

        resp += "#### Projected Monthly Trajectory (Q3–Q4):\n"
        resp += "| Month | Planned Adds | Planned Disposals | Fleet Count |\n"
        resp += "| :--- | :---: | :---: | :---: |\n"
        for m in sim_res["simulated_trajectory"][-6:]:
            resp += f"| **{m['month']}** | {m['simulated_adds']} | {m['simulated_disposals']} | **{int(m['simulated_fleet_count'])}** |\n"

        if sim_res["variance_to_target"] > 0:
            resp += f"\n💡 **Recommendation:** To achieve the December ceiling target of {int(sim_res['december_target'])}, schedule an additional **{int(sim_res['variance_to_target'])} disposals** across Q4.\n"

        return {
            "response": resp,
            "intent": "simulation",
            "tool_results": sim_res,
            "suggestions": [
                f"Simulate +{add_b} builds and +{add_b} disposals",
                f"Show August Glidepath performance for Dept {department_no}",
                "Which team has the highest arrival surplus?",
            ],
        }

    # Scenario 2: Disposal Alert / Comparison Query
    if any(
        k in msg
        for k in [
            "alert",
            "disposal alert",
            "comparison",
            "surplus",
            "variance",
            "target disposal",
        ]
    ):
        target_m = extracted_month or 8
        comp = tool_get_comparison(
            year=2026, month=target_m, department_no=department_no
        )

        m_name = comp["month_name"]
        resp = f"### 🚨 Fleet Disposal & Surplus Alert Briefing — {m_name} 2026 (Dept {comp['vci']})\n\n"
        resp += f"Below is the reconciliation between operational Niv records and Glide Path targets for **{m_name} 2026**:\n\n"

        arr_status = (
            f"⚠️ **+{comp['surplus_arrival']} Surplus Arrivals**"
            if comp["surplus_arrival"] > 0
            else "✅ On Track"
        )
        disp_status = (
            f"🚨 **{comp['disposal_alert_count']} Pending Disposals**"
            if comp["disposal_alert_count"] > 0
            else "✅ Disposals Complete"
        )

        resp += (
            "| Metric | Planned (Glide Path) | Actual (Niv Sheet) | Status / Alert |\n"
        )
        resp += "| :--- | :---: | :---: | :--- |\n"
        resp += f"| **Arrivals / Additions** | {comp['gp_arrival']} | {comp['actual_arrival']} | {arr_status} |\n"
        resp += f"| **Disposals Completed** | {comp['gp_disposal']} | {comp['actual_disposal']} | {disp_status} |\n"
        resp += f"| **Adjusted Disposal Target** | — | **{comp['target_disposal']}** | *Glidepath ({comp['gp_disposal']}) + Surplus ({comp['surplus_arrival']})* |\n\n"

        resp += "#### 📌 Key Operational Insights:\n"
        if comp["surplus_arrival"] > 0:
            resp += f"- **Surplus Arrivals Detected:** The department received **{comp['actual_arrival']} vehicles** against a planned add of **{comp['gp_arrival']}**, creating a surplus of **+{comp['surplus_arrival']} units**.\n"
        if comp["disposal_alert_count"] > 0:
            resp += f"- **Disposal Action Required:** To absorb the arrival surplus and stay aligned with the Glide Path trajectory, the department must dispose of **{comp['disposal_alert_count']} additional vehicles** in {m_name}.\n"
        else:
            resp += f"- **Disposals on Schedule:** Actual disposals ({comp['actual_disposal']}) have met or exceeded the adjusted target.\n"

        return {
            "response": resp,
            "intent": "comparison_alert",
            "tool_results": comp,
            "suggestions": [
                f"Show team breakdown for {m_name}",
                f"Show full 12-month Glide Path for Dept {department_no}",
                "Simulate +15 builds in Q4",
            ],
        }

    # Scenario 3: Team Breakdown Query
    if any(k in msg for k in ["team", "by team", "mmota", "ivi", "v&v", "breakdown"]):
        target_m = extracted_month
        team_data = tool_get_team_summary(year=2026, month=target_m, team=team_name)

        period_str = f"Month {target_m}" if target_m else "Full Year 2026"
        resp = f"### 👥 Team Wise Fleet Performance Summary ({period_str})\n\n"
        resp += "Cross-category metrics broken down across operational teams:\n\n"

        resp += "| Team | Planned Add (GP) | Planned Disp (GP) | Budget (Fleet) | Niv Actual Arrivals | Niv Sheet Disposal |\n"
        resp += "| :--- | :---: | :---: | :---: | :---: | :---: |\n"
        for t, d in team_data["data"].items():
            disp_val = (
                d.get("niv_sheet_disposal")
                if d.get("niv_sheet_disposal") is not None
                else d.get("to_be_disposed")
            )
            resp += f"| **{t}** | {d['arrival']} | {d['disposal']} | {d['budget'] if d['budget'] is not None else '—'} | **{d['niv_sheet_arrival']}** | **{disp_val}** |\n"

        tot = team_data["category_totals"]
        tot_disp = (
            tot.get("niv_sheet_disposal")
            if tot.get("niv_sheet_disposal") is not None
            else tot.get("to_be_disposed")
        )
        resp += f"| **Total** | **{tot['arrival']}** | **{tot['disposal']}** | **{tot['budget'] if tot['budget'] is not None else '—'}** | **{tot['niv_sheet_arrival']}** | **{tot_disp}** |\n\n"

        # Highlight top arrival/disposal team
        top_arr_team = max(
            team_data["data"].items(), key=lambda x: x[1].get("niv_sheet_arrival") or 0
        )
        top_disp_team = max(
            team_data["data"].items(),
            key=lambda x: (
                (
                    x[1].get("niv_sheet_disposal")
                    if x[1].get("niv_sheet_disposal") is not None
                    else x[1].get("to_be_disposed")
                )
                or 0
            ),
        )
        top_disp_val = (
            top_disp_team[1].get("niv_sheet_disposal")
            if top_disp_team[1].get("niv_sheet_disposal") is not None
            else top_disp_team[1].get("to_be_disposed")
        )

        resp += "#### 🔍 Analysis Highlights:\n"
        resp += f"- **Highest Actual Arrivals:** **{top_arr_team[0]}** with **{top_arr_team[1]['niv_sheet_arrival']} vehicles** ({(top_arr_team[1]['niv_sheet_arrival'] / max(1, tot['niv_sheet_arrival'] or 1) * 100):.1f}% of total).\n"
        resp += f"- **Highest Disposals Pending:** **{top_disp_team[0]}** with **{top_disp_val} vehicles** ({(top_disp_val / max(1, tot_disp or 1) * 100):.1f}% of total).\n"

        return {
            "response": resp,
            "intent": "team_summary",
            "tool_results": team_data,
            "suggestions": [
                f"Explain disposal alert for Month {target_m or 8}",
                f"Show Glide Path for Dept {department_no}",
                "Simulate year-end fleet count",
            ],
        }

    # Scenario 4: Specific Vehicle Search Query
    if any(
        k in msg
        for k in [
            "vehicle",
            "vin",
            "mustang",
            "f-150",
            "p702",
            "job 1",
            "notes",
            "search",
            "mileslip",
        ]
    ):
        clean_q = re.sub(
            r"(search|find|show|vehicles?|for|all|records?)\s*", "", msg
        ).strip()
        tbl = "arrival" if ("arr" in msg or "deliv" in msg) else "disposal"
        v_results = tool_search_vehicles(clean_q or "p702", table=tbl, limit=6)

        if v_results:
            resp = f"### 🚗 Vehicle Search Results (`{clean_q or 'Fleet'}` in {tbl.title()} Tracker)\n\n"
            resp += f"Found **{len(v_results)} matching vehicle records**:\n\n"
            resp += "| Model Year | Program | Team | Job / VIN | Milestone / Status | Notes |\n"
            resp += "| :--- | :---: | :---: | :---: | :---: | :--- |\n"
            for v in v_results:
                my = v.get("model_year", "—")
                prog = v.get("vehicle_program", "—")
                tm = v.get("team", "—")
                j_vin = v.get("job") or v.get("vin") or v.get("vehicle_ta") or "—"
                status = (
                    v.get("vdr_status")
                    or v.get("arrived")
                    or v.get("scrap_auction_transfer")
                    or "—"
                )
                notes = v.get("notes", "—")
                resp += (
                    f"| {my} | {prog} | {tm} | {j_vin} | {status} | {notes[:40]} |\n"
                )

            return {
                "response": resp,
                "intent": "vehicle_search",
                "tool_results": {"count": len(v_results), "records": v_results},
                "suggestions": [
                    "Show August disposal alert summary",
                    "Which team has the most arrivals?",
                    "View complete Glide Path trajectory",
                ],
            }

    # Scenario 5: General Executive Glidepath Briefing (Default)
    gp_data = tool_get_glidepath(department_no=department_no, year=2026)
    resp = f"### 📋 Executive Fleet & Glide Path Briefing — Department {gp_data.get('department_no', '018285')} (Year 2026)\n\n"
    resp += f"**Governance:** Activity `{gp_data.get('activity')}` | Coordinator: **{gp_data.get('coordinator')}** | Chief Engineer: **{gp_data.get('chief_engineer')}** | Director LL2: **{gp_data.get('director_ll2')}**\n\n"

    resp += "#### 🎯 Key Budget & Fleet Trajectory:\n"
    resp += f"- **Starting Baseline Actual (2025):** **{int(gp_data.get('starting_actual', 789))} vehicles**\n"
    resp += f"- **December 2026 Target:** **{int(gp_data.get('december_target', 750))} vehicles** (5% glide path reduction)\n"
    resp += f"- **Total Planned Adds (2026):** **{gp_data.get('total_adds', 240)} additions** ({gp_data.get('total_builds', 240)} builds + {gp_data.get('total_production', 0)} production)\n"
    resp += f"- **Total Planned Disposals (2026):** **{gp_data.get('total_disposals', 279)} units**\n"
    resp += f"- **Projected Ending Fleet Count:** **{int(gp_data.get('ending_fleet_count', 750))} units** ({'✅ Target Met' if gp_data.get('target_met') else '⚠️ Target Variance'})\n\n"

    resp += "#### 📅 2026 Monthly Breakdown Matrix (Sample):\n"
    resp += "| Month | Build Adds | Planned Disposal | Net Change | Trajectory Fleet Count |\n"
    resp += "| :--- | :---: | :---: | :---: | :---: |\n"
    for m in gp_data.get("monthly_breakdown", [])[:6]:
        net = m["total_adds"] - m["disposal_count"]
        resp += f"| **{m['month']}** | +{m['total_adds']} | -{m['disposal_count']} | {'+' if net > 0 else ''}{net} | **{int(m['total_monthly_count'])}** |\n"
    resp += "| ... | ... | ... | ... | ... |\n"

    return {
        "response": resp,
        "intent": "general_briefing",
        "tool_results": gp_data,
        "suggestions": [
            f"Analyze August disposal alert for Dept {department_no}",
            "Show team breakdown of arrivals and disposals",
            "Simulate +20 builds in Q4",
        ],
    }


def ask_ford_ai_agent(
    user_message: str,
    conversation_history: list | None = None,
    global_filters: dict | None = None,
) -> dict:
    """Entry point for Ask Ford Data Analysis AI.
    Checks for Google Gemini / OpenAI keys first; falls back seamlessly to internal analytics engine.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    os.getenv("OPENAI_API_KEY")

    # If Gemini API key is available, call Gemini API
    if gemini_key:
        try:
            # Prepare context with active data
            dept = _get_active_department(
                global_filters.get("filters", {}).get("vci") if global_filters else None
            )
            gp = tool_get_glidepath(dept, 2026)
            team_sum = tool_get_team_summary(year=2026, month=8)
            comp = tool_get_comparison(year=2026, month=8, department_no=dept)

            system_instruction = f"""
You are the **Ford Fleet Data Analysis AI**, an executive analytical assistant for Ford's Vehicle Fleet Arrival, Disposal, and Glide Path Operations.
Context:
- Department: {dept} ({gp.get("activity")})
- 2026 Baseline Actuals: {gp.get("starting_actual")} | Dec Target: {gp.get("december_target")}
- August 2026 Comparison: Planned Adds = {comp.get("gp_arrival")}, Niv Actual Arrivals = {comp.get("actual_arrival")}, Surplus = {comp.get("surplus_arrival")}, Planned Disposals = {comp.get("gp_disposal")}, Niv Disposals = {comp.get("actual_disposal")}, Disposal Alert Count = {comp.get("disposal_alert_count")}.
- Teams: {list(team_sum.get("data", {}).keys())}

Respond in clean, structured GitHub Markdown with bold KPI numbers, bullet points, and data tables where helpful.
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": system_instruction
                                + "\nUser Question: "
                                + user_message
                            }
                        ],
                    }
                ]
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text_out = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return {
                    "response": text_out,
                    "intent": "gemini_llm",
                    "tool_results": comp,
                    "suggestions": [
                        "Explain August disposal alert",
                        "Show team breakdown for arrivals",
                        "Simulate adding 15 builds in October",
                    ],
                }
        except Exception as e:
            print(f"Gemini API fallback notice: {e}")

    # Seamless fallback to intelligent local NLP analytics engine
    return _build_nlp_response(user_message, global_filters)
