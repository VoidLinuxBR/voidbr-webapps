#!/usr/bin/env python3

import os
import sys

# Força renderização estável por software na VM
os.environ["GSK_RENDERER"] = "cairo"
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

# Desativa logs, warnings e mensagens do GDK/GLib no console
os.environ["G_MESSAGES_TO_CONSOLE"] = "none"
os.environ["G_MESSAGES_DEBUG"] = "none"

# Redireciona mensagens residuais de erro de baixo nível para o limbo
sys.stderr = open(os.devnull, 'w')

import json
import re
import subprocess
import urllib.request
from pathlib import Path
import threading
import shutil
import gettext

import gi
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gdk, Gio, GLib

__version__ = "1.3.9.2"

# Configuração do Gettext para Internacionalização
APP_NAME = "voidbr-webapps"
LOCALEDIR = "/usr/share/locale"
gettext.bindtextdomain(APP_NAME, LOCALEDIR)
gettext.textdomain(APP_NAME)
_ = gettext.gettext

APP_DIR = Path.home() / ".local/share/voidbr-webapps"
ICONS_DIR = APP_DIR / "icons"
APP_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

JSON_FILE = APP_DIR / "webapps.json"

CSS_DATA = b"""
.btn-add { color: white; background-color: #26a269; }
.btn-remove { color: white; background-color: #c01c28; }
.btn-generate { color: black; background-color: #f5c211; }
.btn-about { color: black; background-color: #e1e1e1; }
.btn-exit { color: white; background-color: #e01b24; }
.success-icon { color: #26a269; margin-right: 8px; }
.app-icon { margin-right: 8px; }
"""

