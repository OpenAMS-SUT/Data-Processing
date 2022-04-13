import sys
# from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QMainWindow, QApplication
from PySide6.QtCharts import QChart, QChartView, QLineSeries
from svnparser import svn_buffer_parser


FILE = 'PBL_Badania_v1/Buffe_32.svn'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create series data
        self.series = QLineSeries()
        parser = svn_buffer_parser()
        parser.load(FILE)
        for n, d in enumerate(parser.get_data('main', 0)):
            self.series.append(n, d)

        # Make chart
        self.chart = QChart()
        self.chart.legend().hide()
        self.chart.addSeries(self.series)
        self.chart.createDefaultAxes()
        self.chart.setTitle(FILE + ' main ch0')

        self._chart_view = QChartView(self.chart)
        self._chart_view.setRenderHint(QPainter.Antialiasing)

        self.setCentralWidget(self._chart_view)



if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    window.resize(440, 300)
    sys.exit(app.exec())