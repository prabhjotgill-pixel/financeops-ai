import calendar
from typing import Any

import httpx
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    backend_url: str = "http://localhost:8000"


class APIError(Exception):
    pass


def request_json(base_url: str, method: str, path: str, **kwargs: Any) -> Any:
    try:
        with httpx.Client(base_url=base_url, timeout=60.0) as client:
            response = client.request(method, path, **kwargs)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise APIError("Backend request failed") from exc
    if response.status_code >= 400:
        detail = payload.get("detail", {})
        message = (
            detail.get("message", "Request failed")
            if isinstance(detail, dict)
            else str(detail)
        )
        raise APIError(message)
    return payload


def classification_fields(
    category: str | None, catalog: dict[str, Any], cash_flow: bool
) -> dict[str, Any]:
    if category is None:
        return {
            "account_type": None,
            "financial_statement": None,
            "financial_category": None,
        }
    definition = next(
        item for item in catalog["categories"] if item["name"] == category
    )
    return {
        "account_type": definition["account_type"],
        "financial_category": category,
        "financial_statement": "CASH_FLOW"
        if cash_flow
        else definition["default_statement"],
    }


def account_controls(base_url: str, company_id: int) -> None:
    catalog = request_json(base_url, "GET", "/api/v1/accounts/classification-catalog")
    accounts = request_json(base_url, "GET", f"/api/v1/companies/{company_id}/accounts")
    categories = [None, *[item["name"] for item in catalog["categories"]]]
    account_names = {
        item["id"]: f"{item['account_code']} — {item['account_name']}"
        for item in accounts
    }

    with st.expander("Chart of accounts and manual classification"):
        st.caption(
            "Classification changes recalculate all reporting periods. "
            "Cash-flow-only classifications are excluded from these statements."
        )
        if accounts:
            st.table(
                [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "account_code",
                            "account_name",
                            "account_type",
                            "financial_statement",
                            "financial_category",
                            "is_active",
                        )
                    }
                    for item in accounts
                ]
            )
        with st.form(f"create_account_{company_id}"):
            code = st.text_input("Account code")
            name = st.text_input("Account name")
            category = st.selectbox(
                "New account category",
                categories,
                format_func=lambda value: value or "Unclassified",
            )
            cash_flow = st.checkbox("New account is cash-flow-only")
            parent = st.selectbox(
                "Parent account",
                [None, *account_names],
                format_func=lambda value: (
                    account_names[value] if value is not None else "None"
                ),
            )
            create = st.form_submit_button("Create account")
        if create:
            try:
                request_json(
                    base_url,
                    "POST",
                    f"/api/v1/companies/{company_id}/accounts",
                    json={
                        "account_code": code,
                        "account_name": name,
                        "parent_account_id": parent,
                        **classification_fields(category, catalog, cash_flow),
                    },
                )
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
        if accounts:
            selected = st.selectbox(
                "Account to classify",
                accounts,
                format_func=lambda item: account_names[item["id"]],
            )
            with st.form(f"classify_{company_id}_{selected['id']}"):
                category = st.selectbox(
                    "Classification category",
                    categories,
                    index=categories.index(selected["financial_category"]),
                    format_func=lambda value: value or "Unclassified",
                )
                cash_flow = st.checkbox(
                    "Cash-flow-only classification",
                    value=selected["financial_statement"] == "CASH_FLOW",
                )
                active = st.checkbox("Active account", value=selected["is_active"])
                parent = st.selectbox(
                    "Updated parent account",
                    [None, *account_names],
                    index=[None, *account_names].index(selected["parent_account_id"]),
                    format_func=lambda value: (
                        account_names[value] if value is not None else "None"
                    ),
                )
                update = st.form_submit_button("Save classification")
            if update:
                try:
                    request_json(
                        base_url,
                        "PATCH",
                        f"/api/v1/accounts/{selected['id']}",
                        json={
                            "is_active": active,
                            "parent_account_id": parent,
                            **classification_fields(category, catalog, cash_flow),
                        },
                    )
                    st.rerun()
                except APIError as exc:
                    st.error(str(exc))


def show_report(report: dict[str, Any]) -> None:
    st.caption(report["resolved_period"]["label"] + " · " + report["currency"])
    st.table(
        [
            {
                "Metric": result["metric"].replace("_", " ").title(),
                "Value": result["value"]
                if result["value"] is not None
                else "Unavailable",
                "Unit": result["unit"],
                "Status": result["status"],
                "Basis": result["calculation_basis"]["kind"],
                "Reason": result["reason"]["message"] if result["reason"] else "",
            }
            for result in report["results"].values()
        ]
    )
    with st.expander("Data-availability and population warnings"):
        st.table(report["warnings"])
        st.write("Loaded and excluded populations")
        st.json(report["populations"])
    with st.expander("Full result contract and classification snapshots"):
        st.json(report)


