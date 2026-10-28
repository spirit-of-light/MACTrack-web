"""Static checks on index.html (rendering is checked by hand in a browser). Run: python3 test_page.py"""
import json
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def near(a, b):
    return a is not None and abs(a - b) < 1e-6


def call_args(src, start):
    """Text of the parenthesised arguments that open at src[start] == '('."""
    depth = 0
    for j in range(start, len(src)):
        depth += {"(": 1, ")": -1}.get(src[j], 0)
        if depth == 0:
            return src[start:j + 1]
    raise AssertionError("unbalanced parens")


def fetch_calls(src):
    """Each fetch's arguments, with the API base (`API + '...'`, `${API}`) dropped so paths read as before."""
    calls = [call_args(src, m.end() - 1) for m in re.finditer(r"(?<![\w.])fetch\s*\(", src)]
    return [re.sub(r"^\(\s*API\s*\+\s*", "(", a).replace("${API}", "", 1) for a in calls]


# The backend's sign-in entry URLs (MACTrack extension/parse.js SITES.<source>.login); keep in step.
SITE_LOGIN = {
    "avenue": "https://avenue.mcmaster.ca/login.php?target=%2Fd2l%2Fhome",
    "childsmath": "https://login.microsoftonline.com/44376307-b429-42ad-8c25-28cd496f4772/oauth2/v2.0/authorize?client_id=9132e1a8-fef6-4c34-bddb-de7608a2381a&response_type=code&response_mode=query&scope=https%3A%2F%2Fgraph.microsoft.com%2FUser.Read",
}


# AC2/AC26-31/AC35/AC41/AC42/AC51/AC83 — what can be proven without a browser
def test_index_static():
    html = (ROOT / "index.html").read_text()
    assert "localStorage" in html, "upcoming window not kept in localStorage (AC42/AC51)"
    assert "/api/items" in html and "/api/status" in html, "page does not read /api/items and /api/status"
    calls = fetch_calls(html)
    assert calls, "page makes no fetch"
    for a in calls:
        url = re.match(r"\(\s*([`'\"])(.*?)\1", a)
        assert url and url.group(2).startswith(("/api/items", "/api/status")), f"unexpected request: fetch{a[:80]}"
        assert "localStorage" not in a and not re.search(r"upcoming|window", a, re.I), f"window sent to server: {a[:120]}"
    edits = [a for a in calls if "/api/items/" in a]
    assert edits, "no inline-edit POST to /api/items/<id> (AC31)"
    for a in edits:
        assert re.search(r"method\s*:\s*['\"]POST['\"]", a) and "application/json" in a, f"edit POST not JSON: {a[:160]}"
    assert not re.search(r"x-token|token\.txt", html, re.I), "page references the ingest token (AC35: only the extension holds it)"
    assert "const UPCOMING_DAYS = 7;" in html and "UPCOMING_DAYS * 864e5" in html, "upcoming window is not 7 days (AC41)"
    assert "login needed" in html, "no login-needed banner text (AC30)"
    assert "—" in html or "&mdash;" in html, "no — for an ungraded course (AC83)"
    assert not re.search(r"""(?:src|href)\s*=\s*['"]?(?:https?:)?//|@import""", html, re.I), "external resource (page must work offline)"


# Bug 7 (page) — the course header renders courses[...].info
def test_index_course_info():
    html = (ROOT / "index.html").read_text()
    assert re.search(r"\.info\b|\[\s*['\"]info['\"]\s*\]", html), "index.html never reads courses[code].info"



# AC90 (2026-10-18) — practice is not tracked, so the page no longer offers it as a type
def test_index_kinds_practice():
    m = re.search(r"const KINDS\s*=\s*\[([^\]]*)\]", (ROOT / "index.html").read_text())
    assert m and "'practice'" not in m.group(1), m and m.group(1)


