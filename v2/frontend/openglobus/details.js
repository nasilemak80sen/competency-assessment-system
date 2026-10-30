/* DOM-safe nationality details panel rendering. */
(function (namespace) {
  function appendPersonnel(documentRef, container, person) {
    const item = documentRef.createElement("div");
    item.className = "person";
    const name = documentRef.createElement("strong");
    name.textContent = person.name || "Unnamed";
    const position = documentRef.createElement("div");
    position.textContent = (person.staffPosition || "Position not specified") + " · " + (person.salaryGrade || "SG —");
    const department = documentRef.createElement("div");
    department.className = "muted";
    department.textContent = (person.department || "Department —") + " · " + (person.sectionName || "Section —");
    item.append(name, position, department);
    container.appendChild(item);
  }
  function showDetails(documentRef, record, people, displayedCount) {
    documentRef.getElementById("detailNationality").textContent = "🌐 " + record.nationality;
    documentRef.getElementById("detailRepresentation").textContent = "Representation: " + (record.representationDisplay || "—");
    documentRef.getElementById("detailCount").textContent = String(displayedCount);
    documentRef.getElementById("detailSections").textContent = String(new Set(people.map((person) => person.sectionName).filter(Boolean)).size);
    const container = documentRef.getElementById("people");
    container.replaceChildren();
    if (!people.length) {
      const empty = documentRef.createElement("div");
      empty.className = "muted";
      empty.textContent = "No personnel detail records match the current filters.";
      container.appendChild(empty);
    } else {
      people.slice(0, 60).forEach((person) => appendPersonnel(documentRef, container, person));
    }
    const panel = documentRef.getElementById("details");
    panel.classList.add("visible");
    panel.setAttribute("aria-hidden", "false");
  }
  function hideDetails(documentRef) {
    const panel = documentRef.getElementById("details");
    panel.classList.remove("visible");
    panel.setAttribute("aria-hidden", "true");
  }
  namespace.details = { showDetails, hideDetails };
})(window.REGlobe = window.REGlobe || {});
