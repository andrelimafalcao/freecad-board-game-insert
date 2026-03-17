import FreeCADGui
import os
import sys

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
    for p in sys.path:
        if (os.path.isfile(os.path.join(p, "insert_designer.py"))
                and os.path.isfile(os.path.join(p, "board_game_insert.py"))):
            return p
    return None

_dir = _find_addon_dir()


class InsertDesignerCommand:
    def GetResources(self):
        res = {
            'MenuText': 'Insert Designer',
            'ToolTip':  'Open the board game insert designer',
        }
        if _dir is not None:
            res['Pixmap'] = os.path.join(_dir, "icons", "insert_designer.svg")
        return res

    def IsActive(self):
        return True

    def Activated(self):
        import FreeCAD
        try:
            import insert_designer
            import importlib
            importlib.reload(insert_designer)
            insert_designer.main()
        except Exception as e:
            FreeCAD.Console.PrintError(f"InsertDesigner: {e}\n")


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
