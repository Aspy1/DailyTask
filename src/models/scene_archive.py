"""场景存档模型 - 支持多场景切换（学期、在校/在家等）"""

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.base import BaseJsonModel


class SceneArchive(BaseJsonModel):
    """场景存档管理器

    支持：
    - 多场景（不同学期、在家/在校等）
    - 完整数据存档（ZIP 压缩）
    - 场景切换（切换当前活跃场景）
    """

    def __init__(self, data_dir: Path, archive_dir: Path | None = None):
        self._data_dir = Path(data_dir)
        self._archive_dir = archive_dir or self._data_dir / "archives"
        self._archive_dir.mkdir(parents=True, exist_ok=True)

        # 元数据文件
        self._meta_file = self._data_dir / "scenes_meta.json"
        self._init_meta()

        super().__init__(self._meta_file)

    def _init_meta(self) -> None:
        """初始化元数据文件"""
        if not self._meta_file.exists():
            self._save({
                "current_scene": "default",
                "scenes": {
                    "default": {
                        "id": "default",
                        "name": "默认场景",
                        "scene_type": "semester",  # semester | location
                        "description": "默认场景",
                        "created_at": datetime.now().isoformat(),
                        "is_active": True,
                    }
                }
            })

    def load(self) -> dict[str, Any]:
        return self._load()

    def _load(self) -> dict:
        """加载元数据"""
        if self._meta_file.exists():
            with open(self._meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"current_scene": "default", "scenes": {}}

    def _save(self, data: dict) -> None:
        """保存元数据"""
        with open(self._meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 场景管理 ──────────────────────────────────────────

    def get_current_scene_id(self) -> str:
        """获取当前场景 ID"""
        data = self._load()
        return data.get("current_scene", "default")

    def get_current_scene(self) -> dict:
        """获取当前场景信息"""
        scenes = self._load().get("scenes", {})
        current_id = self.get_current_scene_id()
        return scenes.get(current_id, {"id": "default", "name": "默认场景"})

    def get_location(self) -> dict[str, float]:
        """获取当前场景的经纬度"""
        scene = self.get_current_scene()
        loc = scene.get("location", {})
        return {
            "lat": float(loc.get("lat", 31.23)),
            "lon": float(loc.get("lon", 121.47)),
        }

    def set_location(self, lat: float, lon: float) -> None:
        """设置当前场景的经纬度"""
        data = self._load()
        current_id = self.get_current_scene_id()
        if current_id in data["scenes"]:
            data["scenes"][current_id]["location"] = {"lat": lat, "lon": lon}
            self._save(data)

    def list_scenes(self) -> list[dict]:
        """列出所有场景"""
        data = self._load()
        return list(data.get("scenes", {}).values())

    def create_scene(
        self,
        name: str,
        scene_type: str = "semester",
        description: str = "",
        copy_from: str | None = None,
    ) -> str:
        """创建新场景

        Args:
            name: 场景名称（如 "2024秋季学期"、"在家"）
            scene_type: 场景类型（semester/location）
            description: 描述
            copy_from: 从哪个场景复制数据（可选）

        Returns:
            新场景 ID
        """
        scene_id = f"scene_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        data = self._load()

        # 如果指定了复制源，复制数据
        if copy_from and copy_from in data["scenes"]:
            src_scene_dir = self._archive_dir / copy_from
            dst_scene_dir = self._archive_dir / scene_id
            if src_scene_dir.exists():
                shutil.copytree(src_scene_dir, dst_scene_dir)

        # 创建场景元数据
        data["scenes"][scene_id] = {
            "id": scene_id,
            "name": name,
            "scene_type": scene_type,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "is_active": False,
        }
        self._save(data)

        return scene_id

    def switch_scene(self, scene_id: str) -> bool:
        """切换到指定场景

        Args:
            scene_id: 目标场景 ID

        Returns:
            是否切换成功
        """
        data = self._load()
        if scene_id not in data["scenes"]:
            return False

        # 切换前保存当前场景数据
        self.save_current_scene()

        # 更新当前场景
        data["current_scene"] = scene_id
        for sid, scene in data["scenes"].items():
            scene["is_active"] = (sid == scene_id)
        self._save(data)

        # 切换后加载新场景数据
        self.load_scene(scene_id)
        return True

    def delete_scene(self, scene_id: str) -> bool:
        """删除场景（不能删除当前场景）"""
        if scene_id == self.get_current_scene_id():
            return False

        data = self._load()
        if scene_id not in data["scenes"]:
            return False

        # 删除场景目录
        scene_dir = self._archive_dir / scene_id
        if scene_dir.exists():
            shutil.rmtree(scene_dir)

        # 删除元数据
        del data["scenes"][scene_id]
        self._save(data)
        return True

    # ── 数据存档 ──────────────────────────────────────────

    def save_current_scene(self) -> None:
        """保存当前场景的完整数据到存档目录"""
        current_id = self.get_current_scene_id()
        scene_dir = self._archive_dir / current_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        # 复制所有数据文件到场景目录
        data_files = [
            "tasks.json",
            "habits.json",
            "courses.json",
            "exams.json",
            "expenses.json",
            "inventory.json",
        ]

        for filename in data_files:
            src = self._data_dir / filename
            if src.exists():
                shutil.copy2(src, scene_dir / filename)

    def load_scene(self, scene_id: str) -> None:
        """加载指定场景的数据文件到 data 目录"""
        if scene_id == self.get_current_scene_id():
            return  # 已经是当前场景

        scene_dir = self._archive_dir / scene_id
        if not scene_dir.exists():
            return

        # 复制存档文件回 data 目录
        for json_file in scene_dir.glob("*.json"):
            shutil.copy2(json_file, self._data_dir / json_file.name)

    def export_scene_archive(self, scene_id: str, export_path: Path) -> bool:
        """导出场景为 ZIP 压缩包"""
        scene_dir = self._archive_dir / scene_id
        if not scene_dir.exists():
            return False

        try:
            with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for json_file in scene_dir.glob("*.json"):
                    zf.write(json_file, json_file.name)
            return True
        except Exception:
            return False

    def import_scene_archive(self, archive_path: Path, new_name: str) -> str | None:
        """从 ZIP 压缩包导入场景

        Args:
            archive_path: ZIP 文件路径
            new_name: 新场景名称

        Returns:
            新场景 ID，失败返回 None
        """
        try:
            # 创建临时目录解压
            temp_dir = self._archive_dir / "_import_temp"
            temp_dir.mkdir(exist_ok=True)

            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(temp_dir)

            # 创建新场景
            scene_id = self.create_scene(new_name)

            # 移动文件到场景目录
            scene_dir = self._archive_dir / scene_id
            for json_file in temp_dir.glob("*.json"):
                shutil.copy2(json_file, scene_dir / json_file.name)

            # 清理临时目录
            shutil.rmtree(temp_dir)

            return scene_id
        except Exception:
            return None

    # ── 学期管理辅助 ──────────────────────────────────────

    def quick_create_semester(self, year: int, semester: int) -> str:
        """快速创建学期场景

        Args:
            year: 年份
            semester: 学期（1=上学期，2=下学期）

        Returns:
            场景 ID
        """
        semester_name = f"{year}年{'上' if semester == 1 else '下'}学期"
        return self.create_scene(
            name=semester_name,
            scene_type="semester",
            description=f"学期存档 {semester_name}",
        )

    def quick_create_location(self, location: str) -> str:
        """快速创建位置场景

        Args:
            location: 位置名称（如 "在家"、"在校"）

        Returns:
            场景 ID
        """
        return self.create_scene(
            name=location,
            scene_type="location",
            description=f"位置场景 {location}",
        )
