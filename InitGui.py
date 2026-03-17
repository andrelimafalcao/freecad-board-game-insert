import FreeCADGui
import os
import sys
import importlib.util

def _find_addon_dir():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    try:
        import inspect
        return os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    except Exception:
        pass
    # FreeCAD adds each mod directory to sys.path before loading it;
    # find ours by the unique combination of files it contains.
    for p in sys.path:
        if (os.path.isfile(os.path.join(p, "insert_designer.py"))
                and os.path.isfile(os.path.join(p, "board_game_insert.py"))):
            return p
    raise RuntimeError("InsertDesigner: could not locate addon directory")

_dir = _find_addon_dir()


def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_dir, filename))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class InsertDesignerCommand:
    def GetResources(self):
        return {
            'MenuText': 'Insert Designer',
            'ToolTip':  'Open the board game insert designer',
            'Pixmap':   os.path.join(_dir, "icons", "insert_designer.svg"),
        }

    def IsActive(self):
        return True

    def Activated(self):
        import FreeCAD
        try:
            mod = _load_module("insert_designer", "insert_designer.py")
            mod.main()
        except Exception as e:
            FreeCAD.Console.PrintError(f"InsertDesigner: {e}\n")


# Register command at module load time — before the workbench Initialize is called
FreeCADGui.addCommand("InsertDesigner_Open", InsertDesignerCommand())


class InsertDesignerWorkbench(FreeCADGui.Workbench):
    MenuText = "Insert Designer"
    ToolTip  = "Board game insert designer tools"

    def Initialize(self):
        self.appendToolbar("Insert Designer", ["InsertDesigner_Open"])
        self.appendMenu("Insert Designer",   ["InsertDesigner_Open"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(InsertDesignerWorkbench())
