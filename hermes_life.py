'''
生活助手数据操作脚本 — Hermes bot + 本地 AI 通用
用法: python hermes_life.py <action> [参数...]

操作:
  add-task <标题> <课程> <DDL> [优先级]    添加作业
  done <关键词>                            标记完成
  undo <关键词>                            取消完成
  edit-task <id> <字段> <值>               修改作业(标题/课程/DDL/优先级)
  today                                    今日课程+待办
  tasks                                    未完成作业
  tasks-all                                全部作业
  courses                                  所有课程
  add-habit <名称> <类型/值> [分钟]         添加习惯
  done-habit <关键词>                      今日打卡
  edit-habit <id> <字段> <值>              修改习惯(名称/类型/分钟)
  status                                   概览
'''

import sys, json, os, re
from datetime import datetime, date

DATA = r'D:\ClaudeCoding\日程规划\data'

def load(fname):
    p = os.path.join(DATA, fname)
    if not os.path.exists(p):
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def save(fname, obj):
    with open(os.path.join(DATA, fname), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def gen_id(items, prefix, key='id'):
    existing = set()
    for it in items:
        try:
            num = int(it[key].split('_')[1])
            existing.add(num)
        except:
            pass
    n = 1
    while n in existing:
        n += 1
    return f'{prefix}_{n:03d}'

def now_iso():
    return datetime.now().isoformat()

# ============== TASKS ==============

def add_task(args):
    if len(args) < 3:
        return ('用法: add-task <标题> <课程名> <截止日期> [优先级]\n'
                '日期格式: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM')
    title = args[0]
    course = args[1]
    due = args[2]
    priority = args[3] if len(args) > 3 else 'medium'
    if 'T' not in due:
        due += 'T23:00:00'
    elif len(due) <= 16:
        due += ':00'

    data = load('tasks.json')
    data.setdefault('tasks', [])
    data.setdefault('archived', [])
    tid = gen_id(data['tasks'] + data['archived'], 't')

    task = {
        'id': tid, 'title': title, 'course_name': course,
        'due_date': due, 'status': 'pending', 'priority': priority,
        'tags': [], 'notes': '', 'created_at': now_iso(), 'reminded': False
    }
    data['tasks'].append(task)
    save('tasks.json', data)
    return f'✓ 已添加: [{tid}] {title} | {course} | DDL {due[:16]}'


def _find_task(kw, data):
    all_items = data.get('tasks', []) + data.get('archived', [])
    kw_lower = kw.lower()
    matches = []
    for t in all_items:
        title = t.get('title', '').lower()
        course = t.get('course_name', '').lower()
        tid = t.get('id', '').lower()
        if kw_lower in title or kw_lower in course or kw_lower in tid:
            matches.append(t)
    return matches


def mark_done(args):
    if not args:
        return '用法: done <关键词> — 匹配标题、课程名、或ID'
    kw = ' '.join(args)
    return _toggle_status(kw, True)


def mark_undo(args):
    if not args:
        return '用法: undo <关键词>'
    kw = ' '.join(args)
    return _toggle_status(kw, False)


def _toggle_status(kw, to_completed):
    data = load('tasks.json')
    data.setdefault('tasks', [])
    data.setdefault('archived', [])
    matched = _find_task(kw, data)

    if not matched:
        return f'未找到匹配「{kw}」的作业'
    if len(matched) > 1:
        lines = [f'找到 {len(matched)} 条，请指定更精确的关键词:']
        for t in matched:
            s = '✓' if t.get('status') == 'completed' else '○'
            lines.append(f'  {s} [{t["id"]}] {t["title"][:30]} | {t.get("course_name","")[:15]}')
        return '\n'.join(lines)

    t = matched[0]
    if to_completed:
        t['status'] = 'completed'
        t['completed_at'] = now_iso()
        data['tasks'] = [x for x in data['tasks'] if x['id'] != t['id']]
        data['archived'].append(t)
        emoji, word = '✓', '完成'
    else:
        t['status'] = 'pending'
        t.pop('completed_at', None)
        data['archived'] = [x for x in data['archived'] if x['id'] != t['id']]
        data['tasks'].append(t)
        emoji, word = '↩', '取消完成'

    save('tasks.json', data)
    return f'{emoji} {word}: [{t["id"]}] {t["title"]} | {t.get("course_name","")}'


def edit_task(args):
    if len(args) < 3:
        return '用法: edit-task <id> <字段> <新值>\n字段: title/course/due/priority'
    tid, field, value = args[0], args[1], ' '.join(args[2:])
    data = load('tasks.json')
    data.setdefault('tasks', [])
    data.setdefault('archived', [])

    # find in both
    target = None
    for t in data['tasks'] + data['archived']:
        if t['id'] == tid:
            target = t
            break
    if not target:
        return f'未找到 [{tid}]'

    field_map = {
        'title': 'title',
        'course': 'course_name',
        'due': 'due_date',
        'ddl': 'due_date',
        'priority': 'priority',
    }
    real_field = field_map.get(field, field)
    if real_field not in target:
        return f'无效字段: {field}（可用: title/course/due/priority）'

    old = target[real_field]
    if real_field == 'due_date' and 'T' not in value:
        value += 'T23:00:00'
    target[real_field] = value
    save('tasks.json', data)
    return f'✏ [{tid}] {real_field}: {old} → {value}'


def remove_task(args):
    '''删除作业: remove-task <id>'''
    if not args:
        return '用法: remove-task <id> — 彻底删除作业'
    tid = args[0]
    data = load('tasks.json')
    data.setdefault('tasks', [])
    data.setdefault('archived', [])
    for lst in [data['tasks'], data['archived']]:
        for i, t in enumerate(lst):
            if t['id'] == tid:
                removed = lst.pop(i)
                save('tasks.json', data)
                return f'🗑 已删除: [{tid}] {removed["title"]}'
    return f'未找到 [{tid}]'


# ============== DISPLAY ==============

def show_today():
    today_obj = date.today()
    today_str = today_obj.isoformat()
    weekday = today_obj.weekday()

    courses_data = load('courses.json')
    lines = ['=== 今日课程 ===']
    has_course = False
    for c in courses_data.get('courses', []):
        dow = c.get('day_of_week')
        try:
            dow = int(dow)
        except:
            dow = -1
        if dow == weekday:
            has_course = True
            slots = c.get('time_slots', [])
            if slots and isinstance(slots[0], dict):
                times = f' 第{",".join(str(s["start"]) for s in slots)}节'
            elif slots:
                times = f' 第{",".join(str(s) for s in slots)}节'
            else:
                times = ''
            lines.append(f'  📚 {c["name"]}{times} | {c.get("location","")}')
    if not has_course:
        lines.append('  (无)')

    tasks_data = load('tasks.json')
    pending = [t for t in tasks_data.get('tasks', []) if t.get('status') == 'pending']
    pending.sort(key=lambda t: t.get('due_date', ''))

    lines.append('\n=== 待完成作业 ===')
    if pending:
        for t in pending:
            ddl = t.get('due_date', '')[:10]
            lines.append(f'  ○ [{t["id"]}] {t["title"][:35]} | {t.get("course_name","")[:12]} | DDL {ddl}')
    else:
        lines.append('  (无)')
    return '\n'.join(lines)


def list_tasks(all_tasks=False):
    data = load('tasks.json')
    active = [t for t in data.get('tasks', []) if t.get('status') == 'pending']
    completed = [t for t in data.get('tasks', []) if t.get('status') == 'completed']
    archived = data.get('archived', [])

    lines = ['=== 进行中 ===']
    for t in active:
        lines.append(f'  ○ [{t["id"]}] {t["title"][:35]} | {t.get("course_name","")[:12]}')

    if all_tasks and completed:
        lines.append('\n=== 已完成 ===')
        for t in completed:
            lines.append(f'  ✓ [{t["id"]}] {t["title"][:35]}')
    if all_tasks and archived:
        lines.append('\n=== 归档 ===')
        for t in archived:
            lines.append(f'  ✓ [{t["id"]}] {t.get("title","")[:35]}')

    if not active:
        return '没有未完成作业 🎉'
    return '\n'.join(lines)


def list_courses_cmd(_):
    data = load('courses.json')
    courses = data.get('courses', [])
    if not courses:
        return '(无课程)'
    lines = ['=== 所有课程 ===']
    for c in courses:
        days = ['一', '二', '三', '四', '五', '六', '日']
        dow = c.get('day_of_week', '')
        try:
            dow = days[int(dow)]
        except:
            pass
        lines.append(f'  周{dow} {c["name"]} | {c.get("location","")}')
    return '\n'.join(lines)


# ============== HABITS ==============

def add_habit(args):
    if len(args) < 2:
        return ('用法: add-habit <名称> <类型/值> [分钟]\n'
                '  例: add-habit 跑步 daily/1 30\n'
                '  例: add-habit 健身 weekly/1,3,5 60')

    name = args[0]
    type_val = args[1]
    mins = int(args[2]) if len(args) > 2 else 30

    try:
        typ, val = type_val.split('/', 1)
    except ValueError:
        return f'格式错误: {type_val}（应为 daily/1 或 weekly/1,3,5 或 monthly/4）'

    if typ == 'daily':
        schedule = {'type': 'daily', 'times_per_day': int(val)}
    elif typ == 'weekly':
        schedule = {'type': 'weekly', 'days': [int(d) for d in val.split(',')]}
    elif typ == 'monthly':
        schedule = {'type': 'monthly', 'value': int(val)}
    else:
        return f'未知类型: {typ}（仅支持 daily/weekly/monthly）'

    data = load('habits.json')
    data.setdefault('habits', [])
    hid = gen_id(data['habits'], 'h')
    habit = {
        'id': hid, 'name': name, 'schedule': schedule,
        'duration_minutes': mins, 'reminder_time': '',
        'streak': 0, 'longest_streak': 0, 'attached_tasks': []
    }
    data['habits'].append(habit)
    save('habits.json', data)
    return f'✓ 已添加习惯: [{hid}] {name} ({typ}, {mins}分钟)'


def done_habit(args):
    if not args:
        return '用法: done-habit <关键词>'
    kw = ' '.join(args).lower()
    data = load('habits.json')
    today_str = date.today().isoformat()

    matched = [h for h in data.get('habits', []) if kw in h.get('name', '').lower()]
    if not matched:
        return f'未找到匹配「{kw}」的习惯'
    if len(matched) > 1:
        return '\n'.join([f'  [{h["id"]}] {h["name"]}' for h in matched])

    h = matched[0]
    data.setdefault('logs', {})
    data['logs'].setdefault(today_str, {})
    data['logs'][today_str][h['id']] = {'completed': True, 'completed_at': now_iso()}
    h['streak'] = h.get('streak', 0) + 1
    if h['streak'] > h.get('longest_streak', 0):
        h['longest_streak'] = h['streak']
    save('habits.json', data)
    return f'✓ {h["name"]} 今日完成！连续 {h["streak"]} 天 🔥'


def edit_habit(args):
    if len(args) < 3:
        return '用法: edit-habit <id> <字段> <新值>\n字段: name/type/mins'
    hid, field, value = args[0], args[1], ' '.join(args[2:])
    data = load('habits.json')

    target = None
    for h in data.get('habits', []):
        if h['id'] == hid:
            target = h
            break
    if not target:
        return f'未找到 [{hid}]'

    if field == 'name':
        target['name'] = value
    elif field == 'mins':
        target['duration_minutes'] = int(value)
    elif field == 'type':
        try:
            typ, val = value.split('/', 1)
            if typ == 'daily':
                target['schedule'] = {'type': 'daily', 'times_per_day': int(val)}
            elif typ == 'weekly':
                target['schedule'] = {'type': 'weekly', 'days': [int(d) for d in val.split(',')]}
            elif typ == 'monthly':
                target['schedule'] = {'type': 'monthly', 'value': int(val)}
        except:
            return f'格式错误: {value}'
    else:
        return f'无效字段: {field}（可用: name/type/mins）'

    save('habits.json', data)
    return f'✏ [{hid}] 已更新'


def status(_=None):
    t = load('tasks.json')
    h = load('habits.json')
    c = load('courses.json')
    pending = len([x for x in t.get('tasks', []) if x.get('status') == 'pending'])
    habits = len(h.get('habits', []))
    courses = len(c.get('courses', []))
    return f'📋 作业: {pending} 待办 | 🔄 习惯: {habits} 项 | 📚 课程: {courses} 门'


# ============== MAIN ==============

HANDLERS = {
    'add-task': add_task,
    'done': mark_done,
    'undo': mark_undo,
    'edit-task': edit_task,
    'remove-task': remove_task,
    'today': lambda a: show_today(),
    'tasks': lambda a: list_tasks(False),
    'tasks-all': lambda a: list_tasks(True),
    'courses': list_courses_cmd,
    'add-habit': add_habit,
    'done-habit': done_habit,
    'edit-habit': edit_habit,
    'status': status,
}

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip())
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    if cmd in HANDLERS:
        try:
            result = HANDLERS[cmd](rest)
            print(result)
        except Exception as e:
            print(f'错误: {e}')
            import traceback
            traceback.print_exc()
    else:
        print(f'未知命令: {cmd}\n可用: {", ".join(HANDLERS.keys())}')
def remove_task(args):
    if not args:
        return '用法: remove-task <id> — 删除作业（彻底删除）'
    tid = args[0]
    data = load('tasks.json')
    data.setdefault('tasks', [])
    data.setdefault('archived', [])
    for lst in [data['tasks'], data['archived']]:
        for i, t in enumerate(lst):
            if t['id'] == tid:
                removed = lst.pop(i)
                save('tasks.json', data)
                return f'🗑 已删除: [{tid}] {removed["title"]}'
    return f'未找到 [{tid}]'



