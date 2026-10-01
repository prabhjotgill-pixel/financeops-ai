import hashlib
from typing import Any

import httpx
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_url: str = "http://localhost:8000"


class APIError(Exception):
    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(message)


def api_call(base_url: str, method: str, path: str, **kwargs: Any) -> Any:
    try:
        with httpx.Client(base_url=base_url, timeout=30.0) as client:
            response = client.request(method, path, **kwargs)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise APIError("Backend request failed") from exc
    if response.status_code >= 400:
        detail = payload.get("detail", {}) if isinstance(payload, dict) else {}
        if isinstance(detail, dict):
            raise APIError(
                str(detail.get("message", "Request failed")),
                str(detail.get("code", "")),
                detail.get("details", {}),
            )
        raise APIError(str(detail))
    return payload


def show_report(report: dict[str, Any]) -> None:
    st.subheader("Validation report")
    columns = st.columns(4)
    columns[0].metric("Rows", report["row_count"])
    columns[1].metric("Importable", report["valid_row_count"])
    columns[2].metric("Warnings", report["warning_row_count"])
    columns[3].metric("Errors", report["error_row_count"])

    st.write("Detected column mapping")
    st.table(
        [
            {"Canonical field": field, "Source column": source}
            for field, source in report["column_mapping"].items()
        ]
    )

    st.write("Debit and credit controls for importable rows")
    if report["controls"]:
        st.table(report["controls"])
    else:
        st.info("No importable rows to total.")

    st.write("Row issues")
    if report["issues"]:
        st.table(report["issues"])
    else:
        st.success("No row issues found.")


def main() -> None:
    st.title("General Ledger ingestion")
    st.caption("Validate a CSV or Excel file, review quality, then import valid rows.")
    base_url = FrontendSettings().backend_url

    try:
        companies = api_call(base_url, "GET", "/api/v1/companies")
    except APIError as exc:
        st.error(str(exc))
        return

    with st.expander("Create company", expanded=not companies):
        with st.form("create_company"):
            name = st.text_input("Company name")
            industry = st.text_input("Industry (optional)")
            currency = st.text_input("Currency code", value="USD", max_chars=3)
            create_clicked = st.form_submit_button("Create company")
        if create_clicked:
            try:
                api_call(
                    base_url,
                    "POST",
                    "/api/v1/companies",
                    json={
                        "name": name,
                        "industry": industry or None,
                        "currency": currency,
                    },
                )
                st.rerun()
            except APIError as exc:
                st.error(str(exc))

    if not companies:
        st.info("Create a company before uploading a GL file.")
        return
    selected = st.selectbox(
        "Company",
        companies,
        format_func=lambda company: f"{company['name']} ({company['currency']})",
    )
    company_id = selected["id"]
    uploaded = st.file_uploader("GL file", type=["csv", "xlsx"], max_upload_size=10)
    if uploaded is None:
        return
    content = uploaded.getvalue()
    sheet_name = None
    if uploaded.name.lower().endswith(".xlsx"):
        try:
            sheets = api_call(
                base_url,
                "POST",
                "/api/v1/files/sheets",
                files={"file": (uploaded.name, content)},
            )["sheets"]
        except APIError as exc:
            st.error(str(exc))
            return
        sheet_name = st.selectbox("Worksheet", sheets)

    selection_key = (company_id, hashlib.sha256(content).hexdigest(), sheet_name)
    if st.session_state.get("ingestion_selection") != selection_key:
        st.session_state["ingestion_selection"] = selection_key
        st.session_state.pop("ingestion_file_id", None)
        st.session_state.pop("ingestion_report", None)
        st.session_state.pop("ingestion_import", None)
        st.session_state.pop("ingestion_already_imported", None)

    if st.button("Parse and validate"):
        try:
            fields = {"company_id": str(company_id)}
            if sheet_name is not None:
                fields["sheet_name"] = sheet_name
            result = api_call(
                base_url,
                "POST",
                "/api/v1/files/upload",
                data=fields,
                files={"file": (uploaded.name, content)},
            )
            st.session_state["ingestion_file_id"] = result["file"]["id"]
            st.session_state["ingestion_report"] = result["report"]
            st.session_state.pop("ingestion_import", None)
            st.session_state["ingestion_already_imported"] = False
        except APIError as exc:
            existing_id = exc.details.get("file_id")
            if exc.code == "DUPLICATE_UPLOAD" and isinstance(existing_id, int):
                try:
                    metadata = api_call(base_url, "GET", f"/api/v1/files/{existing_id}")
                    report = api_call(
                        base_url,
                        "GET",
                        f"/api/v1/files/{existing_id}/validation-report",
                    )
                except APIError as lookup_error:
                    st.error(str(lookup_error))
                else:
                    st.session_state["ingestion_file_id"] = existing_id
                    st.session_state["ingestion_report"] = report
                    st.session_state["ingestion_already_imported"] = (
                        metadata["status"] == "imported"
                    )
                    st.info("This file and worksheet were uploaded earlier.")
            else:
                st.error(str(exc))

    file_id = st.session_state.get("ingestion_file_id")
    report = st.session_state.get("ingestion_report")
    if file_id is None or report is None:
        return
    show_report(report)

    if st.session_state.get("ingestion_already_imported"):
        st.info("This source file has already been imported.")
    elif report["valid_row_count"] and not st.session_state.get("ingestion_import"):
        if st.button("Import valid rows"):
            try:
                st.session_state["ingestion_import"] = api_call(
                    base_url, "POST", f"/api/v1/files/{file_id}/import"
                )
            except APIError as exc:
                st.error(str(exc))

    imported = st.session_state.get("ingestion_import")
    if imported:
        st.success(
            f"Imported {imported['imported_row_count']} rows; "
            f"retained {imported['skipped_row_count']} rejected rows in the report."
        )
        try:
            summary = api_call(
                base_url,
                "GET",
                f"/api/v1/companies/{company_id}/gl/summary",
            )
            st.write(f"Company GL transactions: {summary['transaction_count']}")
        except APIError as exc:
            st.error(str(exc))


if __name__ == "__main__":
    main()