# Spec 0002 AC16 — the `login needed` banner links to the source's login entry URL (Crowdmark -> Avenue's)
def test_index_login_links():
    html = (ROOT / "index.html").read_text()
    urls = {s: SITE_LOGIN[s] for s in ("avenue", "childsmath")}
    for url in urls.values():
        assert url in html, f"{url} not in index.html"
    m = re.search(r"const\s+LOGIN\s*=\s*\{([^}]*)\}", html)
    assert m, "no LOGIN map in index.html"
    vals = dict(re.findall(r"\b(avenue|crowdmark|childsmath)\s*:\s*([^,\n}]+)", m.group(1)))
    assert set(vals) == {"avenue", "crowdmark", "childsmath"}, f"LOGIN keys: {sorted(vals)}"
    lit = lambda v: v.strip().strip("'\"`")
    assert lit(vals["avenue"]) == urls["avenue"], f"LOGIN.avenue {vals['avenue']}"
    assert lit(vals["childsmath"]) == urls["childsmath"], f"LOGIN.childsmath {vals['childsmath']}"
    assert vals["crowdmark"].strip() == vals["avenue"].strip() or lit(vals["crowdmark"]) == urls["avenue"], \
        f"LOGIN.crowdmark is not Avenue's entry URL: {vals['crowdmark']}"
    near = [html[max(0, i.start() - 600):i.start() + 600] for i in re.finditer(r"login needed", html)]
    link = r"(?:\$\(\s*['\"]a['\"]|createElement\(\s*['\"]a['\"])[^;]*?href\s*[:=]\s*LOGIN\[|\.href\s*=\s*LOGIN\["
    assert any(re.search(link, w, re.S) for w in near), "the login-needed status builds no <a> with href from LOGIN"
    assert 'id="banners"' not in html, "top banners are back (developer removed them 2026-10-18)"
    assert any(re.search(r"noopener", w) for w in near), "sign-in link opened without rel=noopener"
    assert "innerHTML" not in html, "index.html uses innerHTML"


# AC111 — the page has an add form and a delete button for manual rows only, both JSON POSTs
def test_index_manual_items():
    html = (ROOT / "index.html").read_text()
    calls = fetch_calls(html)
    adds = [a for a in calls if re.match(r"\(\s*['\"`]/api/items['\"`]\s*,", a)]
    assert adds, "no add POST to /api/items"
    dels = [a for a in calls if re.match(r"\(\s*`/api/items/\$\{item\.id\}/delete`", a)]
    assert dels, "no delete POST to /api/items/<id>/delete"
    for a in adds + dels:
        assert re.search(r"method\s*:\s*['\"]POST['\"]", a) and "application/json" in a, a[:160]
    assert re.search(r"source\s*===\s*['\"]manual['\"]", html), "delete not limited to manual rows"
    assert "Add item" in html and 'type="date"' in html and 'type="time"' in html and "innerHTML" not in html


# Quick (view/edit mode) — view mode by default, remembered in localStorage only; the add form and
# the row editors appear only in edit mode
def test_index_view_edit_mode():
    html = (ROOT / "index.html").read_text()
    assert re.search(r"localStorage\.getItem\(\s*['\"]editMode['\"]\s*\)", html), "edit mode not read from localStorage"
    assert re.search(r"localStorage\.setItem\(\s*['\"]editMode['\"]", html), "edit mode not saved to localStorage"
    assert not any("editMode" in a for a in fetch_calls(html)), "edit mode sent to the server"
    assert re.search(r"<button id=['\"]edit['\"]", html) and "'View' : 'Edit'" in html, "no Edit/View toggle button"
    assert html.index('id="edit"') > html.index('id="sources"'), "Edit button is not at the bottom"
    assert re.search(r"getElementById\(\s*['\"]add['\"]\s*\)\.hidden\s*=", html), "add form not hidden in view mode"
    row = re.search(r"function row\(item\)\s*\{(.*?)\n\}", html, re.S)[1]
    assert re.search(r"if\s*\(\s*!editing\(\)\s*\)", row), "row() has no plain view branch"


def test_index_calendar():
    html = (ROOT / "index.html").read_text()
    for id_ in ("calendar", "cal-back", "cal-fwd", "cal-today"):
        assert re.search(rf"id=['\"]{id_}['\"]", html), f"no #{id_}"
    cal = re.search(r"function calendar\(.*?\n\}", html, re.S)[0]
    assert "length: CAL_DAYS" in cal and "const CAL_DAYS = 14;" in html, "calendar is not 14 days"
    assert re.search(r"calOffset\s*-=\s*STEP", html) and re.search(r"calOffset\s*\+=\s*STEP", html) and "const STEP = 7;" in html, \
        "arrows do not move by a week"
    assert re.search(r"calOffset\s*=\s*0\b", html), "Today button does not reset the calendar"
    assert "onmouseenter: () => hl(true)" in html and "tr.dataset.day = day;" in html, "calendar hover does not highlight rows"
    assert "'Source'" not in html and "`From ${item.source}${item.missing" in html, "source is not a row tooltip in edit mode"


