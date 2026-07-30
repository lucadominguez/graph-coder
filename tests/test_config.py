from graph_coder.config import atomic_write, ensure_layout, load_config


def test_defaults_create_agent_planning_layout(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.storage_dir == tmp_path / ".graph-coder"
    assert cfg.database_path.name == "state.db"
    assert cfg.config_path == tmp_path / ".graph-coder" / "config.toml"
    ensure_layout(cfg)
    assert cfg.storage_dir.is_dir()
    assert cfg.snapshots_dir.is_dir()
    assert cfg.cache_dir.is_dir()
    assert cfg.projections_dir.is_dir()
    assert cfg.context_dir.is_dir()
    assert cfg.artifacts_dir.is_dir()


def test_toml_overrides_and_windows_like_path(tmp_path):
    cfg_file = tmp_path / ".graph-coder.toml"
    cfg_file.write_text(
        '[storage]\ndatabase="custom.db"\n[sqlite]\nbusy_timeout_ms=123\n[recovery]\npacket_event_limit=3\n',
        encoding="utf-8",
    )
    cfg = load_config("C:/workspace/project", cfg_file)
    assert str(cfg.root).replace("\\", "/").endswith("C:/workspace/project")
    assert cfg.database_path.name == "custom.db"
    assert cfg.busy_timeout_ms == 123
    assert cfg.packet_event_limit == 3


def test_atomic_write_replaces_file(tmp_path):
    path = tmp_path / ".graph-coder" / "snapshots" / "state.json"
    atomic_write(path, "one")
    atomic_write(path, "two")
    assert path.read_text(encoding="utf-8") == "two"
