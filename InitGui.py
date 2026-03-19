import FreeCAD
import FreeCADGui
import os


class InsertDesignerCommand:
    def GetResources(self):
        return {
            'MenuText': 'Insert Designer',
            'ToolTip':  'Open the board game insert designer',
            'Pixmap':   'insert_designer.svg',
        }

    def IsActive(self):
        return True

    def Activated(self):
        try:
            import insert_designer
            import importlib
            importlib.reload(insert_designer)
            insert_designer.main()
        except Exception as e:
            FreeCAD.Console.PrintError(f"InsertDesigner: {e}\n")


FreeCADGui.addCommand("InsertDesigner_Open", InsertDesignerCommand())

_icon_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "BGInsertDesigner", "icons")
FreeCADGui.addIconPath(_icon_dir)


class InsertDesignerWorkbench(FreeCADGui.Workbench):
    MenuText = "Insert Designer"
    ToolTip  = "Board game insert designer tools"
    Icon     = "insert_designer.svg"

    def Initialize(self):
        self.appendToolbar("Insert Designer", ["InsertDesigner_Open"])
        self.appendMenu("Insert Designer",   ["InsertDesigner_Open"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(InsertDesignerWorkbench())
