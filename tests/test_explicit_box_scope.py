from drift import main


def test_explicit_box_does_not_discover_or_start_other_persisted_organisms(monkeypatch):
    monkeypatch.setattr(main, '_discover_organisms', lambda: (_ for _ in ()).throw(AssertionError('Other boxes must stay untouched')))
    assert main.selected_organisms('explicit-owner-box') == {}


def test_normal_startup_preserves_existing_discovery(monkeypatch):
    existing = {'existing': object()}
    monkeypatch.setattr(main, '_discover_organisms', lambda: existing)
    assert main.selected_organisms('') is existing
