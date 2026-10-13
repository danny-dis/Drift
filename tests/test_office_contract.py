from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / 'frontend' / 'src'


def test_office_can_be_mounted_in_the_actual_dashboard():
    panel = (FRONTEND / 'OfficePanel.tsx').read_text(encoding='utf-8')
    app = (FRONTEND / 'DriftApp.tsx').read_text(encoding='utf-8')
    assert 'OfficeCanvas' in panel
    assert 'connected' in panel
    assert '<OfficePanel' in app
    assert 'label: "Office"' in app
    assert 'useState<Tab>("inbox")' in app


def test_legacy_gameworld_keeps_snapshot_and_prop_compatibility():
    world = (FRONTEND / 'GameWorld.tsx').read_text(encoding='utf-8')
    assert 'GameWorldHandle' in world
    assert 'forwardRef' in world
    assert 'OfficeCanvas' in world
    canvas = (FRONTEND / 'office' / 'OfficeCanvas.tsx').read_text(encoding='utf-8')
    assert 'snapshot:' in canvas
    assert 'toDataURL' in canvas
    assert 'dispose()' in canvas


def test_office_animation_is_optional_and_pauses_when_unobserved():
    panel = (FRONTEND / 'OfficePanel.tsx').read_text(encoding='utf-8')
    renderer = (FRONTEND / 'office' / 'renderer.ts').read_text(encoding='utf-8')
    assert 'useState(false)' in panel
    assert 'prefers-reduced-motion' in renderer
    assert 'document.hidden' in renderer
    assert 'IntersectionObserver' in renderer
    assert 'cancelAnimationFrame' in renderer
    assert 'Math.min(2, window.devicePixelRatio' in renderer
    assert 'ResizeObserver' in renderer


def test_office_does_not_fabricate_workers_or_fetch_private_data():
    panel = (FRONTEND / 'OfficePanel.tsx').read_text(encoding='utf-8')
    assert 'fetch(' not in panel
    assert 'Backend status unavailable' in panel
    assert 'illustrative' in panel
