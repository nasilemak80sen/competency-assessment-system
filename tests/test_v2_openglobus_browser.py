"""Chromium integration tests using a deterministic OpenGlobus engine test double."""
from __future__ import annotations
import pytest
playwright_sync = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
import pandas as pd  # noqa: E402
from v2.components.openglobus import OPEN_GLOBUS_CSS, OPEN_GLOBUS_JS, _build_openglobus_html  # noqa: E402
from v2.services.geospatial_service import build_nationality_dataset  # noqa: E402

MOCK_OPENGLOBUS = r"""
export class GlobusRgbTerrain {}
export class OpenStreetMap { constructor(name, options) { this.name=name; this.options=options; } }
export class LonLat { constructor(lon,lat,height) { this.lon=lon; this.lat=lat; this.height=height; } }
export class Entity { constructor(options) { Object.assign(this,options); } }
export const control = { KeyboardNavigation: class {} };
export class Vector {
  constructor(name,options) { this.name=name; this.options=options; this.entities=[]; }
  addTo(planet) { this.planet=planet; window.__mockGlobe.layer=this; }
  setEntities(entities) { this.entities=entities; }
  getEntities() { return this.entities; }
}
export class Globe {
  constructor(options) {
    const handlers={};
    const camera={
      setCalls:[], flyCalls:[],
      setLonLat(position) { this.setCalls.push(position); },
      flyLonLat(position,options) { this.flyCalls.push({position,options}); }
    };
    this.planet={camera};
    this.renderer={
      events:{on(name,callback) { handlers[name]=callback; }},
      addControl() {}
    };
    const target=document.getElementById(options.target);
    const canvas=document.createElement("canvas");
    canvas.setAttribute("aria-label","Mock 3D Earth canvas");
    target.appendChild(canvas);
    window.__mockGlobe={
      options,camera,layer:null,
      triggerPick(id) {
        const entity=this.layer.entities.find((item)=>item.properties.id===id);
        if (entity && handlers.lclick) handlers.lclick({pickingObject:entity});
      }
    };
  }
}
"""


def _dataset():
    map_df = pd.DataFrame({
        "Nationality": ["Malaysian", "British", "Indonesian"],
        "Personnel Count": [2, 1, 1],
        "Latitude": [4.2105, 55.3781, -0.7893],
        "Longitude": [101.9758, -3.4360, 113.9213],
        "Representation": [50.0, 25.0, 25.0],
        "Representation Display": ["50.0%", "25.0%", "25.0%"],
    })
    people_df = pd.DataFrame({
        "Nationality": ["Malaysian", "British", "Indonesian", "Malaysian"],
        "Name": ["A", "B", "C", "D"],
        "Staff Position": ["Engineer", "Geologist", "Engineer", "Manager"],
        "Department": ["RE"] * 4, "SG": ["P5", "P6", "P5", "P7"],
        "Employment Category": ["PERMANENT", "CDH", "PERMANENT", "PERMANENT"],
        "Section Name": ["A", "B", "A", "C"],
    })
    return build_nationality_dataset(map_df, people_df)


@pytest.fixture
def browser_page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route(OPEN_GLOBUS_CSS, lambda route: route.fulfill(status=200, content_type="text/css", body=""))
        page.route(
            OPEN_GLOBUS_JS,
            lambda route: route.fulfill(
                status=200, content_type="text/javascript",
                headers={"Access-Control-Allow-Origin": "*"}, body=MOCK_OPENGLOBUS,
            ),
        )
        page.set_content(_build_openglobus_html(_dataset()), wait_until="domcontentloaded")
        page.wait_for_function("document.getElementById('status').dataset.state === 'ready'", timeout=10000)
        yield page
        browser.close()


def test_browser_loads_globe_canvas_and_all_markers(browser_page):
    assert browser_page.locator("#globus canvas").count() == 1
    assert browser_page.locator("#status").get_attribute("data-state") == "ready"
    assert browser_page.evaluate("window.__mockGlobe.layer.entities.length") == 3
    assert browser_page.evaluate("window.__mockGlobe.layer.entities.map(e=>e.properties.personnelCount)") == [2, 1, 1]


def test_browser_filters_markers_and_reset_restores_aggregate_counts(browser_page):
    page = browser_page
    page.locator("#employmentFilter").select_option(label="CDH")
    assert page.evaluate("window.__mockGlobe.layer.entities.map(e=>e.properties.nationality)") == ["British"]
    assert page.locator("#stats").inner_text().startswith("1 visible personnel")
    page.locator("#sgFilter").select_option(label="P5")
    assert page.evaluate("window.__mockGlobe.layer.entities.length") == 0
    page.locator("#resetFilters").click()
    assert page.evaluate("window.__mockGlobe.layer.entities.length") == 3
    assert page.locator("#stats").inner_text().startswith("4 visible personnel")


def test_browser_picking_details_and_camera_fly_to(browser_page):
    page = browser_page
    page.evaluate("window.__mockGlobe.triggerPick('british')")
    assert page.locator("#details").get_attribute("aria-hidden") == "false"
    assert page.locator("#detailNationality").inner_text() == "🌐 British"
    assert page.locator("#detailCount").inner_text() == "1"
    assert "B" in page.locator("#people").inner_text()
    assert page.evaluate("window.__mockGlobe.camera.flyCalls.length") == 1
    page.locator("#flyTo").click()
    assert page.evaluate("window.__mockGlobe.camera.flyCalls.length") == 2


def test_browser_handles_engine_module_load_failure():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route(OPEN_GLOBUS_CSS, lambda route: route.fulfill(status=200, content_type="text/css", body=""))
        page.route(OPEN_GLOBUS_JS, lambda route: route.abort())
        page.set_content(_build_openglobus_html(_dataset()), wait_until="domcontentloaded")
        page.wait_for_function("document.getElementById('status').dataset.state === 'error'", timeout=10000)
        assert "could not be initialized" in page.locator("#status").inner_text()
        browser.close()
