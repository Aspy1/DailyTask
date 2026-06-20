---
name: life-assistant-data
description: Use when the user asks to add/query/modify tasks, habits, courses, expenses, or schedule plans. Directly read/write JSON files in data/.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [data, json, file-io, life-assistant]
---

# Life Assistant Data Bridge

Direct file I/O to the 生活助手 desktop app's JSON data store. All paths are absolute under `data/`.

## Data Files

| File | Purpose |
|------|---------|
| `tasks.json` | Assignments: id, title, course_name, due_date, status (pending/completed) |
| `habits.json` | Daily habits: id, name, schedule (type/days/value), duration_minutes |
| `courses.json` | Courses: id, name, day_of_week, time_slots, location, weeks |
| `expenses.json` | Expenses: records with amount, category, date, note |
| `daily_logs.json` | Schedule plans: plans by date |
| `settings.ini` | App config: theme, language, AI model, email, balance |

## Operations

### Read data
Use `read_file` to read any JSON file. Always read before writing to see current state.

Example: `read_file("data/tasks.json")`

### Add a task
1. Read `tasks.json` first
2. Generate a unique ID: find max existing number, increment. Check both `tasks` and `archived` arrays.
3. Add new entry to `tasks` array
4. Use `execute_code` with Python `json.load` / `json.dump` to write back
5. The desktop app auto-reloads every 3 seconds

Task structure:
```json
{
  "id": "t_010",
  "title": "作业名称",
  "course_name": "课程名",
  "due_date": "2026-06-10T23:00:00",
  "status": "pending",
  "priority": "medium",
  "tags": [],
  "notes": "",
  "created_at": "2026-06-06T12:00:00.000000",
  "reminded": false
}
```

### Mark task complete
1. Read `tasks.json`
2. Find task by id
3. Set `status` to `"completed"` and `completed_at` to current ISO timestamp
4. Write back

### Add a habit
1. Read `habits.json`
2. Generate unique ID (h_001, h_002, etc.)
3. Habit structure:
```json
{
  "id": "h_001",
  "name": "习惯名",
  "schedule": {"type": "daily", "times_per_day": 1},
  "duration_minutes": 30,
  "reminder_time": "",
  "streak": 0,
  "longest_streak": 0,
  "attached_tasks": []
}
```
Schedule types:
- `{"type": "daily", "times_per_day": 1}` — every day, N times
- `{"type": "weekly", "days": [1,3,5]}` — specific weekdays (1=Mon)
- `{"type": "monthly", "value": 4}` — N times per month

### Log habit done
1. Read `habits.json`
2. In `logs` dict, under today's date, set habit_id to `{"completed": true, "completed_at": "<ISO>"}`
3. Increment streak

### Add expense
```json
{
  "amount": 24.5,
  "category": "餐饮",
  "note": "午餐",
  "date": "2026-06-06T12:00:00"
}
```
Categories: 餐饮, 交通, 购物, 娱乐, 学习, 其他

### Query today
Read `tasks.json` (pending tasks), `habits.json` (active today + done status), `courses.json` (today's courses).

## Important Rules

- **Always use absolute paths**: `data/xxx.json`
- **Always read before write** to avoid overwriting concurrent changes
- **Generate unique IDs** by scanning all existing IDs (including archived)
- **Use Python in execute_code** for JSON manipulation
- **Double-check due_date format**: `YYYY-MM-DDTHH:MM:SS`
- **The desktop app reloads automatically** within 3 seconds of file change
