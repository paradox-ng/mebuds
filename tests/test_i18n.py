import re
import xml.etree.ElementTree as ET
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "mebuds" / "data" / "i18n"
PLACEHOLDER = re.compile(r"\{\w+\}")


def test_every_language_is_complete_and_compiled():
    files = sorted(I18N.glob("mebuds_*.ts"))
    assert len(files) >= 8
    for ts in files:
        assert ts.with_suffix(".qm").is_file(), f"{ts.name} isn't compiled"
        for msg in ET.parse(ts).getroot().iter("message"):
            tr = msg.find("translation")
            assert tr.get("type") != "unfinished", (ts.name, msg.findtext("source"))
            # {name}, {level}... must survive translation or .format() breaks.
            assert set(PLACEHOLDER.findall(msg.findtext("source"))) == set(
                PLACEHOLDER.findall(tr.text or "")
            ), (ts.name, msg.findtext("source"))


def test_catalan_loads(qapp):
    from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

    translator = QTranslator()
    assert translator.load(QLocale("ca"), "mebuds", "_", str(I18N))
    QCoreApplication.installTranslator(translator)
    try:
        assert QCoreApplication.translate("ControlWindow", "Equalizer") == "Equalitzador"
        assert QCoreApplication.translate("features", "Boost volume") == "Augmenta el volum"
    finally:
        QCoreApplication.removeTranslator(translator)
