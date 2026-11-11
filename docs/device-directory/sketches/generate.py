"""Generate S5 device-directory sketches (static HTML) at 1280 and 1920."""
import hashlib
import html
import unicodedata
import sys
from pathlib import Path

OUT = Path(sys.argv[1])


def device_key(station: str) -> str:
    normalized = unicodedata.normalize("NFKC", station).strip().upper()
    return "dev-" + hashlib.sha256(b"gdds-directory/station/v1\x00" + normalized.encode()).hexdigest()[:16]

OUT.mkdir(parents=True, exist_ok=True)

REGION1 = [
    ("安徽", 2104), ("福建", 1876), ("河南", 2610), ("湖北", 2233),
    ("江苏", 3012), ("江西", 1524), ("山东", 3368), ("浙江", 1699),
]
JS_CHILDREN = [
    ("常熟", 131), ("常州", 168), ("丹阳", 74), ("东台", 62), ("海门", 58), ("淮安", 117),
    ("江阴", 96), ("昆山", 152), ("溧阳", 49), ("连云港", 103), ("南京", 286), ("南通", 159),
    ("如皋", 61), ("宿迁", 88), ("苏州", 214), ("太仓", 77), ("泰州", 121), ("无锡", 197),
    ("徐州", 176), ("盐城", 142), ("扬州", 133), ("宜兴", 83), ("张家港", 108), ("镇江", 157),
]
assert sum(c for _, c in JS_CHILDREN) == 3012, sum(c for _, c in JS_CHILDREN)

PROJECTS = [
    ("白洋湾 110kV 变电站", "SZ-0107", None, False),
    ("滨湖 220kV 变电站", "SZ-0023", None, False),
    ("沧浪 110kV 变电站", "SZ-0215", None, False),
    ("城南 110kV 变电站", "SZ-0142", None, True),
    ("城南 110kV 变电站", "SZ-0388", None, True),
    ("东环 220kV 变电站", "SZ-0031", None, False),
    ("枫桥 110kV 变电站", "SZ-0256", None, False),
    ("观前 110kV 变电站", "SZ-0119", None, False),
    ("虎丘 220kV 变电站", "SZ-0047", None, False),
    ("金鸡湖 220kV 变电站", "SZ-0012", None, False),
    ("娄葑 110kV 变电站", "SZ-0233", None, False),
    ("木渎 110kV 变电站", "SZ-0301", None, False),
    ("南环 35kV 开关站", "SZ-0412", None, False),
    ("盘门 110kV 变电站", "SZ-0127", None, False),
    ("青剑湖 110kV 变电站", "SZ-0278", None, False),
    ("狮山 220kV 变电站", "SZ-0058", None, False),
    ("唐家浜 35kV 开关站", "SZ-0435", None, False),
    ("吴中 220kV 变电站", "SZ-0066", None, False),
    ("胥口 110kV 变电站", "SZ-0319", None, False),
    ("浒墅关 110kV 变电站", "SZ-0244", None, False),
    ("越溪 110kV 变电站", "SZ-0352", None, False),
]

UNPROVISIONED = {"SZ-0412", "SZ-0435"}

# Cross-region results for the pinyin-initial query "cn".
SEARCH = [
    ("长宁 220kV 变电站", "浙江 / 宁波", "NB-0018", None, "长宁", False),
    ("城南 110kV 变电站", "江苏 / 苏州", "SZ-0142", None, "城南", True),
    ("城南 110kV 变电站", "江苏 / 苏州", "SZ-0388", None, "城南", True),
    ("城南 35kV 开关站", "江苏 / 无锡", "WX-0207", None, "城南", False),
    ("城南中心 220kV 变电站", "河南 / 洛阳", "LY-0039", None, "城南", False),
    ("城宁 110kV 变电站", "安徽 / 芜湖", "WH-0093", None, "城宁", False),
    ("川南 110kV 变电站", "湖北 / 宜昌", "YC-0164", None, "川南", False),
    ("春宁 35kV 开关站", "福建 / 三明", "SM-0331", None, "春宁", False),
    ("翠南 110kV 变电站", "山东 / 济南", "JN-0275", None, "翠南", False),
]
SEARCH_COUNTS = {"安徽": 1, "福建": 1, "河南": 1, "湖北": 1, "江苏": 3, "江西": 0, "山东": 1, "浙江": 1}

