import os
import nuke
import pipeline_write     # adds the Pipeline tab to Nuke's own Write node automatically
import render_browser
import render_queue_submit
import paai_show_ui

ICON = os.path.join(os.path.dirname(__file__), "icons", "paai_logo_icon32.png")
if not os.path.isfile(ICON):
    ICON = os.path.join(os.path.dirname(__file__), "icons", "paai_logo_icon.png")

m = nuke.menu("Nuke").addMenu("PAAI Pipeline", icon=ICON if os.path.isfile(ICON) else None)
m.addCommand("Render Browser", render_browser.show, "ctrl+shift+b",
             icon=ICON if os.path.isfile(ICON) else None)
m.addCommand("Submit to Render Queue", render_queue_submit.show, "ctrl+shift+q",
             icon=ICON if os.path.isfile(ICON) else None)
m.addCommand("Add PAAI Pipeline tab to selected Writes", pipeline_write.add_to_selected)
m.addCommand("Add PAAI Pipeline tab to all Writes", pipeline_write.setup_all_writes)
m.addCommand("Create / Check Show…", paai_show_ui.show)
render_browser.register_panel()
