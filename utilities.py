#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function


import re
import os
import sys
import socket
import copy
from datetime import datetime, timedelta
from lxml import objectify


url = "https://raw.githubusercontent.com/lsq/epubtocgenerator-sigil-plugin/master/checkversion.xml"
delta = 12


rules_default = {
    "rules": [
        {
            "level": 1,
            "element": "h1",
            "parent_attrs": {
                "class": "",
                "id": "",
            },
            "child_element": "",  # ← 无子元素
            "child_attrs": {
                "class": "",
                "id": "",
            },
            "text_pattern": "^(Preface|Foreword|Acknowledgements)()",
            "case_insensitive": True,
            "zone_type": "frontmatter",
            "display_template": "",
            "description": "前言/后记/序部分",
        },
        {
            "level": 1,
            "element": "h1",
            "parent_attrs": {
                "class": "",
                "id": "",
            },
            "child_element": "",  # ← 无子元素
            "child_attrs": {
                "class": "",
                "id": "",
            },
            "text_pattern": "^Part\\s+([IVX]+):?\\s*(.*)",
            "case_insensitive": True,
            "zone_type": "part",
            "display_template": "第{num}部",
            "description": "部",
        },
        {
            "level": 1,
            "element": "h1",
            "parent_attrs": {
                "class": "",
                "id": "",
            },
            "child_element": "",  # ← 无子元素
            "child_attrs": {
                "class": "",
                "id": "",
            },
            "text_pattern": "^Chapter\\s+(\\d+)[\\s:\\-–]*(.*)",
            "case_insensitive": True,
            "zone_type": "chapter",
            "display_template": "Lesson {num}: {text}",
            "description": "章节",
        },
        {
            "level": 1,
            "element": "h1",
            "parent_attrs": {
                "class": "",
                "id": "",
            },
            "child_element": "",  # ← 无子元素
            "child_attrs": {
                "class": "",
                "id": "",
            },
            "text_pattern": "^Appendix\\s+([A-Z]):?\\s*(.*)",
            "case_insensitive": True,
            "zone_type": "appendix",
            "display_template": "附录 {num}：{text}",
            "description": "附录",
        },
        {
            "level": 1,
            "element": "h1",
            "parent_attrs": {
                "class": "",
                "id": "",
            },
            "child_element": "",  # ← 无子元素
            "child_attrs": {
                "class": "",
                "id": "",
            },
            "text_pattern": "^(Glossary|Index|Bibliography)$",
            "case_insensitive": True,
            "zone_type": "backmatter",
            "display_template": "",
            "description": "索引/引用",
        },
        {
            "level": 1,
            "element": "div",
            "parent_attrs": {
                "class": "calibre5",
            },
            "child_element": "span",
            "child_attrs": {
                "class": "calibre6",
            },
            "text_pattern": "^Chapter\\s+\\d+:",
            "case_insensitive": True,
            "description": "Calibre 一级标题：Chapter X:（带 span 子元素）",
        },
        {
            "level": 2,
            "element": "div",
            "parent_attrs": {
                "class": "calibre10",
            },
            "child_element": "span",
            "child_attrs": {
                "class": "calibre9",
            },
            "text_pattern": ".*",
            "case_insensitive": False,
            "description": "Calibre 二级标题",
        },
        {
            "level": 3,
            "element": "div",
            "parent_attrs": {
                "class": "calibre10",
            },
            "child_element": "span",
            "child_attrs": {
                "class": "calibre16",
            },
            "text_pattern": ".*",
            "case_insensitive": False,
            "description": "Calibre 三级标题",
        },
    ],
    "style": {
        "1": {"class": "calibre13"},
        "2": {"class": "calibre12"},
        "3": {"class": "calibre14"},
    },
}

font_tweaks = {
    "font_family": "Helvetica",
    "font_size": "10",
}

miscellaneous_settings = {
    "windowGeometry": None,
    "language_override": None,
    "icon_color": "#27AAE1",
    "qtwrapper_override": None,
    "automate_runs_headless": False,
}

