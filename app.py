import json
from io import BytesIO
from pathlib import Path

import viktor as vkt

SCRIPTS = Path(__file__).parent / "revit_scripts"

CATEGORIES = {
    "OST_StructuralColumns": "Structural Columns",
    "OST_StructuralFraming": "Structural Framing",
    "OST_StructuralFoundation": "Structural Foundations",
    "OST_Floors": "Floors",
    "OST_Walls": "Walls",
    "OST_Roofs": "Roofs",
    "OST_Columns": "Columns",
    "OST_Stairs": "Stairs",
    "OST_Railings": "Railings",
    "OST_Doors": "Doors",
    "OST_Windows": "Windows",
    "OST_GenericModel": "Generic Models",
}
CATEGORY_OPTIONS = [vkt.OptionListElement(value, label) for value, label in CATEGORIES.items()]


def run_agent(task_script, mode="query", inputs=None, title="VIKTOR", timeout=240):
    """Send a Revit script to the Revit worker and return the pyRevit Agent Runtime response."""
    job = {"mode": mode, "title": title, "inputs": inputs or {}, "timeout": timeout}
    analysis = vkt.revit.RevitAnalysis(
        script=vkt.File.from_path(SCRIPTS / "run_agent.py"),
        files=[
            ("revit_task.py", vkt.File.from_path(SCRIPTS / task_script)),
            ("job.json", BytesIO(json.dumps(job).encode())),
        ],
        output_filenames=["output.json"],
    )
    analysis.execute(timeout=timeout + 60)
    response = json.loads(analysis.get_output_file("output.json").getvalue())
    if response.get("status") != "ok":
        error = response.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        raise vkt.UserError(f"Revit run failed: {message}")
    return response


def target_view(params):
    if params.target == "named":
        if not params.view_name:
            raise vkt.UserError("Enter the name of the Revit view.")
        return {"mode": "named", "name": params.view_name}
    return {"mode": "active"}


def colour_rules(params):
    rules, seen = [], set()
    for i, row in enumerate(params.rules, start=1):
        if not row.category:
            raise vkt.UserError(f"Select a category in rule {i}.")
        if row.category in seen:
            raise vkt.UserError(f"{CATEGORIES[row.category]} is used in more than one rule.")
        if row.color is None:
            raise vkt.UserError(f"Select a colour in rule {i}.")
        seen.add(row.category)
        rules.append({"category": row.category, "color": [row.color.r, row.color.g, row.color.b]})
    if not rules:
        raise vkt.UserError("Add at least one colour rule.")
    return rules


class Parametrization(vkt.Parametrization):
    intro = vkt.Text(
        "# Revit colour by category\n"
        "Colours the elements of each selected category in the Revit model that is open on the worker. "
        "The app uses the **pyRevit Agent Runtime**: the table reads the model (`query` mode) and the buttons "
        "write the colour overrides to the view (`modify` mode). Every change is one undo entry in Revit."
    )
    target = vkt.OptionField(
        "Revit view",
        options=[vkt.OptionListElement("active", "Active view"), vkt.OptionListElement("named", "View by name")],
        default="named",
        variant="radio-inline",
        flex=100,
    )
    view_name = vkt.TextField(
        "View name",
        default="Structure Only",
        visible=vkt.IsEqual(vkt.Lookup("target"), "named"),
        description="Name of a plan, section or 3D view in the Revit model.",
    )
    rules_text = vkt.Text("## Colour rules\nAdd one rule per category.")
    rules = vkt.DynamicArray(
        "Colour rules",
        row_label="Rule",
        default=[
            {"category": "OST_StructuralColumns", "color": vkt.Color(230, 57, 70)},
            {"category": "OST_StructuralFraming", "color": vkt.Color(29, 53, 87)},
            {"category": "OST_Floors", "color": vkt.Color(168, 218, 220)},
        ],
    )
    rules.category = vkt.OptionField("Category", options=CATEGORY_OPTIONS, flex=60)
    rules.color = vkt.ColorField("Colour", default=vkt.Color(69, 123, 157), flex=40)
    preview = vkt.BooleanField(
        "Preview only (dry run)",
        default=False,
        description="Runs the change in Revit and rolls it back, without changing the view.",
    )
    apply = vkt.ActionButton("Apply colours in Revit", method="apply_colours", longpoll=True, flex=50)
    reset = vkt.ActionButton("Reset colours", method="reset_colours", longpoll=True, flex=50)


class Controller(vkt.Controller):
    label = "Revit colour by category"
    parametrization = Parametrization

    @vkt.TableView("Elements per category", duration_guess=10)
    def elements_per_category(self, params, **kwargs):
        rules = colour_rules(params)
        response = run_agent(
            "model_info.py",
            mode="query",
            inputs={"target": target_view(params), "categories": [r["category"] for r in rules]},
            title="VIKTOR model info",
        )
        result = response["result"]
        colours = {r["category"]: vkt.Color(*r["color"]) for r in rules}
        rows = [
            [c["label"], c["count"], vkt.TableCell("", background_color=colours[c["category"]])]
            for c in result["counts"]
        ]
        return vkt.TableResult(
            rows,
            column_headers=["Category", f"Elements in '{result['view']}'", "Colour"],
            row_headers=[result["model"]] * len(rows),
        )

    def apply_colours(self, params, **kwargs):
        response = run_agent(
            "colour_by_category.py",
            mode="dry_run" if params.preview else "modify",
            inputs={"target": target_view(params), "rules": colour_rules(params)},
            title="VIKTOR colour by category",
            timeout=600,  # leave time to approve the change when the pyRevit policy is 'ask'
        )
        result = response["result"]
        total = sum(s["elements"] for s in result["summary"])
        action = "Previewed" if params.preview else "Coloured"
        vkt.UserMessage.success(
            f"{action} {total} elements in view '{result['view']}' ({response.get('decision')})."
        )

    def reset_colours(self, params, **kwargs):
        response = run_agent(
            "colour_by_category.py",
            mode="modify",
            inputs={"target": target_view(params), "rules": colour_rules(params), "reset": True},
            title="VIKTOR reset colours",
            timeout=600,
        )
        total = sum(s["elements"] for s in response["result"]["summary"])
        vkt.UserMessage.success(f"Reset the colour of {total} elements in view '{response['result']['view']}'.")
