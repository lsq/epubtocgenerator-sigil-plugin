#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

import os
import sys
import math
import json
from pathlib import Path
import ast
import regex as re
import copy

from utilities import (
    UpdateChecker,
    taglist,
    combobox_defaults,
    remove_dupes,
    rules_default,
    ZONE_TYPES,
)
from parsing_engine import MarkupParser

from plugin_utils import Qt, QtCore, QtGui, QtWidgets, QAction
from plugin_utils import PluginApplication, iswindows, _t  # , Signal, Slot, loadUi


DEBUG = 0
if DEBUG:
    if "PySide6" in sys.modules:
        print("Plugin using PySide6")
    else:
        print("Plugin using PyQt5")

BAIL_OUT = False
PROCESSED = False


def launch_gui(bk, prefs):

    icon = os.path.join(bk._w.plugin_dir, bk._w.plugin_name, "plugin.svg")
    mdp = True if iswindows else False
    app = PluginApplication(
        sys.argv,
        bk,
        app_icon=icon,
        match_dark_palette=mdp,
        dont_use_native_menubars=True,
    )

    win = guiMain(bk, prefs)
    # Use exec() and not exec_() for PyQt5/PySide6 compliance
    app.exec()
    return win.getAbort()


class ConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent, title_rules, combobox_values):
        super(ConfigDialog, self).__init__()
        self.gui = parent
        self.combobox_values = combobox_values
        self.title_rules = title_rules
        self.qlinedit_widgets = {}
        self.qlinedit_widgets["rules"] = {}
        self.qlinedit_widgets["style"] = {}
        self.setup_ui()
        self.setWindowTitle(_t("ConfigDialog", "Customize Title Rules"))

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        columns_frame = QtWidgets.QHBoxLayout()
        style_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(columns_frame)
        layout.addLayout(style_layout)

        # How many columns of nine items each will it take to display
        # a text box for each tag in taglist?
        num_cols = len(self.title_rules["rules"])

        # Create an integer-indexed dictionary of QVBoxLayouts representing the number of
        # columns necessary. Added left to right in the parent QHBoxLayout.
        column = {}
        for i in range(1, num_cols + 1):
            column[i] = QtWidgets.QVBoxLayout()
            column[i].setAlignment(Qt.AlignLeft)
            columns_frame.addLayout(column[i])

        # Create a dictionary of QLineEdit widgets (indexed by tag name) and stack them
        # (top to bottom) and their labels in as many columns as it takes.
        curr_col = 1
        tooltip = {}
        tooltipt = _t(
            "ConfigDialog",
            'Comma separated list of html elements (no angle "&lt;" brackets).',
        )
        tooltip["level"] = _t(
            "ConfigDialog",
            "Level(chapter/section/subsection) number: 1, 2, 3",
        )
        tooltip["element"] = _t(
            "ConfigDialog",
            "one of html elements for parent tag",
        )
        tooltip["parent_attrs"] = _t(
            "ConfigDialog",
            'html atrribute of json format: {"class": "calibre5"}',
        )
        tooltip["child_element"] = _t(
            "ConfigDialog",
            "one of html elements for child tag",
        )
        tooltip["child_attrs"] = _t(
            "ConfigDialog",
            'html atrribute of json format: {"class": "calibre5"}',
        )
        tooltip["text_pattern"] = _t(
            "ConfigDialog",
            "regual expression or normal text",
        )
        tooltip["zone_type"] = _t(
            "ConfigDialog",
            "zone_type for example: frontmatter/part/chapter/appendix/backmatter",
        )
        tooltip["case_insensitive"] = _t(
            "ConfigDialog",
            "text pattern case sensitive",
        )
        tooltip["display_template"] = _t(
            "ConfigDialog",
            "title format of toc",
        )
        tooltip["description"] = _t(
            "ConfigDialog",
            "description for rules",
        )
        rules_array = self.qlinedit_widgets["rules"]
        for rule in self.title_rules["rules"]:
            # Column item limit surpassed - switch to next column.
            if curr_col > 1:
                column[curr_col - 1].addStretch()

            for k, v in rule.items():
                # Add lable and QLineEdit widget to current column.
                # self.gui.text_panel.insertHtml("<h4>{}: {}...</h4><br>".format(k, v))
                label = QtWidgets.QLabel(
                    '{} "{}" {}'.format(
                        _t("ConfigDialog", "Choices to change"),
                        k,
                        _t("ConfigDialog", "to:"),
                    ),
                    self,
                )
                label.setAlignment(Qt.AlignCenter)
                rules_array["{}-{}".format(curr_col, k)] = QtWidgets.QLineEdit(
                    "{}".format(v), self
                )
                rules_array["{}-{}".format(curr_col, k)].setToolTip(
                    "<p>{}".format(tooltip["{}".format(k)])
                )
                # self.gui.text_panel.insertHtml("<h5>{}: {}...</h5><br>".format(k, v))
                column[curr_col].addWidget(label)
                column[curr_col].addWidget(rules_array["{}-{}".format(curr_col, k)])
                # if not len("{}".format(v)):
                # rules_array["{}-{}".format(curr_col, k)].setDisabled(True)
            curr_col += 1

        column[curr_col - 1].addStretch()

        styles = self.title_rules["style"]
        style_num = len(styles)
        st_column = {}
        for i in range(1, style_num + 1):
            st_column[i] = QtWidgets.QVBoxLayout()
            st_column[i].setAlignment(Qt.AlignLeft)
            style_layout.addLayout(st_column[i])

        style_array = self.qlinedit_widgets["style"]
        for idx, level in enumerate(styles):
            slabel = QtWidgets.QLabel("Level: {}".format(level), self)
            slabel.setAlignment(Qt.AlignCenter)
            style_array["{}".format(level)] = QtWidgets.QLineEdit(
                "{}".format(styles["{}".format(level)]), self
            )
            style_array["{}".format(level)].setToolTip(
                "<p>Choices change Toc.html level {} style".format(level)
            )
            st_column[idx + 1].addWidget(slabel)
            st_column[idx + 1].addWidget(style_array["{}".format(level)])

        vcolumn = QtWidgets.QVBoxLayout()
        vcolumn.setAlignment(Qt.AlignLeft)
        layout.addLayout(vcolumn)
        label = QtWidgets.QLabel(
            '{} "{}" {}'.format(
                _t("ConfigDialog", "Choices to change"),
                "Tags",
                _t("ConfigDialog", "elements to:"),
            ),
            self,
        )
        label.setAlignment(Qt.AlignCenter)
        self.qlinedit_widgets["tags"] = QtWidgets.QLineEdit(
            ", ".join(self.combobox_values["{}".format("tags")]), self
        )
        self.qlinedit_widgets["tags"].setToolTip("<p>{}".format(tooltipt))
        vcolumn.addWidget(label)
        vcolumn.addWidget(self.qlinedit_widgets["tags"])

        vcolumn.addStretch()

        layout.addSpacing(10)
        attrs_layout = QtWidgets.QVBoxLayout()
        attrs_layout.setAlignment(Qt.AlignCenter)
        layout.addLayout(attrs_layout)
        label = QtWidgets.QLabel(
            _t("ConfigDialog", "HTML attributes available to search for:"), self
        )
        label.setAlignment(Qt.AlignCenter)
        self.attrs_txtBox = QtWidgets.QLineEdit(
            ", ".join(self.combobox_values["attrs"]), self
        )
        self.attrs_txtBox.setToolTip(
            "<p>{}".format(
                _t(
                    "ConfigDialog",
                    "Comma separated list of html attribute names (no quotes).",
                )
            )
        )
        attrs_layout.addWidget(label)
        attrs_layout.addWidget(self.attrs_txtBox)

        layout.addSpacing(10)
        right_layout = QtWidgets.QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        layout.addLayout(right_layout)

        self.auto_headless = QtWidgets.QCheckBox(
            _t("ConfigDialog", "Plugin runs headless in Automate Lists"), self
        )
        self.auto_headless.setToolTip(
            "<p>{}".format(
                _t(
                    "ConfigDialog",
                    "The GUI will not be used when the plugin is run via an Automate List",
                )
            )
        )
        self.auto_headless.setChecked(self.gui.misc_prefs["automate_runs_headless"])
        right_layout.addWidget(self.auto_headless)
        right_layout.insertSpacing(1, 30)

        reset_button = QtWidgets.QPushButton(
            _t("ConfigDialog", "Reset all defaults"), self
        )
        reset_button.setToolTip(
            "<p>{}".format(
                _t("ConfigDialog", "Reset all settings to original defaults.")
            )
        )
        reset_button.clicked.connect(self.reset_defaults)
        right_layout.addWidget(reset_button)

        layout.addSpacing(10)
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def save_settings(self):
        # Save current dialog sttings back to JSON config file
        for tag in ["tags"]:
            tmp_list = str(self.qlinedit_widgets[tag].displayText()).split(",")
            tmp_list = remove_dupes([x.strip(" ") for x in tmp_list])
            self.combobox_values["{}".format(tag)] = list(filter(None, tmp_list))

        tmp_list = str(self.attrs_txtBox.displayText()).split(",")
        tmp_list = remove_dupes([x.strip(" ") for x in tmp_list])
        self.combobox_values["attrs"] = list(filter(None, tmp_list))
        self.gui.misc_prefs["automate_runs_headless"] = self.auto_headless.isChecked()
        for k, v in self.qlinedit_widgets["rules"].items():
            idx = str(k).split("-")
            if (
                idx[1] == "case_insensitive"
                or idx[1] == "parent_attrs"
                or idx[1] == "child_attrs"
            ):
                tmp_list = ast.literal_eval(v.displayText())
            else:
                tmp_list = str(v.displayText())
            self.title_rules["rules"][int(idx[0]) - 1]["{}".format(idx[1])] = tmp_list
        for k, v in self.qlinedit_widgets["style"].items():
            tmp_list = ast.literal_eval(v.displayText())
            self.title_rules["style"]["{}".format(k)] = tmp_list
        self.accept()

    def reset_defaults(self):
        caption = _t("ConfigDialog", "Are you sure?")
        msg = "<p>{}".format(
            _t(
                "ConfigDialog",
                "Reset all customizable options to their original defaults?",
            )
        )
        if (
            QtWidgets.QMessageBox.question(
                self,
                caption,
                msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            )
            == QtWidgets.QMessageBox.Yes
        ):
            self.gui.misc_prefs["automate_runs_headless"] = False
            for tag in ["tags"]:
                self.combobox_values["{}".format(tag)] = combobox_defaults[
                    "{}".format(tag)
                ]
            self.combobox_values["attrs"] = combobox_defaults["attrs"]
            self.title_rules["rules"] = copy.deepcopy(rules_default["rules"])
            self.accept()