def test_index_hide_courses():
    html = (ROOT / "index.html").read_text()
    assert re.search(r"localStorage\.getItem\(\s*['\"]hiddenCourses['\"]", html), "hidden courses not read from localStorage"
    assert re.search(r"localStorage\.setItem\(\s*['\"]hiddenCourses['\"]", html), "hidden courses not saved to localStorage"
    assert not any("hiddenCourses" in a for a in fetch_calls(html)), "hidden courses sent to the server"
    assert re.search(r"calendar\(data\.items\.filter\(\(i\) => visible\.includes\(", html), "calendar does not skip hidden courses"
    assert re.search(r"courses = editing\(\) \? all : visible", html), "view mode does not skip hidden courses"
    assert re.search(r"if \(!editing\(\)\) return b;", html), "eye button not limited to edit mode"
    assert re.search(r"all\.indexOf\(c\)", html), "course colours shift when a course is hidden"


def test_index_single_list():
    html = (ROOT / "index.html").read_text()
    assert 'id="kinds"' not in html and "typeButtons" not in html, "type filter buttons are back"
    for id_ in ("courses", "statuses"):
        assert re.search(rf"<div id=['\"]{id_}['\"] class=['\"]chips['\"]", html), f"no #{id_} button row"
    assert re.search(r"\['', \.\.\.values\]\.map", html) and "v || 'All'" in html, "button rows do not start with All"
    assert "const shownKind = (i) => editing() || i.kind !== 'other';" in html \
        and "shownKind(i) && !i.done" in html, "other items show outside edit mode"
    assert "const keep = (i) => shownKind(i) && !(hideDone && i.done);" in html, "Hide done not applied"
    assert "textContent: 'Hide done'" in html and "STATES" not in html, "status is not the single Hide done toggle"
    assert "tr.overdue { background: var(--overdue-bg); box-shadow: inset 3px 0 var(--overdue-text); }" in html, "overdue rows not red"
    assert ".chips { display: grid; grid-template-columns: 1fr;" in html, "filter groups are not single columns"
    head = re.search(r"tip\(\$\('th', \{ textContent: '✓' \}\), 'Done'\).*?\['Type', 'Course', 'Title', 'Due', 'Time left', 'Weight', 'Mark',", html, re.S)
    assert head, "list columns are not Done | Type | Course | Title | Due | Time left | Weight | Mark"
    assert "upcoming }" not in html and "Upcoming'" not in html, "Upcoming still offered as a status"
    assert html.index('id="calendar"') < html.index('id="courses"'), "calendar is not above the filters"
    assert re.search(r'<div id="layout">\s*<main>.*?</main>\s*<aside id="filters">', html, re.S), "filters are not a sidebar right of the list"
    assert re.search(r'<div id="cal-wrap">.*?id="calendar".*?<div id="layout">\s*<main>\s*<p id="summary"', html, re.S), \
        "top bar is not full width above the list and sidebar"
    assert "#filters { position: sticky; top: var(--head-top, 0);" in html, "sidebar does not stick below the calendar"
    assert "#cal-wrap { position: sticky;" in html, "calendar does not stay in view"
    assert "margin: 0 1.5rem 1.5rem;" in html and "#top { display: flex; gap: .8rem; align-items: flex-start; padding-top: 1rem; }" in html, \
        "page top margin makes the top bar jump when it pins"
    assert "grid-template-columns: repeat(7, var(--day)); grid-auto-rows: var(--day);" in html and "--day: 8.5rem;" in html, \
        "calendar days are not fixed squares"
    assert ".next { height: calc(2 * var(--day) + 1px);" in html and "#next-test, #next-lab { flex: 1;" in html, \
        "Next test box does not fill the rest of the top bar at the calendar's height"
    assert "dateTime(s.synced_at)" in html and "alignDots(document.getElementById('sources'))" in html, \
        "Last synced is not in the due-date style"
    assert re.search(r"\.items thead th \{ position: sticky; top: var\(--head-top", html), "column titles do not follow scrolling"
    assert 'id="windows"' not in html and "upcomingDays" not in html, "window buttons are back"
    top = re.search(r'<div id="top">(.*?)<div id="layout">', html, re.S)[1]
    assert top.index('id="calendar"') < top.index('id="cal-nav"') < top.index('id="next-test"'), "arrows are not right of the calendar"
    assert re.search(r'id="cal-back".*?id="cal-today".*?id="cal-fwd"', top, re.S) and "flex-direction: column; gap: .3rem; } /* up:" in html, \
        "arrows are not up / today / down in a column"
    assert "from.getDay() === 0 || from.getDay() === 6" in html and ".day.weekend { background: var(--weekend-bg); }" in html, \
        "weekend days not grey"
    assert ".sort((a, b) => !!a.done - !!b.done || dueMs(a) - dueMs(b))" in html, "done items not listed after open ones"
    assert re.search(r"<th>Website</th><th>Status</th><th>Last synced</th>", html), "no sync status table"
    assert html.index('id="sources"') > html.index("</main>"), "sync table is not below the item list"
    assert re.search(r"const KINDS = \[[^\]]*'midterm'[^\]]*'homework'", html), "midterm or homework dropped from KINDS"
    assert ".items { table-layout: fixed;" in html, "item list columns not locked"
    assert html.index('id="tests"') < html.index('id="labs"') < html.index('id="items"'), "tables are not Tests, Labs, Coursework"
    assert "['tests', shown.filter((i) => TESTS.includes(i.kind))], ['labs', shown.filter(isLab)]" in html \
        and "['items', shown.filter((i) => !TESTS.includes(i.kind) && !isLab(i))]" in html, "tests and labs are not split out"
    assert re.search(r'<div id="pair">\s*<div id="tests-part">.*?<div id="labs-part">.*?</div>\s*</div>\s*<div id="work-part">', html, re.S) \
        and "#pair { display: flex;" in html, "tests and labs are not side by side"
    assert "const typed = id === 'items' || editing();" in html and "if (!typed) tr.children[1].remove();" in html, \
        "tests or labs table has a Type column in view mode, or none in edit mode"
    assert "Progress" not in html and "<section" not in html, "progress column or per-course sections remain"
    assert "round2(item.weight), markText(item)" in html and "round2(i.mark)" in html, "weight and mark not rounded in view mode"