class WebAppManager(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.voidlinux.VoidBR.WebApps")

    def do_activate(self):
        self.win = MainWindow(self)
        self.win.present()

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)

        self.set_title(f"VoidBR WebApps - v{__version__}")
        self.set_default_size(900, 500)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_DATA)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.apps = self.load_apps()
        self.setup_actions()

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, 
                           margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        self.set_child(main_box)

        toolbar = Gtk.Box(spacing=10, hexpand=True)
        main_box.append(toolbar)

        btn_add = Gtk.Button(label=_("Adicionar"))
        btn_add.set_icon_name("list-add-symbolic")
        btn_add.add_css_class("suggested-action")
        btn_add.set_tooltip_text(_("Adicionar um novo WebApp e gerar seu atalho automaticamente"))
        btn_add.connect("clicked", self.on_add)

        btn_remove = Gtk.Button(label=_("Remover"))
        btn_remove.set_icon_name("user-trash-symbolic")
        btn_remove.add_css_class("destructive-action")
        btn_remove.set_tooltip_text(_("Remover o WebApp selecionado e apagar seu atalho do sistema"))
        btn_remove.connect("clicked", self.on_remove)

        btn_generate = Gtk.Button(label=_("Gerar Atalho"))
        btn_generate.set_icon_name("emblem-system-symbolic")
        btn_generate.add_css_class("btn-generate")
        btn_generate.set_tooltip_text(_("Regerar manualmente o arquivo de atalho do WebApp selecionado"))
        btn_generate.connect("clicked", self.on_generate)

        spacer = Gtk.Box(hexpand=True)

        btn_about = Gtk.Button(label=_("Sobre"))
        btn_about.set_icon_name("help-about-symbolic")
        btn_about.add_css_class("btn-about")
        btn_about.set_tooltip_text(_("Ver informações, desenvolvedores e créditos do projeto"))
        btn_about.connect("clicked", self.on_about)

        btn_exit = Gtk.Button(label=_("Sair"))
        btn_exit.set_icon_name("application-exit-symbolic")
        btn_exit.add_css_class("btn-exit")
        btn_exit.set_tooltip_text(_("Fechar o gerenciador VoidBR WebApps"))
        btn_exit.connect("clicked", lambda b: self.close())

        toolbar.append(btn_add)
        toolbar.append(btn_remove)
        toolbar.append(btn_generate)
        toolbar.append(spacer)
        toolbar.append(btn_about)
        toolbar.append(btn_exit)

        self.store = Gtk.StringList()
        self.selection = Gtk.SingleSelection(model=self.store)
        self.listview = Gtk.ListView(model=self.selection, factory=self.create_factory())
        
        self.listview.connect("activate", self.on_item_activated)

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.listview)
        main_box.append(scroll)

        self.refresh()

    def setup_actions(self):
        act_run = Gio.SimpleAction.new("run-app", None)
        act_run.connect("activate", lambda a, p: self.on_item_activated(None, self.selection.get_selected()))
        self.add_action(act_run)

        act_edit = Gio.SimpleAction.new("edit-app", None)
        act_edit.connect("activate", lambda a, p: self.on_edit())
        self.add_action(act_edit)

        act_gen = Gio.SimpleAction.new("generate-app", None)
        act_gen.connect("activate", lambda a, p: self.on_generate(None))
        self.add_action(act_gen)

        act_rem = Gio.SimpleAction.new("remove-app", None)
        act_rem.connect("activate", lambda a, p: self.on_remove(None))
        self.add_action(act_rem)

    def create_factory(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.factory_setup)
        factory.connect("bind", self.factory_bind)
        return factory

    def factory_setup(self, factory, item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        icon = Gtk.Image()
        icon.add_css_class("app-icon")
        label = Gtk.Label(xalign=0)
        box.append(icon)
        box.append(label)
        item.set_child(box)

        gesture = Gtk.GestureClick.new()
        gesture.set_button(Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", self.on_row_right_clicked, item)
        box.add_controller(gesture)

    def factory_bind(self, factory, item):
        box = item.get_child()
        icon_widget = box.get_first_child()
        label_widget = box.get_last_child()
        
        position = item.get_position()
        if position < len(self.apps):
            app = self.apps[position]
            label_widget.set_text(f"{app['name']}  →  {app['url']}")
            
            icon_path = app.get("icon")
            if icon_path and os.path.exists(icon_path):
                icon_widget.set_from_file(icon_path)
                icon_widget.set_pixel_size(24)
                icon_widget.remove_css_class("success-icon")
            else:
                icon_widget.set_from_icon_name("emblem-ok-symbolic")
                icon_widget.add_css_class("success-icon")

    def on_row_right_clicked(self, gesture, n_press, x, y, item):
        position = item.get_position()
        self.selection.set_selected(position)

        menu = Gio.Menu.new()
        menu.append(_("Executar"), "win.run-app")
        menu.append(_("Editar"), "win.edit-app")
        menu.append(_("Gerar Atalho"), "win.generate-app")
        menu.append(_("Remover"), "win.remove-app")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(item.get_child())
        
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()

    def _get_browser_exec(self):
        browsers = ["chromium", "google-chrome-stable", "google-chrome", "brave-browser", "microsoft-edge", "vivaldi"]
        for b in browsers:
            if shutil.which(b):
                return b
        return None

    def on_item_activated(self, listview, position):
        if position == Gtk.INVALID_LIST_POSITION or position >= len(self.apps): return
        app = self.apps[position]
        url = app['url']
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        browser = self._get_browser_exec()
        if browser:
            subprocess.Popen([browser, f"--app={url}"])
        else:
            subprocess.Popen(["xdg-open", url])

    def refresh(self):
        while self.store.get_n_items():
            self.store.remove(0)
        for app in self.apps:
            self.store.append(f"{app['name']}  →  {app['url']}")

    def load_apps(self):
        if not JSON_FILE.exists(): return []
        try:
            with open(JSON_FILE, encoding="utf-8") as f:
                return json.load(f)
        except: return []

    def save_apps(self):
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.apps, f, indent=2, ensure_ascii=False)

    def on_add(self, button):
        dialog = Gtk.Window(title=_("Novo WebApp"), transient_for=self, modal=True, default_width=400, destroy_with_parent=True)
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        dialog.set_child(main_layout)

        grid = Gtk.Grid(row_spacing=10, column_spacing=10)
        main_layout.append(grid)

        url_entry = Gtk.Entry(placeholder_text="https://exemplo.com", hexpand=True)
        name_entry = Gtk.Entry(placeholder_text=_("Nome do App"), hexpand=True)

        grid.attach(Gtk.Label(label=_("URL:"), xalign=1), 0, 0, 1, 1)
        grid.attach(url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Nome:"), xalign=1), 0, 1, 1, 1)
        grid.attach(name_entry, 1, 1, 1, 1)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        main_layout.append(button_box)

        btn_cancel = Gtk.Button(label=_("Cancelar"))
        btn_cancel.connect("clicked", lambda b: dialog.close())

        btn_save = Gtk.Button(label=_("Salvar"))
        btn_save.add_css_class("suggested-action")
        
        def save_clicked(b):
            name = name_entry.get_text().strip()
            url = url_entry.get_text().strip()
            if name and url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                new_app = {"name": name, "url": url, "icon": ""}
                self.apps.append(new_app)
                self.save_apps()
                self.refresh()
                
                threading.Thread(target=self.download_favicon, args=(new_app, url), daemon=True).start()
            dialog.close()

        btn_save.connect("clicked", save_clicked)
        button_box.append(btn_cancel)
        button_box.append(btn_save)
        dialog.present()

    def on_edit(self):
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION: return
        app = self.apps[pos]

        dialog = Gtk.Window(title=_("Editar WebApp"), transient_for=self, modal=True, default_width=400, destroy_with_parent=True)
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        dialog.set_child(main_layout)

        grid = Gtk.Grid(row_spacing=10, column_spacing=10)
        main_layout.append(grid)

        url_entry = Gtk.Entry(text=app["url"], hexpand=True)
        name_entry = Gtk.Entry(text=app["name"], hexpand=True)

        grid.attach(Gtk.Label(label=_("URL:"), xalign=1), 0, 0, 1, 1)
        grid.attach(url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Nome:"), xalign=1), 0, 1, 1, 1)
        grid.attach(name_entry, 1, 1, 1, 1)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END)
        main_layout.append(button_box)

        btn_cancel = Gtk.Button(label=_("Cancelar"))
        btn_cancel.connect("clicked", lambda b: dialog.close())

        btn_save = Gtk.Button(label=_("Salvar"))
        btn_save.add_css_class("suggested-action")
        
        def save_clicked(b):
            name = name_entry.get_text().strip()
            url = url_entry.get_text().strip()
            if name and url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                if url != app["url"]:
                    if app.get("icon") and os.path.exists(app["icon"]):
                        try: os.remove(app["icon"])
                        except: pass
                    app["icon"] = ""
                    threading.Thread(target=self.download_favicon, args=(app, url), daemon=True).start()
                app["name"] = name
                app["url"] = url
                self.save_apps()
                self.refresh()
                
                self.generate_desktop_file(app)
            dialog.close()

        btn_save.connect("clicked", save_clicked)
        button_box.append(btn_cancel)
        button_box.append(btn_save)
        dialog.present()

    def download_favicon(self, app_dict, url):
        try:
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
            if not domain: return
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', app_dict['name'].lower().replace(' ', '-'))
            icon_path = ICONS_DIR / f"{clean_name}.png"
            favicon_url = f"https://www.google.com/s2/favicons?sz=64&domain={domain}"
            req = urllib.request.Request(favicon_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                with open(icon_path, 'wb') as f:
                    f.write(response.read())
            app_dict["icon"] = str(icon_path)
            
            self.generate_desktop_file(app_dict)
            GLib.idle_add(self.save_and_refresh_ui)
        except Exception as e:
            sys.__stderr__.write(f"Erro ao baixar ícone para {url}: {e}\n")
            self.generate_desktop_file(app_dict)
            GLib.idle_add(self.save_and_refresh_ui)

    def save_and_refresh_ui(self):
        self.save_apps()
        self.refresh()

    def on_remove(self, button):
        pos = self.selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION:
            app = self.apps[pos]
            if app.get("icon") and os.path.exists(app["icon"]):
                try: os.remove(app["icon"])
                except: pass
                
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', app['name'].lower().replace(' ', '-'))
            desktop_file = Path.home() / f".local/share/applications/voidbr-webapp-{clean_name}.desktop"
            if desktop_file.exists():
                try: os.remove(desktop_file)
                except: pass

            del self.apps[pos]
            self.save_apps()
            self.refresh()

    def generate_desktop_file(self, app):
        desktop_dir = Path.home() / ".local/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', app['name'].lower().replace(' ', '-'))
        filename = desktop_dir / f"voidbr-webapp-{clean_name}.desktop"

        icon_to_use = app.get("icon") if (app.get("icon") and os.path.exists(app["icon"])) else "web-browser"
        url = app['url']
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        browser = self._get_browser_exec()
        if browser:
            exec_command = f'{browser} --app="{url}"'
        else:
            exec_command = f'xdg-open "{url}"'

        desktop = f"""[Desktop Entry]
Type=Application
Name={app['name']}
Exec={exec_command}
Icon={icon_to_use}
Terminal=false
Categories=Network;X-VoidBR-WebApps;
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(desktop)
        os.chmod(filename, 0o755)
        
        try:
            subprocess.run(["xdg-desktop-menu", "forceupdate"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def on_generate(self, button):
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION: return
        self.generate_desktop_file(self.apps[pos])
        print(f"Atalho para {self.apps[pos]['name']} regerado manualmente.")

    def on_about(self, button):
        about = Gtk.AboutDialog(
            transient_for=self,
            modal=True,
            program_name="VoidBR WebApps",
            version=__version__,
            copyright="© 2026 Comunidade VoidBR",
            license_type=Gtk.License.GPL_3_0,
            comments=_("Gerenciador oficial de WebApps para o ecossistema VoidBR."),
            website="https://github.com/voidlinuxbr/voidbr-webapps",
            website_label=_("Website do Projeto"),
            authors=["Vilmar Catafesta <vcatafesta@gmail.com>"],
            artists=["Eduardo Charquero <eduardocharquero@gmail.com>"]
        )
        about.set_logo_icon_name("voidbr")
        about.present()

if __name__ == "__main__":
    app = WebAppManager()
    app.run()
