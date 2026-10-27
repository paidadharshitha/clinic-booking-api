"""The booking portal, developer guide, and API share one application."""

from html.parser import HTMLParser

import pytest


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


@pytest.mark.parametrize(
    ("page", "stylesheet", "script"),
    [
        ("/", "/assets/portal.css", "/assets/portal.js"),
        ("/guide", "/assets/styles.css", "/assets/app.js"),
    ],
    ids=["booking-portal", "api-playground"],
)
def test_pages_and_linked_assets_load_outside_repository(
    client, monkeypatch, tmp_path, page, stylesheet, script
):
    # Package assets must resolve in a wheel or container, independently of cwd.
    monkeypatch.chdir(tmp_path)
    response = client.get(page)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>" in response.text
    links = AssetLinks()
    links.feed(response.text)
    assert stylesheet in links.stylesheets, "Each page must load its own packaged stylesheet."
    assert script in links.scripts, "Each page must load its own interactive JavaScript."
    assert links.fonts, "Each page must load its packaged font."
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
    assert "/guide" not in paths
    assert not any(path.startswith("/assets") for path in paths)
    assert "/bookings" in paths
    assert "/clinics/{clinic_id}/slots" in paths