def test_index_due_format():
    html = (ROOT / "index.html").read_text()
    js = "\n".join(re.search(rf"^const {n} = .*?;$", html, re.M)[0] for n in ("MONTHS", "pad"))
    js += "\n" + re.search(r"^const dueText = .*?^\};$", html, re.M | re.S)[0]
    js += """
const now = new Date(2026, 9, 18);
const out = [dueText(null, now), dueText(new Date(2026, 9, 20, 9, 5).toISOString(), now),
  dueText(new Date(2027, 0, 3, 23, 59).toISOString(), now)];
console.log(JSON.stringify(out));"""
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert got == [[], ["20 Oct", "09:05"], ["03 Jan 2027", "23:59"]], got
    assert "grid-template-columns: var(--date-w, max-content)" in html and "div.due {" in html and "--date-w" in html, "due dots not aligned"


def test_index_single_save():
    html = (ROOT / "index.html").read_text()
    row = re.search(r"function row\(item\)\s*\{(.*?)\n\}", html, re.S)[1]
    assert "textContent: 'Save'" not in row and "textContent: 'Delete'" not in row, "per-row Save or Delete button left"
    assert re.search(r'<aside id="filters">\s*<button id="save">', html), "no single Save button at the top of the sidebar"
    assert re.search(r"for \(const \[id, p\] of pending\)", html), "Save does not send every pending row"
    assert "icon(TRASH)" in row, "delete is not a trash icon"
    assert re.search(r'<aside id="filters">.*?<form id="add">.*?</aside>', html, re.S), "add-item form is not in the sidebar"
    assert re.search(r'<select name="course" required', html), "add-item course is not a select"
    assert "appearance: textfield" in html, "number inputs still show increment buttons"
    assert "#layout.editing #filters" not in html, "edit mode moves the filters out of the sidebar"
    assert ".chips button.course { border-left: 4px solid var(--c); }" in html and "var(--c, var(--text-faint))" not in html, \
        "grey edge on non-course buttons"
    assert "#add[hidden] { display: none; }" in html, "add form's display rule overrides hidden in view mode"


