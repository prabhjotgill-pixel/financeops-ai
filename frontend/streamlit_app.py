import httpx
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_url: str = "http://localhost:8000"


def fetch_status(base_url: str, endpoint: str) -> tuple[bool, str]:
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/v1/health/{endpoint}",
            timeout=5.0,
        )
        payload = response.json()
        if not isinstance(payload, dict):
            return False, "Unexpected backend response"
        status = payload.get("status")
        if endpoint == "live":
            return response.status_code == 200 and status == "alive", str(status)
        return response.status_code == 200 and status == "ready", str(status)
    except (httpx.HTTPError, ValueError):
        return False, "Backend unreachable"


def main() -> None:
    settings = FrontendSettings()
    st.title("FinanceOps AI")
    st.caption("Service status")

    backend_ok, backend_status = fetch_status(settings.backend_url, "live")
    if backend_ok:
        st.success("Backend reachable")
    else:
        st.error(f"Backend unavailable: {backend_status}")

    if backend_ok:
        database_ok, database_status = fetch_status(settings.backend_url, "ready")
        if database_ok:
            st.success("Database ready")
        else:
            st.error(f"Database unavailable: {database_status}")
    else:
        st.info("Database status unknown while the backend is unreachable")


if __name__ == "__main__":
    main()
