#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

from collections import OrderedDict
import regex as re
from xml.etree import ElementTree as ET
from sigil_bs4 import BeautifulSoup, Tag, NavigableString

# from bs4 import BeautifulSoup, NavigableString, Tag
from xml.sax.saxutils import escape

DEBUG = None


# ========== 上下文状态机 ==========
class TOCContext:
    def __init__(self):
        self.chapter_counter = 0
        self.appendix_counter = 0
        self.frontmatter_counter = 0
        self.backmatter_counter = 0
        self.part_counter = 0
        self.section_counters = {}

    def get_section_counter(self, base_id):
        if base_id not in self.section_counters:
            self.section_counters[base_id] = {"sec2": 0, "sec3": 0, "sec4": 0}
        return self.section_counters[base_id]


def int_to_roman(num):
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman = ""
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman += syb[i]
            num -= val[i]
        i += 1
    return roman


def safe_id_from_text(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "toc-item"


def extract_clean_text_and_number(raw_text, compiled_pattern):
    """
    使用用户提供的 compiled_pattern（必须含捕获组）解析标题。
    - group(1) → {num}
    - group(2)（可选）→ {text}；若无或为空，则用 raw_text
    """
    match = compiled_pattern.match(raw_text)
    if not match:
        return "", raw_text.strip()
    groups = match.groups()
    num_part = groups[0].strip() if len(groups) >= 1 else ""
    clean_text = (
        groups[1].strip() if len(groups) >= 2 and groups[1] else raw_text.strip()
    )
    return num_part, clean_text


def attrs_match(elem_attrs, required_attrs):
    """
    检查元素的实际属性是否满足 required_attrs 要求
    required_attrs: dict, e.g., {"class": "calibre5", "id": "ch1"}
    elem_attrs: dict from elem.attrs (BeautifulSoup)
    """
    if not required_attrs:
        return True
    for key, expected_value in required_attrs.items():
        actual_value = elem_attrs.get(key, "")
        # 支持 class 是列表的情况（BeautifulSoup 特性）
        if key == "class" and isinstance(actual_value, list):
            actual_value = " ".join(actual_value)
        # 简单字符串包含或精确匹配？这里采用：若 expected_value 是正则以 ^ 开头，则 regex；否则 substring 匹配
        if (
            expected_value.startswith("^")
            or expected_value.endswith("$")
            or ".*" in expected_value
        ):
            try:
                if not re.search(expected_value, str(actual_value)):
                    return False
            except re.error:
                return False
        else:
            # 普通情况：expected_value 必须是 actual_value 的子串（适用于 class="a b c" 包含 "b"）
            if expected_value not in str(actual_value):
                return False
    return True


def create_classify_heading_function(rules):
    def classify_heading(elem):
        for rule in rules:
            if elem.name != rule["element"]:
                continue

            parent_attrs = rule.get("parent_attrs")
            if parent_attrs is None:
                legacy_class = rule.get("class", "").strip()
                parent_attrs = {"class": legacy_class} if legacy_class else {}
            if not attrs_match(elem.attrs, parent_attrs):
                continue

            child_element = rule.get("child_element", "").strip()
            use_child = bool(child_element)

            if use_child:
                children = [
                    c
                    for c in elem.children
                    if not (isinstance(c, NavigableString) and c.strip() == "")
                ]
                if len(children) != 1:
                    continue
                child = children[0]
                if child.name != child_element:
                    continue

                child_attrs = rule.get("child_attrs")
                if child_attrs is None:
                    legacy_child_class = rule.get("child_class", "").strip()
                    child_attrs = (
                        {"class": legacy_child_class} if legacy_child_class else {}
                    )
                if not attrs_match(child.attrs, child_attrs):
                    continue

                text = child.get_text(strip=True)
            else:
                text = elem.get_text(strip=True)

            if rule["compiled_pattern"].match(text):
                zone_type = rule.get("zone_type", "chapter")
                numbering = rule.get("numbering", None)
                display_template = rule.get("display_template", "")
                return (
                    rule["level"],
                    text,
                    zone_type,
                    numbering,
                    display_template,
                    rule["compiled_pattern"],
                )

        return None, None, None, None, None, None

    return classify_heading


def attrMatch(attr_str, method, srch_str):
    if method == "normal":
        return attr_str == srch_str
    elif method == "regex":
        if re.match(r"""%s""" % srch_str, attr_str, re.U) is not None:
            return True
        else:
            return False


def attrs_equal(a, b):
    """Compare two attribute dictionaries for exact equality."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if set(a.keys()) != set(b.keys()):
        return False
    return all(a[k] == b[k] for k in a)


def get_title_and_uid(opf):
    # 解析整个 OPF
    # opf_root = ET.fromstring(opf)
    opf_root = opf

    # OPF 默认命名空间（注意！package 有默认 ns）
    OPF_NS = "http://www.idpf.org/2007/opf"
    DC_NS = "http://purl.org/dc/elements/1.1/"

    # 因为 <package> 使用了默认命名空间，所有子元素都属于它
    # 所以 metadata 路径是：{OPF_NS}metadata
    metadata = opf_root.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        return "Untitled", "unknown"

    # 查找 dc:title
    title_elem = metadata.find(f"{{{DC_NS}}}title")
    title = (
        title_elem.text.strip()
        if title_elem is not None and title_elem.text
        else "Untitled"
    )

    # 查找 unique-identifier
    uid_id = opf_root.get("unique-identifier")  # 来自 <package unique-identifier="...">
    if uid_id:
        id_elem = metadata.find(f'{{{DC_NS}}}identifier[@id="{uid_id}"]')
    else:
        # fallback: 第一个 identifier
        id_elem = metadata.find(f"{{{DC_NS}}}identifier")

    uid = id_elem.text.strip() if id_elem is not None and id_elem.text else "unknown"

    return title, uid


class MarkupParser(object):
    """The criteria parameter dictionary specs
    criteria['html']              Param 1 - the contents of the (x)html file: unicode text.
    criteria['action']            Param 2 - action to take: unicode text ('modify' or 'delete')
    criteria['tag']               Param 3 - tag to alter/delete: unicode text
    criteria['attrib']            Param 4 - attribute to use in match: unicode text or None
    criteria['srch_str']          Param 5 - value of the attribute to use in match: unicode text (literal or regexp) or None
    criteria['srch_method']       Param 6 - is the value given literal or a regexp: boolean
    """

    def __init__(self, bk, criteria):
        self.bk = bk
        self.rules = criteria["rules"]
        self.tags = criteria["tags"]
        self.style = criteria["style"]
        self.occurrences = 0

    def generate_toc(self):
        try:
            for rule in self.rules:
                pattern = rule.get("text_pattern", ".*")
                flags = re.IGNORECASE if rule.get("case_insensitive", False) else 0
                rule["compiled_pattern"] = re.compile(pattern, flags)

            classify_heading = create_classify_heading_function(self.rules)
            print("🚀 开始执行 TOC 生成...")

            spine_files = [itm for itm, ln in self.bk.getspine() if itm is not None]
            if not spine_files:
                print("❌ Spine 为空，无法继续")
                raise Exception("Spine 为空")
            print(f"✅ 按 spine 顺序处理 {len(spine_files)} 个文件")

            # === 收集标题 ===
            root = ET.fromstring(self.bk.get_opf())
            title, uid = get_title_and_uid(root)
            all_raw_items = []
            file_soups = {}
            for fname in spine_files:
                content = self.bk.readfile(fname)
                soup = BeautifulSoup(content, "html.parser")
                file_soups[fname] = soup
                # 扩展搜索标签（根据需要可增加）
                for elem in soup.find_all(self.tags):
                    result = classify_heading(elem)
                    (
                        level,
                        text,
                        zone_type,
                        numbering,
                        display_template,
                        compiled_pat,
                    ) = result
                    if level is None:
                        continue
                    all_raw_items.append(
                        {
                            "level": level,
                            "elem": elem,
                            "file_name": self.bk.id_to_href(fname),
                            "raw_text": text,
                            "zone_type": zone_type,
                            "numbering": numbering,
                            "display_template": display_template,
                            "compiled_pattern": compiled_pat,
                        }
                    )

            if not all_raw_items:
                print("❌ 未找到任何符合配置规则的标题")
                return None, self.occurrences

            context = TOCContext()
            toc_items = [
                {
                    "level": 0,
                    "text": "Table of Contents",
                    "file": "toc.html",
                    "anchor": "toc",
                }
            ]
            for idx, item in enumerate(all_raw_items):
                if item["level"] == 1:
                    zt = item["zone_type"]
                    raw = item["raw_text"]
                    template = item["display_template"]
                    compiled_pat = item["compiled_pattern"]

                    # ✅ 关键：使用 text_pattern 的捕获组解析
                    raw_num, clean_text = extract_clean_text_and_number(
                        raw, compiled_pat
                    )

                    if zt == "chapter":
                        context.chapter_counter += 1
                        auto_num = str(context.chapter_counter)
                        anchor_id = auto_num
                        if template:
                            display_text = template.format(
                                num=auto_num, text=clean_text, raw=raw
                            )
                        else:
                            display_text = f"Chapter {auto_num}"

                    elif zt == "part":
                        context.part_counter += 1
                        roman = int_to_roman(context.part_counter)
                        anchor_id = f"part-{roman.lower()}"
                        if template:
                            display_text = template.format(
                                num=roman, text=clean_text, raw=raw
                            )
                        else:
                            display_text = raw

                    elif zt == "appendix":
                        context.appendix_counter += 1
                        letter = chr(ord("A") + context.appendix_counter - 1)
                        anchor_id = f"app-{letter.lower()}"
                        if template:
                            display_text = template.format(
                                num=letter, text=clean_text, raw=raw
                            )
                        else:
                            display_text = f"Appendix {letter}"

                    elif zt in ("frontmatter", "backmatter"):
                        anchor_id = f"{zt[:4]}-{safe_id_from_text(raw)}"
                        if template:
                            display_text = template.format(num="", text=raw, raw=raw)
                        else:
                            display_text = raw

                    item["display_text"] = display_text
                    item["anchor_id"] = anchor_id
                    item["elem"]["id"] = anchor_id
                    toc_items.append(
                        {
                            "level": 1,
                            "text": display_text,
                            "file": item["file_name"],
                            "anchor": anchor_id,
                        }
                    )
                    self.occurrences += 1

                else:  # level >= 2
                    parent = None
                    for j in range(idx - 1, -1, -1):
                        if all_raw_items[j]["level"] == 1:
                            parent = all_raw_items[j]
                            break
                    if not parent:
                        continue

                    base_id = parent["anchor_id"]
                    counter = context.get_section_counter(base_id)
                    lvl = item["level"]

                    if lvl == 2:
                        counter["sec2"] += 1
                        seq = counter["sec2"]
                        anchor = f"{base_id}-{seq}"
                    elif lvl == 3:
                        counter["sec3"] += 1
                        seq = counter["sec3"]
                        anchor = f"{base_id}-s{seq}"
                    else:
                        counter["sec4"] += 1
                        seq = counter["sec4"]
                        anchor = f"{base_id}-ss{seq}"

                    item["anchor_id"] = anchor
                    item["elem"]["id"] = anchor
                    item["display_text"] = item["raw_text"]
                    toc_items.append(
                        {
                            "level": lvl,
                            "text": item["raw_text"],
                            "file": item["file_name"],
                            "anchor": anchor,
                        }
                    )
                    self.occurrences += 1

            # ========== 保存修改后的 HTML ==========
            for fname, soup in file_soups.items():
                self.bk.writefile(fname, str(soup))

            # ========== 构建 TOC 树结构 ==========
            def build_tree(items):
                root = {"children": []}
                stack = [root]
                for item in items:
                    if item["level"] == 0:
                        continue
                    node = {
                        "level": item["level"],
                        "text": item["text"],
                        "src": f"{item['file']}#{item['anchor']}",
                        "children": [],
                    }
                    while len(stack) > item["level"]:
                        stack.pop()
                    stack[-1]["children"].append(node)
                    stack.append(node)
                return root["children"]

            tree = build_tree(toc_items)

            # === 生成 NCX ===
            navpoints = []
            stack = []
            for idx, item in enumerate(toc_items):
                play_order = idx + 1
                np = {
                    "id": f"navPoint-{play_order}",
                    "playOrder": play_order,
                    "text": item["text"],
                    "src": f"{item['file']}#{item['anchor']}",
                    "children": [],
                }
                level = item["level"]
                if level > 0:
                    while stack and stack[-1]["level"] >= level:
                        stack.pop()
                    if level == 1:
                        np["level"] = 1
                        navpoints.append(np)
                        stack = [np]
                    else:
                        if stack:
                            stack[-1]["children"].append(np)
                            np["level"] = level
                            stack.append(np)
                else:
                    # level = 0 (toc.html)
                    navpoints.insert(0, np)

            # ========== 递归生成 NCX navPoint ==========
            def add_nav_point(parent_el, node, play_order_counter, level=1):
                """
                递归添加 navPoint 节点
                :param parent_el: 父级 XML 元素（如 navMap 或上级 navPoint）
                :param node: 当前节点（含 text, src, children）
                :param play_order_counter: 可变对象，用于维护全局 playOrder
                :return: None
                """
                play_order_counter[0] += 1
                nav_point = ET.SubElement(
                    parent_el,
                    f"{{{NCX_NS}}}navPoint",
                    id=f"navPoint-{play_order_counter[0]}",
                    playOrder=str(play_order_counter[0]),
                )
                nav_label = ET.SubElement(nav_point, f"{{{NCX_NS}}}navLabel")
                ET.SubElement(nav_label, f"{{{NCX_NS}}}text").text = escape(
                    node["text"]
                )
                ET.SubElement(nav_point, f"{{{NCX_NS}}}content", src=node["src"])

                # 递归子节点
                for child in node.get("children", []):
                    add_nav_point(nav_point, child, play_order_counter, level + 1)

            def calc_max_depth(nodes):
                return max(
                    (1 + calc_max_depth(child["children"]) for child in nodes),
                    default=0,
                )

            # ========== 生成 NCX ==========
            NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
            ncx_root = ET.Element(f"{{{NCX_NS}}}ncx", version="2005-1")
            head = ET.SubElement(ncx_root, f"{{{NCX_NS}}}head")
            ET.SubElement(head, f"{{{NCX_NS}}}meta", name="dtb:uid", content=uid)

            # 计算最大深度（用于 dtb:depth）
            def max_depth(nodes, depth=0):
                if not nodes:
                    return depth
                return max(max_depth(child["children"], depth + 1) for child in nodes)

            max_d = max_depth(tree)
            ET.SubElement(
                head,
                f"{{{NCX_NS}}}meta",
                name="dtb:depth",
                content=str(max_d if max_d > 0 else 1),
            )
            doc_title = ET.SubElement(ncx_root, f"{{{NCX_NS}}}docTitle")
            ET.SubElement(doc_title, f"{{{NCX_NS}}}text").text = escape(title)
            nav_map = ET.SubElement(ncx_root, f"{{{NCX_NS}}}navMap")

            # 从 root 开始递归构建（注意：tree 是顶层列表，不含虚拟根）
            play_counter = [0]  # 使用 list 作为可变整数
            for node in navpoints:
                add_nav_point(nav_map, node, play_counter)

            ncx_id = self.bk.bookpath_to_id("toc.ncx")
            if ncx_id is None:
                # 2. 改写manifest
                self.bk.addfile(
                    "ncx",
                    "toc.ncx",
                    ET.tostring(ncx_root, encoding="unicode"),
                    "application/xml",
                )
                # 3. 添加spine信息
                # bk.setspine()
                # book.spine_insert_before(1, 'newToc', None)
            else:
                # 3. 添加spine信息
                # book.writefile(ncx_id, ncx_content)  # 路径相对于 EPUB 根目录
                self.bk.writefile(ncx_id, ET.tostring(ncx_root, encoding="unicode"))
            # book.write_file("toc.ncx", ncx_content)
            print("✅ 已生成 toc.ncx")

            # === 生成 HTML 目录 ===
            style_cls = {}
            for lev, cl in self.style.items():
                cls_ar = []
                for k, v in cl.items():
                    if v:
                        cls_ar.append(f'{k}="{v}"')
                style_cls[f"{lev}"] = " ".join(cls_ar)

            def generate_html_toc(tree, level=1):
                if not tree:
                    return []
                lines = ["<ol>"]
                for node in tree:
                    # 跳过 toc.xhtml 节点，因为它不是内容章节
                    if node["src"] == "toc.html":
                        continue
                    # cls = (
                    #     "calibre13"
                    #     if level == 1
                    #     else ("calibre12" if level == 2 else "calibre14")
                    # )
                    cls = style_cls.get(f"{level}", "")
                    # print(f"style:{self.style}")
                    # print(f"cls_ar: {cls_ar}")
                    link = f'<a href="{node["src"]}" {cls}>{escape(node["text"])}</a>'
                    lines.append(f"  <li>{link}")
                    if node["children"]:
                        lines.extend(
                            "  " + line
                            for line in generate_html_toc(node["children"], level + 1)
                        )
                    lines.append("  </li>")
                lines.append("</ol>")
                return lines

            html_toc_lines = [
                '<?xml version="1.0" encoding="utf-8"?>',
                "<!DOCTYPE html>",
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="en">',
                "<head>",
                '  <meta charset="utf-8"/>',
                f"  <title>{escape(title)} - Table of Contents</title>",
                "  <style>",
                "    body { font-family: serif; margin: 2em; }",
                "    ol { list-style-type: none; padding-left: 0; }",
                "    li { margin: 0.5em 0; }",
                "    a:hover { text-decoration: underline; }",
                "  </style>",
                '  <link href="stylesheet.css" rel="stylesheet" type="text/css"/>',
                '  <link href="page_styles.css" rel="stylesheet" type="text/css"/>',
                "</head>",
                "<body>",
                '<h1 id="toc" class="calibre13">Table of Contents</h1>',
                *generate_html_toc(tree),
                "</body>",
                "</html>",
            ]

            toc_html_content = "\n".join(html_toc_lines)
            # print("✅ 已生成 toc.html")

            # === 更新 OPF：添加 toc.html 到 manifest 和 spine 开头 ===
            namespaces = {"opf": "http://www.idpf.org/2007/opf"}
            manifest = root.find(".//opf:manifest", namespaces)
            spine = root.find(".//opf:spine", namespaces)

            if manifest is None or spine is None:
                print("❌ OPF 缺少 manifest 或 spine")
                return

            # 检查是否已存在 toc.html
            toc_item = manifest.find('.//opf:item[@href="toc.html"]', namespaces)
            toc_id = "toc"
            if toc_item is None:
                item_elem = ET.Element("item")
                item_elem.set("id", toc_id)
                item_elem.set("href", "toc.html")
                item_elem.set("media-type", "application/xhtml+xml")
                manifest.append(item_elem)
                self.bk.addfile(
                    toc_id, "toc.html", toc_html_content, "application/xhtml+xml"
                )
                print("✅ 已添加 toc.html 到 manifest")
                print("✅ 已生成 toc.html")
            else:
                toc_id = toc_item.get("id") or toc_id
                self.bk.writefile(toc_id, toc_html_content)
                print("✅ 已更新 toc.html")

            # 检查 spine 是否已有
            existing_ref = spine.find(f'.//opf:itemref[@idref="{toc_id}"]', namespaces)
            if existing_ref is None:
                itemref = ET.Element("itemref")
                itemref.set("idref", toc_id)
                spine.insert(0, itemref)
                self.bk.spine_insert_before(1, toc_id, None)
                print("✅ 已将 toc.html 插入 spine 开头")
            """
            """

            def getRules(level):
                rulesText = []
                for rl in self.rules:
                    if rl["level"] == level:
                        rpat = "|".join(
                            list(f"{k}.{v}" for k, v in rl["parent_attrs"].items() if v)
                        )
                        rcat = "|".join(
                            list(f"{k}.{v}" for k, v in rl["child_attrs"].items() if v)
                        )
                        rulesText.append(
                            f'{rl["element"]}: {rpat} > {rl["child_element"]}: {rcat} + \'{rl["text_pattern"]}\''
                        )
                return "\n\t".join(rulesText)

            # 更新 OPF
            print("✅ OPF 已更新")

            print("\n🎉 Calibre 风格 TOC 生成完成！")
            # print("   - 一级标题：div.calibre5 > span.calibre6 + 'Chapter \\d+:'")
            print(f"   - 一级标题：{getRules(1)}")
            print(f"   - 二级标题：{getRules(2)}")
            print(f"   - 三级标题：{getRules(3)}")
            print("   - 目录文件：toc.html（含 calibre13/12/14 class）")
            print("   - 导航文件：toc.ncx")
            print("   - 已自动集成到 EPUB")

            return None, self.occurrences

        except Exception as e:
            print(f"❌ Error: {e}")
            return e, self.occurrences