def test_index_next_blocks_and_row_hover():
    html = (ROOT / "index.html").read_text()
    top = re.search(r'<div id="top">(.*?)<div id="layout">', html, re.S)[1]
    assert top.index('id="calendar"') < top.index('id="next-test"') < top.index('id="next-lab"') and 'id="next-up"' not in html, \
        "top bar is not the calendar, Next test, Next lab"
    assert "#next-test, #next-lab { flex: 1;" in html, "the two boxes do not share the rest of the top bar"
    assert "const nextLab = ahead.find(isLab);" in html and "lab ? 'Selected lab' : 'Next lab'" in html, "no Next lab box"
    assert ".next .what { margin-left: auto; text-align: right;" in html, "details are not right-aligned opposite the titles"
    assert "ahead.find((i) => TESTS.includes(i.kind))" in html, "Next test picks the wrong item"
    assert "`Room ${room ?? 'TBD'}`" in html, "an item with no known room does not say TBD"
    assert "test ? 'Selected test' : 'Next test'" in html and "tr.addEventListener('mouseenter', () => showPicked(i));" in html \
        and "tr.addEventListener('mouseleave', () => showPicked(null));" in html, "hovering a test or lab does not show it in its box"
    assert "container-type: inline-size;" in html and ".next .title { font-size: clamp(" in html, "Next test text does not scale with its box"
    assert "id === 'tests' && h === 'Due' ? 'Time' : h" in html, "tests table still says Due"
    assert "querySelector(`#calendar .day[data-day=\"${day}\"]`)" in html and "cell.dataset.day = day;" in html, \
        "row hover does not highlight its calendar day"
    js = re.search(r"^const roomOf = .*?^\};$", html, re.M | re.S)[0] + """
const info = [{ name: 'Lab Room', value: 'ABB 126' }, { name: 'Test 1 Room', value: 'PGCLL B131' }, { name: 'Test 10 Room', value: 'X' }];
console.log(JSON.stringify([roomOf('Test 1', info), roomOf('Test 2', info), roomOf('Test 10', info), roomOf('Exam', [])]));"""
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert got == ["PGCLL B131", None, "X", None], got


def test_index_grades_links_empty_unload_filters():
    html = (ROOT / "index.html").read_text()
    assert html.index('id="items"') < html.index('id="grades"') < html.index('id="sources"'), "grades table is not after the list"
    assert "<th>Course</th><th>Grade</th><th>Graded</th>" in html, "no Course | Grade | Graded table"
    assert "/^https?:\\/\\//i.test(item.url ?? '')" in html and "href: item.url" in html, "titles do not link to http(s) urls only"
    assert "No items match these filters." in html and "'Clear filters'" in html, "no empty state"
    assert "addEventListener('beforeunload'" in html and "if (pending.size) e.preventDefault()" in html, "no unsaved-edits warning"
    assert "localStorage.getItem('filters')" in html and "localStorage.setItem('filters'" in html, "filters not remembered"
    assert not any("filters" in a for a in fetch_calls(html)), "filters sent to the server"


def test_index_time_left_refresh():
    html = (ROOT / "index.html").read_text()
    body = re.search(r"^function tick\(\) \{.*?^\}$", html, re.M | re.S)[0]
    assert "tr.querySelector('.left').textContent = left(i)" in body and "setTimeout(tick," in body, "time left cells are not refreshed"
    assert "render()" not in body and "setInterval" not in html, "refresh rebuilds the page or polls"
    # the wait is the time until the next displayed change: hour steps over a day, minute steps under it
    js = """
const dueMs = (i) => i.due; let timed, tickTimer; const overdue = () => false, upcoming = () => false, left = () => '';
let waited; const setTimeout = (f, ms) => { waited = ms - 50; }; const clearTimeout = () => {};
const Date = { now: () => 0 };
const row = () => ({ querySelector: () => ({}), classList: { toggle() {} } });
""" + body + """
const out = [];
for (const due of [2 * 864e5 + 36e5 * 4 + 6e4 * 30, 36e5 * 3 + 6e4 * 20 + 1e3 * 15, -(36e5 + 6e4 * 10)]) {
  timed = [[row(), { due }]]; tick(); out.push(waited);
}
console.log(JSON.stringify(out));"""
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert got == [6e4 * 30, 1e3 * 15, 6e4], got


def test_index_tooltips_and_more():
    html = (ROOT / "index.html").read_text()
    js = html.split("<script>")[1]
    assert not re.search(r"\btitle\s*[:=]\s*[`'(]|\.title\s*=", js) and ' title="' not in html, "a browser title tooltip is left"
    assert '<div id="tip" role="tooltip" hidden></div>' in html and "closest('[data-tip]')" in html, "no page tooltip"
    assert "more.textContent = `+${n} more`;" in html, "full calendar days do not say +N more"
    more = re.search(r"for \(const day of cal\.children\) \{.*?\n  \}", html, re.S)[0]
    assert "tip(day," in more and "tip(cell," not in html, "calendar day tooltip shows without +N more"
    assert html.count('data-tip-delay="1000"') == 3 and "Number(t.dataset.tipDelay) || 0" in html, "nav button tooltips are not delayed 1 s"


if __name__ == "__main__":
    failed = 0
    for name, fn in [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]:
        try:
            fn()
            print(f"ok   {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            if "-v" in sys.argv:
                traceback.print_exc()
    sys.exit(1 if failed else 0)
