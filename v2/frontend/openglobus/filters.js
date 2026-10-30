/* Client-side workforce filtering. No Streamlit rerun is needed. */
(function (namespace) {
  const FILTERS = [
    { key: "employmentCategory", elementId: "employmentFilter" },
    { key: "salaryGrade", elementId: "sgFilter" },
    { key: "sectionName", elementId: "sectionFilter" }
  ];
  function createFilterController(dataset, documentRef, onChange) {
    const controls = FILTERS.map((definition) => ({ ...definition, element: documentRef.getElementById(definition.elementId) }));
    for (const control of controls) {
      const values = [...new Set(dataset.records.flatMap((record) => (record.people || []).map((person) => person[control.key]).filter(Boolean)))].sort((a,b) => a.localeCompare(b));
      for (const value of values) {
        const option = documentRef.createElement("option");
        option.value = value; option.textContent = value; control.element.appendChild(option);
      }
      control.element.addEventListener("change", onChange);
    }
    function getState() { return Object.fromEntries(controls.map((control) => [control.key, control.element.value])); }
    function hasActiveFilters() { return controls.some((control) => Boolean(control.element.value)); }
    function visiblePeople(record) {
      const state = getState();
      return (record.people || []).filter((person) => controls.every((control) => !state[control.key] || person[control.key] === state[control.key]));
    }
    function markerCount(record) {
      // Use the aggregate count without filters; filtered counts use detail rows.
      return hasActiveFilters() ? visiblePeople(record).length : record.personnelCount;
    }
    function reset() { controls.forEach((control) => { control.element.value = ""; }); onChange(); }
    return { getState, hasActiveFilters, visiblePeople, markerCount, reset };
  }
  namespace.filters = { createFilterController };
})(window.REGlobe = window.REGlobe || {});