update_settings = {
    "last_time_checked": str(datetime.now() - timedelta(hours=13)),
    "last_online_version": "0.0.0",
}

ZONE_TYPES = ["chapter", "part", "appendix", "frontmatter", "backmatter"]
# To add a new tag, add it to taglist and add a list of tags it can be changed to to combobox_defaults
taglist = [
    "span",
    "div",
    "h1",
    "h2",
    "h3",
    "p",
    "i",
    "em",
    "b",
    "strong",
    "u",
    "small",
    "a",
    "blockquote",
    "header",
    "section",
    "footer",
    "nav",
    "article",
]

combobox_defaults = {
    "tags": [
        "span",
        "div",
        "h1",
        "h2",
        "h3",
        "p",
        "i",
        "em",
        "b",
        "strong",
        "u",
        "small",
        "a",
        "blockquote",
        "header",
        "section",
        "footer",
        "nav",
        "article",
    ],
    "attrs": ["class", "id", "style", "href"],
}


def tuple_version(v):
    # No aplha characters in version strings allowed here!
    return tuple(map(int, (v.split("."))))


def remove_dupes(values):
    """Could just use set(), but some combobox values are preloaded
    from prefs using an index. So order matters"""
    output = []
    seen = set()
    for value in values:
        # If value has not been encountered yet,
        # ... add it to both list and set.
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def check_for_custom_icon(prefs_dir):
    def icon_check(iconpath):
        if os.path.exists(iconpath) and os.path.isfile(iconpath):
            return True
        else:
            return False

    if icon_check(os.path.join(prefs_dir, "plugin.svg")):
        return True
    elif icon_check(os.path.join(prefs_dir, "plugin.png")):
        return True
    else:
        return False


def change_icon_color(svg, original_color, new_color):
    with open(svg, "rb") as f:
        data = f.read()
    data = data.decode("utf-8")
    data = data.replace(original_color, new_color)
    data = data.encode("utf-8")
    with open(svg, "wb") as fo:
        fo.write(data)


def get_icon_color(svg):
    import regex as re

    regexp = r'''fill="(#([0-9a-fA-F])+)"'''
    data = ""
    with open(svg, "rb") as f:
        data = f.read()
    data = data.decode("utf-8")
    m = re.search(regexp, data)
    if m is not None:
        return m.group(1)
    else:
        return None


def valid_attributes(tattr):
    """This is not going to catch every, single way a user can screw this up, but
    it's going to ensure that they can't enter an attribute string that's going to:
    a) hang the attribute parser
    b) make the xhmtl invalid"""

    # Make a fake xml string and try to parse the attributes of the "stuff" element
    # with lxml's objectify.
    template = """<root><stuff %s>dummy</stuff></root>""" % tattr
    try:
        root = objectify.fromstring(template)
        root.stuff.attrib
    except Exception:
        return False
    return True


# Some keys were renamed along the way. Convert users existing prefs to new ones.
def fix_old_keys(combo_values):
    if "sec_changes" in combo_values:
        combo_values["section_changes"] = combo_values.pop("sec_changes")
    if "block_changes" in combo_values:
        combo_values["blockquote_changes"] = combo_values.pop("block_changes")
    return combo_values


def check_for_new_prefs(prefs_group, default_values):
    """Make sure that adding new tags doesn't mean that the user has
    to delete their preferences json and start all over. Piecemeal defaults
    instead of the wholesale approach."""
    for key, value in default_values.items():
        if key not in prefs_group:
            prefs_group[key] = value


