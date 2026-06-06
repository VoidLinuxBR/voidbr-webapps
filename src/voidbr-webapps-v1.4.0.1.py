#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#   voidbr-webapps
#   Created: sex 05 jun 2026 13:02:13 -04
#   Altered: sex 05 jun 2026 13:02:13 -04
#   Updated: sex 05 jun 2026 16:38:00 -04
#
#   Copyright (c) 2019-2026, Vilmar Catafesta <vcatafesta@gmail.com>
#   Copyright (c) 2019-2026, ChiliLinux Development Team <https://chililinux.com> <https://github.com/chililinux>
#   Assembled By Vilmar Catafesta for the ChiliLinux project.
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions
#   are met:
#   1. Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#   2. Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
#   THIS SOFTWARE IS PROVIDED BY Vilmar Catafesta ''AS IS'' AND ANY EXPRESS OR
#   IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
#   OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#   IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
#   INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#   NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
#   THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
##############################################################################

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

from gi.repository import Gtk, Gdk, Gio, GLib, GObject

__version__ = "1.4.0.1"

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
.error-text { color: #c01c28; font-size: 11px; margin-top: 2px; }
.preview-icon { border: 1px solid #ccc; padding: 2px; border-radius: 4px; background-color: #fafafa; }
columnview { background-color: @theme_bg_color; }
columnview row { padding: 4px; }
"""

class WebAppItem(GObject.Object):
    """Objeto customizado para encapsular os dados de cada WebApp na Gtk.ColumnView"""
    __gtype_name__ = 'WebAppItem'

    def __init__(self, name, browser, url, icon, index):
        super().__init__()
        self._name = name
        self._browser = browser
        self._url = url
        self._icon = icon
        self._index = index

    @GObject.Property(type=str)
    def name(self): return self._name

    @GObject.Property(type=str)
    def browser(self): return self._browser

    @GObject.Property(type=str)
    def url(self): return self._url

    @GObject.Property(type=str)
    def icon(self): return self._icon

    @GObject.Property(type=int)
    def index(self): return self._index


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
        self.set_default_size(950, 500)

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

        # Configuração do Modelo de Dados ListStore e Ordenação
        self.store = Gio.ListStore.new(WebAppItem)
        
        self.sort_model = Gtk.SortListModel(model=self.store)
        self.selection = Gtk.SingleSelection(model=self.sort_model)
        
        # Criação da ColumnView (Tabela)
        self.columnview = Gtk.ColumnView(model=self.selection)
        self.columnview.set_hexpand(True)
        self.columnview.set_vexpand(True)
        
        self.columnview.connect("activate", self.on_item_activated_view)

        # Vincular gerenciador de ordenação nativa da ColumnView
        self.sort_model.set_sorter(self.columnview.get_sorter())

        # Construção das Colunas
        self.setup_columns()

        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.columnview)
        main_box.append(scroll)

        self.refresh()

    def setup_actions(self):
        act_run = Gio.SimpleAction.new("run-app", None)
        act_run.connect("activate", lambda a, p: self.on_menu_action("run"))
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

    def setup_columns(self):
        # --- Coluna 1: Aplicativo (Ícone + Nome) ---
        factory_name = Gtk.SignalListItemFactory()
        factory_name.connect("setup", self.on_setup_name_column)
        factory_name.connect("bind", self.on_bind_name_column)
        
        col_name = Gtk.ColumnViewColumn(title=_("Aplicativo"), factory=factory_name)
        col_name.set_expand(True)
        
        sorter_name = Gtk.StringSorter.new()
        sorter_name.set_expression(Gtk.PropertyExpression.new(WebAppItem, None, "name"))
        col_name.set_sorter(sorter_name)
        self.columnview.append_column(col_name)

        # --- Coluna 2: Navegador ---
        factory_browser = Gtk.SignalListItemFactory()
        factory_browser.connect("setup", lambda f, i: i.set_child(Gtk.Label(xalign=0, margin_start=6)))
        factory_browser.connect("bind", self.on_bind_browser_column)
        
        col_browser = Gtk.ColumnViewColumn(title=_("Navegador"), factory=factory_browser)
        col_browser.set_fixed_width(220)
        
        sorter_browser = Gtk.StringSorter.new()
        sorter_browser.set_expression(Gtk.PropertyExpression.new(WebAppItem, None, "browser"))
        col_browser.set_sorter(sorter_browser)
        self.columnview.append_column(col_browser)

        # --- Coluna 3: URL ---
        factory_url = Gtk.SignalListItemFactory()
        factory_url.connect("setup", lambda f, i: i.set_child(Gtk.Label(xalign=0, margin_start=6)))
        factory_url.connect("bind", self.on_bind_url_column)
        
        col_url = Gtk.ColumnViewColumn(title=_("URL"), factory=factory_url)
        col_url.set_expand(True)
        
        sorter_url = Gtk.StringSorter.new()
        sorter_url.set_expression(Gtk.PropertyExpression.new(WebAppItem, None, "url"))
        col_url.set_sorter(sorter_url)
        self.columnview.append_column(col_url)

    # --- Handlers de ciclo de vida das fábricas de células da ColumnView ---

    def on_setup_name_column(self, factory, item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, margin_start=6)
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

    def on_bind_name_column(self, factory, item):
        box = item.get_child()
        icon_widget = box.get_first_child()
        label_widget = box.get_last_child()
        
        obj = item.get_item()
        label_widget.set_text(obj.name)
        
        if obj.icon and os.path.exists(obj.icon):
            icon_widget.set_from_file(obj.icon)
            icon_widget.set_pixel_size(24)
        else:
            icon_widget.set_from_icon_name("web-browser")

    def on_bind_browser_column(self, factory, item):
        label = item.get_child()
        obj = item.get_item()
        browsers_map = self._get_installed_browsers()
        friendly_name = browsers_map.get(obj.browser, obj.browser)
        label.set_text(friendly_name)

    def on_bind_url_column(self, factory, item):
        label = item.get_child()
        obj = item.get_item()
        label.set_text(obj.url)

    def on_row_right_clicked(self, gesture, n_press, x, y, item):
        self.selection.set_selected(item.get_position())

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

    def _resolve_browser_exec(self, b_id):
        variants = {
            "chromium": ["chromium"],
            "google-chrome-stable": ["google-chrome-stable", "google-chrome"],
            "brave-browser": ["brave-browser", "brave"],
            "firefox": ["firefox"],
            "microsoft-edge": ["microsoft-edge", "microsoft-edge-stable"],
            "vivaldi": ["vivaldi", "vivaldi-stable"]
        }
        if b_id in variants:
            for variant in variants[b_id]:
                if shutil.which(variant):
                    return variant
        return None

    def _get_installed_browsers(self):
        supported = {
            "chromium": "Chromium",
            "google-chrome-stable": "Google Chrome",
            "brave-browser": "Brave Browser",
            "firefox": "Mozilla Firefox",
            "microsoft-edge": "Microsoft Edge",
            "vivaldi": "Vivaldi"
        }
        installed = {"default": _("Navegador Padrão do Sistema (xdg-open)")}
        for b_id, b_name in supported.items():
            if self._resolve_browser_exec(b_id) is not None:
                installed[b_id] = b_name
        return installed

    def _get_selected_app_and_index(self):
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION: 
            return None, -1
        obj = self.sort_model.get_item(pos)
        if obj and obj.index < len(self.apps):
            return self.apps[obj.index], obj.index
        return None, -1

    def on_item_activated_view(self, view, position):
        if position == Gtk.INVALID_LIST_POSITION: return
        obj = self.sort_model.get_item(position)
        if not obj or obj.index >= len(self.apps): return
        
        app = self.apps[obj.index]
        url = app['url']
        browser_choice = app.get("browser", "default")
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        exec_binary = self._resolve_browser_exec(browser_choice) if browser_choice != "default" else None

        if not exec_binary:
            subprocess.Popen(["xdg-open", url])
        elif browser_choice == "firefox":
            subprocess.Popen([exec_binary, "--new-window", url])
        else:
            subprocess.Popen([exec_binary, f"--app={url}"])

    def on_menu_action(self, action_type):
        pos = self.selection.get_selected()
        if pos != Gtk.INVALID_LIST_POSITION:
            self.on_item_activated_view(None, pos)

    def refresh(self):
        self.store.remove_all()
        for idx, app in enumerate(self.apps):
            browser_label = app.get("browser", "default")
            item_obj = WebAppItem(
                name=app['name'],
                browser=browser_label,
                url=app['url'],
                icon=app.get('icon', ''),
                index=idx
            )
            self.store.append(item_obj)

    def load_apps(self):
        if not JSON_FILE.exists(): return []
        try:
            with open(JSON_FILE, encoding="utf-8") as f:
                data = json.load(f)
                for app in data:
                    if "browser" not in app:
                        app["browser"] = "default"
                return data
        except: return []

    def save_apps(self):
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self.apps, f, indent=2, ensure_ascii=False)

    def is_valid_url(self, url):
        regex = re.compile(
            r'^(?:http|ftp)s?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return re.match(regex, url) is not None

    def _build_browser_combo(self, active_id="default"):
        combo = Gtk.ComboBoxText()
        browsers = self._get_installed_browsers()
        
        if active_id not in browsers:
            browsers[active_id] = active_id

        for b_id, b_name in browsers.items():
            combo.append(b_id, b_name)
        
        combo.set_active_id(active_id)
        return combo

    def _setup_file_dialog_filter(self):
        file_filter = Gtk.FileFilter()
        file_filter.set_name(_("Imagens (*.png, *.jpg, *.svg)"))
        file_filter.add_mime_type("image/png")
        file_filter.add_mime_type("image/jpeg")
        file_filter.add_mime_type("image/svg+xml")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        return Gtk.FileDialog(title=_("Selecionar Ícone Personalizado"), filters=filters)

    def _async_fetch_favicon_preview(self, url, preview_widget, status_widget, dialog_obj):
        if not url or "." not in url: return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            
        GLib.idle_add(lambda: status_widget.set_text(_("Buscando ícone do site...")))

        def worker():
            try:
                domain = url.replace("https://", "").replace("http://", "").split("/")[0]
                if not domain: raise ValueError()
                favicon_url = f"https://www.google.com/s2/favicons?sz=64&domain={domain}"
                req = urllib.request.Request(favicon_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=4) as response:
                    data = response.read()
                
                cache_path = APP_DIR / "temp_preview.png"
                with open(cache_path, "wb") as f:
                    f.write(data)
                
                def update_ui():
                    if not getattr(dialog_obj, "user_locked_custom_icon", False):
                        preview_widget.set_from_file(str(cache_path))
                        dialog_obj.selected_custom_icon = str(cache_path)
                        dialog_obj.is_url_favicon = True
                        status_widget.set_text("")

                GLib.idle_add(update_ui)
            except Exception:
                def update_ui_error():
                    if not getattr(dialog_obj, "user_locked_custom_icon", False):
                        preview_widget.set_from_icon_name("web-browser")
                        dialog_obj.selected_custom_icon = None
                        dialog_obj.is_url_favicon = False
                        status_widget.set_text(_("⚠️ Ícone da URL não encontrado. Usando ícone padrão do sistema."))
                GLib.idle_add(update_ui_error)
                
        threading.Thread(target=worker, daemon=True).start()

    def on_add(self, button):
        dialog = Gtk.Window(title=_("Novo WebApp"), transient_for=self, modal=True, default_width=460, destroy_with_parent=True)
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        dialog.set_child(main_layout)

        grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        main_layout.append(grid)

        url_entry = Gtk.Entry(placeholder_text="https://exemplo.com", hexpand=True)
        name_entry = Gtk.Entry(placeholder_text=_("Nome do App"), hexpand=True)
        browser_combo = self._build_browser_combo("default")

        url_error_label = Gtk.Label(xalign=0)
        url_error_label.add_css_class("error-text")
        name_error_label = Gtk.Label(xalign=0)
        name_error_label.add_css_class("error-text")

        grid.attach(Gtk.Label(label=_("URL:"), xalign=1), 0, 0, 1, 1)
        grid.attach(url_entry, 1, 0, 1, 1)
        grid.attach(url_error_label, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label=_("Nome:"), xalign=1), 0, 2, 1, 1)
        grid.attach(name_entry, 1, 2, 1, 1)
        grid.attach(name_error_label, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label=_("Navegador:"), xalign=1), 0, 4, 1, 1)
        grid.attach(browser_combo, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label=_("Ícone:"), xalign=1), 0, 5, 1, 1)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        grid.attach(icon_box, 1, 5, 1, 1)

        preview_img = Gtk.Image.new_from_icon_name("web-browser")
        preview_img.set_pixel_size(32)
        preview_img.add_css_class("preview-icon")
        icon_box.append(preview_img)

        btn_browse = Gtk.Button(label=_("Escolher Ícone..."))
        btn_browse.set_icon_name("folder-open-symbolic")
        icon_box.append(btn_browse)

        icon_status_label = Gtk.Label(xalign=0)
        icon_status_label.add_css_class("error-text")
        grid.attach(icon_status_label, 1, 6, 1, 1)

        dialog.selected_custom_icon = None
        dialog.user_locked_custom_icon = False
        dialog.is_url_favicon = False

        def on_url_changed(entry):
            url_text = entry.get_text().strip()
            if url_text and "." in url_text:
                self._async_fetch_favicon_preview(url_text, preview_img, icon_status_label, dialog)

        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("leave", lambda c: on_url_changed(url_entry))
        url_entry.add_controller(focus_controller)
        url_entry.connect("activate", on_url_changed)

        def on_browse_clicked(btn):
            file_dialog = self._setup_file_dialog_filter()
            def callback(res, target):
                try:
                    f = res.open_finish(target)
                    if f:
                        dialog.selected_custom_icon = f.get_path()
                        dialog.user_locked_custom_icon = True
                        dialog.is_url_favicon = False
                        preview_img.set_from_file(dialog.selected_custom_icon)
                        icon_status_label.set_text("")
                except Exception: pass
            file_dialog.open(dialog, None, callback)

        btn_browse.connect("clicked", on_browse_clicked)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END, margin_top=10)
        main_layout.append(button_box)

        btn_cancel = Gtk.Button(label=_("Cancelar"))
        btn_cancel.connect("clicked", lambda b: dialog.close())

        btn_save = Gtk.Button(label=_("Salvar"))
        btn_save.add_css_class("suggested-action")
        
        def save_clicked(b):
            name = name_entry.get_text().strip()
            url = url_entry.get_text().strip()
            browser = browser_combo.get_active_id()
            
            name_error_label.set_text("")
            url_error_label.set_text("")
            has_error = False

            if not name:
                name_error_label.set_text(_("O campo nome é obrigatório."))
                has_error = True

            if not url:
                url_error_label.set_text(_("O campo URL é obrigatório."))
                has_error = True
            else:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url

                if not self.is_valid_url(url):
                    url_error_label.set_text(_("URL inválida. Use um formato como: https://exemplo.com"))
                    has_error = True

            if has_error: return

            new_app = {"name": name, "url": url, "icon": "", "browser": browser}
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', name.lower().replace(' ', '-'))
            
            if dialog.selected_custom_icon and os.path.exists(dialog.selected_custom_icon):
                ext = Path(dialog.selected_custom_icon).suffix if not dialog.is_url_favicon else ".png"
                dest_path = ICONS_DIR / f"{clean_name}{ext}"
                try:
                    shutil.copy(dialog.selected_custom_icon, dest_path)
                    new_app["icon"] = str(dest_path)
                except Exception: pass
                
            self.apps.append(new_app)
            self.save_apps()
            self.refresh()
            
            if not new_app["icon"]:
                threading.Thread(target=self.download_favicon, args=(new_app, url), daemon=True).start()
            else:
                self.generate_desktop_file(new_app)

            dialog.close()

        btn_save.connect("clicked", save_clicked)
        button_box.append(btn_cancel)
        button_box.append(btn_save)
        dialog.present()

    def on_edit(self):
        app, idx = self._get_selected_app_and_index()
        if not app: return

        dialog = Gtk.Window(title=_("Editar WebApp"), transient_for=self, modal=True, default_width=460, destroy_with_parent=True)
        main_layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        dialog.set_child(main_layout)

        grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        main_layout.append(grid)

        url_entry = Gtk.Entry(text=app["url"], hexpand=True)
        name_entry = Gtk.Entry(text=app["name"], hexpand=True)
        browser_combo = self._build_browser_combo(app.get("browser", "default"))

        url_error_label = Gtk.Label(xalign=0)
        url_error_label.add_css_class("error-text")
        name_error_label = Gtk.Label(xalign=0)
        name_error_label.add_css_class("error-text")

        grid.attach(Gtk.Label(label=_("URL:"), xalign=1), 0, 0, 1, 1)
        grid.attach(url_entry, 1, 0, 1, 1)
        grid.attach(url_error_label, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label=_("Nome:"), xalign=1), 0, 2, 1, 1)
        grid.attach(name_entry, 1, 2, 1, 1)
        grid.attach(name_error_label, 1, 3, 1, 1)

        grid.attach(Gtk.Label(label=_("Navegador:"), xalign=1), 0, 4, 1, 1)
        grid.attach(browser_combo, 1, 4, 1, 1)

        grid.attach(Gtk.Label(label=_("Ícone:"), xalign=1), 0, 5, 1, 1)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        grid.attach(icon_box, 1, 5, 1, 1)

        preview_img = Gtk.Image()
        preview_img.set_pixel_size(32)
        preview_img.add_css_class("preview-icon")
        if app.get("icon") and os.path.exists(app["icon"]):
            preview_img.set_from_file(app["icon"])
        else:
            preview_img.set_from_icon_name("web-browser")
        icon_box.append(preview_img)

        btn_browse = Gtk.Button(label=_("Escolher Ícone..."))
        btn_browse.set_icon_name("folder-open-symbolic")
        icon_box.append(btn_browse)

        icon_status_label = Gtk.Label(xalign=0)
        icon_status_label.add_css_class("error-text")
        grid.attach(icon_status_label, 1, 6, 1, 1)

        dialog.selected_custom_icon = app.get("icon")
        dialog.user_locked_custom_icon = True if (app.get("icon") and os.path.exists(app["icon"])) else False
        dialog.is_url_favicon = False

        def on_url_changed(entry):
            url_text = entry.get_text().strip()
            if url_text and "." in url_text:
                dialog.user_locked_custom_icon = False
                self._async_fetch_favicon_preview(url_text, preview_img, icon_status_label, dialog)

        focus_controller = Gtk.EventControllerFocus.new()
        focus_controller.connect("leave", lambda c: on_url_changed(url_entry))
        url_entry.add_controller(focus_controller)
        url_entry.connect("activate", on_url_changed)

        def on_browse_clicked(btn):
            file_dialog = self._setup_file_dialog_filter()
            def callback(res, target):
                try:
                    f = res.open_finish(target)
                    if f:
                        dialog.selected_custom_icon = f.get_path()
                        dialog.user_locked_custom_icon = True
                        dialog.is_url_favicon = False
                        preview_img.set_from_file(dialog.selected_custom_icon)
                        icon_status_label.set_text("")
                except Exception: pass
            file_dialog.open(dialog, None, callback)

        btn_browse.connect("clicked", on_browse_clicked)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.END, margin_top=10)
        main_layout.append(button_box)

        btn_cancel = Gtk.Button(label=_("Cancelar"))
        btn_cancel.connect("clicked", lambda b: dialog.close())

        btn_save = Gtk.Button(label=_("Salvar"))
        btn_save.add_css_class("suggested-action")
        
        def save_clicked(b):
            name = name_entry.get_text().strip()
            url = url_entry.get_text().strip()
            browser = browser_combo.get_active_id()
            
            name_error_label.set_text("")
            url_error_label.set_text("")
            has_error = False

            if not name:
                name_error_label.set_text(_("O campo nome é obrigatório."))
                has_error = True

            if not url:
                url_error_label.set_text(_("O campo URL é obrigatório."))
                has_error = True
            else:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url

                if not self.is_valid_url(url):
                    url_error_label.set_text(_("URL inválida. Use um formato como: https://exemplo.com"))
                    has_error = True

            if has_error: return

            url_changed = (url != app["url"])
            icon_changed = (dialog.selected_custom_icon != app.get("icon"))

            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', name.lower().replace(' ', '-'))

            if dialog.selected_custom_icon and os.path.exists(dialog.selected_custom_icon) and (icon_changed or url_changed):
                ext = Path(dialog.selected_custom_icon).suffix if not dialog.is_url_favicon else ".png"
                dest_path = ICONS_DIR / f"{clean_name}{ext}"
                try:
                    if app.get("icon") and os.path.exists(app["icon"]) and app["icon"] != dialog.selected_custom_icon:
                        os.remove(app["icon"])
                    shutil.copy(dialog.selected_custom_icon, dest_path)
                    app["icon"] = str(dest_path)
                except Exception: pass
            elif url_changed and not icon_changed and not dialog.selected_custom_icon:
                if app.get("icon") and os.path.exists(app["icon"]):
                    try: os.remove(app["icon"])
                    except: pass
                app["icon"] = ""
                threading.Thread(target=self.download_favicon, args=(app, url), daemon=True).start()
            
            app["name"] = name
            app["url"] = url
            app["browser"] = browser
            self.save_apps()
            self.refresh()
            
            if not (url_changed and not icon_changed and not dialog.selected_custom_icon):
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
        app, idx = self._get_selected_app_and_index()
        if idx != -1 and app:
            if app.get("icon") and os.path.exists(app["icon"]):
                try: os.remove(app["icon"])
                except: pass
                
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '', app['name'].lower().replace(' ', '-'))
            desktop_file = Path.home() / f".local/share/applications/voidbr-webapp-{clean_name}.desktop"
            if desktop_file.exists():
                try: os.remove(desktop_file)
                except: pass

            del self.apps[idx]
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

        browser_choice = app.get("browser", "default")
        exec_binary = self._resolve_browser_exec(browser_choice) if browser_choice != "default" else None
        
        if not exec_binary:
            exec_command = f'xdg-open "{url}"'
        elif browser_choice == "firefox":
            exec_command = f'{exec_binary} --new-window "{url}"'
        else:
            exec_command = f'{exec_binary} --app="{url}"'

        desktop = f"""[Desktop Entry]
Type=Application
Name={app['name']}
Exec={exec_command}
Icon={icon_to_use}
Terminal=false
Categories=X-VoidBR-WebApps;
"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(desktop)
        os.chmod(filename, 0o755)
        
        try:
            subprocess.run(["xdg-desktop-menu", "forceupdate"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def on_generate(self, button):
        app, idx = self._get_selected_app_and_index()
        if app:
            self.generate_desktop_file(app)
            print(f"Atalho para {app['name']} regerado manualmente.")

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
            artists=[
                "Vilmar Catafesta <vcatafesta@gmail.com>",
                "Eduardo Charquero <eduardocharquero@gmail.com>"
            ]
        )
        about.set_logo_icon_name("voidbr")
        about.present()

if __name__ == "__main__":
    app = WebAppManager()
    app.run()
