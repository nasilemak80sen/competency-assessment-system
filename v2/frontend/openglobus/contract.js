/* Browser-side validation for the Python geospatial contract. */
(function (namespace) {
  function parseDataset(documentRef) {
    const node = documentRef.getElementById("re-globe-config");
    if (!node) throw new Error("Missing geospatial configuration payload.");
    let config;
    try { config = JSON.parse(node.textContent || "{}"); }
    catch (error) { throw new Error("Invalid geospatial JSON payload: " + error.message); }
    if (!config || config.schemaVersion !== 1) throw new Error("Unsupported geospatial schema version: " + config?.schemaVersion);
    if (config.datasetType !== "nationality-distribution") throw new Error("Unsupported geospatial dataset type: " + config?.datasetType);
    if (!Array.isArray(config.records) || config.records.length === 0) throw new Error("Geospatial dataset contains no nationality records.");
    const ids = new Set();
    for (const [index, record] of config.records.entries()) {
      if (!record || typeof record.id !== "string" || !record.id.trim() || ids.has(record.id)) throw new Error("Geospatial record " + index + " has an invalid or duplicate id.");
      ids.add(record.id);
      if (typeof record.nationality !== "string" || !record.nationality.trim()) throw new Error("Geospatial record " + index + " has no nationality label.");
      if (!Number.isInteger(record.personnelCount) || record.personnelCount <= 0) throw new Error("Geospatial record " + index + " has an invalid personnelCount.");
      if (!Number.isFinite(record.latitude) || record.latitude < -90 || record.latitude > 90 || !Number.isFinite(record.longitude) || record.longitude < -180 || record.longitude > 180) throw new Error("Geospatial record " + index + " has invalid coordinates.");
      if (!Array.isArray(record.people)) throw new Error("Geospatial record " + index + " people must be an array.");
    }
    if (config.summary?.nationalityCount !== config.records.length) throw new Error("Geospatial summary nationalityCount does not match records.");
    return config;
  }
  namespace.contract = { parseDataset };
})(window.REGlobe = window.REGlobe || {});
