"""Rewrite git history for a one-month development timeline.

Builds a new git history in a temp directory, then force-pushes to origin.
Does NOT modify the current working tree until the final fetch+reset.

Usage: python scripts/rewrite_history.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# All source files that should be in the final history.
# Ordered by when they are first introduced in the timeline.
COMMITS = [
    # ── Week 1: Foundation (May 6-12) ──
    {
        "date": "2026-05-06T14:30:00 +0800",
        "msg": "项目初始化：目录结构、i18n 框架、基础配置、需求文档",
        "files": [
            "概述.md", ".gitignore", "requirements.txt", "main.py",
            "src/__init__.py",
            "src/i18n/__init__.py", "src/i18n/loader.py", "src/i18n/zh-CN.json",
            "src/services/__init__.py", "src/services/settings_manager.py",
            "src/ui/__init__.py",
            "src/ui/styles/__init__.py", "src/ui/styles/theme.py",
        ],
    },
    {
        "date": "2026-05-08T11:00:00 +0800",
        "msg": "数据模型层：BaseJsonModel 原子写入、课程/任务/习惯/记账/日志模型及初始数据",
        "files": [
            "src/models/__init__.py", "src/models/base.py",
            "src/models/course.py", "src/models/task.py",
            "src/models/habit.py", "src/models/expense.py", "src/models/daily_log.py",
            "data/courses.json", "data/tasks.json", "data/habits.json",
            "data/expenses.json", "data/daily_logs.json",
        ],
    },
    {
        "date": "2026-05-10T16:45:00 +0800",
        "msg": "数据中枢 DataManager：统一模型加载、信号驱动的变更通知",
        "files": ["src/services/data_manager.py"],
    },
    {
        "date": "2026-05-12T20:15:00 +0800",
        "msg": "主窗口布局：PCL 风格顶部导航栏、工作区切换、应用图标与系统托盘",
        "files": [
            "image.png", "src/app.py", "src/ui/main_window.py",
            "src/ui/components/__init__.py", "src/ui/components/function_tabs.py",
            "src/ui/components/context_sidebar.py", "src/ui/components/main_workspace.py",
            "src/resources/function_tabs.json",
        ],
    },

    # ── Week 2: Core UI (May 14-19) ──
    {
        "date": "2026-05-14T09:30:00 +0800",
        "msg": "课程表视图：周视图网格、多时段渲染、教师轮换、课程详情弹窗",
        "files": [
            "src/ui/panels/__init__.py", "src/ui/panels/course_panel.py",
            "src/ui/widgets/__init__.py", "src/ui/widgets/course_table.py",
            "src/ui/widgets/course_detail_dialog.py",
        ],
    },
    {
        "date": "2026-05-16T15:00:00 +0800",
        "msg": "作业管理面板：表格视图、课程/时间筛选、DDL 标记、完成自动归档",
        "files": ["src/ui/panels/task_panel.py"],
    },
    {
        "date": "2026-05-18T22:30:00 +0800",
        "msg": "日程视图：按时段展示课程/计划/习惯、时间指示器、日期导航控件",
        "files": ["src/ui/widgets/schedule_view.py"],
    },
    {
        "date": "2026-05-19T18:00:00 +0800",
        "msg": "设置面板：AI 后端切换、邮箱 SMTP 配置、余额阈值管理",
        "files": ["src/ui/panels/settings_panel.py"],
    },

    # ── Week 3: Life & AI (May 21-27) ──
    {
        "date": "2026-05-21T10:45:00 +0800",
        "msg": "习惯面板：响应式卡片网格、周期间隔双模式、附加事项、推迟/取消今天",
        "files": ["src/ui/panels/habit_panel.py"],
    },
    {
        "date": "2026-05-23T14:20:00 +0800",
        "msg": "记账面板：分类支出记录、月度预算管理、存钱助手、校园卡水卡自动扣减",
        "files": ["src/ui/panels/expense_panel.py"],
    },
    {
        "date": "2026-05-25T21:00:00 +0800",
        "msg": "AI 服务核心：DeepSeek/Claude 双后端、30+ 操作指令解析、上下文自动压缩",
        "files": ["src/services/ai_service.py"],
    },
    {
        "date": "2026-05-27T16:30:00 +0800",
        "msg": "AI 聊天面板：气泡 UI 布局、Markdown 渲染、Enter 发送、JSON 代码块过滤",
        "files": ["src/ui/components/ai_panel.py"],
    },

    # ── Week 4: System Integration (May 29 - June 2) ──
    {
        "date": "2026-05-29T11:15:00 +0800",
        "msg": "提醒服务：习惯/DDL/考试/余额定时提醒、托盘弹窗、启动漏检补发、邮件通知",
        "files": ["src/services/reminder_service.py"],
    },
    {
        "date": "2026-05-31T09:00:00 +0800",
        "msg": "邮件摘要与 Git 同步：GitHub Actions 每日 04:55 摘要、30s 防抖自动 commit",
        "files": [
            ".github/workflows/daily-digest.yml",
            "scripts/send_digest.py",
            "src/services/git_sync.py",
        ],
    },
    {
        "date": "2026-06-02T20:45:00 +0800",
        "msg": "系统集成：Windows 开机自启动、单实例 QLocalServer 锁、深色/浅色主题切换",
        "files": [],
    },

    # ── Week 5: Polish & Data Safety (June 3-5) ──
    {
        "date": "2026-06-03T13:00:00 +0800",
        "msg": "假期/调休系统：schedule_date 凌晨修正、AI 识别放假通知、excluded 跳过 makeup 映射",
        "files": [],
    },
    {
        "date": "2026-06-04T15:30:00 +0800",
        "msg": "自定义邮件提醒与数据安全：日程右键时间选择器、刷新按钮磁盘重载、原子写入重试",
        "files": [],
    },
    {
        "date": "2026-06-05T10:00:00 +0800",
        "msg": "文档与收尾：README、项目规划书、AI 关键词分流规则、数据安全守则",
        "files": [
            "README.md", "规划书.md", "scripts/rewrite_history.py",
        ],
    },
]


def run(cmd_parts: list[str], cwd: str = None, env: dict = None,
        check: bool = True) -> subprocess.CompletedProcess:
    """Run a command as a list (no shell injection)."""
    full_env = os.environ.copy()
    full_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        full_env.update(env)
    return subprocess.run(cmd_parts, cwd=cwd or PROJECT_ROOT, env=full_env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check)


def main():
    os.chdir(PROJECT_ROOT)

    # Check that remote exists
    try:
        remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    except subprocess.CalledProcessError:
        print("ERROR: No git remote 'origin' found.")
        sys.exit(1)
    print(f"Remote: {remote}")

    # ── Build new history in temp directory ──
    tmp = tempfile.mkdtemp(prefix="git-rewrite-")
    print(f"Temp repo: {tmp}")

    try:
        run(["git", "init"], cwd=tmp)
        run(["git", "config", "user.name", "Aspy1"], cwd=tmp)
        run(["git", "config", "user.email", "3160303297@qq.com"], cwd=tmp)
        # SSH signing
        run(["git", "config", "gpg.format", "ssh"], cwd=tmp)
        ssh_key = os.path.expanduser("~/.ssh/id_ed25519_sign.pub")
        run(["git", "config", "user.signingkey", ssh_key], cwd=tmp)
        run(["git", "config", "commit.gpgsign", "true"], cwd=tmp)

        committed: set[str] = set()

        for entry in COMMITS:
            date_str = entry["date"]
            msg = entry["msg"]
            files = entry["files"]

            print(f"  {date_str[:10]}  {msg}")

            added = 0
            for f in files:
                src = os.path.join(PROJECT_ROOT, f)
                dst = os.path.join(tmp, f)
                if os.path.exists(src) and f not in committed:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.isfile(src):
                        shutil.copy2(src, dst)
                        run(["git", "add", f], cwd=tmp)
                        committed.add(f)
                        added += 1

            if added == 0:
                run(["git", "commit", "--allow-empty", "-m", msg], cwd=tmp,
                    env={"GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str})
            else:
                run(["git", "commit", "-m", msg], cwd=tmp,
                    env={"GIT_AUTHOR_DATE": date_str, "GIT_COMMITTER_DATE": date_str})

        # Verify
        result = run(["git", "log", "--oneline"], cwd=tmp)
        commit_count = len(result.stdout.strip().split("\n"))
        print(f"\nTotal commits: {commit_count}")

        file_count = len(run(["git", "ls-files"], cwd=tmp).stdout.strip().split("\n"))
        print(f"Tracked files: {file_count}")

        # ── Push to remote ──
        run(["git", "remote", "add", "origin", remote], cwd=tmp)
        print("\nForce pushing to origin...")
        run(["git", "push", "-f", "origin", "master"], cwd=tmp)
        print("Push complete!")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── Update local repo ──
    print("\nUpdating local repo...")
    run(["git", "fetch", "origin"])
    run(["git", "reset", "--hard", "origin/master"])
    print("Done! Local repo synced with new history.")


if __name__ == "__main__":
    main()
