/* Creates OpenGlobus Entity instances and refreshes the nationality Vector. */
(function (namespace) {
  function renderNationalityLayer(engine, vectorLayer, dataset, filterController, selectedId) {
    const counts = dataset.records.map((record) => filterController.markerCount(record));
    const maxCount = Math.max(...counts, 1);
    const entities = dataset.records.map((record, index) => {
      const count = counts[index];
      if (count <= 0) return null;
      const selected = selectedId === record.id;
      return new engine.Entity({
        name: record.nationality,
        lonlat: [record.longitude, record.latitude],
        billboard: { src: namespace.markers.markerSvg(count, maxCount, selected), size: [44, 44], offset: [0, 20] },
        label: {
          text: record.nationality + " · " + count,
          size: selected ? 16 : 12,
          offset: [0, 30, 0],
          color: selected ? "rgba(32,65,154,.98)" : "rgba(24,50,56,.94)",
          outlineColor: "rgba(255,255,255,.96)", outline: 2
        },
        properties: {
          id: record.id, nationality: record.nationality,
          personnelCount: count, representationDisplay: record.representationDisplay,
          latitude: record.latitude, longitude: record.longitude
        }
      });
    }).filter(Boolean);
    vectorLayer.setEntities(entities);
    const total = entities.reduce((sum, entity) => sum + Number(entity.properties.personnelCount || 0), 0);
    return { entityCount: entities.length, personnelCount: total };
  }
  namespace.layers = { renderNationalityLayer };
})(window.REGlobe = window.REGlobe || {});
