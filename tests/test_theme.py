from pathlib import Path


def test_theme_applies_and_assets_exist(qapp):
    from mebuds import theme

    theme.apply(qapp)
    for colors in (theme.DARK, theme.LIGHT):
        css = theme._stylesheet(colors)
        for url in [part.split('")')[0] for part in css.split('url("')[1:]]:
            assert Path(url).is_file(), url
    assert "QTabBar::tab" in qapp.styleSheet()
