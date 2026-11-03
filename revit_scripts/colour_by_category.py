# Runs inside Revit (Agent Runtime, modify mode).
# Applies a solid colour override to every element of each category in the target view,
# or clears the overrides when inputs["reset"] is true.
def get_target_view(target):
    if target.get("mode") == "named":
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
            if not v.IsTemplate and v.Name == target.get("name"):
                return v
        raise Exception("No view named '%s' found in the model." % target.get("name"))
    view = doc.ActiveView
    if view is None or view.ViewType in (DB.ViewType.DrawingSheet, DB.ViewType.Schedule, DB.ViewType.ProjectBrowser):
        raise Exception("The active view '%s' cannot show model elements. Open a plan, section or 3D view." % (view.Name if view else "-"))
    return view

view = get_target_view(inputs.get("target", {"mode": "active"}))
reset = inputs.get("reset", False)
solid = None
for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
    if fp.GetFillPattern().IsSolidFill:
        solid = fp
        break

summary = []
t = DB.Transaction(doc, "VIKTOR colour by category")
t.Start()
for rule in inputs["rules"]:
    bic = getattr(DB.BuiltInCategory, rule["category"])
    settings = DB.OverrideGraphicSettings()
    if not reset:
        r, g, b = rule["color"]
        colour = DB.Color(r, g, b)
        settings.SetProjectionLineColor(colour)
        settings.SetCutLineColor(colour)
        if solid is not None:
            settings.SetSurfaceForegroundPatternId(solid.Id)
            settings.SetSurfaceForegroundPatternColor(colour)
            settings.SetCutForegroundPatternId(solid.Id)
            settings.SetCutForegroundPatternColor(colour)
    ids = DB.FilteredElementCollector(doc, view.Id).OfCategory(bic).WhereElementIsNotElementType().ToElementIds()
    for element_id in ids:
        view.SetElementOverrides(element_id, settings)
    summary.append({"category": rule["category"], "label": DB.LabelUtils.GetLabelFor(bic),
                    "color": rule.get("color"), "elements": len(ids)})
t.Commit()

result = {"model": doc.Title, "view": view.Name, "reset": reset, "summary": summary}