ICON = {
    "search": '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>',
    "down": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"></path></svg>',
    "right": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"></path></svg>',
    "clock": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>',
    "user": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"></circle><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"></path></svg>',
    "x": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"></path></svg>',
}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#F3F5F7}
.page{display:flex;flex-direction:column;background:#F3F5F7;color:#1B2229;overflow:hidden;
  font-family:'IBM Plex Sans','PingFang SC','Noto Sans SC','Noto Sans CJK SC','Microsoft YaHei',sans-serif;font-size:13px}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px}
.muted{color:#5F6B78}
header.top{height:52px;flex:0 0 52px;display:flex;align-items:center;gap:14px;padding:0 20px;background:#FFFFFF;border-bottom:1px solid #EEF1F4}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:15px}
.brand-mark{width:22px;height:22px;border-radius:5px;background:#1F5FBF;display:grid;place-items:center;color:#fff;font-size:12px;font-weight:600}
.tag{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:4px;background:#F1F3F5;color:#4A5563;font-size:12px;font-weight:500}
.tag--info{background:#E0F2FE;color:#0B5A8A}
.vsep{width:1px;height:18px;background:#DDE2E7}
.spacer{flex:1}
.ghost-btn{display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 10px;border:1px solid #DDE2E7;border-radius:6px;background:#FFFFFF;color:#1B2229;font:inherit}
.searchbar{height:64px;flex:0 0 64px;display:flex;align-items:center;gap:16px;padding:0 20px;background:#FFFFFF;border-bottom:1px solid #DDE2E7}
.search{display:flex;align-items:center;gap:8px;height:38px;padding:0 12px;border:1px solid #C9D0D8;border-radius:8px;background:#FFFFFF;color:#5F6B78}
.search--active{border-color:#1F5FBF;box-shadow:0 0 0 3px rgba(31,95,191,.16);color:#1B2229}
.search input{border:0;outline:0;font:inherit;font-size:14px;flex:1;background:transparent;color:inherit}
.kbd{display:inline-flex;align-items:center;height:20px;padding:0 6px;border:1px solid #DDE2E7;border-radius:4px;background:#F7F9FB;color:#5F6B78;font-size:11px}
.seg{display:inline-flex;padding:3px;gap:2px;border-radius:8px;background:#F1F3F5}
.seg button{height:30px;padding:0 12px;border:0;border-radius:6px;background:transparent;color:#4A5563;font:inherit}
.seg button[aria-checked=true]{background:#FFFFFF;color:#1B2229;font-weight:600;box-shadow:0 1px 2px rgba(27,34,41,.12)}
.recent{display:flex;align-items:center;gap:8px;min-width:0}
.chip{text-decoration:none;display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:14px;background:#F1F3F5;color:#1B2229;white-space:nowrap}
.chip .muted{font-size:12px}
.body{flex:1;display:flex;min-height:0}
nav.tree{flex:0 0 auto;background:#FFFFFF;border-right:1px solid #DDE2E7;display:flex;flex-direction:column;min-height:0}
.tree-head{padding:12px 12px 8px}
.tree-filter{display:flex;align-items:center;gap:6px;height:30px;padding:0 10px;border:1px solid #DDE2E7;border-radius:6px;color:#A3ACB6}
.tree-list{flex:1;overflow:hidden;padding:0 8px 8px}
.node{display:flex;align-items:center;gap:6px;height:28px;padding:0 8px;border-radius:6px;color:#1B2229;white-space:nowrap}
.node .count{margin-left:auto;color:#5F6B78;font-size:12px;font-variant-numeric:tabular-nums}
.node .caret{width:14px;color:#5F6B78;display:inline-flex}
.node--l2{padding-left:30px}
.node--root{font-weight:600}
.node--sel{background:#E8F0FB;color:#174A96;font-weight:600;box-shadow:inset 3px 0 0 #1F5FBF}
.node--sel .count{color:#174A96}
.node--dim{color:#A3ACB6}
.node--dim .count{color:#A3ACB6}
.node--open{font-weight:600}
main.content{flex:1;min-width:0;padding:20px;display:flex;flex-direction:column}
.card{flex:1;min-height:0;background:#FFFFFF;border:1px solid #DDE2E7;border-radius:8px;display:flex;flex-direction:column;overflow:hidden}
.card-head{display:flex;align-items:center;gap:12px;height:56px;flex:0 0 56px;padding:0 16px;border-bottom:1px solid #EEF1F4}
.crumb{display:flex;align-items:center;gap:6px;font-size:16px;font-weight:600}
.crumb .sep{color:#A3ACB6;font-weight:400}
.crumb .parent{color:#5F6B78;font-weight:500}
.local-filter{display:flex;align-items:center;gap:6px;height:30px;width:240px;padding:0 10px;border:1px solid #DDE2E7;border-radius:6px;color:#A3ACB6}
table{width:100%;border-collapse:collapse;table-layout:fixed}
thead th{height:36px;padding:0 16px;text-align:left;font-weight:500;color:#5F6B78;font-size:12px;background:#F7F9FB;border-bottom:1px solid #DDE2E7}
tbody td{height:36px;padding:0 16px;border-bottom:1px solid #EEF1F4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tbody tr.hover td{background:#F7F9FB}
tbody tr.focus td{background:#E8F0FB}
tbody tr.focus td:first-child{box-shadow:inset 3px 0 0 #1F5FBF}
.name{font-weight:500}
.dup{display:inline-flex;align-items:center;height:18px;margin-left:8px;padding:0 6px;border-radius:4px;background:#FFE4C7;box-shadow:inset 0 0 0 1px #F5C796;color:#9A3412;font-size:11px;font-weight:500;vertical-align:1px}
.enter{display:inline-flex;align-items:center;gap:2px;color:#A3ACB6}
tr.hover .enter,tr.focus .enter{color:#1F5FBF;font-weight:500}
.enter--off{display:inline-flex;align-items:center;height:20px;padding:0 7px;border-radius:4px;background:#F1F3F5;color:#5F6B78;font-size:12px}
mark{background:#FFF1B8;color:inherit;border-radius:2px;padding:0 1px}
.table-wrap{flex:1;min-height:0;overflow:hidden}
.card-foot{height:48px;flex:0 0 48px;display:flex;align-items:center;gap:12px;padding:0 16px;border-top:1px solid #EEF1F4;color:#5F6B78;font-size:12px}
.pager{display:inline-flex;gap:4px}
.pager span{display:inline-grid;place-items:center;min-width:28px;height:28px;padding:0 6px;border-radius:6px;border:1px solid #DDE2E7;color:#4A5563;background:#fff}
.pager span.cur{background:#1F5FBF;border-color:#1F5FBF;color:#fff;font-weight:600}
.hint{display:inline-flex;align-items:center;gap:6px}
.notice{display:flex;align-items:center;gap:8px;margin:0 0 12px;padding:8px 12px;border-radius:6px;background:#E0F2FE;box-shadow:inset 0 0 0 1px #B5DDF6;color:#0B5A8A;font-size:12px}
"""


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def header(stats: bool) -> str:
    stat = (
        '<span class="vsep"></span><span class="muted">目录导入 2026-11-10 · 8 个地区一 · 196 个地区二 · 18,426 个项目</span>'
        if stats else '<span class="vsep"></span><span class="muted">18,426 个项目</span>'
    )
    return f"""
  <header class="top">
    <div class="brand"><span class="brand-mark">网</span>网关设备目录</div>
    <span class="tag tag--info">试运行</span>
    {stat}
    <span class="spacer"></span>
    <span class="muted">进入身份</span>
    <button type="button" class="ghost-btn" aria-haspopup="listbox" title="跳转到网关系统时使用的测试身份">{ICON['user']}test1 · 全部权限{ICON['down']}</button>
  </header>"""


def searchbar(width: int, query: str | None, scope_all: bool, recent_count: int) -> str:
    recent = [("城南 110kV 变电站", "苏州"), ("虎丘 220kV 变电站", "苏州"), ("长宁 220kV 变电站", "宁波"),
              ("川南 110kV 变电站", "宜昌"), ("金鸡湖 220kV 变电站", "苏州")][:recent_count]
    chips = "".join(f'<a class="chip" href="#">{esc(n)}<span class="muted">{esc(r)}</span></a>' for n, r in recent)
    if query is None:
        box = f"""<label class="search" style="width:{width}px">{ICON['search']}<input placeholder="搜索项目名、站号或拼音首字母，如 cnbdz"><span class="kbd">/</span></label>"""
    else:
        box = f"""<label class="search search--active" style="width:{width}px">{ICON['search']}<input value="{esc(query)}"><span class="muted" style="font-size:12px">9 个结果</span>{ICON['x']}</label>"""
    scope = f"""<div class="seg" role="radiogroup" aria-label="搜索范围">
      <button type="button" role="radio" aria-checked="{'true' if scope_all else 'false'}">全部地区</button>
      <button type="button" role="radio" aria-checked="{'false' if scope_all else 'true'}">仅 江苏 / 苏州</button>
    </div>"""
    return f"""
  <div class="searchbar">
    {box}
    {scope}
    <span class="spacer"></span>
    <div class="recent"><span class="muted hint">{ICON['clock']}最近访问</span>{chips}</div>
  </div>"""


def tree(width: int, search: bool) -> str:
    rows = []
    total = "9" if search else "18,426"
    rows.append(f'<div class="node node--root"><span class="caret"></span>{"全部匹配" if search else "全部地区"}<span class="count">{total}</span></div>')
    for name, count in REGION1:
        if search:
            c = SEARCH_COUNTS[name]
            cls = "node node--dim" if c == 0 else "node"
            open_ = name == "江苏"
            caret = ICON['down'] if open_ else ICON['right']
            rows.append(f'<div class="{cls}{" node--open" if open_ else ""}"><span class="caret">{caret}</span>{name}<span class="count">{c}</span></div>')
            if open_:
                rows.append('<div class="node node--l2">苏州<span class="count">2</span></div>')
                rows.append('<div class="node node--l2">无锡<span class="count">1</span></div>')
            continue
        open_ = name == "江苏"
        caret = ICON['down'] if open_ else ICON['right']
        rows.append(f'<div class="node{" node--open" if open_ else ""}"><span class="caret">{caret}</span>{name}<span class="count">{count:,}</span></div>')
        if open_:
            for child, c in JS_CHILDREN:
                sel = " node--sel" if child == "苏州" else ""
                aria = ' aria-current="true"' if sel else ""
                rows.append(f'<div class="node node--l2{sel}"{aria}>{child}<span class="count">{c}</span></div>')
    head = (
        '<div class="tree-head"><div class="muted" style="font-size:12px">按地区筛选结果</div></div>'
        if search else
        f'<div class="tree-head"><div class="tree-filter">{ICON["search"]}筛选地区</div></div>'
    )
    return f"""
    <nav class="tree" aria-label="地区" style="width:{width}px">
      {head}
      <div class="tree-list">
        {''.join(rows)}
      </div>
    </nav>"""


def browse_card(rows_visible: int, wide: bool) -> str:
    cols = (
        '<col><col style="width:160px"><col style="width:220px"><col style="width:150px">'
        if wide else '<col><col style="width:110px"><col style="width:190px"><col style="width:120px">'
    )
    body = []
    for i, (name, code, _key, dup) in enumerate(PROJECTS[:rows_visible]):
        key = device_key(code)
        off = code in UNPROVISIONED
        cls = ' class="focus"' if i == 3 else (' class="hover"' if i == 8 else "")
        dup_tag = '<span class="dup" title="苏州下有 2 个同名项目，按站号区分">同名</span>' if dup else ""
        body.append(
            f'<tr{cls}><td><span class="name">{esc(name)}</span>{dup_tag}</td>'
            f'<td class="mono">{code}</td><td class="mono muted">{key}</td>'
            + (f'<td><span class="enter enter--off" title="该设备尚未在网关系统开通">未开通</span></td></tr>' if off
               else f'<td><span class="enter">进入提交树{ICON["right"]}</span></td></tr>')
        )
    return f"""
      <section class="card" aria-label="项目列表">
        <div class="card-head">
          <div class="crumb"><span class="parent">江苏</span><span class="sep">/</span>苏州</div>
          <span class="muted">共 214 个项目</span>
          <span class="spacer"></span>
          <div class="local-filter">{ICON['search']}在苏州内筛选</div>
          <span class="muted" style="font-size:12px">按名称排序</span>
        </div>
        <div class="table-wrap">
          <table>
            <colgroup>{cols}</colgroup>
            <thead><tr><th>项目名</th><th>站号</th><th>设备标识</th><th></th></tr></thead>
            <tbody>{''.join(body)}</tbody>
          </table>
        </div>
        <div class="card-foot">
          <span>第 1–50 项，共 214 项</span>
          <div class="pager"><span>‹</span><span class="cur">1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>›</span></div>
          <span class="spacer"></span>
          <span class="hint"><span class="kbd">↑</span><span class="kbd">↓</span>选择<span class="kbd">Enter</span>进入提交树</span>
        </div>
      </section>"""


def search_card() -> str:
    body = []
    for i, (name, path, code, _key, hit, dup) in enumerate(SEARCH):
        key = device_key(code)
        name_html = esc(name).replace(esc(hit), f"<mark>{esc(hit)}</mark>", 1)
        cls = ' class="focus"' if i == 1 else ""
        dup_tag = '<span class="dup" title="苏州下有 2 个同名项目，按站号区分">同名</span>' if dup else ""
        body.append(
            f'<tr{cls}><td><span class="name">{name_html}</span>{dup_tag}</td>'
            f'<td class="muted">{esc(path)}</td><td class="mono">{code}</td><td class="mono muted">{key}</td>'
            f'<td><span class="enter">进入提交树{ICON["right"]}</span></td></tr>'
        )
    return f"""
      <div class="notice">按拼音首字母“cn”匹配；结果跨全部地区，按名称排序。左侧数字为各地区的匹配数，点击可只看该地区。</div>
      <section class="card" aria-label="搜索结果">
        <div class="card-head">
          <div class="crumb">搜索结果</div>
          <span class="muted">“cn” 匹配 9 个项目</span>
          <span class="spacer"></span>
          <span class="muted" style="font-size:12px">按名称排序</span>
        </div>
        <div class="table-wrap">
          <table>
            <colgroup><col><col style="width:220px"><col style="width:160px"><col style="width:220px"><col style="width:150px"></colgroup>
            <thead><tr><th>项目名</th><th>地区</th><th>站号</th><th>设备标识</th><th></th></tr></thead>
            <tbody>{''.join(body)}</tbody>
          </table>
        </div>
        <div class="card-foot">
          <span>共 9 项</span>
          <span class="spacer"></span>
          <span class="hint"><span class="kbd">Esc</span>清除搜索，回到 江苏 / 苏州</span>
        </div>
      </section>"""


def page(title: str, width: int, height: int, inner: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<!-- 设计草图（设备目录）：独立的目录系统，选中项目后跳转到网关系统的数据提交树。仅作视觉与交互参考，不是实现代码；数据为示例。 -->
<div class="page" style="width:{width}px;height:{height}px">{inner}
</div>
</body>
</html>
"""


def browse(width: int, height: int, wide: bool) -> str:
    tree_w = 280 if wide else 240
    rows = 21 if wide else 14
    return (
        header(stats=wide)
        + searchbar(560 if wide else 380, None, scope_all=True, recent_count=4 if wide else 2)
        + f'\n  <div class="body">{tree(tree_w, search=False)}\n    <main class="content">{browse_card(rows, wide)}\n    </main>\n  </div>'
    )


def search(width: int, height: int) -> str:
    return (
        header(stats=True)
        + searchbar(560, "cn", scope_all=True, recent_count=4)
        + f'\n  <div class="body">{tree(280, search=True)}\n    <main class="content">{search_card()}\n    </main>\n  </div>'
    )


(OUT / "directory-1280.html").write_text(page("设备目录 · 浏览 · 1280", 1280, 800, browse(1280, 800, False)), encoding="utf-8")
(OUT / "directory-1920.html").write_text(page("设备目录 · 浏览 · 1920", 1920, 1080, browse(1920, 1080, True)), encoding="utf-8")
(OUT / "search-1920.html").write_text(page("设备目录 · 跨地区搜索 · 1920", 1920, 1080, search(1920, 1080)), encoding="utf-8")
print("ok")