class guiMain(QtWidgets.QMainWindow):
    def __init__(self, bk, prefs):
        super(guiMain, self).__init__()
        self.taglist = taglist
        # Edit Plugin container object
        self.bk = bk

        # Handy prefs groupings
        self.misc_prefs = prefs["miscellaneous_settings"]
        self.update_prefs = prefs["update_settings"]
        self.combobox_values = prefs["combobox_values"]
        self.title_rules = prefs["title_rules"]

        self._ok_to_close = False
        # Check online github files for newer version
        self.update, self.newversion = self.check_for_update()
        self.setup_ui()

    def setup_ui(self):
        app = PluginApplication.instance()
        p = app.palette()
        link_color = p.color(QtGui.QPalette.Active, QtGui.QPalette.Link).name()

        self.NO_ATTRIB_STR = _t("guiMain", "No attributes (naked tag)")
        self.NO_TAG_STR = _t("guiMain", "No tags(All tags)")
        self.setWindowTitle(_t("guiMain", "TocGenerator(Basic)"))
        self.setGeometry(100, 100, 1000, 600)

        configAct = QAction(_t("guiMain", "Config"), self)
        configAct.setShortcut("Ctrl+Alt+C")
        tooltip = _t("guiMain", "Configure")
        configAct.setToolTip(tooltip + " " + self.bk._w.plugin_name)
        icon = os.path.join(self.bk._w.plugin_dir, self.bk._w.plugin_name, "config.svg")
        configAct.setIcon(QtGui.QIcon(icon))
        configAct.triggered.connect(self.showConfig)

        editToolBar = self.addToolBar(_t("guiMain", "Edit"))
        editToolBar.setMovable(False)
        editToolBar.setFloatable(False)
        editToolBar.setContextMenuPolicy(Qt.PreventContextMenu)
        editToolBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        editToolBar.addAction(configAct)

        layout = QtWidgets.QVBoxLayout()

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        if self.update:
            update_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(update_layout)
            self.label = QtWidgets.QLabel()
            self.label.setText(
                _t("guiMain", "Plugin Update Available") + " " + str(self.newversion)
            )
            self.label.setStyleSheet("QLabel {{color: {};}}".format(link_color))
            update_layout.addWidget(self.label)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            [
                "Level",
                "Element",
                "Class",
                "Child Element",
                "Child Class",
                "Text Pattern",
                "Case Insensitive",
                "Zone Type",
                "Display Template",
            ]
        )
        # 设置水平表头样式
        #         self.table.horizontalHeader().setStyleSheet(
        #             """
        #     QHeaderView::section {
        #         background-color: #4CAF50;
        #         color: white;
        #         font-weight: bold;
        #         border: 1px solid #45a049;
        #         padding: 4px;
        #     }
        # """
        # )
        self.table.horizontalHeader().setStyleSheet(
            """
    QHeaderView::section {
        background-color: white;
        color: #2c3e50;
        padding: 8px 10px;
        border: none;
        border-right: 1px solid #eee;
        font-weight: 600;
        font-size: 13px;
        text-align: left;
    }
    QHeaderView::section:last {
        border-right: none;
    }
"""
        )
        # 同时给表格加个外框提升质感
        self.table.setStyleSheet(
            "QTableWidget { border: 1px solid #ddd; border-radius: 6px; }"
        )

        # 可选：设置垂直表头样式
        self.table.verticalHeader().setStyleSheet(
            """
    QHeaderView::section {
        background-color: #2196F3;
        color: white;
        font-weight: bold;
    }
"""
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # self.table.horizontalHeader().setSectionResizeMode( QtWidgets.QHeaderView.Stretch)
        # self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(1, 120)
        self.table.horizontalHeader().setSectionResizeMode(
            5, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            8, QtWidgets.QHeaderView.Stretch
        )
        layout.addWidget(self.table)
        self.load_config()

        check_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(check_layout)
        self.check_text = QtWidgets.QCheckBox(
            _t("guiMain", "Use GUI rules setting(Basic)."), self
        )
        # self.check_text.stateChanged.connect(self.update_txt_box)
        check_layout.addWidget(self.check_text)

        layout.addSpacing(10)
        self.text_panel = QtWidgets.QTextEdit()
        self.text_panel.setReadOnly(True)
        layout.addWidget(self.text_panel)

        layout.addSpacing(10)
        first_button_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(first_button_layout)
        save_config_button = QtWidgets.QPushButton(_t("guiMain", "Save Config"), self)
        save_config_button.setToolTip(
            "<p>{}".format(_t("guiMain", "Save current config for headless use"))
        )
        first_button_layout.addWidget(save_config_button)
        save_config_button.clicked.connect(self._save_config_clicked)

        self.btn_add = QtWidgets.QPushButton("Add Rule")
        self.btn_add.clicked.connect(self.add_rule)
        first_button_layout.addWidget(self.btn_add)

        self.btn_delete = QtWidgets.QPushButton("Delete Rule")
        self.btn_delete.clicked.connect(self.delete_rule)
        first_button_layout.addWidget(self.btn_delete)

        layout.addSpacing(10)
        button_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(button_layout)
        self.process_button = QtWidgets.QPushButton(_t("guiMain", "Generate TOC"), self)
        self.process_button.setToolTip(
            "<p>{}".format(_t("guiMain", "Generate Toc of the book files"))
        )
        self.process_button.clicked.connect(self._process_clicked)
        button_layout.addWidget(self.process_button)

        self.abort_button = QtWidgets.QPushButton(_t("guiMain", "Abort Changes"), self)
        self.abort_button.setToolTip(
            "<p>{}".format(_t("guiMain", "Make no changes and exit"))
        )
        self.abort_button.clicked.connect(self._abort_clicked)
        self.abort_button.setDisabled(True)
        button_layout.addWidget(self.abort_button)

        self.quit_button = QtWidgets.QPushButton(_t("guiMain", "Quit"), self)
        self.quit_button.setToolTip(
            "<p>{}".format(_t("guiMain", "Quit with no changes"))
        )
        self.quit_button.clicked.connect(self._quit_clicked)
        button_layout.addWidget(self.quit_button)

        if self.misc_prefs["windowGeometry"] is not None:
            try:
                self.restoreGeometry(
                    QtCore.QByteArray.fromHex(
                        self.misc_prefs["windowGeometry"].encode("ascii")
                    )
                )
            except Exception:
                pass
        self.show()

    def update_gui(self):
        # 先清除所有表格记录
        self.table.setRowCount(0)
        self.load_config()

    def validate(self):
        criteria = {}
        criteria["rules"] = []
        criteria["tags"] = self.combobox_values["tags"]
        criteria["style"] = copy.deepcopy(self.title_rules["style"])
        rules = self.title_rules["rules"]
        for row, rule in enumerate(rules):
            if "parent_attrs" in rule and "class" in rule["parent_attrs"]:
                rule["parent_attrs"]["class"] = self.table.item(row, 2).text()
            else:
                rule["class"] = self.table.item(row, 2).text()
            if "child_attrs" in rule and "class" in rule["child_attrs"]:
                rule["child_attrs"]["class"] = self.table.item(row, 4).text()
            else:
                rule["child_class"] = self.table.item(row, 4).text()
            if self.check_text:
                rule["parent_attrs"] = {"class": self.table.item(row, 2).text()}
                rule["child_attrs"] = {"class": self.table.item(row, 4).text()}
            # for row in range(self.table.rowCount()):
            rule["level"] = int(self.table.item(row, 0).text())
            rule["element"] = self.table.item(row, 1).text()
            rule["child_element"] = self.table.item(row, 3).text()
            rule["text_pattern"] = self.table.item(row, 5).text()
            rule["case_insensitive"] = self.table.cellWidget(row, 6).isChecked()
            rule["zone_type"] = self.table.cellWidget(row, 7).currentText()
            rule["display_template"] = (
                self.table.item(row, 8).text() if self.table.item(row, 8) else ""
            )

            if (
                not (
                    rule.get("element", "")
                    and rule.get("element", "").strip()
                    and rule.get("level", "")
                )
                or rule.get("element") not in self.combobox_values["tags"]
                or (
                    rule.get("child_element")
                    and rule.get("child_element") not in self.combobox_values["tags"]
                )
            ):
                title = _t("guiMain", "Error")
                msg = "<p>row {1}:  {0}".format(
                    _t(
                        "guiMain",
                        "Must enter a value(in prebuild tags) for the element/level selected",
                    ),
                    row,
                )
                return (
                    QtWidgets.QMessageBox.warning(
                        self, title, msg, QtWidgets.QMessageBox.Ok
                    ),
                    {},
                )
            # pattern = rule.get("text_pattern", ".*")
            # flags = re.IGNORECASE if rule.get("case_insensitive", False) else 0
            # rule["compiled_pattern"] = re.compile(pattern, flags)
            nrule = copy.deepcopy(rule)
            criteria["rules"].append(nrule)

        return (None, criteria)

    def _process_clicked(self):
        error, criteria = self.validate()
        if error is not None:
            return
        global PROCESSED

        # Disable the 'Process' button, disable the context customization menu
        self.process_button.setDisabled(True)
        PROCESSED = True

        totals = 0
        self.text_panel.clear()
        self.text_panel.insertHtml(
            "<h4>{}...</h4><br>".format(_t("guiMain", "Starting"))
        )

        if True:
            # Hand off the "criteria" parameters dictionary to the parsing engine
            parser = MarkupParser(self.bk, criteria)

            # Retrieve the new markup and the number of occurrences changed
            try:
                t, occurrences = parser.generate_toc()
                if t is not None:
                    print(f"Parse Error: {t}")
            except Exception:
                self.text_panel.insertHtml(
                    "<p>{}! {}.</p>\n".format(
                        _t("guiMain", "Error parsing"),
                        _t("guiMain", "File skipped"),
                    )
                )

            # Report whether or not changes were made (and how many)
            totals += occurrences
            if occurrences:
                # write changed markup back to file
                self.text_panel.insertHtml(
                    "<p>{} :&#160;&#160;&#160;{}</p>".format(
                        _t("guiMain", "Occurrences found/changed in"),
                        int(occurrences),
                    )
                )
            else:
                self.text_panel.insertHtml(
                    "<p>{}</p>\n".format(
                        _t("guiMain", "Criteria not found in"),
                    )
                )
            self.text_panel.insertPlainText("\n")

        # report totals
        if totals:
            self.quit_button.setText(_t("guiMain", "Commit and Exit"))
            self.quit_button.setToolTip(
                "<p>{}".format(_t("guiMain", "Commit all changes and exit"))
            )
            self.abort_button.setDisabled(False)
            self.text_panel.insertHtml(
                "<br><h4>{}:&#160;&#160;&#160;{}</h4>".format(
                    _t("guiMain", "Total occurrences found/changed"), int(totals)
                )
            )
        else:
            self.text_panel.insertHtml(
                "<br><h4>{}</h4>".format(_t("guiMain", "No changes made to book"))
            )
        self.text_panel.insertHtml("<br><h4>{}</h4>".format(_t("guiMain", "Finished")))

    def add_rule(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QtWidgets.QTableWidgetItem("1"))
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem("div"))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(".*"))
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(False)
        self.table.setCellWidget(row, 6, checkbox)
        combo = QtWidgets.QComboBox()
        combo.addItems(ZONE_TYPES)
        combo.setCurrentText("chapter")
        self.table.setCellWidget(row, 7, combo)
        self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(""))  # Display Template
        self.title_rules["rules"].append(
            {
                "level": 1,
                "element": "div",
                "parent_attrs": {
                    "class": "",
                },
                "child_element": "",  # ← 无子元素
                "child_attrs": {"class": ""},
                "text_pattern": "",
                "case_insensitive": True,
                "zone_type": "chapter",
                "display_template": "",
                "description": "",
            }
        )

    def delete_rule(self):
        selected_rows = [
            index.row() for index in self.table.selectionModel().selectedRows()
        ]
        selected_rows.sort(reverse=True)
        for row in selected_rows:
            self.table.removeRow(row)
            del self.title_rules["rules"][row]
        if not selected_rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要删除的规则")

    def load_config(self):
        try:
            # GUI 只显示兼容字段（class / child_class）
            self.populate_table(self.title_rules["rules"])
            print("✅ 已加载配置")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"加载配置失败: {e}")

    def populate_table(self, rules):
        self.table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            # print(f"{row}:{str(rule)}")
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(rule["level"])))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(rule["element"]))
            # 优先从 parent_attrs.class 提取，否则用旧 class 字段
            cls = ""
            if "parent_attrs" in rule and "class" in rule["parent_attrs"]:
                cls = rule["parent_attrs"]["class"]
            elif "parent_attrs" not in rule:
                cls = rule.get("class", "")
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(cls))

            child_elem = rule.get("child_element", "")
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(child_elem))

            child_cls = ""
            if "child_attrs" in rule and "class" in rule["child_attrs"]:
                child_cls = rule["child_attrs"]["class"]
            elif "child_attrs" not in rule:
                child_cls = rule.get("child_class", "")
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(child_cls))

            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(rule["text_pattern"]))
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(rule.get("case_insensitive", False))
            self.table.setCellWidget(row, 6, checkbox)
            combo = QtWidgets.QComboBox()
            combo.addItems(ZONE_TYPES)
            combo.setCurrentText(rule.get("zone_type", "chapter"))
            self.table.setCellWidget(row, 7, combo)
            tpl = rule.get("display_template", "")
            self.table.setItem(row, 8, QtWidgets.QTableWidgetItem(tpl))

    def _save_config_clicked(self):
        error, criteria = self.validate()
        if error is not None:
            return
        two_up = Path(self.bk._w.plugin_dir).resolve().parents[0]
        headless_prefs = two_up.joinpath(
            "plugins_prefs", self.bk._w.plugin_name, "headless.json"
        )
        try:
            with open(headless_prefs, "w", encoding="utf-8") as f:
                json.dump(criteria, f, indent=2, ensure_ascii=False)
            print(f"✅ 配置已保存: {headless_prefs}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "错误", f"保存配置失败: {e}")

    def _quit_clicked(self):
        self.misc_prefs["windowGeometry"] = (
            self.saveGeometry().toHex().data().decode("ascii")
        )
        # if PROCESSED:
        #     self.gui_prefs["action"] = self.action_combo.currentIndex()
        #     self.gui_prefs["tag"] = self.tag_combo.currentIndex()
        #     self.gui_prefs["attrs"] = self.attr_combo.currentIndex()
        self._ok_to_close = True
        self.close()

    def _abort_clicked(self):
        global BAIL_OUT
        BAIL_OUT = True
        self._ok_to_close = True
        self.close()

    def getAbort(self):
        return BAIL_OUT

    def showConfig(self):
        """Launch Customization Dialog"""
        dlg = ConfigDialog(self, self.title_rules, self.combobox_values)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.update_gui()

    def check_for_update(self):
        """Use updatecheck.py to check for newer versions of the plugin"""
        last_time_checked = self.update_prefs["last_time_checked"]
        last_online_version = self.update_prefs["last_online_version"]
        chk = UpdateChecker(last_time_checked, last_online_version, self.bk._w)
        update_available, online_version, time = chk.update_info()
        # update preferences with latest date/time/version
        self.update_prefs["last_time_checked"] = time
        if online_version is not None:
            self.update_prefs["last_online_version"] = online_version
        if update_available:
            return (True, online_version)
        return (False, online_version)

    def closeEvent(self, event):
        if self._ok_to_close:
            event.accept()  # let the window close
        else:
            self._abort_clicked()


def main():
    return -1


if __name__ == "__main__":
    sys.exit(main())
