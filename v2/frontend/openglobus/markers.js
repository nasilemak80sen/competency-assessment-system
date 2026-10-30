/* Proportional marker SVG generation. */
(function (namespace) {
  function markerSvg(count, maxCount, selected = false) {
    const normalised = Math.sqrt(Math.max(count, 1)) / Math.sqrt(Math.max(maxCount, 1));
    const radius = 9 + normalised * 11, size = Math.ceil(radius * 2 + 8);
    const fill = selected ? "#20419A" : "#00A19C", center = size / 2, cy = radius + 4;
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '"><circle cx="' + center + '" cy="' + cy + '" r="' + radius + '" fill="' + fill + '" fill-opacity=".94" stroke="#fff" stroke-width="3"/><circle cx="' + center + '" cy="' + cy + '" r="' + Math.max(3, radius * .28) + '" fill="#fff"/></svg>';
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }
  namespace.markers = { markerSvg };
})(window.REGlobe = window.REGlobe || {});
