/* OpenGlobus application bootstrap and interaction orchestration. */
const status = document.getElementById("status");
function setStatus(state, message) {
  status.dataset.state = state;
  status.textContent = message;
  status.classList.toggle("hidden", state === "ready");
}
function showError(error) {
  console.error("OpenGlobus initialization failed:", error);
  setStatus("error", "3D Earth could not be initialized. Check WebGL and network access, then reload the dashboard.");
}

(async function initializeNationalityGlobe() {
  try {
    const config = JSON.parse(document.getElementById("re-globe-config").textContent || "{}");
    const dataset = window.REGlobe.contract.parseDataset(document);
    // The dynamic import is inside try/catch, so CDN/module failures are handled.
    const engine = await import(config.openGlobusUrl);
    const osm = new engine.OpenStreetMap("OpenStreetMap", {
      isBaseLayer: true, visibility: true,
      attribution: "© OpenStreetMap contributors, ODbL"
    });
    const globe = new engine.Globe({
      target: "globus",
      name: "RE Nationality Intelligence Globe",
      terrain: new engine.GlobusRgbTerrain(),
      layers: [osm],
      atmosphereEnabled: true,
      resourcesSrc: config.resourcesUrl,
      fontsSrc: config.fontsUrl,
      msaa: 4,
      idleMode: false,
      navigation: { mode: "north", inertia: 0.18, zoomSpeed: 1.15 }
    });
    const nationalityLayer = new engine.Vector("Nationalities", {
      entities: [], pickingEnabled: true, async: true
    });
    nationalityLayer.addTo(globe.planet);
    if (engine.control && engine.control.KeyboardNavigation) {
      globe.renderer.addControl(new engine.control.KeyboardNavigation());
    }
    // Start over Southeast Asia so workforce markers are immediately visible.
    if (globe.planet && globe.planet.camera) {
      globe.planet.camera.setLonLat(new engine.LonLat(101.9758, 4.2105, 12000000));
    }

    let selectedRecord = null;
    const stats = document.getElementById("stats");
    function renderLayer() {
      const result = window.REGlobe.layers.renderNationalityLayer(
        engine, nationalityLayer, dataset, filterController,
        selectedRecord ? selectedRecord.id : null
      );
      stats.textContent = result.personnelCount + " visible personnel · " +
        result.entityCount + " nationalities · Click a pin for details";
      return result;
    }
    const filterController = window.REGlobe.filters.createFilterController(
      dataset, document,
      () => {
        selectedRecord = null;
        window.REGlobe.details.hideDetails(document);
        renderLayer();
      }
    );
    function clearSelection() {
      selectedRecord = null;
      window.REGlobe.details.hideDetails(document);
      renderLayer();
    }
    document.getElementById("resetFilters").addEventListener("click", () => filterController.reset());
    document.getElementById("closeDetails").addEventListener("click", clearSelection);
    document.getElementById("flyTo").addEventListener("click", () => {
      if (selectedRecord) window.REGlobe.camera.flyToRecord(globe, selectedRecord, engine.LonLat);
    });
    globe.renderer.events.on("lclick", (event) => {
      const picked = event && event.pickingObject;
      const pickedId = picked && picked.properties && picked.properties.id;
      if (!pickedId) return;
      const record = dataset.records.find((item) => item.id === pickedId);
      if (!record) return;
      selectedRecord = record;
      const visiblePeople = filterController.visiblePeople(record);
      const displayedCount = filterController.markerCount(record);
      window.REGlobe.details.showDetails(document, record, visiblePeople, displayedCount);
      renderLayer();
      window.REGlobe.camera.flyToRecord(globe, record, engine.LonLat);
    });

    const initial = renderLayer();
    if (initial.entityCount !== dataset.records.length) {
      throw new Error("Expected " + dataset.records.length + " nationality markers, rendered " + initial.entityCount + ".");
    }
    setStatus("ready", "3D Earth ready");
    window.setTimeout(() => window.dispatchEvent(new Event("resize")), 250);
  } catch (error) {
    showError(error);
  }
})();
