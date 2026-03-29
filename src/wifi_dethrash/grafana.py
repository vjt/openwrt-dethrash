from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class DatasourceInfo:
    uid: str
    name: str
    type: str


class GrafanaClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=30,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GrafanaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def discover_datasources(self) -> list[DatasourceInfo]:
        """Fetch all configured datasources."""
        resp = self._client.get(f"{self._base_url}/api/datasources")
        resp.raise_for_status()
        return [
            DatasourceInfo(uid=ds["uid"], name=ds["name"], type=ds["type"])
            for ds in resp.json()
        ]

    def find_datasource_uid(
        self, datasources: list[DatasourceInfo], ds_type: str,
    ) -> str:
        """Find the UID of the first datasource matching ds_type.

        Raises ValueError if not found.
        """
        for ds in datasources:
            if ds.type == ds_type:
                return ds.uid
        available = ", ".join(f"{ds.name} ({ds.type})" for ds in datasources)
        raise ValueError(
            f"No datasource of type '{ds_type}' found. Available: {available}"
        )

    def push_dashboard(self, dashboard: dict[str, object]) -> str:
        """Push dashboard via API. Returns the dashboard URL path."""
        resp = self._client.post(
            f"{self._base_url}/api/dashboards/db",
            json={"dashboard": dashboard, "overwrite": True},
        )
        resp.raise_for_status()
        return resp.json().get("url", "/")

    def annotate(
        self,
        text: str,
        tags: list[str] | None = None,
        dashboard_uid: str = "wifi-dethrash",
    ) -> int:
        """Create an annotation on the dashboard. Returns annotation ID."""
        resp = self._client.post(
            f"{self._base_url}/api/annotations",
            json={
                "dashboardUID": dashboard_uid,
                "text": text,
                "tags": tags or ["config-change"],
            },
        )
        resp.raise_for_status()
        return resp.json().get("id", 0)
