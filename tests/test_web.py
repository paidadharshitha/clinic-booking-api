"""The packaged interactive guide and API remain available from one application."""

from html.parser import HTMLParser


class AssetLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []
        self.fonts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "link" and attributes.get("rel") == "stylesheet":
            href = attributes.get("href")
            if href and href.startswith("/assets/"):
                self.stylesheets.append(href)
        if tag == "script":
            src = attributes.get("src")
            if src and src.startswith("/assets/"):
                self.scripts.append(src)
        if tag == "link" and attributes.get("as") == "font":
            href = attributes.get("href")
            if href and href.startswith("/assets/"):
                self.fonts.append(href)


def test_interactive_guide_and_linked_assets_load_outside_repository(client, monkeypatch, tmp_path):
    # Package assets must resolve in a wheel or container, independently of cwd.
    monkeypatch.chdir(tmp_path)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>" in response.text
    links = AssetLinks()
    links.feed(response.text)
    assert links.stylesheets, "The guide must load its packaged stylesheet."
    assert links.scripts, "The guide must load its interactive JavaScript."
    assert links.fonts, "The guide must load its packaged font."
    for path in links.stylesheets + links.scripts + links.fonts:
        asset = client.get(path)
        assert asset.status_code == 200, path
        assert asset.content, path
        if path in links.stylesheets:
            assert asset.headers["content-type"].startswith("text/css")
        elif path in links.scripts:
            assert "javascript" in asset.headers["content-type"]
        else:
            assert asset.headers["content-type"].startswith("font/woff2")


def test_frontend_preserves_api_docs_health_and_schema(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/clinics").status_code == 200

    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/" not in paths
    assert not any(path.startswith("/assets") for path in paths)
    assert "/bookings" in paths
    assert "/clinics/{clinic_id}/slots" in paths
