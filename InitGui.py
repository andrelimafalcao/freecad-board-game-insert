import FreeCADGui
import os

_dir = os.path.dirname(os.path.abspath(__file__))


class InsertDesignerCommand:
    def GetResources(self):
        return {
            'MenuText': 'Insert Designer',
            'ToolTip':  'Open the board game insert designer',
        }

    def IsActive(self):
        return True

    def Activated(self):
        import FreeCAD
        macro = os.path.join(_dir, "insert_designer.py")
        try:
            with open(macro, "r") as f:
                exec(compile(f.read(), macro, "exec"), {"__file__": macro})
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
