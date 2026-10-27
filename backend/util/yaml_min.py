"""
极小化的 YAML 子集解析器（无第三方依赖，仅用标准库）。

支持本工程 config.yaml 用到的语法：
  - 注释（整行 `#` 与行内 `#`，忽略引号内的 `#`）
  - 嵌套映射（2 空格缩进）
  - 块序列（`- item`）
  - 行内流映射 `{ a: b, c: d }` 与流序列 `[a, b]`
  - 标量：双/单引号字符串、未引号字符串、int/float/bool/null

说明：这是为「配置加载」而写的受限解析器，足以解析本项目的 config.yaml。
若未来配置用到更复杂 YAML 语法，请安装 PyYAML 并替换本模块。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _strip_comment(line: str) -> str:
    """去除注释，但保留引号内的 #。"""
    out = []
    in_s = False
    in_d = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            in_d = not in_d
        elif c == "#" and not in_s and not in_d:
            # 行内注释：仅当 # 前是空白或行首时才算注释
            if i == 0 or line[i - 1] in (" ", "\t"):
                break
        out.append(c)
        i += 1
    return "".join(out)


def _parse_scalar(tok: str):
    tok = tok.strip()
    if tok == "" or tok.lower() == "null" or tok == "~":
        return None
    if (tok[0] == '"' and tok[-1] == '"') or (tok[0] == "'" and tok[-1] == "'"):
        return tok[1:-1]
    low = tok.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _parse_flow(tok: str):
    """解析流映射 {...} 或流序列 [...]"""
    tok = tok.strip()
    if tok.startswith("{"):
        inner = tok[1: tok.rfind("}")]
        d = {}
        for part in _split_top(inner, ","):
            if not part.strip():
                continue
            k, _, v = part.partition(":")
            d[k.strip()] = _parse_scalar(v)
        return d
    if tok.startswith("["):
        inner = tok[1: tok.rfind("]")]
        return [_parse_scalar(p) for p in _split_top(inner, ",") if p.strip() != ""]
    return _parse_scalar(tok)


def _split_top(s: str, sep: str):
    """按顶层分隔符切分（忽略括号内的分隔符）。"""
    parts = []
    depth = 0
    cur = []
    for c in s:
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return parts


class _Line:
    __slots__ = ("indent", "content")

    def __init__(self, indent, content):
        self.indent = indent
        self.content = content


def _preprocess(text: str):
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(_Line(indent, stripped.strip()))
    return lines


def _parse_block(lines, indent, pos):
    if pos[0] >= len(lines):
        return None
    if lines[pos[0]].content.startswith("- "):
        return _parse_seq(lines, indent, pos)
    return _parse_map(lines, indent, pos)


def _parse_seq(lines, indent, pos):
    items = []
    while pos[0] < len(lines):
        ln = lines[pos[0]]
        if ln.indent != indent or not ln.content.startswith("- "):
            break
        rest = ln.content[2:].strip()
        if rest == "":
            # 嵌套块：- \n   <deeper>
            pos[0] += 1
            if pos[0] < len(lines) and lines[pos[0]].indent > indent:
                items.append(_parse_block(lines, lines[pos[0]].indent, pos))
            else:
                items.append(None)
        elif rest.startswith("{") or rest.startswith("["):
            items.append(_parse_flow(rest))
            pos[0] += 1
        elif ":" in rest and not (rest.startswith('"') or rest.startswith("'")):
            # 以映射开始的序列项：- key: val
            item_indent = indent + 2
            ln.indent = item_indent
            ln.content = rest
            items.append(_parse_map(lines, item_indent, pos))
        else:
            items.append(_parse_scalar(rest))
            pos[0] += 1
    return items


def _parse_map(lines, indent, pos):
    d = {}
    while pos[0] < len(lines):
        ln = lines[pos[0]]
        if ln.indent != indent:
            break
        if ln.content.startswith("- "):
            break
        key, sep, val = ln.content.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "":
            pos[0] += 1
            if pos[0] < len(lines) and lines[pos[0]].indent > indent:
                d[key] = _parse_block(lines, lines[pos[0]].indent, pos)
            else:
                d[key] = None
        elif val.startswith("{") or val.startswith("["):
            d[key] = _parse_flow(val)
            pos[0] += 1
        else:
            d[key] = _parse_scalar(val)
            pos[0] += 1
    return d


def load_yaml(text: str):
    lines = _preprocess(text)
    pos = [0]
    return _parse_block(lines, 0, pos)


def load_yaml_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return load_yaml(f.read())
