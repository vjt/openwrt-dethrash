import pytest
from wifi_dethrash.grafana import GrafanaClient, DatasourceInfo


DATASOURCES_RESP = [
    {"uid": "prom-abc", "name": "VictoriaMetrics", "type": "prometheus"},
    {"uid": "vl-xyz", "name": "VictoriaLogs", "type": "victoriametrics-logs-datasource"},
]

PUSH_RESP = {"id": 1, "uid": "wifi-dethrash", "url": "/d/wifi-dethrash/wifi-mesh-health", "status": "success"}


class TestDiscoverDatasources:
    def test_returns_datasource_list(self, respx_mock) -> None:
        respx_mock.get("http://grafana:3000/api/datasources").respond(
            json=DATASOURCES_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            ds = gf.discover_datasources()

        assert len(ds) == 2
        assert ds[0].uid == "prom-abc"
        assert ds[0].type == "prometheus"
        assert ds[1].uid == "vl-xyz"

    def test_sends_auth_header(self, respx_mock) -> None:
        respx_mock.get("http://grafana:3000/api/datasources").respond(
            json=DATASOURCES_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_secret") as gf:
            gf.discover_datasources()

        request = respx_mock.calls[0].request
        assert request.headers["Authorization"] == "Bearer glsa_secret"


class TestFindDatasourceUid:
    def test_finds_by_type(self) -> None:
        datasources = [
            DatasourceInfo(uid="prom-abc", name="VM", type="prometheus"),
            DatasourceInfo(uid="vl-xyz", name="VL", type="victoriametrics-logs-datasource"),
        ]

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            assert gf.find_datasource_uid(datasources, "prometheus") == "prom-abc"
            assert gf.find_datasource_uid(
                datasources, "victoriametrics-logs-datasource") == "vl-xyz"

    def test_raises_on_missing_type(self) -> None:
        datasources = [
            DatasourceInfo(uid="prom-abc", name="VM", type="prometheus"),
        ]

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            with pytest.raises(ValueError, match="No datasource of type"):
                gf.find_datasource_uid(datasources, "victoriametrics-logs-datasource")


class TestPushDashboard:
    def test_pushes_and_returns_url(self, respx_mock) -> None:
        respx_mock.post("http://grafana:3000/api/dashboards/db").respond(
            json=PUSH_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            url = gf.push_dashboard({"title": "Test", "panels": []})

        assert url == "/d/wifi-dethrash/wifi-mesh-health"

        # Verify request body wraps dashboard with overwrite
        import json
        request = respx_mock.calls[0].request
        body = json.loads(request.content)
        assert body["overwrite"] is True
        assert body["dashboard"]["title"] == "Test"

    def test_sends_auth_header_on_push(self, respx_mock) -> None:
        respx_mock.post("http://grafana:3000/api/dashboards/db").respond(
            json=PUSH_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_push_token") as gf:
            gf.push_dashboard({"title": "Test"})

        request = respx_mock.calls[0].request
        assert request.headers["Authorization"] == "Bearer glsa_push_token"


ANNOTATE_RESP = {"id": 42, "message": "Annotation added"}


class TestAnnotate:
    def test_creates_annotation(self, respx_mock) -> None:
        respx_mock.post("http://grafana:3000/api/annotations").respond(
            json=ANNOTATE_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            ann_id = gf.annotate("txpower changed")

        assert ann_id == 42

        import json
        request = respx_mock.calls[0].request
        body = json.loads(request.content)
        assert body["text"] == "txpower changed"
        assert body["dashboardUID"] == "wifi-dethrash"
        assert body["tags"] == ["config-change"]

    def test_custom_tags(self, respx_mock) -> None:
        respx_mock.post("http://grafana:3000/api/annotations").respond(
            json=ANNOTATE_RESP
        )

        with GrafanaClient("http://grafana:3000", "glsa_test") as gf:
            gf.annotate("test", tags=["usteer", "txpower"])

        import json
        request = respx_mock.calls[0].request
        body = json.loads(request.content)
        assert body["tags"] == ["usteer", "txpower"]
