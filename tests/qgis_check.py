r"""Headless QGIS (PyQGIS) test of the WMTS service: load all layers via GetCapabilities, render, identify values.

Run with the Python that ships with QGIS, e.g.:
    "C:\Program Files\QGIS 3.40.9\bin\python-qgis-ltr.bat" tests\qgis_check.py
"""
import os
import sys

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsMapRendererParallelJob,
                       QgsMapSettings, QgsPointXY, QgsProject, QgsRasterLayer, QgsRaster, QgsRectangle)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
BASE = "http://localhost:8081/geoserver/gwc/service/wmts"
CAPS = BASE + "?REQUEST=GetCapabilities&SERVICE=WMTS&VERSION=1.0.0"

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", r"C:\Program Files\QGIS 3.40.9\apps\qgis-ltr"), True)
app = QgsApplication([], False)
app.initQgis()


def wmts_layer(layer, matrixset, fmt="image/png", style=""):
    uri = (f"contextualWMSLegend=0&crs=EPSG:{matrixset.split(':')[1] if matrixset != 'EPSG:900913' else '3857'}"
           f"&dpiMode=7&featureCount=10&format={fmt}&layers={layer}&styles={style}"
           f"&tileMatrixSet={matrixset}&url={CAPS}")
    return QgsRasterLayer(uri, layer, "wms")


results = []
def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


# 1. every layer loads through WMTS in QGIS (EPSG:3857 matrix set)
LAYERS = ["bhoonidhi:bs_hh_c95", "bhoonidhi:bs_hh_c96", "bhoonidhi:bs_hh_c97", "bhoonidhi:bs_hv_c95", "bhoonidhi:bs_hv_c96",
          "bhoonidhi:bs_hv_c97", "bhoonidhi:ws_c95", "bhoonidhi:ws_c96", "bhoonidhi:ws_c97", "bhoonidhi:wschange_c95_c97"]
loaded = {}
for L in LAYERS:
    lyr = wmts_layer(L, "EPSG:3857")
    check(f"load {L} (EPSG:3857)", lyr.isValid(), lyr.error().summary() if not lyr.isValid() else lyr.crs().authid())
    if lyr.isValid():
        loaded[L] = lyr

# 2. the EPSG:4326 matrix set also works
lyr4326 = wmts_layer("bhoonidhi:bs_hh_c97", "EPSG:4326")
check("load bs_hh_c97 (EPSG:4326 matrix set)", lyr4326.isValid(), lyr4326.crs().authid() if lyr4326.isValid() else lyr4326.error().summary())

# 3. render a map with the radar layer and the change layer on top (Nagarjuna Sagar), save as PNG
if "bhoonidhi:bs_hh_c97" in loaded and "bhoonidhi:wschange_c95_c97" in loaded:
    proj = QgsProject.instance()
    for L in ("bhoonidhi:bs_hh_c97", "bhoonidhi:wschange_c95_c97"):
        proj.addMapLayer(loaded[L])
    ms = QgsMapSettings()
    ms.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
    ll = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), QgsCoordinateReferenceSystem("EPSG:3857"), proj)
    ms.setExtent(ll.transformBoundingBox(QgsRectangle(78.9, 16.2, 79.6, 16.8)))
    ms.setOutputSize(QSize(1100, 900))
    ms.setBackgroundColor(QColor("white"))
    ms.setLayers([loaded["bhoonidhi:wschange_c95_c97"], loaded["bhoonidhi:bs_hh_c97"]])
    job = QgsMapRendererParallelJob(ms)
    job.start()
    job.waitForFinished()
    img = job.renderedImage()
    path = os.path.join(OUT, "qgis_render.png")
    img.save(path, "PNG")
    # count non-white pixels as a sanity check that tiles really arrived
    non_white = sum(1 for x in range(0, img.width(), 7) for y in range(0, img.height(), 7) if img.pixelColor(x, y).name() != "#ffffff")
    check("render map from WMTS in QGIS", non_white > 500, f"{non_white} non-white sample pixels -> {path}")

# 4. identify (WMTS GetFeatureInfo through QGIS): open water vs land, HH backscatter cycle 97
lyr = loaded.get("bhoonidhi:bs_hh_c97")
if lyr:
    t = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), lyr.crs(), QgsProject.instance())
    for name, (lon, lat), lo, hi in (("open water", (79.22292, 16.96458), -35, -15), ("land", (79.8, 16.2), -16, -3)):
        pt = t.transform(QgsPointXY(lon, lat))
        ident = lyr.dataProvider().identify(pt, QgsRaster.IdentifyFormatText,
                                            QgsRectangle(pt.x() - 20, pt.y() - 20, pt.x() + 20, pt.y() + 20), 50, 50, 96)
        txt = str(ident.results()) if ident.isValid() else "identify failed"
        import re
        m = re.search(r"-?\d+\.\d+", txt)
        val = float(m.group()) if m else None
        check(f"identify {name} via GetFeatureInfo", val is not None and lo <= val <= hi, f"value={val}")

print(f"\nQGIS {__import__('qgis.core').core.Qgis.version()}: {sum(results)}/{len(results)} checks passed")
app.exitQgis()
sys.exit(0 if all(results) else 1)
