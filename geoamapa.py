# ================================
# GEOAMAPA.PY
# ================================

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QComboBox
)

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRectangle, QgsFeatureRequest,
    QgsDataSourceUri, QgsFeature, QgsGeometry, QgsDistanceArea
)

RESULT_LAYER_PREFIX = "GeoAmapá - "
MAX_FEATURES = 2000
MAX_AREA_KM2 = 10000

CAR_WFS_BASE = "https://geoserver.car.gov.br/geoserver/sicar/ows"
CAR_TYPENAME = "sicar:sicar_imoveis_ap"
INCRA_OGC_BASE = "http://acervofundiario.incra.gov.br/i3geo/ogc.php"


# ================================
# DIALOG
# ================================
class GeoAmapaDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("GeoAmapá")
        self.setMinimumWidth(640)

        self._last_extent_project = None

        plugin_dir = os.path.dirname(__file__)
        gpkg_path = os.path.join(plugin_dir, "dados", "geoamapa_bases.gpkg")

        # BASES
        self._bases = {

            # LOCAIS
            "Terra Indígena": {"tipo": "gpkg", "path": gpkg_path, "layer": "terra-indigena"},
            "Unidades de Conservação": {"tipo": "gpkg", "path": gpkg_path, "layer": "uc"},
            "Assentamentos": {"tipo": "gpkg", "path": gpkg_path, "layer": "assentamentos"},
            "Direito Minerário": {"tipo": "gpkg", "path": gpkg_path, "layer": "direito_minerario"},

            # CAR
            "CAR (AP)": {"tipo": "wfs", "url": CAR_WFS_BASE, "typename": CAR_TYPENAME},

            # INCRA
            "SIGEF particular - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=certificada_sigef_particular_ap", "typename": "certificada_sigef_particular_ap"},
            "SIGEF público - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=certificada_sigef_publico_ap", "typename": "certificada_sigef_publico_ap"},
            "Imóveis certificados privado - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=imoveiscertificados_privado_ap", "typename": "imoveiscertificados_privado_ap"},
            "Imóveis certificados público - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=imoveiscertificados_publico_ap", "typename": "imoveiscertificados_publico_ap"},
            "ParcelaGeo - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=parcelageo_ap", "typename": "parcelageo_ap"},
            "Reconhecimento - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=reconhecimento_ap", "typename": "reconhecimento_ap"},
            "Quilombolas - INCRA": {"tipo": "wfs", "url": f"{INCRA_OGC_BASE}?tema=quilombolas_ap", "typename": "quilombolas_ap"},
        }

        # UI
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Retângulo (extensão atual do mapa):"))

        row = QHBoxLayout()
        self.edt_extent = QLineEdit()
        self.edt_extent.setReadOnly(True)
        row.addWidget(self.edt_extent)

        btn = QPushButton("Capturar")
        btn.clicked.connect(self.capture_extent)
        row.addWidget(btn)
        layout.addLayout(row)

        layout.addWidget(QLabel("Base:"))
        self.cmb_base = QComboBox()
        self.cmb_base.addItems(self._bases.keys())
        layout.addWidget(self.cmb_base)

        run_btn = QPushButton("Consultar")
        run_btn.clicked.connect(self.run_query)
        layout.addWidget(run_btn)

        self.lbl_status = QLabel("Status: pronto.")
        layout.addWidget(self.lbl_status)

    # CAPTURAR EXTENSÃO
    def capture_extent(self):
        canvas = self.iface.mapCanvas()
        ext = canvas.extent()
        self._last_extent_project = QgsRectangle(ext)

        self.edt_extent.setText(
            f"xMin={ext.xMinimum():.3f}, yMin={ext.yMinimum():.3f}, "
            f"xMax={ext.xMaximum():.3f}, yMax={ext.yMaximum():.3f}"
        )

    # CONSULTA
    def run_query(self):

        if not self._last_extent_project:
            QMessageBox.warning(self, "GeoAmapá", "Capture a extensão primeiro.")
            return

        # ------------------------------
        # VALIDA TAMANHO DA ÁREA
        # ------------------------------
        canvas = self.iface.mapCanvas()
        crs = canvas.mapSettings().destinationCrs()

        da = QgsDistanceArea()
        da.setSourceCrs(crs, QgsProject.instance().transformContext())
        da.setEllipsoid("GRS80")

        geom = QgsGeometry.fromRect(self._last_extent_project)
        area_km2 = da.measureArea(geom) / 1_000_000.0

        if area_km2 > MAX_AREA_KM2:
            QMessageBox.warning(
                self,
                "GeoAmapá",
                f"A área selecionada possui aproximadamente {area_km2:.0f} km².\n\n"
                "Aproxime mais o zoom para realizar a consulta."
            )
            return

        # ------------------------------

        base_selected = self.cmb_base.currentText()
        base_cfg = self._bases[base_selected]

        rect = self._last_extent_project

        if base_cfg["tipo"] == "gpkg":
            uri = f"{base_cfg['path']}|layername={base_cfg['layer']}"
            src_layer = QgsVectorLayer(uri, "tmp", "ogr")
        else:
            uri = QgsDataSourceUri()
            uri.setParam("url", base_cfg["url"])
            uri.setParam("typename", base_cfg["typename"])
            src_layer = QgsVectorLayer(uri.uri(False), "tmp", "WFS")

        if not src_layer.isValid():
            QMessageBox.critical(self, "GeoAmapá", f"Falha ao carregar a base selecionada.\n\nBase: {base_selected}")
            return

        req = QgsFeatureRequest().setFilterRect(rect).setLimit(MAX_FEATURES + 1)

        mem = QgsVectorLayer("MultiPolygon?crs=EPSG:4674", f"{RESULT_LAYER_PREFIX}{base_selected}", "memory")
        pr = mem.dataProvider()
        pr.addAttributes(src_layer.fields())
        mem.updateFields()

        feats = []
        for f in src_layer.getFeatures(req):
            nf = QgsFeature(mem.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes(f.attributes())
            feats.append(nf)

        # ------------------------------
        # SEM RESULTADO
        # ------------------------------
        if len(feats) == 0:
            QMessageBox.information(
                self,
                "GeoAmapá",
                f"Nenhuma feição encontrada para:\n{base_selected}\nna área selecionada."
            )
            return

        pr.addFeatures(feats)
        QgsProject.instance().addMapLayer(mem)

        self.lbl_status.setText(f"Feições encontradas: {len(feats)}")


# ================================
# PLUGIN
# ================================
class GeoAmapaPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "logo.png")
        self.action = QAction(QIcon(icon_path), "GeoAmapá", self.iface.mainWindow())
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu("GeoAmapá", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("GeoAmapá", self.action)
        self.iface.removeToolBarIcon(self.action)

    def open_dialog(self):
        self.dialog = GeoAmapaDialog(self.iface)
        self.dialog.show()