def main() -> None:
    st.title("Financial Analysis")
    st.caption(
        "Deterministic results from classified GL transactions. Calculated values "
        "describe the loaded population; incomplete values retain evidence limits; "
        "unavailable values have no reliable calculation."
    )
    base_url = FrontendSettings().backend_url
    try:
        companies = request_json(base_url, "GET", "/api/v1/companies")
        if not companies:
            st.info("Create a company on the Ingestion page first.")
            return
        company = st.selectbox(
            "Company", companies, format_func=lambda item: item["name"]
        )
        company_id = company["id"]
        account_controls(base_url, company_id)
        api_base = f"/api/v1/companies/{company_id}/financials"
        discovery = request_json(base_url, "GET", f"{api_base}/periods")
        currency = st.selectbox(
            "Reporting currency",
            discovery["currencies"],
            index=discovery["currencies"].index(company["currency"]),
        )
        discovery = request_json(
            base_url, "GET", f"{api_base}/periods", params={"currency": currency}
        )
        if not discovery["fiscal_years"]:
            st.info("Import GL transactions in this currency before viewing analysis.")
            return
        fiscal_year = st.selectbox(
            "Financial year (starting year)",
            sorted(discovery["fiscal_years"], reverse=True),
        )
        period_type = st.selectbox("Reporting period", ["year", "quarter", "month"])
        parameters: dict[str, Any] = {
            "fiscal_year": fiscal_year,
            "period_type": period_type,
            "currency": currency,
        }
        if period_type == "quarter":
            parameters["quarter"] = st.selectbox("Fiscal quarter", [1, 2, 3, 4])
        if period_type == "month":
            start = discovery["financial_year_start_month"]
            months = list(range(start, 13)) + list(range(1, start))
            parameters["month"] = st.selectbox(
                "Month", months, format_func=lambda value: calendar.month_name[value]
            )
        reports = {
            name: request_json(base_url, "GET", f"{api_base}/{name}", params=parameters)
            for name in ("pnl", "balance-sheet", "ratios", "metrics")
        }
        tabs = st.tabs(
            [
                "P&L",
                "Balance Sheet",
                "Ratios",
                "Working capital",
                "Period summaries",
                "Source transactions",
            ]
        )
        for tab, name in zip(tabs[:4], reports, strict=True):
            with tab:
                if name == "balance-sheet":
                    st.warning(
                        "These amounts are cumulative classified activity. "
                        "Verified opening and closing balances are unavailable."
                    )
                show_report(reports[name])
        with tabs[4]:
            grouping = st.selectbox("Summary grouping", ["month", "quarter", "year"])
            if st.button("Load period summaries"):
                summary = request_json(
                    base_url,
                    "GET",
                    f"{api_base}/period-summaries",
                    params={
                        "fiscal_year": fiscal_year,
                        "period_type": grouping,
                        "currency": currency,
                    },
                )
                st.table(
                    [
                        {
                            "Period": report["resolved_period"]["label"],
                            "Operating revenue": report["results"]["operating_revenue"][
                                "value"
                            ],
                            "PAT": report["results"]["pat"]["value"],
                            "PAT status": report["results"]["pat"]["status"],
                        }
                        for report in summary["reports"]
                    ]
                )
        with tabs[5]:
            population = st.selectbox("Population", ["contributing", "excluded"])
            report_type = st.selectbox("Source report", list(reports))
            query = parameters | {
                "population": population,
                "report_type": report_type,
                "population_fingerprint": reports[report_type][
                    "population_fingerprint"
                ],
            }
            if population == "contributing":
                query["metric"] = st.selectbox(
                    "Source metric", list(reports[report_type]["results"])
                )
            else:
                query["scope"] = st.selectbox(
                    "Excluded population scope", ["period_activity", "activity_derived"]
                )
            query["offset"] = st.number_input("Row offset", min_value=0, step=50)
            query["limit"] = 50
            if st.button("Load source rows"):
                trace = request_json(
                    base_url, "GET", f"{api_base}/transactions", params=query
                )
                st.write(f"Matching transactions: {trace['total']}")
                st.table(
                    [
                        {
                            key: item[key]
                            for key in (
                                "transaction_id",
                                "transaction_date",
                                "source_file_id",
                                "source_row_number",
                                "account_code",
                                "account_name",
                                "debit",
                                "credit",
                                "currency",
                                "match_method",
                                "exclusion_reason",
                            )
                        }
                        for item in trace["transactions"]
                    ]
                )
                with st.expander("Source classification and calculation basis"):
                    st.json(trace)
    except APIError as exc:
        st.error(str(exc))


if __name__ == "__main__":
    main()
