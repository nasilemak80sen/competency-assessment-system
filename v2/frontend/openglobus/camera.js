/* Camera movement is isolated so it can be tested independently. */
(function (namespace) {
  function flyToRecord(globe, record, LonLat) {
    if (!globe || !globe.planet || !globe.planet.camera) return false;
    globe.planet.camera.flyLonLat(
      new LonLat(record.longitude, record.latitude, 3500000),
      { duration: 900 }
    );
    return true;
  }
  namespace.camera = { flyToRecord };
})(window.REGlobe = window.REGlobe || {});
