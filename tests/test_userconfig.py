"""单元测试：用户配置管理 (userconfig.py)"""

import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src import userconfig


class TestLoadEnvFile:
    """测试 load_env_file() 配置读取"""

    def test_empty_file(self, tmp_path):
        """空文件返回空字典"""
        f = tmp_path / ".env"
        f.write_text("")
        assert userconfig.load_env_file(f) == {}

    def test_missing_file(self, tmp_path):
        """不存在的文件返回空字典"""
        f = tmp_path / "nonexistent.env"
        assert userconfig.load_env_file(f) == {}

    def test_key_value(self, tmp_path):
        """解析 KEY=VALUE 格式"""
        f = tmp_path / ".env"
        f.write_text('OPENAI_API_KEY="sk-test123"\nMODEL=gpt-4\n')
        result = userconfig.load_env_file(f)
        assert result["OPENAI_API_KEY"] == "sk-test123"
        assert result["MODEL"] == "gpt-4"

    def test_export_prefix(self, tmp_path):
        """解析 export KEY=VALUE 格式"""
        f = tmp_path / ".env"
        f.write_text('export OPENAI_API_KEY="sk-test"\n')
        result = userconfig.load_env_file(f)
        assert result["OPENAI_API_KEY"] == "sk-test"

    def test_skip_comments_and_blanks(self, tmp_path):
        """跳过注释行和空行"""
        f = tmp_path / ".env"
        f.write_text("# 这是注释\n\nKEY=val\n")
        result = userconfig.load_env_file(f)
        assert "KEY" in result
        assert len(result) == 1

    def test_trim_quotes(self, tmp_path):
        """去掉值的引号"""
        f = tmp_path / ".env"
        f.write_text('A="double"\nB=\'single\'\nC=bare\n')
        result = userconfig.load_env_file(f)
        assert result["A"] == "double"
        assert result["B"] == "single"
        assert result["C"] == "bare"

    def test_malformed_line(self, tmp_path):
        """不完整 KEY= 行被忽略"""
        f = tmp_path / ".env"
        f.write_text("NOT_A_VALID_LINE\nKEY=val\n")
        result = userconfig.load_env_file(f)
        assert "KEY" in result
        assert len(result) == 1


class TestSaveEnvFile:
    """测试 save_env_file() 配置写入"""

    def test_save_new_file(self, tmp_path):
        """保存到新文件"""
        target = tmp_path / "new.env"
        userconfig.save_env_file({"KEY": "value"}, target)
        content = target.read_text().strip()
        assert 'KEY="value"' in content
        # 权限检查
        assert oct(os.stat(target).st_mode & 0o777) == "0o600"

    def test_update_existing_key(self, tmp_path):
        """更新已有 key，保留注释和其他行"""
        target = tmp_path / "env"
        target.write_text("# 注释行\nOLD=before\nOTHER=keep\n")
        userconfig.save_env_file({"OLD": "after"}, target)
        content = target.read_text()
        assert "# 注释行\n" in content
        assert 'OLD="after"' in content
        assert "OTHER=keep" in content  # 未修改的行保留原格式

    def test_preserve_export_prefix(self, tmp_path):
        """保留原行的 export 前缀"""
        target = tmp_path / "env"
        target.write_text('export KEY=old\n')
        userconfig.save_env_file({"KEY": "new"}, target)
        content = target.read_text()
        assert 'export KEY="new"' in content

    def test_add_new_keys(self, tmp_path):
        """新 key 添加到末尾"""
        target = tmp_path / "env"
        target.write_text("EXISTING=val\n")
        userconfig.save_env_file({"EXISTING": "v1", "NEW": "v2"}, target)
        content = target.read_text()
        assert 'EXISTING="v1"' in content
        assert 'NEW="v2"' in content

    def test_add_header(self, tmp_path):
        """添加文件头"""
        target = tmp_path / "env"
        header = "# 配置头\n# 第二行"
        userconfig.save_env_file({"KEY": "val"}, target, header=header)
        content = target.read_text()
        assert content.startswith(header)

    def test_ensure_dir_created(self, tmp_path):
        """自动创建目录"""
        target = tmp_path / "newdir" / "subdir" / "env"
        assert not target.parent.exists()
        userconfig.save_env_file({"KEY": "val"}, target)
        assert target.exists()

    def test_permission_600(self, tmp_path):
        """保存后权限为 600"""
        target = tmp_path / "secure.env"
        userconfig.save_env_file({"KEY": "val"}, target)
        mode = os.stat(target).st_mode & 0o777
        assert mode == 0o600, f"expected 600, got {oct(mode)}"


