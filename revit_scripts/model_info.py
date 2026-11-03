# Runs inside Revit (Agent Runtime, query mode).
# Returns the model, the target view and the number of elements per requested category in that view.
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
counts = []
for name in inputs.get("categories", []):
    bic = getattr(DB.BuiltInCategory, name)
    n = DB.FilteredElementCollector(doc, view.Id).OfCategory(bic).WhereElementIsNotElementType().GetElementCount()
    counts.append({"category": name, "label": DB.LabelUtils.GetLabelFor(bic), "count": n})

result = {"model": doc.Title, "view": view.Name, "view_type": str(view.ViewType), "counts": counts}