def setupPrefs(prefs):
    if "font_tweaks" not in prefs:
        prefs["font_tweaks"] = font_tweaks
    else:  # otherwise, use the piecemeal method in case new prefs have been added since json creation.
        check_for_new_prefs(prefs["font_tweaks"], font_tweaks)
    if "miscellaneous_settings" not in prefs:
        prefs["miscellaneous_settings"] = miscellaneous_settings
    else:
        check_for_new_prefs(prefs["miscellaneous_settings"], miscellaneous_settings)
    if "update_settings" not in prefs:
        prefs["update_settings"] = update_settings
    else:
        check_for_new_prefs(prefs["update_settings"], update_settings)
    if "combobox_values" not in prefs:
        prefs["combobox_values"] = combobox_defaults
    else:
        check_for_new_prefs(fix_old_keys(prefs["combobox_values"]), combobox_defaults)
    if "title_rules" not in prefs:
        prefs["title_rules"] = copy.deepcopy(rules_default)
    else:
        check_for_new_prefs(fix_old_keys(prefs["title_rules"]), rules_default)
    return prefs


def string_to_date(datestring):
    return datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S.%f")


class UpdateChecker:
    """
    self.delta              : How often to check -- in hours
    self.url                : url to github xml file
    self.lasttimechecked    : 'stringified' datetime object of last check
    self.lastonlineversion  : version string of last online version retrieved/stored
    self.w                  : bk._w from plugin.py
    """

    def __init__(self, lasttimechecked, lastonlineversion, w):
        self.delta = delta
        self.url = url
        self.lasttimechecked = string_to_date(
            lasttimechecked
        )  # back to datetieme object
        self.lastonlineversion = lastonlineversion
        self.w = w

    def is_connected(self):
        try:
            # connect to the host -- tells us if the host is reachable
            # 8.8.8.8 is a Google nameserver
            sock = socket.create_connection(("8.8.8.8", 53), 1)
            sock.close()
            return True
        except Exception:
            pass
        return False

    def get_online_version(self):
        _online_version = None
        _version_pattern = re.compile(r"<current-version>([^<]*)</current-version>")

        try:
            from urllib.request import urlopen
        except ImportError:
            from urllib2 import urlopen

        # get the latest version from the plugin's github page
        if self.is_connected():
            try:
                response = urlopen(self.url, timeout=2)
                the_page = response.read()
                the_page = the_page.decode("utf-8", "ignore")
                m = _version_pattern.search(the_page)
                if m:
                    _online_version = m.group(1).strip()
            except Exception:
                pass

        return _online_version

    def get_current_version(self):
        _version_pattern = re.compile(r"<version>([^<]*)</version>")
        _installed_version = None

        ppath = os.path.join(self.w.plugin_dir, self.w.plugin_name, "plugin.xml")
        with open(ppath, "rb") as f:
            data = f.read()
            data = data.decode("utf-8", "ignore")
            m = _version_pattern.search(data)
            if m:
                _installed_version = m.group(1).strip()
        return _installed_version

    def update_info(self):
        _online_version = None
        _current_version = self.get_current_version()

        # only retrieve online resource if the allotted time has passed since last check
        if datetime.now() - self.lasttimechecked > timedelta(hours=self.delta):
            _online_version = self.get_online_version()
            # if online version is newer, make sure it hasn't been seen already
            if (
                _online_version is not None
                and tuple_version(_online_version) > tuple_version(_current_version)
                and _online_version != self.lastonlineversion
            ):
                return True, _online_version, str(datetime.now())
        return False, _online_version, str(datetime.now())


def main():
    """Used to test outside of Sigil"""

    class w:
        def __init__(self):
            w.plugin_name = "TagMechanic"
            w.plugin_dir = "/home/dmassay/.local/share/sigil-ebook/sigil/plugins"

    tmedt = str(datetime.now() - timedelta(hours=delta + 1))
    version = "0.1.0"
    sim_w = w()
    chk = UpdateChecker(tmedt, version, sim_w)
    print(chk.update_info())
    print(tuple_version("0.80.3"))
    print(tuple_version("0.80.3") > tuple_version("0.80.1"))
    print(tuple_version("0.80.3") > tuple_version("0.80.30"))


if __name__ == "__main__":
    sys.exit(main())