class TestGetConfig:
    """测试 get_config() 配置合并"""

    def test_default_values(self):
        """无文件和环境变量时返回默认值"""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as td:
                # 确保用户文件不存在
                with patch.object(userconfig, "CONFIG_FILE", Path(td) / "nonexistent"):
                    cfg = userconfig.get_config()
                    assert cfg["OPENAI_MODEL"] == "deepseek-chat"
                    assert cfg["WECHAT_WINDOW_NAME"] == "微信"

    def test_env_overrides_default(self):
        """环境变量覆盖默认值"""
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4"}, clear=True):
            with tempfile.TemporaryDirectory() as td:
                with patch.object(userconfig, "CONFIG_FILE", Path(td) / "nonexistent"):
                    cfg = userconfig.get_config()
                    assert cfg["OPENAI_MODEL"] == "gpt-4"

    def test_file_overrides_default(self, tmp_path):
        """用户文件覆盖默认值"""
        env_file = tmp_path / "env"
        env_file.write_text('OPENAI_MODEL="from-file"\n')
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(userconfig, "CONFIG_FILE", env_file):
                cfg = userconfig.get_config()
                assert cfg["OPENAI_MODEL"] == "from-file"

    def test_env_overrides_file(self, tmp_path):
        """环境变量优先级高于用户文件"""
        env_file = tmp_path / "env"
        env_file.write_text('OPENAI_MODEL="from-file"\n')
        with patch.dict(os.environ, {"OPENAI_MODEL": "from-env"}, clear=True):
            with patch.object(userconfig, "CONFIG_FILE", env_file):
                cfg = userconfig.get_config()
                assert cfg["OPENAI_MODEL"] == "from-env"

    def test_all_keys_present(self):
        """返回的字典包含所有默认 key"""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as td:
                with patch.object(userconfig, "CONFIG_FILE", Path(td) / "nonexistent"):
                    cfg = userconfig.get_config()
                    for key in userconfig.DEFAULT_CONFIG:
                        assert key in cfg, f"缺少 key: {key}"


class TestGetConfigValue:
    """测试 get_config_value()"""

    def test_env_priority(self):
        """环境变量优先"""
        with patch.dict(os.environ, {"TEST_KEY": "env_val"}, clear=True):
            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "env"
                f.write_text('TEST_KEY="file_val"\n')
                with patch.object(userconfig, "CONFIG_FILE", f):
                    assert userconfig.get_config_value("TEST_KEY") == "env_val"

    def test_file_fallback(self, tmp_path):
        """无环境变量时读文件"""
        with patch.dict(os.environ, {}, clear=True):
            f = tmp_path / "env"
            f.write_text('TEST_KEY="file_val"\n')
            with patch.object(userconfig, "CONFIG_FILE", f):
                assert userconfig.get_config_value("TEST_KEY") == "file_val"

    def test_default_fallback(self):
        """都不存在时返回默认值"""
        with patch.dict(os.environ, {}, clear=True):
            with tempfile.TemporaryDirectory() as td:
                with patch.object(userconfig, "CONFIG_FILE", Path(td) / "nonexistent"):
                    assert userconfig.get_config_value("UNDEFINED_KEY", "fallback") == "fallback"


class TestMaskKey:
    """测试 mask_key()"""

    def test_empty(self):
        assert userconfig.mask_key("") == "(未设置)"

    def test_short_key(self):
        """短 key 全部显示后加 ****"""
        assert userconfig.mask_key("abc") == "abc****"

    def test_long_key_masked(self):
        result = userconfig.mask_key("sk-test-api-key-12345")
        assert result.startswith("sk-t")
        assert "..." in result
        assert result.endswith("2345")

    def test_custom_visible_chars(self):
        result = userconfig.mask_key("abcdefgh", visible_chars=2)
        assert result == "ab****"


class TestEnsureConfigDir:
    """测试 ensure_config_dir()"""

    def test_creates_dir(self, tmp_path):
        with patch.object(userconfig, "CONFIG_DIR", tmp_path / "newcfg"):
            assert not (tmp_path / "newcfg").exists()
            userconfig.ensure_config_dir()
            assert (tmp_path / "newcfg").is_dir()

    def test_existing_dir(self, tmp_path):
        with patch.object(userconfig, "CONFIG_DIR", tmp_path / "existing"):
            (tmp_path / "existing").mkdir()
            userconfig.ensure_config_dir()  # 不抛异常