############################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# http://flatcam.org                                       #
# Author: Juan Pablo Caram (c)                             #
# Date: 2/5/2014                                           #
# MIT Licence                                              #
############################################################

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt
import FlatCAMApp
from camlib import *
from FlatCAMTool import FlatCAMTool
from ObjectUI import LengthEntry, RadioSet

from shapely.geometry import Polygon, LineString, Point, LinearRing, MultiLineString
from shapely.geometry import MultiPoint, MultiPolygon
from shapely.geometry import box as shply_box
from shapely.ops import cascaded_union, unary_union
import shapely.affinity as affinity
from shapely.wkt import loads as sloads
from shapely.wkt import dumps as sdumps
from shapely.geometry.base import BaseGeometry

from numpy import arctan2, Inf, array, sqrt, pi, ceil, sin, cos, sign, dot
from numpy.linalg import solve

from rtree import index as rtindex
from GUIElements import OptionalInputSection, FCCheckBox, FCEntry, FCEntry2, FCComboBox, FCTextAreaRich, \
    VerticalScrollArea, FCTable
from vispy.scene.visuals import Markers
from copy import copy
import freetype as ft


class BufferSelectionTool(FlatCAMTool):
    """
    Simple input for buffer distance.
    """

    toolName = "Buffer Selection"

    def __init__(self, app, draw_app):
        FlatCAMTool.__init__(self, app)

        self.draw_app = draw_app

        # Title
        title_label = QtWidgets.QLabel("<font size=4><b>%s</b></font>" % self.toolName)
        self.layout.addWidget(title_label)

        # this way I can hide/show the frame
        self.buffer_tool_frame = QtWidgets.QFrame()
        self.buffer_tool_frame.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.buffer_tool_frame)
        self.buffer_tools_box = QtWidgets.QVBoxLayout()
        self.buffer_tools_box.setContentsMargins(0, 0, 0, 0)
        self.buffer_tool_frame.setLayout(self.buffer_tools_box)

        # Form Layout
        form_layout = QtWidgets.QFormLayout()
        self.buffer_tools_box.addLayout(form_layout)

        # Buffer distance
        self.buffer_distance_entry = LengthEntry()
        form_layout.addRow("Buffer distance:", self.buffer_distance_entry)
        self.buffer_corner_lbl = QtWidgets.QLabel("Buffer corner:")
        self.buffer_corner_lbl.setToolTip(
            "There are 3 types of corners:\n"
            " - 'Round': the corner is rounded for exterior buffer.\n"
            " - 'Square:' the corner is met in a sharp angle for exterior buffer.\n"
            " - 'Beveled:' the corner is a line that directly connects the features meeting in the corner"
        )
        self.buffer_corner_cb = FCComboBox()
        self.buffer_corner_cb.addItem("Round")
        self.buffer_corner_cb.addItem("Square")
        self.buffer_corner_cb.addItem("Beveled")
        form_layout.addRow(self.buffer_corner_lbl, self.buffer_corner_cb)

        # Buttons
        hlay = QtWidgets.QHBoxLayout()
        self.buffer_tools_box.addLayout(hlay)

        self.buffer_int_button = QtWidgets.QPushButton("Buffer Interior")
        hlay.addWidget(self.buffer_int_button)
        self.buffer_ext_button = QtWidgets.QPushButton("Buffer Exterior")
        hlay.addWidget(self.buffer_ext_button)

        hlay1 = QtWidgets.QHBoxLayout()
        self.buffer_tools_box.addLayout(hlay1)

        self.buffer_button = QtWidgets.QPushButton("Full Buffer")
        hlay1.addWidget(self.buffer_button)

        self.layout.addStretch()

        # Signals
        self.buffer_button.clicked.connect(self.on_buffer)
        self.buffer_int_button.clicked.connect(self.on_buffer_int)
        self.buffer_ext_button.clicked.connect(self.on_buffer_ext)

        # Init GUI
        self.buffer_distance_entry.set_value(0.01)

    def on_buffer(self):
        buffer_distance = self.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer(buffer_distance, join_style)

    def on_buffer_int(self):
        buffer_distance = self.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer_int(buffer_distance, join_style)

    def on_buffer_ext(self):
        buffer_distance = self.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer_ext(buffer_distance, join_style)

    def hide_tool(self):
        self.buffer_tool_frame.hide()
        self.app.ui.notebook.setCurrentWidget(self.app.ui.project_tab)

class TextInputTool(FlatCAMTool):
    """
    Simple input for buffer distance.
    """

    toolName = "Text Input Tool"

    def __init__(self, app):
        FlatCAMTool.__init__(self, app)

        self.app = app
        self.text_path = []

        # this way I can hide/show the frame
        self.text_tool_frame = QtWidgets.QFrame()
        self.text_tool_frame.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.text_tool_frame)
        self.text_tools_box = QtWidgets.QVBoxLayout()
        self.text_tools_box.setContentsMargins(0, 0, 0, 0)
        self.text_tool_frame.setLayout(self.text_tools_box)

        # Title
        title_label = QtWidgets.QLabel("<font size=4><b>%s</b></font>" % self.toolName)
        self.text_tools_box.addWidget(title_label)

        # Form Layout
        self.form_layout = QtWidgets.QFormLayout()
        self.text_tools_box.addLayout(self.form_layout)

        # Font type
        if sys.platform == "win32":
            f_current = QtGui.QFont("Arial")
        elif sys.platform == "linux":
            f_current = QtGui.QFont("FreeMono")
        else:
            f_current = QtGui.QFont("Helvetica Neue")

        self.font_name = f_current.family()

        self.font_type_cb = QtWidgets.QFontComboBox(self)
        self.font_type_cb.setCurrentFont(f_current)
        self.form_layout.addRow("Font:", self.font_type_cb)

        # Flag variables to show if font is bold, italic, both or none (regular)
        self.font_bold = False
        self.font_italic = False

        # # Create dictionaries with the filenames of the fonts
        # # Key: Fontname
        # # Value: Font File Name.ttf
        #
        # # regular fonts
        # self.ff_names_regular ={}
        # # bold fonts
        # self.ff_names_bold = {}
        # # italic fonts
        # self.ff_names_italic = {}
        # # bold and italic fonts
        # self.ff_names_bi = {}
        #
        # if sys.platform == 'win32':
        #     from winreg import ConnectRegistry, OpenKey, EnumValue, HKEY_LOCAL_MACHINE
        #     registry = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
        #     font_key = OpenKey(registry, "SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        #     try:
        #         i = 0
        #         while 1:
        #             name_font, value, type = EnumValue(font_key, i)
        #             k = name_font.replace(" (TrueType)", '')
        #             if 'Bold' in k and 'Italic' in k:
        #                 k = k.replace(" Bold Italic", '')
        #                 self.ff_names_bi.update({k: value})
        #             elif 'Bold' in k:
        #                 k = k.replace(" Bold", '')
        #                 self.ff_names_bold.update({k: value})
        #             elif 'Italic' in k:
        #                 k = k.replace(" Italic", '')
        #                 self.ff_names_italic.update({k: value})
        #             else:
        #                 self.ff_names_regular.update({k: value})
        #             i += 1
        #     except WindowsError:
        #         pass

        # Font size
        self.font_size_cb = FCComboBox()
        self.font_size_cb.setEditable(True)
        self.font_size_cb.setMinimumContentsLength(3)
        self.font_size_cb.setMaximumWidth(70)

        font_sizes = ['6', '7', '8', '9', '10', '11', '12', '13', '14',
                     '15', '16', '18', '20', '22', '24', '26', '28',
                     '32', '36', '40', '44', '48', '54', '60', '66',
                     '72', '80', '88', '96']

        for i in font_sizes:
            self.font_size_cb.addItem(i)
        self.font_size_cb.setCurrentIndex(4)

        hlay = QtWidgets.QHBoxLayout()
        hlay.addWidget(self.font_size_cb)
        hlay.addStretch()

        self.font_bold_tb = QtWidgets.QToolButton()
        self.font_bold_tb.setCheckable(True)
        self.font_bold_tb.setIcon(QtGui.QIcon('share/bold32.png'))
        hlay.addWidget(self.font_bold_tb)

        self.font_italic_tb = QtWidgets.QToolButton()
        self.font_italic_tb.setCheckable(True)
        self.font_italic_tb.setIcon(QtGui.QIcon('share/italic32.png'))
        hlay.addWidget(self.font_italic_tb)

        self.form_layout.addRow("Size:", hlay)

        # Text input
        self.text_input_entry = FCTextAreaRich()
        self.text_input_entry.setTabStopWidth(12)
        self.text_input_entry.setMinimumHeight(200)
        # self.text_input_entry.setMaximumHeight(150)
        self.text_input_entry.setCurrentFont(f_current)
        self.text_input_entry.setFontPointSize(10)
        self.form_layout.addRow("Text:", self.text_input_entry)

        # Buttons
        hlay1 = QtWidgets.QHBoxLayout()
        self.form_layout.addRow("", hlay1)
        hlay1.addStretch()
        self.apply_button = QtWidgets.QPushButton("Apply")
        hlay1.addWidget(self.apply_button)

        # self.layout.addStretch()

        # Signals
        self.apply_button.clicked.connect(self.on_apply_button)
        self.font_type_cb.currentFontChanged.connect(self.font_family)
        self.font_size_cb.activated.connect(self.font_size)
        self.font_bold_tb.clicked.connect(self.on_bold_button)
        self.font_italic_tb.clicked.connect(self.on_italic_button)

    def on_apply_button(self):
        font_to_geo_type = ""

        if self.font_bold is True:
            font_to_geo_type = 'bold'
        elif self.font_italic is True:
            font_to_geo_type = 'italic'
        elif self.font_bold is True and self.font_italic is True:
            font_to_geo_type = 'bi'
        elif self.font_bold is False and self.font_italic is False:
            font_to_geo_type = 'regular'
        string_to_geo = self.text_input_entry.get_value()
        font_to_geo_size = self.font_size_cb.get_value()

        self.text_path = self.app.f_parse.font_to_geometry(
                    char_string=string_to_geo,
                    font_name=self.font_name,
                    font_size=font_to_geo_size,
                    font_type=font_to_geo_type,
                    units=self.app.general_options_form.general_group.units_radio.get_value().upper())

    def font_family(self, font):
        self.text_input_entry.selectAll()
        font.setPointSize(float(self.font_size_cb.get_value()))
        self.text_input_entry.setCurrentFont(font)
        self.font_name = self.font_type_cb.currentFont().family()

    def font_size(self):
        self.text_input_entry.selectAll()
        self.text_input_entry.setFontPointSize(float(self.font_size_cb.get_value()))

    def on_bold_button(self):
        if self.font_bold_tb.isChecked():
            self.text_input_entry.selectAll()
            self.text_input_entry.setFontWeight(QtGui.QFont.Bold)
            self.font_bold = True
        else:
            self.text_input_entry.selectAll()
            self.text_input_entry.setFontWeight(QtGui.QFont.Normal)
            self.font_bold = False

    def on_italic_button(self):
        if self.font_italic_tb.isChecked():
            self.text_input_entry.selectAll()
            self.text_input_entry.setFontItalic(True)
            self.font_italic = True
        else:
            self.text_input_entry.selectAll()
            self.text_input_entry.setFontItalic(False)
            self.font_italic = False

    def hide_tool(self):
        self.text_tool_frame.hide()
        self.app.ui.notebook.setCurrentWidget(self.app.ui.project_tab)


class PaintOptionsTool(FlatCAMTool):
    """
    Inputs to specify how to paint the selected polygons.
    """

    toolName = "Paint Options"

    def __init__(self, app, fcdraw):
        FlatCAMTool.__init__(self, app)

        self.app = app
        self.fcdraw = fcdraw

        ## Title
        title_label = QtWidgets.QLabel("<font size=4><b>%s</b></font>" % self.toolName)
        self.layout.addWidget(title_label)

        grid = QtWidgets.QGridLayout()
        self.layout.addLayout(grid)

        # Tool dia
        ptdlabel = QtWidgets.QLabel('Tool dia:')
        ptdlabel.setToolTip(
            "Diameter of the tool to\n"
            "be used in the operation."
        )
        grid.addWidget(ptdlabel, 0, 0)

        self.painttooldia_entry = LengthEntry()
        grid.addWidget(self.painttooldia_entry, 0, 1)

        # Overlap
        ovlabel = QtWidgets.QLabel('Overlap:')
        ovlabel.setToolTip(
            "How much (fraction) of the tool width to overlap each tool pass.\n"
            "Example:\n"
            "A value here of 0.25 means 25% from the tool diameter found above.\n\n"
            "Adjust the value starting with lower values\n"
            "and increasing it if areas that should be painted are still \n"
            "not painted.\n"
            "Lower values = faster processing, faster execution on PCB.\n"
            "Higher values = slow processing and slow execution on CNC\n"
            "due of too many paths."
        )
        grid.addWidget(ovlabel, 1, 0)
        self.paintoverlap_entry = LengthEntry()
        grid.addWidget(self.paintoverlap_entry, 1, 1)

        # Margin
        marginlabel = QtWidgets.QLabel('Margin:')
        marginlabel.setToolTip(
            "Distance by which to avoid\n"
            "the edges of the polygon to\n"
            "be painted."
        )
        grid.addWidget(marginlabel, 2, 0)
        self.paintmargin_entry = LengthEntry()
        grid.addWidget(self.paintmargin_entry, 2, 1)

        # Method
        methodlabel = QtWidgets.QLabel('Method:')
        methodlabel.setToolTip(
            "Algorithm to paint the polygon:<BR>"
            "<B>Standard</B>: Fixed step inwards.<BR>"
            "<B>Seed-based</B>: Outwards from seed."
        )
        grid.addWidget(methodlabel, 3, 0)
        self.paintmethod_combo = RadioSet([
            {"label": "Standard", "value": "standard"},
            {"label": "Seed-based", "value": "seed"},
            {"label": "Straight lines", "value": "lines"}
        ], orientation='vertical', stretch=False)
        grid.addWidget(self.paintmethod_combo, 3, 1)

        # Connect lines
        pathconnectlabel = QtWidgets.QLabel("Connect:")
        pathconnectlabel.setToolTip(
            "Draw lines between resulting\n"
            "segments to minimize tool lifts."
        )
        grid.addWidget(pathconnectlabel, 4, 0)
        self.pathconnect_cb = FCCheckBox()
        grid.addWidget(self.pathconnect_cb, 4, 1)

        contourlabel = QtWidgets.QLabel("Contour:")
        contourlabel.setToolTip(
            "Cut around the perimeter of the polygon\n"
            "to trim rough edges."
        )
        grid.addWidget(contourlabel, 5, 0)
        self.paintcontour_cb = FCCheckBox()
        grid.addWidget(self.paintcontour_cb, 5, 1)


        ## Buttons
        hlay = QtWidgets.QHBoxLayout()
        self.layout.addLayout(hlay)
        hlay.addStretch()
        self.paint_button = QtWidgets.QPushButton("Paint")
        hlay.addWidget(self.paint_button)

        self.layout.addStretch()

        ## Signals
        self.paint_button.clicked.connect(self.on_paint)

        ## Init GUI
        self.painttooldia_entry.set_value(0)
        self.paintoverlap_entry.set_value(0)
        self.paintmargin_entry.set_value(0)
        self.paintmethod_combo.set_value("seed")


    def on_paint(self):

        tooldia = self.painttooldia_entry.get_value()
        overlap = self.paintoverlap_entry.get_value()
        margin = self.paintmargin_entry.get_value()
        method = self.paintmethod_combo.get_value()
        contour = self.paintcontour_cb.get_value()
        connect = self.pathconnect_cb.get_value()

        self.fcdraw.paint(tooldia, overlap, margin, connect=connect, contour=contour, method=method)
        self.fcdraw.select_tool("select")
        self.app.ui.notebook.setTabText(2, "Tools")
        self.app.ui.notebook.setCurrentWidget(self.app.ui.project_tab)


class DrawToolShape(object):
    """
    Encapsulates "shapes" under a common class.
    """

    tolerance = None

    @staticmethod
    def get_pts(o):
        """
        Returns a list of all points in the object, where
        the object can be a Polygon, Not a polygon, or a list
        of such. Search is done recursively.

        :param: geometric object
        :return: List of points
        :rtype: list
        """
        pts = []

        ## Iterable: descend into each item.
        try:
            for subo in o:
                pts += DrawToolShape.get_pts(subo)

        ## Non-iterable
        except TypeError:
            if o is not None:
                ## DrawToolShape: descend into .geo.
                if isinstance(o, DrawToolShape):
                    pts += DrawToolShape.get_pts(o.geo)

                ## Descend into .exerior and .interiors
                elif type(o) == Polygon:
                    pts += DrawToolShape.get_pts(o.exterior)
                    for i in o.interiors:
                        pts += DrawToolShape.get_pts(i)
                elif type(o) == MultiLineString:
                    for line in o.geoms:
                        pts += DrawToolShape.get_pts(line)
                ## Has .coords: list them.
                else:
                    if DrawToolShape.tolerance is not None:
                        pts += list(o.simplify(DrawToolShape.tolerance).coords)
                    else:
                        pts += list(o.coords)
            else:
                return
        return pts

    def __init__(self, geo=[]):

        # Shapely type or list of such
        self.geo = geo
        self.utility = False

    def get_all_points(self):
        return DrawToolShape.get_pts(self)


class DrawToolUtilityShape(DrawToolShape):
    """
    Utility shapes are temporary geometry in the editor
    to assist in the creation of shapes. For example it
    will show the outline of a rectangle from the first
    point to the current mouse pointer before the second
    point is clicked and the final geometry is created.
    """

    def __init__(self, geo=[]):
        super(DrawToolUtilityShape, self).__init__(geo=geo)
        self.utility = True


class DrawTool(object):
    """
    Abstract Class representing a tool in the drawing
    program. Can generate geometry, including temporary
    utility geometry that is updated on user clicks
    and mouse motion.
    """

    def __init__(self, draw_app):
        self.draw_app = draw_app
        self.complete = False
        self.start_msg = "Click on 1st point..."
        self.points = []
        self.geometry = None  # DrawToolShape or None

    def click(self, point):
        """
        :param point: [x, y] Coordinate pair.
        """
        return ""

    def click_release(self, point):
        """
        :param point: [x, y] Coordinate pair.
        """
        return ""

    def on_key(self, key):
        return None

    def utility_geometry(self, data=None):
        return None


class FCShapeTool(DrawTool):
    """
    Abstract class for tools that create a shape.
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)

    def make(self):
        pass


class FCCircle(FCShapeTool):
    """
    Resulting type: Polygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.start_msg = "Click on CENTER ..."
        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

    def click(self, point):
        self.points.append(point)

        if len(self.points) == 1:
            return "Click on perimeter to complete ..."

        if len(self.points) == 2:
            self.make()
            return "Done."

        return ""

    def utility_geometry(self, data=None):
        if len(self.points) == 1:
            p1 = self.points[0]
            p2 = data
            radius = sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
            return DrawToolUtilityShape(Point(p1).buffer(radius, int(self.steps_per_circ / 4)))

        return None

    def make(self):
        p1 = self.points[0]
        p2 = self.points[1]
        radius = distance(p1, p2)
        self.geometry = DrawToolShape(Point(p1).buffer(radius, int(self.steps_per_circ / 4)))
        self.complete = True


class FCArc(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.start_msg = "Click on CENTER ..."

        # Direction of rotation between point 1 and 2.
        # 'cw' or 'ccw'. Switch direction by hitting the
        # 'o' key.
        self.direction = "cw"

        # Mode
        # C12 = Center, p1, p2
        # 12C = p1, p2, Center
        # 132 = p1, p3, p2
        self.mode = "c12"  # Center, p1, p2

        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

    def click(self, point):
        self.points.append(point)

        if len(self.points) == 1:
            return "Click on 1st point ..."

        if len(self.points) == 2:
            return "Click on 2nd point to complete ..."

        if len(self.points) == 3:
            self.make()
            return "Done."

        return ""

    def on_key(self, key):
        if key == 'o':
            self.direction = 'cw' if self.direction == 'ccw' else 'ccw'
            return 'Direction: ' + self.direction.upper()

        if key == 'p':
            if self.mode == 'c12':
                self.mode = '12c'
            elif self.mode == '12c':
                self.mode = '132'
            else:
                self.mode = 'c12'
            return 'Mode: ' + self.mode

    def utility_geometry(self, data=None):
        if len(self.points) == 1:  # Show the radius
            center = self.points[0]
            p1 = data

            return DrawToolUtilityShape(LineString([center, p1]))

        if len(self.points) == 2:  # Show the arc

            if self.mode == 'c12':
                center = self.points[0]
                p1 = self.points[1]
                p2 = data

                radius = sqrt((center[0] - p1[0]) ** 2 + (center[1] - p1[1]) ** 2)
                startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
                stopangle = arctan2(p2[1] - center[1], p2[0] - center[0])

                return DrawToolUtilityShape([LineString(arc(center, radius, startangle, stopangle,
                                                            self.direction, self.steps_per_circ)),
                                             Point(center)])

            elif self.mode == '132':
                p1 = array(self.points[0])
                p3 = array(self.points[1])
                p2 = array(data)

                center, radius, t = three_point_circle(p1, p2, p3)
                direction = 'cw' if sign(t) > 0 else 'ccw'

                startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
                stopangle = arctan2(p3[1] - center[1], p3[0] - center[0])

                return DrawToolUtilityShape([LineString(arc(center, radius, startangle, stopangle,
                                                            direction, self.steps_per_circ)),
                                             Point(center), Point(p1), Point(p3)])

            else:  # '12c'
                p1 = array(self.points[0])
                p2 = array(self.points[1])

                # Midpoint
                a = (p1 + p2) / 2.0

                # Parallel vector
                c = p2 - p1

                # Perpendicular vector
                b = dot(c, array([[0, -1], [1, 0]], dtype=float32))
                b /= norm(b)

                # Distance
                t = distance(data, a)

                # Which side? Cross product with c.
                # cross(M-A, B-A), where line is AB and M is test point.
                side = (data[0] - p1[0]) * c[1] - (data[1] - p1[1]) * c[0]
                t *= sign(side)

                # Center = a + bt
                center = a + b * t

                radius = norm(center - p1)
                startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
                stopangle = arctan2(p2[1] - center[1], p2[0] - center[0])

                return DrawToolUtilityShape([LineString(arc(center, radius, startangle, stopangle,
                                                            self.direction, self.steps_per_circ)),
                                             Point(center)])

        return None

    def make(self):

        if self.mode == 'c12':
            center = self.points[0]
            p1 = self.points[1]
            p2 = self.points[2]

            radius = distance(center, p1)
            startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
            stopangle = arctan2(p2[1] - center[1], p2[0] - center[0])
            self.geometry = DrawToolShape(LineString(arc(center, radius, startangle, stopangle,
                                                         self.direction, self.steps_per_circ)))

        elif self.mode == '132':
            p1 = array(self.points[0])
            p3 = array(self.points[1])
            p2 = array(self.points[2])

            center, radius, t = three_point_circle(p1, p2, p3)
            direction = 'cw' if sign(t) > 0 else 'ccw'

            startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
            stopangle = arctan2(p3[1] - center[1], p3[0] - center[0])

            self.geometry = DrawToolShape(LineString(arc(center, radius, startangle, stopangle,
                                                         direction, self.steps_per_circ)))

        else:  # self.mode == '12c'
            p1 = array(self.points[0])
            p2 = array(self.points[1])
            pc = array(self.points[2])

            # Midpoint
            a = (p1 + p2) / 2.0

            # Parallel vector
            c = p2 - p1

            # Perpendicular vector
            b = dot(c, array([[0, -1], [1, 0]], dtype=float32))
            b /= norm(b)

            # Distance
            t = distance(pc, a)

            # Which side? Cross product with c.
            # cross(M-A, B-A), where line is AB and M is test point.
            side = (pc[0] - p1[0]) * c[1] - (pc[1] - p1[1]) * c[0]
            t *= sign(side)

            # Center = a + bt
            center = a + b * t

            radius = norm(center - p1)
            startangle = arctan2(p1[1] - center[1], p1[0] - center[0])
            stopangle = arctan2(p2[1] - center[1], p2[0] - center[0])

            self.geometry = DrawToolShape(LineString(arc(center, radius, startangle, stopangle,
                                                         self.direction, self.steps_per_circ)))
        self.complete = True


class FCRectangle(FCShapeTool):
    """
    Resulting type: Polygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.start_msg = "Click on 1st corner ..."

    def click(self, point):
        self.points.append(point)

        if len(self.points) == 1:
            return "Click on opposite corner to complete ..."

        if len(self.points) == 2:
            self.make()
            return "Done."

        return ""

    def utility_geometry(self, data=None):
        if len(self.points) == 1:
            p1 = self.points[0]
            p2 = data
            return DrawToolUtilityShape(LinearRing([p1, (p2[0], p1[1]), p2, (p1[0], p2[1])]))

        return None

    def make(self):
        p1 = self.points[0]
        p2 = self.points[1]
        # self.geometry = LinearRing([p1, (p2[0], p1[1]), p2, (p1[0], p2[1])])
        self.geometry = DrawToolShape(Polygon([p1, (p2[0], p1[1]), p2, (p1[0], p2[1])]))
        self.complete = True


class FCPolygon(FCShapeTool):
    """
    Resulting type: Polygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.start_msg = "Click on 1st point ..."

    def click(self, point):
        self.draw_app.in_action = True
        self.points.append(point)

        if len(self.points) > 0:
            return "Click on next point or hit ENTER to complete ..."

        return ""

    def utility_geometry(self, data=None):
        if len(self.points) == 1:
            temp_points = [x for x in self.points]
            temp_points.append(data)
            return DrawToolUtilityShape(LineString(temp_points))

        if len(self.points) > 1:
            temp_points = [x for x in self.points]
            temp_points.append(data)
            return DrawToolUtilityShape(LinearRing(temp_points))

        return None

    def make(self):
        # self.geometry = LinearRing(self.points)
        self.geometry = DrawToolShape(Polygon(self.points))
        self.draw_app.in_action = False
        self.complete = True

    def on_key(self, key):
        if key == 'backspace':
            if len(self.points) > 0:
                self.points = self.points[0:-1]


class FCPath(FCPolygon):
    """
    Resulting type: LineString
    """

    def make(self):
        self.geometry = DrawToolShape(LineString(self.points))
        self.draw_app.in_action = False
        self.complete = True

    def utility_geometry(self, data=None):
        if len(self.points) > 0:
            temp_points = [x for x in self.points]
            temp_points.append(data)
            return DrawToolUtilityShape(LineString(temp_points))

        return None

    def on_key(self, key):
        if key == 'backspace':
            if len(self.points) > 0:
                self.points = self.points[0:-1]


class FCSelect(DrawTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.storage = self.draw_app.storage
        # self.shape_buffer = self.draw_app.shape_buffer
        # self.selected = self.draw_app.selected

    def click_release(self, point):

        self.select_shapes(point)
        return ""

    def select_shapes(self, pos):
        # list where we store the overlapped shapes under our mouse left click position
        over_shape_list = []

        # pos[0] and pos[1] are the mouse click coordinates (x, y)
        for obj_shape in self.storage.get_objects():
            # first method of click selection -> inconvenient
            # minx, miny, maxx, maxy = obj_shape.geo.bounds
            # if (minx <= pos[0] <= maxx) and (miny <= pos[1] <= maxy):
            #     over_shape_list.append(obj_shape)

            # second method of click selection -> slow
            # outside = obj_shape.geo.buffer(0.1)
            # inside = obj_shape.geo.buffer(-0.1)
            # shape_band = outside.difference(inside)
            # if Point(pos).within(shape_band):
            #     over_shape_list.append(obj_shape)

            # 3rd method of click selection -> inconvenient
            try:
                _, closest_shape = self.storage.nearest(pos)
            except StopIteration:
                return ""

            over_shape_list.append(closest_shape)

        try:
            # if there is no shape under our click then deselect all shapes
            # it will not work for 3rd method of click selection
            if not over_shape_list:
                self.draw_app.selected = []
                FlatCAMGeoEditor.draw_shape_idx = -1
            else:
                # if there are shapes under our click then advance through the list of them, one at the time in a
                # circular way
                FlatCAMGeoEditor.draw_shape_idx = (FlatCAMGeoEditor.draw_shape_idx + 1) % len(over_shape_list)
                obj_to_add = over_shape_list[int(FlatCAMGeoEditor.draw_shape_idx)]

                key_modifier = QtWidgets.QApplication.keyboardModifiers()
                if self.draw_app.app.defaults["global_mselect_key"] == 'Control':
                    # if CONTROL key is pressed then we add to the selected list the current shape but if it's already
                    # in the selected list, we removed it. Therefore first click selects, second deselects.
                    if key_modifier == Qt.ControlModifier:
                        if obj_to_add in self.draw_app.selected:
                            self.draw_app.selected.remove(obj_to_add)
                        else:
                            self.draw_app.selected.append(obj_to_add)
                    else:
                        self.draw_app.selected = []
                        self.draw_app.selected.append(obj_to_add)
                else:
                    if key_modifier == Qt.ShiftModifier:
                        if obj_to_add in self.draw_app.selected:
                            self.draw_app.selected.remove(obj_to_add)
                        else:
                            self.draw_app.selected.append(obj_to_add)
                    else:
                        self.draw_app.selected = []
                        self.draw_app.selected.append(obj_to_add)

        except Exception as e:
            log.error("[ERROR] Something went bad. %s" % str(e))
            raise


class FCDrillSelect(DrawTool):
    def __init__(self, exc_editor_app):
        DrawTool.__init__(self, exc_editor_app)

        self.exc_editor_app = exc_editor_app
        self.storage = self.exc_editor_app.storage_dict
        # self.selected = self.exc_editor_app.selected

        # here we store all shapes that were selected so we can search for the nearest to our click location
        self.sel_storage = FlatCAMExcEditor.make_storage()

        self.exc_editor_app.resize_frame.hide()
        self.exc_editor_app.array_frame.hide()

    def click(self, point):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()
        if self.exc_editor_app.app.defaults["global_mselect_key"] == 'Control':
            if key_modifier == Qt.ControlModifier:
                pass
            else:
                self.exc_editor_app.selected = []
        else:
            if key_modifier == Qt.ShiftModifier:
                pass
            else:
                self.exc_editor_app.selected = []

    def click_release(self, point):
        self.select_shapes(point)
        return ""

    def select_shapes(self, pos):
        self.exc_editor_app.tools_table_exc.clearSelection()

        try:
            # for storage in self.exc_editor_app.storage_dict:
            #     _, partial_closest_shape = self.exc_editor_app.storage_dict[storage].nearest(pos)
            #     if partial_closest_shape is not None:
            #         self.sel_storage.insert(partial_closest_shape)
            #
            # _, closest_shape = self.sel_storage.nearest(pos)

            for storage in self.exc_editor_app.storage_dict:
                for shape in self.exc_editor_app.storage_dict[storage].get_objects():
                    self.sel_storage.insert(shape)

            _, closest_shape = self.sel_storage.nearest(pos)


            # constrain selection to happen only within a certain bounding box
            x_coord, y_coord = closest_shape.geo[0].xy
            delta = (x_coord[1] - x_coord[0])
            # closest_shape_coords = (((x_coord[0] + delta / 2)), y_coord[0])
            xmin = x_coord[0] - (0.7 * delta)
            xmax = x_coord[0] + (1.7 * delta)
            ymin = y_coord[0] - (0.7 * delta)
            ymax = y_coord[0] + (1.7 * delta)
        except StopIteration:
            return ""

        if pos[0] < xmin or pos[0] > xmax or pos[1] < ymin or pos[1] > ymax:
            self.exc_editor_app.selected = []
        else:
            key_modifier = QtWidgets.QApplication.keyboardModifiers()
            if self.exc_editor_app.app.defaults["global_mselect_key"] == 'Control':
                # if CONTROL key is pressed then we add to the selected list the current shape but if it's already
                # in the selected list, we removed it. Therefore first click selects, second deselects.
                if key_modifier == Qt.ControlModifier:
                    if closest_shape in self.exc_editor_app.selected:
                        self.exc_editor_app.selected.remove(closest_shape)
                    else:
                        self.exc_editor_app.selected.append(closest_shape)
                else:
                    self.exc_editor_app.selected = []
                    self.exc_editor_app.selected.append(closest_shape)
            else:
                if key_modifier == Qt.ShiftModifier:
                    if closest_shape in self.exc_editor_app.selected:
                        self.exc_editor_app.selected.remove(closest_shape)
                    else:
                        self.exc_editor_app.selected.append(closest_shape)
                else:
                    self.exc_editor_app.selected = []
                    self.exc_editor_app.selected.append(closest_shape)

            # select the diameter of the selected shape in the tool table
            for storage in self.exc_editor_app.storage_dict:
                for shape_s in self.exc_editor_app.selected:
                    if shape_s in self.exc_editor_app.storage_dict[storage].get_objects():
                        for key in self.exc_editor_app.tool2tooldia:
                            if self.exc_editor_app.tool2tooldia[key] == storage:
                                item = self.exc_editor_app.tools_table_exc.item((key - 1), 1)
                                self.exc_editor_app.tools_table_exc.setCurrentItem(item)
                                # item.setSelected(True)
                                # self.exc_editor_app.tools_table_exc.selectItem(key - 1)
                                # midx = self.exc_editor_app.tools_table_exc.model().index((key - 1), 0)
                                # self.exc_editor_app.tools_table_exc.setCurrentIndex(midx)
                                self.draw_app.last_tool_selected = key
        # delete whatever is in selection storage, there is no longer need for those shapes
        self.sel_storage = FlatCAMExcEditor.make_storage()

        return ""

        # pos[0] and pos[1] are the mouse click coordinates (x, y)
        # for storage in self.exc_editor_app.storage_dict:
        #     for obj_shape in self.exc_editor_app.storage_dict[storage].get_objects():
        #         minx, miny, maxx, maxy = obj_shape.geo.bounds
        #         if (minx <= pos[0] <= maxx) and (miny <= pos[1] <= maxy):
        #             over_shape_list.append(obj_shape)
        #
        # try:
        #     # if there is no shape under our click then deselect all shapes
        #     if not over_shape_list:
        #         self.exc_editor_app.selected = []
        #         FlatCAMExcEditor.draw_shape_idx = -1
        #         self.exc_editor_app.tools_table_exc.clearSelection()
        #     else:
        #         # if there are shapes under our click then advance through the list of them, one at the time in a
        #         # circular way
        #         FlatCAMExcEditor.draw_shape_idx = (FlatCAMExcEditor.draw_shape_idx + 1) % len(over_shape_list)
        #         obj_to_add = over_shape_list[int(FlatCAMExcEditor.draw_shape_idx)]
        #
        #         if self.exc_editor_app.app.defaults["global_mselect_key"] == 'Shift':
        #             if self.exc_editor_app.modifiers == Qt.ShiftModifier:
        #                 if obj_to_add in self.exc_editor_app.selected:
        #                     self.exc_editor_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.exc_editor_app.selected.append(obj_to_add)
        #             else:
        #                 self.exc_editor_app.selected = []
        #                 self.exc_editor_app.selected.append(obj_to_add)
        #         else:
        #             # if CONTROL key is pressed then we add to the selected list the current shape but if it's already
        #             # in the selected list, we removed it. Therefore first click selects, second deselects.
        #             if self.exc_editor_app.modifiers == Qt.ControlModifier:
        #                 if obj_to_add in self.exc_editor_app.selected:
        #                     self.exc_editor_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.exc_editor_app.selected.append(obj_to_add)
        #             else:
        #                 self.exc_editor_app.selected = []
        #                 self.exc_editor_app.selected.append(obj_to_add)
        #
        #     for storage in self.exc_editor_app.storage_dict:
        #         for shape in self.exc_editor_app.selected:
        #             if shape in self.exc_editor_app.storage_dict[storage].get_objects():
        #                 for key in self.exc_editor_app.tool2tooldia:
        #                     if self.exc_editor_app.tool2tooldia[key] == storage:
        #                         item = self.exc_editor_app.tools_table_exc.item((key - 1), 1)
        #                         item.setSelected(True)
        #                         # self.exc_editor_app.tools_table_exc.selectItem(key - 1)
        #
        # except Exception as e:
        #     log.error("[ERROR] Something went bad. %s" % str(e))
        #     raise


class FCMove(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)
        # self.shape_buffer = self.draw_app.shape_buffer
        self.origin = None
        self.destination = None
        self.start_msg = "Click on reference point."

    def set_origin(self, origin):
        self.origin = origin

    def click(self, point):
        if len(self.draw_app.get_selected()) == 0:
            return "Nothing to move."

        if self.origin is None:
            self.set_origin(point)
            return "Click on final location."
        else:
            self.destination = point
            self.make()
            return "Done."

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        self.geometry = [DrawToolShape(affinity.translate(geom.geo, xoff=dx, yoff=dy))
                         for geom in self.draw_app.get_selected()]

        # Delete old
        self.draw_app.delete_selected()

        # # Select the new
        # for g in self.geometry:
        #     # Note that g is not in the app's buffer yet!
        #     self.draw_app.set_selected(g)

        self.complete = True

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        geo_list = []

        if self.origin is None:
            return None

        if len(self.draw_app.get_selected()) == 0:
            return None

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]
        for geom in self.draw_app.get_selected():
            geo_list.append(affinity.translate(geom.geo, xoff=dx, yoff=dy))

        return DrawToolUtilityShape(geo_list)
        # return DrawToolUtilityShape([affinity.translate(geom.geo, xoff=dx, yoff=dy)
        #                              for geom in self.draw_app.get_selected()])


class FCCopy(FCMove):

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        self.geometry = [DrawToolShape(affinity.translate(geom.geo, xoff=dx, yoff=dy))
                         for geom in self.draw_app.get_selected()]
        self.complete = True


class FCText(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)
        # self.shape_buffer = self.draw_app.shape_buffer
        self.draw_app = draw_app
        self.app = draw_app.app

        self.start_msg = "Click on the Destination point..."
        self.origin = (0, 0)
        self.text_gui = TextInputTool(self.app)
        self.text_gui.run()

    def click(self, point):
        # Create new geometry
        dx = point[0]
        dy = point[1]
        try:
            self.geometry = DrawToolShape(affinity.translate(self.text_gui.text_path, xoff=dx, yoff=dy))
        except Exception as e:
            log.debug("Font geometry is empty or incorrect: %s" % str(e))
            self.draw_app.app.inform.emit("[error]Font not supported. Only Regular, Bold, Italic and BoldItalic are "
                                          "supported. Error: %s" % str(e))
            self.text_gui.text_path = []
            self.text_gui.hide_tool()
            self.draw_app.select_tool('select')
            return

        self.text_gui.text_path = []
        self.text_gui.hide_tool()
        self.complete = True

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data: mouse position coords
        :return:
        """

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]

        try:
            return DrawToolUtilityShape(affinity.translate(self.text_gui.text_path, xoff=dx, yoff=dy))
        except:
            return

class FCBuffer(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)
        # self.shape_buffer = self.draw_app.shape_buffer
        self.draw_app = draw_app
        self.app = draw_app.app

        self.start_msg = "Create buffer geometry ..."
        self.origin = (0, 0)
        self.buff_tool = BufferSelectionTool(self.app, self.draw_app)
        self.buff_tool.run()
        self.app.ui.notebook.setTabText(2, "Buffer Tool")
        self.activate()

    def on_buffer(self):
        buffer_distance = self.buff_tool.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buff_tool.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer(buffer_distance, join_style)
        self.app.ui.notebook.setTabText(2, "Tools")
        self.disactivate()

    def on_buffer_int(self):
        buffer_distance = self.buff_tool.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buff_tool.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer_int(buffer_distance, join_style)
        self.app.ui.notebook.setTabText(2, "Tools")
        self.disactivate()

    def on_buffer_ext(self):
        buffer_distance = self.buff_tool.buffer_distance_entry.get_value()
        # the cb index start from 0 but the join styles for the buffer start from 1 therefore the adjustment
        # I populated the combobox such that the index coincide with the join styles value (whcih is really an INT)
        join_style = self.buff_tool.buffer_corner_cb.currentIndex() + 1
        self.draw_app.buffer_ext(buffer_distance, join_style)
        self.app.ui.notebook.setTabText(2, "Tools")
        self.disactivate()

    def activate(self):
        self.buff_tool.buffer_button.clicked.disconnect()
        self.buff_tool.buffer_int_button.clicked.disconnect()
        self.buff_tool.buffer_ext_button.clicked.disconnect()

        self.buff_tool.buffer_button.clicked.connect(self.on_buffer)
        self.buff_tool.buffer_int_button.clicked.connect(self.on_buffer_int)
        self.buff_tool.buffer_ext_button.clicked.connect(self.on_buffer_ext)

    def disactivate(self):
        self.buff_tool.buffer_button.clicked.disconnect()
        self.buff_tool.buffer_int_button.clicked.disconnect()
        self.buff_tool.buffer_ext_button.clicked.disconnect()

        self.buff_tool.buffer_button.clicked.connect(self.buff_tool.on_buffer)
        self.buff_tool.buffer_int_button.clicked.connect(self.buff_tool.on_buffer_int)
        self.buff_tool.buffer_ext_button.clicked.connect(self.buff_tool.on_buffer_ext)
        self.complete = True
        self.draw_app.select_tool("select")
        self.buff_tool.hide_tool()


class FCPaint(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)
        # self.shape_buffer = self.draw_app.shape_buffer
        self.draw_app = draw_app
        self.app = draw_app.app

        self.start_msg = "Create Paint geometry ..."
        self.origin = (0, 0)
        self.paint_tool = PaintOptionsTool(self.app, self.draw_app)
        self.paint_tool.run()
        self.app.ui.notebook.setTabText(2, "Paint Tool")


class FCRotate(FCShapeTool):
    def __init__(self, draw_app):
        FCShapeTool.__init__(self, draw_app)

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit("Click anywhere to finish the Rotation")

    def set_origin(self, origin):
        self.origin = origin


    def make(self):
        # Create new geometry
        # dx = self.origin[0]
        # dy = self.origin[1]
        self.geometry = [DrawToolShape(affinity.rotate(geom.geo, angle = -90, origin='center'))
                         for geom in self.draw_app.get_selected()]
        # Delete old
        self.draw_app.delete_selected()
        self.complete = True

        # MS: automatically select the Select Tool after finishing the action but is not working yet :(
        #self.draw_app.select_tool("select")

    def on_key(self, key):
        if key == 'Enter':
            if self.complete == True:
                self.make()

    def click(self, point):
        self.make()
        return "Done."

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        return DrawToolUtilityShape([affinity.rotate(geom.geo, angle = -90, origin='center')
                                     for geom in self.draw_app.get_selected()])


class FCDrillAdd(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)

        self.selected_dia = None
        try:
            self.draw_app.app.inform.emit(self.start_msg)
            # self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.tools_table_exc.currentRow() + 1]
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)

        except KeyError:
            self.draw_app.app.inform.emit("[warning_notcl] To add a drill first select a tool")
            self.draw_app.select_tool("select")
            return

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit("Click on target location ...")

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):
        self.make()
        return "Done."

    def utility_geometry(self, data=None):
        self.points = data
        return DrawToolUtilityShape(self.util_shape(data))

    def util_shape(self, point):

        start_hor_line = ((point[0] - (self.selected_dia / 2)), point[1])
        stop_hor_line = ((point[0] + (self.selected_dia / 2)), point[1])
        start_vert_line = (point[0], (point[1] - (self.selected_dia / 2)))
        stop_vert_line = (point[0], (point[1] + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):

        # add the point to drills if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia].append(self.points)
        else:
            self.draw_app.points_edit[self.selected_dia] = [self.points]

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]
        self.geometry = DrawToolShape(self.util_shape(self.points))
        self.complete = True
        self.draw_app.app.inform.emit("[success]Done. Drill added.")


class FCDrillArray(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)

        self.draw_app.array_frame.show()

        self.selected_dia = None
        self.drill_axis = 'X'
        self.drill_array = 'linear'
        self.drill_array_size = None
        self.drill_pitch = None

        self.drill_angle = None
        self.drill_direction = None
        self.drill_radius = None

        self.origin = None
        self.destination = None
        self.flag_for_circ_array = None

        self.last_dx = 0
        self.last_dy = 0

        self.pt = []

        try:
            self.draw_app.app.inform.emit(self.start_msg)
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit("[warning_notcl] To add an Drill Array first select a tool in Tool Table")
            return

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y), static=True)

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit("Click on target location ...")

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):

        if self.drill_array == 'Linear':
            self.make()
            return
        else:
            if self.flag_for_circ_array is None:
                self.draw_app.in_action = True
                self.pt.append(point)

                self.flag_for_circ_array = True
                self.set_origin(point)
                self.draw_app.app.inform.emit("Click on the circular array Start position")
            else:
                self.destination = point
                self.make()
                self.flag_for_circ_array = None
                return

    def set_origin(self, origin):
        self.origin = origin

    def utility_geometry(self, data=None, static=None):
        self.drill_axis = self.draw_app.drill_axis_radio.get_value()
        self.drill_direction = self.draw_app.drill_direction_radio.get_value()
        self.drill_array = self.draw_app.array_type_combo.get_value()
        try:
            self.drill_array_size = int(self.draw_app.drill_array_size_entry.get_value())
            try:
                self.drill_pitch = float(self.draw_app.drill_pitch_entry.get_value())
                self.drill_angle = float(self.draw_app.drill_angle_entry.get_value())
            except TypeError:
                self.draw_app.app.inform.emit(
                    "[error_notcl] The value is not Float. Check for comma instead of dot separator.")
                return
        except Exception as e:
            self.draw_app.app.inform.emit("[error_notcl] The value is mistyped. Check the value.")
            return

        if self.drill_array == 'Linear':
            # if self.origin is None:
            #     self.origin = (0, 0)
            #
            # dx = data[0] - self.origin[0]
            # dy = data[1] - self.origin[1]
            dx = data[0]
            dy = data[1]

            geo_list = []
            geo = None
            self.points = data

            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((data[0] + (self.drill_pitch * item)), data[1]))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((data[0], (data[1] + (self.drill_pitch * item))))
                if static is None or static is False:
                    geo_list.append(affinity.translate(geo, xoff=(dx - self.last_dx), yoff=(dy - self.last_dy)))
                else:
                    geo_list.append(geo)
            # self.origin = data

            self.last_dx = dx
            self.last_dy = dy
            return DrawToolUtilityShape(geo_list)
        else:
            if len(self.pt) > 0:
                temp_points = [x for x in self.pt]
                temp_points.append(data)
                return DrawToolUtilityShape(LineString(temp_points))


    def util_shape(self, point):
        start_hor_line = ((point[0] - (self.selected_dia / 2)), point[1])
        stop_hor_line = ((point[0] + (self.selected_dia / 2)), point[1])
        start_vert_line = (point[0], (point[1] - (self.selected_dia / 2)))
        stop_vert_line = (point[0], (point[1] + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):
        self.geometry = []
        geo = None

        # add the point to drills if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia not in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia] = []
        for i in range(self.drill_array_size):
            self.draw_app.points_edit[self.selected_dia].append(self.points)

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        if self.drill_array == 'Linear':
            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((self.points[0] + (self.drill_pitch * item)), self.points[1]))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((self.points[0], (self.points[1] + (self.drill_pitch * item))))

                self.geometry.append(DrawToolShape(geo))
        else:
            if (self.drill_angle * self.drill_array_size) > 360:
                self.draw_app.app.inform.emit("[warning_notcl]Too many drills for the selected spacing angle.")
                return

            radius = distance(self.destination, self.origin)
            initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)
            for i in range(self.drill_array_size):
                angle_radians = math.radians(self.drill_angle * i)
                if self.drill_direction == 'CW':
                    x = self.origin[0] + radius * math.cos(-angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(-angle_radians + initial_angle)
                else:
                    x = self.origin[0] + radius * math.cos(angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(angle_radians + initial_angle)

                geo = self.util_shape((x, y))
                self.geometry.append(DrawToolShape(geo))
        self.complete = True
        self.draw_app.app.inform.emit("[success]Done. Drill Array added.")
        self.draw_app.in_action = True
        self.draw_app.array_frame.hide()
        return

class FCDrillResize(FCShapeTool):

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.draw_app.app.inform.emit("Click on the Drill(s) to resize ...")
        self.resize_dia = None
        self.draw_app.resize_frame.show()
        self.points = None
        self.selected_dia_list = []
        self.current_storage = None
        self.geometry = []
        self.destination_storage = None

        self.draw_app.resize_btn.clicked.connect(self.make)

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def make(self):
        self.draw_app.is_modified = True

        try:
            new_dia = self.draw_app.resdrill_entry.get_value()
        except:
            self.draw_app.app.inform.emit("[error_notcl]Resize drill(s) failed. Please enter a diameter for resize.")
            return

        if new_dia not in self.draw_app.olddia_newdia:
            self.destination_storage = FlatCAMGeoEditor.make_storage()
            self.draw_app.storage_dict[new_dia] = self.destination_storage

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.draw_app.olddia_newdia[new_dia] = new_dia
        else:
            self.destination_storage = self.draw_app.storage_dict[new_dia]

        for index in self.draw_app.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.tools_table_exc.item(row, 1).text()
            self.selected_dia_list.append(float(dia_on_row))

        # since we add a new tool, we update also the intial state of the tool_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.draw_app.tool2tooldia[len(self.draw_app.olddia_newdia)] = new_dia

        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():
                    factor = new_dia / sel_dia
                    self.geometry.append(
                        DrawToolShape(affinity.scale(select_shape.geo, xfact=factor, yfact=factor, origin='center'))
                    )
                    self.current_storage.remove(select_shape)
                    # a hack to make the tool_table display less drills per diameter when shape(drill) is deleted
                    # self.points_edit it's only useful first time when we load the data into the storage
                    # but is still used as reference when building tool_table in self.build_ui()
                    # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                    # deleting self.points_edit elements (doesn't matter who but just the number)
                    # solved the display issue.
                    del self.draw_app.points_edit[sel_dia][0]

                    sel_shapes_to_be_deleted.append(select_shape)

                    self.draw_app.on_exc_shape_complete(self.destination_storage)
                    # a hack to make the tool_table display more drills per diameter when shape(drill) is added
                    # self.points_edit it's only useful first time when we load the data into the storage
                    # but is still used as reference when building tool_table in self.build_ui()
                    # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                    # deleting self.points_edit elements (doesn't matter who but just the number)
                    # solved the display issue.
                    if new_dia not in self.draw_app.points_edit:
                        self.draw_app.points_edit[new_dia] = [(0, 0)]
                    else:
                        self.draw_app.points_edit[new_dia].append((0,0))
                    self.geometry = []

                    # if following the resize of the drills there will be no more drills for the selected tool then
                    # delete that tool
                    if not self.draw_app.points_edit[sel_dia]:
                        self.draw_app.on_tool_delete(sel_dia)

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.replot()

        self.draw_app.resize_frame.hide()
        self.complete = True
        self.draw_app.app.inform.emit("[success]Done. Drill Resize completed.")

        # MS: always return to the Select Tool
        self.draw_app.select_tool("select")


class FCDrillMove(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        # self.shape_buffer = self.draw_app.shape_buffer
        self.origin = None
        self.destination = None
        self.selected_dia_list = []

        if self.draw_app.launched_from_shortcuts is True:
            self.draw_app.launched_from_shortcuts = False
            self.draw_app.app.inform.emit("Click on target location ...")
        else:
            self.draw_app.app.inform.emit("Click on reference location ...")
        self.current_storage = None
        self.geometry = []

        for index in self.draw_app.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.tools_table_exc.item(row, 1).text()
            self.selected_dia_list.append(float(dia_on_row))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def set_origin(self, origin):
        self.origin = origin

    def click(self, point):
        if len(self.draw_app.get_selected()) == 0:
            return "Nothing to move."

        if self.origin is None:
            self.set_origin(point)
            self.draw_app.app.inform.emit("Click on target location ...")
            return
        else:
            self.destination = point
            self.make()

            # MS: always return to the Select Tool
            self.draw_app.select_tool("select")
            return

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():

                    self.geometry.append(DrawToolShape(affinity.translate(select_shape.geo, xoff=dx, yoff=dy)))
                    self.current_storage.remove(select_shape)
                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit("[success]Done. Drill(s) Move completed.")

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        geo_list = []

        if self.origin is None:
            return None

        if len(self.draw_app.get_selected()) == 0:
            return None

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]
        for geom in self.draw_app.get_selected():
            geo_list.append(affinity.translate(geom.geo, xoff=dx, yoff=dy))
        return DrawToolUtilityShape(geo_list)


class FCDrillCopy(FCDrillMove):

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():
                    self.geometry.append(DrawToolShape(affinity.translate(select_shape.geo, xoff=dx, yoff=dy)))

                    # add some fake drills into the self.draw_app.points_edit to update the drill count in tool table
                    self.draw_app.points_edit[sel_dia].append((0, 0))

                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit("[success]Done. Drill(s) copied.")


########################
### Main Application ###
########################
class FlatCAMGeoEditor(QtCore.QObject):

    draw_shape_idx = -1

    def __init__(self, app, disabled=False):
        assert isinstance(app, FlatCAMApp.App), \
            "Expected the app to be a FlatCAMApp.App, got %s" % type(app)

        super(FlatCAMGeoEditor, self).__init__()

        self.app = app
        self.canvas = app.plotcanvas

        self.app.ui.geo_edit_toolbar.setDisabled(disabled)
        self.app.ui.snap_max_dist_entry.setDisabled(disabled)

        self.app.ui.geo_add_circle_menuitem.triggered.connect(lambda: self.select_tool('circle'))
        self.app.ui.geo_add_arc_menuitem.triggered.connect(lambda: self.select_tool('arc'))
        self.app.ui.geo_add_rectangle_menuitem.triggered.connect(lambda: self.select_tool('rectangle'))
        self.app.ui.geo_add_polygon_menuitem.triggered.connect(lambda: self.select_tool('polygon'))
        self.app.ui.geo_add_path_menuitem.triggered.connect(lambda: self.select_tool('path'))
        self.app.ui.geo_add_text_menuitem.triggered.connect(lambda: self.select_tool('text'))
        self.app.ui.geo_paint_menuitem.triggered.connect(self.on_paint_tool)
        self.app.ui.geo_buffer_menuitem.triggered.connect(self.on_buffer_tool)
        self.app.ui.geo_delete_menuitem.triggered.connect(self.on_delete_btn)
        self.app.ui.geo_union_menuitem.triggered.connect(self.union)
        self.app.ui.geo_intersection_menuitem.triggered.connect(self.intersection)
        self.app.ui.geo_subtract_menuitem.triggered.connect(self.subtract)
        self.app.ui.geo_cutpath_menuitem.triggered.connect(self.cutpath)
        self.app.ui.geo_copy_menuitem.triggered.connect(lambda: self.select_tool('copy'))

        self.app.ui.geo_union_btn.triggered.connect(self.union)
        self.app.ui.geo_intersection_btn.triggered.connect(self.intersection)
        self.app.ui.geo_subtract_btn.triggered.connect(self.subtract)
        self.app.ui.geo_cutpath_btn.triggered.connect(self.cutpath)
        self.app.ui.geo_delete_btn.triggered.connect(self.on_delete_btn)

        ## Toolbar events and properties
        self.tools = {
            "select": {"button": self.app.ui.geo_select_btn,
                       "constructor": FCSelect},
            "arc": {"button": self.app.ui.geo_add_arc_btn,
                    "constructor": FCArc},
            "circle": {"button": self.app.ui.geo_add_circle_btn,
                       "constructor": FCCircle},
            "path": {"button": self.app.ui.geo_add_path_btn,
                     "constructor": FCPath},
            "rectangle": {"button": self.app.ui.geo_add_rectangle_btn,
                          "constructor": FCRectangle},
            "polygon": {"button": self.app.ui.geo_add_polygon_btn,
                        "constructor": FCPolygon},
            "text": {"button": self.app.ui.geo_add_text_btn,
                     "constructor": FCText},
            "buffer": {"button": self.app.ui.geo_add_buffer_btn,
                     "constructor": FCBuffer},
            "paint": {"button": self.app.ui.geo_add_paint_btn,
                       "constructor": FCPaint},
            "move": {"button": self.app.ui.geo_move_btn,
                     "constructor": FCMove},
            "rotate": {"button": self.app.ui.geo_rotate_btn,
                     "constructor": FCRotate},
            "copy": {"button": self.app.ui.geo_copy_btn,
                     "constructor": FCCopy}
        }

        ### Data
        self.active_tool = None

        self.storage = FlatCAMGeoEditor.make_storage()
        self.utility = []

        # VisPy visuals
        self.fcgeometry = None
        self.shapes = self.app.plotcanvas.new_shape_collection(layers=1)
        self.tool_shape = self.app.plotcanvas.new_shape_collection(layers=1)
        self.app.pool_recreated.connect(self.pool_recreated)

        # Remove from scene
        self.shapes.enabled = False
        self.tool_shape.enabled = False

        ## List of selected shapes.
        self.selected = []

        self.flat_geo = []

        self.move_timer = QtCore.QTimer()
        self.move_timer.setSingleShot(True)

        self.key = None  # Currently pressed key
        self.geo_key_modifiers = None
        self.x = None  # Current mouse cursor pos
        self.y = None
        # Current snapped mouse pos
        self.snap_x = None
        self.snap_y = None
        self.pos = None

        # signal that there is an action active like polygon or path
        self.in_action = False

        def make_callback(thetool):
            def f():
                self.on_tool_select(thetool)
            return f

        for tool in self.tools:
            self.tools[tool]["button"].triggered.connect(make_callback(tool))  # Events
            self.tools[tool]["button"].setCheckable(True)  # Checkable

        self.app.ui.grid_snap_btn.triggered.connect(self.on_grid_toggled)
        self.app.ui.corner_snap_btn.triggered.connect(lambda: self.toolbar_tool_toggle("corner_snap"))

        self.options = {
            "global_gridx": 0.1,
            "global_gridy": 0.1,
            "snap_max": 0.05,
            "grid_snap": True,
            "corner_snap": False,
            "grid_gap_link": True
        }
        self.app.options_read_form()

        for option in self.options:
            if option in self.app.options:
                self.options[option] = self.app.options[option]

        self.app.ui.grid_gap_x_entry.setText(str(self.options["global_gridx"]))
        self.app.ui.grid_gap_y_entry.setText(str(self.options["global_gridy"]))
        self.app.ui.snap_max_dist_entry.setText(str(self.options["snap_max"]))
        self.app.ui.grid_gap_link_cb.setChecked(True)

        self.rtree_index = rtindex.Index()

        def entry2option(option, entry):
            try:
                self.options[option] = float(entry.text())
            except Exception as e:
                log.debug(str(e))

        self.app.ui.grid_gap_x_entry.setValidator(QtGui.QDoubleValidator())
        self.app.ui.grid_gap_x_entry.textChanged.connect(
            lambda: entry2option("global_gridx", self.app.ui.grid_gap_x_entry))

        self.app.ui.grid_gap_y_entry.setValidator(QtGui.QDoubleValidator())
        self.app.ui.grid_gap_y_entry.textChanged.connect(
            lambda: entry2option("global_gridy", self.app.ui.grid_gap_y_entry))

        self.app.ui.snap_max_dist_entry.setValidator(QtGui.QDoubleValidator())
        self.app.ui.snap_max_dist_entry.textChanged.connect(
            lambda: entry2option("snap_max", self.app.ui.snap_max_dist_entry))

        # store the status of the editor so the Delete at object level will not work until the edit is finished
        self.editor_active = False

        # if using Paint store here the tool diameter used
        self.paint_tooldia = None

    def pool_recreated(self, pool):
        self.shapes.pool = pool
        self.tool_shape.pool = pool

    def activate(self):
        self.connect_canvas_event_handlers()
        self.shapes.enabled = True
        self.tool_shape.enabled = True
        self.app.app_cursor.enabled = True
        self.app.ui.snap_max_dist_entry.setDisabled(False)
        self.app.ui.corner_snap_btn.setEnabled(True)

        self.app.ui.geo_editor_menu.setDisabled(False)
        # Tell the App that the editor is active
        self.editor_active = True

    def deactivate(self):
        self.disconnect_canvas_event_handlers()
        self.clear()
        self.app.ui.geo_edit_toolbar.setDisabled(True)
        self.app.ui.geo_edit_toolbar.setVisible(False)
        self.app.ui.snap_max_dist_entry.setDisabled(True)
        self.app.ui.corner_snap_btn.setEnabled(False)
        # never deactivate the snap toolbar - MS
        # self.app.ui.snap_toolbar.setDisabled(True)  # TODO: Combine and move into tool

        # Disable visuals
        self.shapes.enabled = False
        self.tool_shape.enabled = False
        self.app.app_cursor.enabled = False

        self.app.ui.geo_editor_menu.setDisabled(True)
        # Tell the app that the editor is no longer active
        self.editor_active = False

        # Show original geometry
        if self.fcgeometry:
            self.fcgeometry.visible = True

    def connect_canvas_event_handlers(self):
        ## Canvas events

        # make sure that the shortcuts key and mouse events will no longer be linked to the methods from FlatCAMApp
        # but those from FlatCAMGeoEditor
        self.app.plotcanvas.vis_disconnect('key_press', self.app.on_key_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_release', self.app.on_mouse_click_release_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_double_click', self.app.on_double_click_over_plot)
        self.app.collection.view.keyPressed.disconnect()
        self.app.collection.view.clicked.disconnect()

        self.canvas.vis_connect('mouse_press', self.on_canvas_click)
        self.canvas.vis_connect('mouse_move', self.on_canvas_move)
        self.canvas.vis_connect('mouse_release', self.on_canvas_click_release)
        self.canvas.vis_connect('key_press', self.on_canvas_key)
        self.canvas.vis_connect('key_release', self.on_canvas_key_release)

    def disconnect_canvas_event_handlers(self):

        self.canvas.vis_disconnect('mouse_press', self.on_canvas_click)
        self.canvas.vis_disconnect('mouse_move', self.on_canvas_move)
        self.canvas.vis_disconnect('mouse_release', self.on_canvas_click_release)
        self.canvas.vis_disconnect('key_press', self.on_canvas_key)
        self.canvas.vis_disconnect('key_release', self.on_canvas_key_release)

        # we restore the key and mouse control to FlatCAMApp method
        self.app.plotcanvas.vis_connect('key_press', self.app.on_key_over_plot)
        self.app.plotcanvas.vis_connect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.plotcanvas.vis_connect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.plotcanvas.vis_connect('mouse_release', self.app.on_mouse_click_release_over_plot)
        self.app.plotcanvas.vis_connect('mouse_double_click', self.app.on_double_click_over_plot)
        self.app.collection.view.keyPressed.connect(self.app.collection.on_key)
        self.app.collection.view.clicked.connect(self.app.collection.on_mouse_down)

    def add_shape(self, shape):
        """
        Adds a shape to the shape storage.

        :param shape: Shape to be added.
        :type shape: DrawToolShape
        :return: None
        """

        # List of DrawToolShape?
        if isinstance(shape, list):
            for subshape in shape:
                self.add_shape(subshape)
            return

        assert isinstance(shape, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % type(shape)

        assert shape.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shape.geo, list) and len(shape.geo) > 0) or \
               not isinstance(shape.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shape, DrawToolUtilityShape):
            self.utility.append(shape)
        else:
            self.storage.insert(shape)  # TODO: Check performance

    def delete_utility_geometry(self):
        # for_deletion = [shape for shape in self.shape_buffer if shape.utility]
        # for_deletion = [shape for shape in self.storage.get_objects() if shape.utility]
        for_deletion = [shape for shape in self.utility]
        for shape in for_deletion:
            self.delete_shape(shape)

        self.tool_shape.clear(update=True)
        self.tool_shape.redraw()

    def cutpath(self):
        selected = self.get_selected()
        tools = selected[1:]
        toolgeo = cascaded_union([shp.geo for shp in tools])

        target = selected[0]
        if type(target.geo) == Polygon:
            for ring in poly2rings(target.geo):
                self.add_shape(DrawToolShape(ring.difference(toolgeo)))
            self.delete_shape(target)
        elif type(target.geo) == LineString or type(target.geo) == LinearRing:
            self.add_shape(DrawToolShape(target.geo.difference(toolgeo)))
            self.delete_shape(target)
        elif type(target.geo) == MultiLineString:
            try:
                for linestring in target.geo.geoms:
                    self.add_shape(DrawToolShape(linestring.difference(toolgeo)))
            except:
                self.app.log.warning("Current LinearString does not intersect the target")
            self.delete_shape(target)
        else:
            self.app.log.warning("Not implemented. Object type: %s" % str(type(target.geo)))

        self.replot()

    def toolbar_tool_toggle(self, key):
        self.options[key] = self.sender().isChecked()
        if self.options[key] == True:
            return 1
        else:
            return 0

    def clear(self):
        self.active_tool = None
        # self.shape_buffer = []
        self.selected = []
        self.shapes.clear(update=True)
        self.tool_shape.clear(update=True)

        self.storage = FlatCAMGeoEditor.make_storage()
        self.replot()

    def edit_fcgeometry(self, fcgeometry):
        """
        Imports the geometry from the given FlatCAM Geometry object
        into the editor.

        :param fcgeometry: FlatCAMGeometry
        :return: None
        """
        assert isinstance(fcgeometry, Geometry), \
            "Expected a Geometry, got %s" % type(fcgeometry)

        self.deactivate()
        self.activate()

        # Hide original geometry
        self.fcgeometry = fcgeometry
        fcgeometry.visible = False

        # Set selection tolerance
        DrawToolShape.tolerance = fcgeometry.drawing_tolerance * 10

        self.select_tool("select")

        # Link shapes into editor.
        for shape in fcgeometry.flatten():
            if shape is not None:  # TODO: Make flatten never create a None
                if type(shape) == Polygon:
                    self.add_shape(DrawToolShape(shape.exterior))
                    for inter in shape.interiors:
                        self.add_shape(DrawToolShape(inter))
                else:
                    self.add_shape(DrawToolShape(shape))

        self.replot()
        self.app.ui.geo_edit_toolbar.setDisabled(False)
        self.app.ui.geo_edit_toolbar.setVisible(True)
        self.app.ui.snap_toolbar.setDisabled(False)

        # start with GRID toolbar activated
        if self.app.ui.grid_snap_btn.isChecked() == False:
            self.app.ui.grid_snap_btn.trigger()

    def on_buffer_tool(self):
        buff_tool = BufferSelectionTool(self.app, self)
        buff_tool.run()

    def on_paint_tool(self):
        paint_tool = PaintOptionsTool(self.app, self)
        paint_tool.run()

    def on_tool_select(self, tool):
        """
        Behavior of the toolbar. Tool initialization.

        :rtype : None
        """
        self.app.log.debug("on_tool_select('%s')" % tool)

        # This is to make the group behave as radio group
        if tool in self.tools:
            if self.tools[tool]["button"].isChecked():
                self.app.log.debug("%s is checked." % tool)
                for t in self.tools:
                    if t != tool:
                        self.tools[t]["button"].setChecked(False)

                self.active_tool = self.tools[tool]["constructor"](self)
                if not isinstance(self.active_tool, FCSelect):
                    self.app.inform.emit(self.active_tool.start_msg)
            else:
                self.app.log.debug("%s is NOT checked." % tool)
                for t in self.tools:
                    self.tools[t]["button"].setChecked(False)
                self.active_tool = None

    def draw_tool_path(self):
        self.select_tool('path')
        return

    def draw_tool_rectangle(self):
        self.select_tool('rectangle')
        return

    def on_grid_toggled(self):
        self.toolbar_tool_toggle("grid_snap")

        # make sure that the cursor shape is enabled/disabled, too
        if self.options['grid_snap'] is True:
            self.app.app_cursor.enabled = True
        else:
            self.app.app_cursor.enabled = False

    def on_canvas_click(self, event):
        """
        event.x and .y have canvas coordinates
        event.xdaya and .ydata have plot coordinates

        :param event: Event object dispatched by Matplotlib
        :return: None
        """

        if event.button is 1:
            self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                                   "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (0, 0))
            self.pos = self.canvas.vispy_canvas.translate_coords(event.pos)

            ### Snap coordinates
            x, y = self.snap(self.pos[0], self.pos[1])

            self.pos = (x, y)

            # Selection with left mouse button
            if self.active_tool is not None and event.button is 1:
                # Dispatch event to active_tool
                # msg = self.active_tool.click(self.snap(event.xdata, event.ydata))
                msg = self.active_tool.click(self.snap(self.pos[0], self.pos[1]))

                # If it is a shape generating tool
                if isinstance(self.active_tool, FCShapeTool) and self.active_tool.complete:
                    self.on_shape_complete()

                    # MS: always return to the Select Tool
                    self.select_tool("select")
                    return

                if isinstance(self.active_tool, FCSelect):
                    # self.app.log.debug("Replotting after click.")
                    self.replot()

            else:
                self.app.log.debug("No active tool to respond to click!")

    def on_canvas_move(self, event):
        """
        Called on 'mouse_move' event

        event.pos have canvas screen coordinates

        :param event: Event object dispatched by VisPy SceneCavas
        :return: None
        """

        pos = self.canvas.vispy_canvas.translate_coords(event.pos)
        event.xdata, event.ydata = pos[0], pos[1]

        self.x = event.xdata
        self.y = event.ydata

        # Prevent updates on pan
        # if len(event.buttons) > 0:
        #     return

        # if the RMB is clicked and mouse is moving over plot then 'panning_action' is True
        if event.button == 2:
            self.app.panning_action = True
            return
        else:
            self.app.panning_action = False

        try:
            x = float(event.xdata)
            y = float(event.ydata)
        except TypeError:
            return

        if self.active_tool is None:
            return

        ### Snap coordinates
        x, y = self.snap(x, y)

        self.snap_x = x
        self.snap_y = y

        # update the position label in the infobar since the APP mouse event handlers are disconnected
        self.app.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
                                       "<b>Y</b>: %.4f" % (x, y))

        if self.pos is None:
            self.pos = (0, 0)
        dx = x - self.pos[0]
        dy = y - self.pos[1]

        # update the reference position label in the infobar since the APP mouse event handlers are disconnected
        self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                           "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (dx, dy))

        ### Utility geometry (animated)
        geo = self.active_tool.utility_geometry(data=(x, y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:

            # Remove any previous utility shape
            self.tool_shape.clear(update=True)
            self.draw_utility_geometry(geo=geo)

        ### Selection area on canvas section ###
        dx = pos[0] - self.pos[0]
        if event.is_dragging == 1 and event.button == 1:
            self.app.delete_selection_shape()
            if dx < 0:
                self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x,y),
                     color=self.app.defaults["global_alt_sel_line"],
                     face_color=self.app.defaults['global_alt_sel_fill'])
                self.app.selection_type = False
            else:
                self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x,y))
                self.app.selection_type = True
        else:
            self.app.selection_type = None

        # Update cursor
        self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color='black', size=20)

    def on_canvas_click_release(self, event):
        pos_canvas = self.canvas.vispy_canvas.translate_coords(event.pos)

        if self.app.grid_status():
            pos = self.snap(pos_canvas[0], pos_canvas[1])
        else:
            pos = (pos_canvas[0], pos_canvas[1])

        # if the released mouse button was RMB then test if it was a panning motion or not, if not it was a context
        # canvas menu
        try:
            if event.button == 2:  # right click
                if self.app.panning_action is True:
                    self.app.panning_action = False
                else:
                    if self.in_action is False:
                        self.app.cursor = QtGui.QCursor()
                        self.app.ui.popMenu.popup(self.app.cursor.pos())
                    else:
                        # if right click on canvas and the active tool need to be finished (like Path or Polygon)
                        # right mouse click will finish the action
                        if isinstance(self.active_tool, FCShapeTool):
                            self.active_tool.click(self.snap(self.x, self.y))
                            self.active_tool.make()
                            if self.active_tool.complete:
                                self.on_shape_complete()
                                self.app.inform.emit("[success]Done.")
                            # automatically make the selection tool active after completing current action
                            self.select_tool('select')
        except Exception as e:
            log.warning("Error: %s" % str(e))
            return

        # if the released mouse button was LMB then test if we had a right-to-left selection or a left-to-right
        # selection and then select a type of selection ("enclosing" or "touching")
        try:
            if event.button == 1:  # left click
                if self.app.selection_type is not None:
                    self.draw_selection_area_handler(self.pos, pos, self.app.selection_type)
                    self.app.selection_type = None
                elif isinstance(self.active_tool, FCSelect):
                    # Dispatch event to active_tool
                    # msg = self.active_tool.click(self.snap(event.xdata, event.ydata))
                    msg = self.active_tool.click_release((self.pos[0], self.pos[1]))
                    self.app.inform.emit(msg)
                    self.replot()
        except Exception as e:
            log.warning("Error: %s" % str(e))
            return

    def draw_selection_area_handler(self, start_pos, end_pos, sel_type):
        """

        :param start_pos: mouse position when the selection LMB click was done
        :param end_pos: mouse position when the left mouse button is released
        :param sel_type: if True it's a left to right selection (enclosure), if False it's a 'touch' selection
        :type Bool
        :return:
        """
        poly_selection = Polygon([start_pos, (end_pos[0], start_pos[1]), end_pos, (start_pos[0], end_pos[1])])

        self.app.delete_selection_shape()
        for obj in self.storage.get_objects():
            if (sel_type is True and poly_selection.contains(obj.geo)) or \
                    (sel_type is False and poly_selection.intersects(obj.geo)):
                    if self.key == self.app.defaults["global_mselect_key"]:
                        if obj in self.selected:
                            self.selected.remove(obj)
                        else:
                            # add the object to the selected shapes
                            self.selected.append(obj)
                    else:
                        self.selected.append(obj)
        self.replot()

    def draw_utility_geometry(self, geo):
            # Add the new utility shape
            try:
                # this case is for the Font Parse
                for el in list(geo.geo):
                    if type(el) == MultiPolygon:
                        for poly in el.geoms:
                            self.tool_shape.add(
                                shape=poly,
                                color=(self.app.defaults["global_draw_color"] + '80'),
                                update=False,
                                layer=0,
                                tolerance=None
                            )
                    elif type(el) == MultiLineString:
                        for linestring in el.geoms:
                            self.tool_shape.add(
                                shape=linestring,
                                color=(self.app.defaults["global_draw_color"] + '80'),
                                update=False,
                                layer=0,
                                tolerance=None
                            )
                    else:
                        self.tool_shape.add(
                            shape=el,
                            color=(self.app.defaults["global_draw_color"] + '80'),
                            update=False,
                            layer=0,
                            tolerance=None
                        )
            except TypeError:
                self.tool_shape.add(
                    shape=geo.geo, color=(self.app.defaults["global_draw_color"] + '80'),
                    update=False, layer=0, tolerance=None)

            self.tool_shape.redraw()

    def on_canvas_key(self, event):
        """
        event.key has the key.

        :param event:
        :return:
        """
        self.key = event.key.name
        self.geo_key_modifiers = QtWidgets.QApplication.keyboardModifiers()

        if self.geo_key_modifiers == Qt.ControlModifier:
            # save (update) the current geometry and return to the App
            if self.key == 'S':
                self.app.editor2object()
                return

            # toggle the measurement tool
            if self.key == 'M':
                self.app.measurement_tool.run()
                return

        # Finish the current action. Use with tools that do not
        # complete automatically, like a polygon or path.
        if event.key.name == 'Enter':
            if isinstance(self.active_tool, FCShapeTool):
                self.active_tool.click(self.snap(self.x, self.y))
                self.active_tool.make()
                if self.active_tool.complete:
                    self.on_shape_complete()
                    self.app.inform.emit("[success]Done.")
                # automatically make the selection tool active after completing current action
                self.select_tool('select')
            return

        # Abort the current action
        if event.key.name == 'Escape':
            # TODO: ...?
            # self.on_tool_select("select")
            self.app.inform.emit("[warning_notcl]Cancelled.")

            self.delete_utility_geometry()

            self.replot()
            # self.select_btn.setChecked(True)
            # self.on_tool_select('select')
            self.select_tool('select')
            return

        # Delete selected object
        if event.key.name == 'Delete':
            self.delete_selected()
            self.replot()

        # Move
        if event.key.name == 'Space':
            self.app.ui.geo_rotate_btn.setChecked(True)
            self.on_tool_select('rotate')
            self.active_tool.set_origin(self.snap(self.x, self.y))

        # Arc Tool
        if event.key.name == 'A':
            self.select_tool('arc')

        # Buffer
        if event.key.name == 'B':
            self.select_tool('buffer')

        # Copy
        if event.key.name == 'C':
            self.app.ui.geo_copy_btn.setChecked(True)
            self.on_tool_select('copy')
            self.active_tool.set_origin(self.snap(self.x, self.y))
            self.app.inform.emit("Click on target point.")

        # Grid Snap
        if event.key.name == 'G':
            self.app.ui.grid_snap_btn.trigger()

            # make sure that the cursor shape is enabled/disabled, too
            if self.options['grid_snap'] is True:
                self.app.app_cursor.enabled = True
            else:
                self.app.app_cursor.enabled = False

        # Paint
        if event.key.name == 'I':
            self.select_tool('paint')

        # Corner Snap
        if event.key.name == 'K':
            self.app.ui.corner_snap_btn.trigger()

        # Move
        if event.key.name == 'M':
            self.app.ui.geo_move_btn.setChecked(True)
            self.on_tool_select('move')
            self.active_tool.set_origin(self.snap(self.x, self.y))
            self.app.inform.emit("Click on target point.")

        # Polygon Tool
        if event.key.name == 'N':
            self.select_tool('polygon')

        # Circle Tool
        if event.key.name == 'O':
            self.select_tool('circle')

        # Path Tool
        if event.key.name == 'P':
            self.select_tool('path')

        # Rectangle Tool
        if event.key.name == 'R':
            self.select_tool('rectangle')

        # Select Tool
        if event.key.name == 'S':
            self.select_tool('select')

        # Add Text Tool
        if event.key.name == 'T':
            self.select_tool('text')

        # Cut Action Tool
        if event.key.name == 'X':
            if self.get_selected() is not None:
                self.cutpath()
            else:
                msg = 'Please first select a geometry item to be cutted\n' \
                      'then select the geometry item that will be cutted\n' \
                      'out of the first item. In the end press ~X~ key or\n' \
                      'the toolbar button.' \

                messagebox =QtWidgets.QMessageBox()
                messagebox.setText(msg)
                messagebox.setWindowTitle("Warning")
                messagebox.setWindowIcon(QtGui.QIcon('share/warning.png'))
                messagebox.setStandardButtons(QtWidgets.QMessageBox.Ok)
                messagebox.setDefaultButton(QtWidgets.QMessageBox.Ok)
                messagebox.exec_()

        # Propagate to tool
        response = None
        if self.active_tool is not None:
            response = self.active_tool.on_key(event.key)
        if response is not None:
            self.app.inform.emit(response)

        # Show Shortcut list
        if event.key.name == '`':
            self.on_shortcut_list()

    def on_shortcut_list(self):
        msg = '''<b>Shortcut list in Geometry Editor</b><br>
<br>
<b>A:</b>       Add an 'Arc'<br>
<b>B:</b>       Add a Buffer Geo<br>
<b>C:</b>       Copy Geo Item<br>
<b>G:</b>       Grid Snap On/Off<br>
<b>G:</b>       Paint Tool<br>
<b>K:</b>       Corner Snap On/Off<br>
<b>M:</b>       Move Geo Item<br>
<br>
<b>N:</b>       Add an 'Polygon'<br>
<b>O:</b>       Add a 'Circle'<br>
<b>P:</b>       Add a 'Path'<br>
<b>R:</b>       Add an 'Rectangle'<br>
<b>S:</b>       Select Tool Active<br>
<b>T:</b>       Add Text Geometry<br>
<br>
<b>X:</b>       Cut Path<br>
<br>
<b>~:</b>       Show Shortcut List<br>
<br>
<b>Space:</b>   Rotate selected Geometry<br>
<b>Enter:</b>   Finish Current Action<br>
<b>Escape:</b>  Abort Current Action<br>
<b>Delete:</b>  Delete Obj'''

        helpbox =QtWidgets.QMessageBox()
        helpbox.setText(msg)
        helpbox.setWindowTitle("Help")
        helpbox.setWindowIcon(QtGui.QIcon('share/help.png'))
        helpbox.setStandardButtons(QtWidgets.QMessageBox.Ok)
        helpbox.setDefaultButton(QtWidgets.QMessageBox.Ok)
        helpbox.exec_()

    def on_canvas_key_release(self, event):
        self.key = None

    def on_delete_btn(self):
        self.delete_selected()
        self.replot()

    def delete_selected(self):
        tempref = [s for s in self.selected]
        for shape in tempref:
            self.delete_shape(shape)

        self.selected = []

    def delete_shape(self, shape):

        if shape in self.utility:
            self.utility.remove(shape)
            return

        self.storage.remove(shape)

        if shape in self.selected:
            self.selected.remove(shape)  # TODO: Check performance

    def get_selected(self):
        """
        Returns list of shapes that are selected in the editor.

        :return: List of shapes.
        """
        # return [shape for shape in self.shape_buffer if shape["selected"]]
        return self.selected

    def plot_shape(self, geometry=None, color='black', linewidth=1):
        """
        Plots a geometric object or list of objects without rendering. Plotted objects
        are returned as a list. This allows for efficient/animated rendering.

        :param geometry: Geometry to be plotted (Any Shapely.geom kind or list of such)
        :param color: Shape color
        :param linewidth: Width of lines in # of pixels.
        :return: List of plotted elements.
        """
        plot_elements = []

        if geometry is None:
            geometry = self.active_tool.geometry

        try:
            for geo in geometry.geoms:
                plot_elements += self.plot_shape(geometry=geo, color=color, linewidth=linewidth)

        ## Non-iterable
        except TypeError:

            ## DrawToolShape
            if isinstance(geometry, DrawToolShape):
                plot_elements += self.plot_shape(geometry=geometry.geo, color=color, linewidth=linewidth)

            ## Polygon: Descend into exterior and each interior.
            if type(geometry) == Polygon:
                plot_elements += self.plot_shape(geometry=geometry.exterior, color=color, linewidth=linewidth)
                plot_elements += self.plot_shape(geometry=geometry.interiors, color=color, linewidth=linewidth)

            if type(geometry) == LineString or type(geometry) == LinearRing:
                plot_elements.append(self.shapes.add(shape=geometry, color=color, layer=0,
                                                     tolerance=self.fcgeometry.drawing_tolerance))

            if type(geometry) == Point:
                pass

        return plot_elements

    def plot_all(self):
        """
        Plots all shapes in the editor.

        :return: None
        :rtype: None
        """
        # self.app.log.debug("plot_all()")
        self.shapes.clear(update=True)

        for shape in self.storage.get_objects():

            if shape.geo is None:  # TODO: This shouldn't have happened
                continue

            if shape in self.selected:
                self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_sel_draw_color'], linewidth=2)
                continue

            self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_draw_color'])

        for shape in self.utility:
            self.plot_shape(geometry=shape.geo, linewidth=1)
            continue

        self.shapes.redraw()

    def replot(self):
        self.plot_all()

    def on_shape_complete(self):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        self.add_shape(self.active_tool.geometry)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    @staticmethod
    def make_storage():

        ## Shape storage.
        storage = FlatCAMRTreeStorage()
        storage.get_points = DrawToolShape.get_pts

        return storage

    def select_tool(self, toolname):
        """
        Selects a drawing tool. Impacts the object and GUI.

        :param toolname: Name of the tool.
        :return: None
        """
        self.tools[toolname]["button"].setChecked(True)
        self.on_tool_select(toolname)

    def set_selected(self, shape):

        # Remove and add to the end.
        if shape in self.selected:
            self.selected.remove(shape)

        self.selected.append(shape)

    def set_unselected(self, shape):
        if shape in self.selected:
            self.selected.remove(shape)

    def snap(self, x, y):
        """
        Adjusts coordinates to snap settings.

        :param x: Input coordinate X
        :param y: Input coordinate Y
        :return: Snapped (x, y)
        """

        snap_x, snap_y = (x, y)
        snap_distance = Inf

        ### Object (corner?) snap
        ### No need for the objects, just the coordinates
        ### in the index.
        if self.options["corner_snap"]:
            try:
                nearest_pt, shape = self.storage.nearest((x, y))

                nearest_pt_distance = distance((x, y), nearest_pt)
                if nearest_pt_distance <= self.options["snap_max"]:
                    snap_distance = nearest_pt_distance
                    snap_x, snap_y = nearest_pt
            except (StopIteration, AssertionError):
                pass

        ### Grid snap
        if self.options["grid_snap"]:
            if self.options["global_gridx"] != 0:
                snap_x_ = round(x / self.options["global_gridx"]) * self.options['global_gridx']
            else:
                snap_x_ = x

            # If the Grid_gap_linked on Grid Toolbar is checked then the snap distance on GridY entry will be ignored
            # and it will use the snap distance from GridX entry
            if self.app.ui.grid_gap_link_cb.isChecked():
                if self.options["global_gridx"] != 0:
                    snap_y_ = round(y / self.options["global_gridx"]) * self.options['global_gridx']
                else:
                    snap_y_ = y
            else:
                if self.options["global_gridy"] != 0:
                    snap_y_ = round(y / self.options["global_gridy"]) * self.options['global_gridy']
                else:
                    snap_y_ = y
            nearest_grid_distance = distance((x, y), (snap_x_, snap_y_))
            if nearest_grid_distance < snap_distance:
                snap_x, snap_y = (snap_x_, snap_y_)

        return snap_x, snap_y

    def update_fcgeometry(self, fcgeometry):
        """
        Transfers the geometry tool shape buffer to the selected geometry
        object. The geometry already in the object are removed.

        :param fcgeometry: FlatCAMGeometry
        :return: None
        """
        fcgeometry.solid_geometry = []
        # for shape in self.shape_buffer:
        for shape in self.storage.get_objects():
            fcgeometry.solid_geometry.append(shape.geo)

        # re-enable all the widgets in the Selected Tab that were disabled after entering in Edit Geometry Mode
        sel_tab_widget_list = self.app.ui.selected_tab.findChildren(QtWidgets.QWidget)
        for w in sel_tab_widget_list:
            w.setEnabled(True)

    def update_options(self, obj):
        if self.paint_tooldia:
            obj.options['cnctooldia'] = self.paint_tooldia
            self.paint_tooldia = None
            return True
        else:
            return False

    def union(self):
        """
        Makes union of selected polygons. Original polygons
        are deleted.

        :return: None.
        """

        results = cascaded_union([t.geo for t in self.get_selected()])

        # Delete originals.
        for_deletion = [s for s in self.get_selected()]
        for shape in for_deletion:
            self.delete_shape(shape)

        # Selected geometry is now gone!
        self.selected = []

        self.add_shape(DrawToolShape(results))

        self.replot()

    def intersection(self):
        """
        Makes intersectino of selected polygons. Original polygons are deleted.

        :return: None
        """

        shapes = self.get_selected()

        results = shapes[0].geo

        for shape in shapes[1:]:
            results = results.intersection(shape.geo)

        # Delete originals.
        for_deletion = [s for s in self.get_selected()]
        for shape in for_deletion:
            self.delete_shape(shape)

        # Selected geometry is now gone!
        self.selected = []

        self.add_shape(DrawToolShape(results))

        self.replot()

    def subtract(self):
        selected = self.get_selected()
        try:
            tools = selected[1:]
            toolgeo = cascaded_union([shp.geo for shp in tools])
            result = selected[0].geo.difference(toolgeo)

            self.delete_shape(selected[0])
            self.add_shape(DrawToolShape(result))

            self.replot()
        except Exception as e:
            log.debug(str(e))

    def buffer(self, buf_distance, join_style):
        selected = self.get_selected()

        if buf_distance < 0:
            self.app.inform.emit(
                "[error_notcl]Negative buffer value is not accepted. Use Buffer interior to generate an 'inside' shape")

            # deselect everything
            self.selected = []
            self.replot()
            return

        if len(selected) == 0:
            self.app.inform.emit("[warning_notcl] Nothing selected for buffering.")
            return

        if not isinstance(buf_distance, float):
            self.app.inform.emit("[warning_notcl] Invalid distance for buffering.")

            # deselect everything
            self.selected = []
            self.replot()
            return

        pre_buffer = cascaded_union([t.geo for t in selected])
        results = pre_buffer.buffer(buf_distance - 1e-10, resolution=32, join_style=join_style)
        if results.is_empty:
            self.app.inform.emit("[error_notcl]Failed, the result is empty. Choose a different buffer value.")
            # deselect everything
            self.selected = []
            self.replot()
            return
        self.add_shape(DrawToolShape(results))

        self.replot()
        self.app.inform.emit("[success]Full buffer geometry created.")

    def buffer_int(self, buf_distance, join_style):
        selected = self.get_selected()

        if buf_distance < 0:
            self.app.inform.emit(
                "[error_notcl]Negative buffer value is not accepted. Use Buffer interior to generate an 'inside' shape")
            # deselect everything
            self.selected = []
            self.replot()
            return

        if len(selected) == 0:
            self.app.inform.emit("[warning_notcl] Nothing selected for buffering.")
            return

        if not isinstance(buf_distance, float):
            self.app.inform.emit("[warning_notcl] Invalid distance for buffering.")
            # deselect everything
            self.selected = []
            self.replot()
            return

        pre_buffer = cascaded_union([t.geo for t in selected])
        results = pre_buffer.buffer(-buf_distance + 1e-10, resolution=32, join_style=join_style)
        if results.is_empty:
            self.app.inform.emit("[error_notcl]Failed, the result is empty. Choose a smaller buffer value.")
            # deselect everything
            self.selected = []
            self.replot()
            return
        if type(results) == MultiPolygon:
            for poly in results.geoms:
                self.add_shape(DrawToolShape(poly.exterior))
        else:
            self.add_shape(DrawToolShape(results.exterior))

        self.replot()
        self.app.inform.emit("[success]Exterior buffer geometry created.")
        # selected = self.get_selected()
        #
        # if len(selected) == 0:
        #     self.app.inform.emit("[WARNING] Nothing selected for buffering.")
        #     return
        #
        # if not isinstance(buf_distance, float):
        #     self.app.inform.emit("[warning] Invalid distance for buffering.")
        #     return
        #
        # pre_buffer = cascaded_union([t.geo for t in selected])
        # results = pre_buffer.buffer(buf_distance)
        # if results.is_empty:
        #     self.app.inform.emit("Failed. Choose a smaller buffer value.")
        #     return
        #
        # int_geo = []
        # if type(results) == MultiPolygon:
        #     for poly in results:
        #         for g in poly.interiors:
        #             int_geo.append(g)
        #         res = cascaded_union(int_geo)
        #         self.add_shape(DrawToolShape(res))
        # else:
        #     print(results.interiors)
        #     for g in results.interiors:
        #         int_geo.append(g)
        #     res = cascaded_union(int_geo)
        #     self.add_shape(DrawToolShape(res))
        #
        # self.replot()
        # self.app.inform.emit("Interior buffer geometry created.")

    def buffer_ext(self, buf_distance, join_style):
        selected = self.get_selected()

        if buf_distance < 0:
            self.app.inform.emit("[error_notcl]Negative buffer value is not accepted. "
                                 "Use Buffer interior to generate an 'inside' shape")
            # deselect everything
            self.selected = []
            self.replot()
            return

        if len(selected) == 0:
            self.app.inform.emit("[warning_notcl] Nothing selected for buffering.")
            return

        if not isinstance(buf_distance, float):
            self.app.inform.emit("[warning_notcl] Invalid distance for buffering.")
            # deselect everything
            self.selected = []
            self.replot()
            return

        pre_buffer = cascaded_union([t.geo for t in selected])
        results = pre_buffer.buffer(buf_distance - 1e-10, resolution=32, join_style=join_style)
        if results.is_empty:
            self.app.inform.emit("[error_notcl]Failed, the result is empty. Choose a different buffer value.")
            # deselect everything
            self.selected = []
            self.replot()
            return
        if type(results) == MultiPolygon:
            for poly in results.geoms:
                self.add_shape(DrawToolShape(poly.exterior))
        else:
            self.add_shape(DrawToolShape(results.exterior))

        self.replot()
        self.app.inform.emit("[success]Exterior buffer geometry created.")

    # def paint(self, tooldia, overlap, margin, method):
    #     selected = self.get_selected()
    #
    #     if len(selected) == 0:
    #         self.app.inform.emit("[warning] Nothing selected for painting.")
    #         return
    #
    #     for param in [tooldia, overlap, margin]:
    #         if not isinstance(param, float):
    #             param_name = [k for k, v in locals().items() if v is param][0]
    #             self.app.inform.emit("[warning] Invalid value for {}".format(param))
    #
    #     # Todo: Check for valid method.
    #
    #     # Todo: This is the 3rd implementation on painting polys... try to consolidate
    #
    #     results = []
    #
    #     def recurse(geo):
    #         try:
    #             for subg in geo:
    #                 for subsubg in recurse(subg):
    #                     yield subsubg
    #         except TypeError:
    #             if isinstance(geo, LinearRing):
    #                 yield geo
    #
    #         raise StopIteration
    #
    #     for geo in selected:
    #         print(type(geo.geo))
    #
    #         local_results = []
    #         for poly in recurse(geo.geo):
    #             if method == "seed":
    #                 # Type(cp) == FlatCAMRTreeStorage | None
    #                 cp = Geometry.clear_polygon2(poly.buffer(-margin),
    #                                              tooldia, overlap=overlap)
    #
    #             else:
    #                 # Type(cp) == FlatCAMRTreeStorage | None
    #                 cp = Geometry.clear_polygon(poly.buffer(-margin),
    #                                             tooldia, overlap=overlap)
    #
    #             if cp is not None:
    #                 local_results += list(cp.get_objects())
    #
    #             results.append(cascaded_union(local_results))
    #
    #     # This is a dirty patch:
    #     for r in results:
    #         self.add_shape(DrawToolShape(r))
    #
    #     self.replot()

    def paint(self, tooldia, overlap, margin, connect, contour, method):

        self.paint_tooldia = tooldia

        selected = self.get_selected()

        if len(selected) == 0:
            self.app.inform.emit("[warning_notcl]Nothing selected for painting.")
            return

        for param in [tooldia, overlap, margin]:
            if not isinstance(param, float):
                param_name = [k for k, v in locals().items() if v is param][0]
                self.app.inform.emit("[warning] Invalid value for {}".format(param))

        results = []

        if tooldia >= overlap:
            self.app.inform.emit(
                "[error_notcl] Could not do Paint. Overlap value has to be less than Tool Dia value.")
            return

        def recurse(geometry, reset=True):
            """
            Creates a list of non-iterable linear geometry objects.
            Results are placed in self.flat_geometry

            :param geometry: Shapely type or list or list of list of such.
            :param reset: Clears the contents of self.flat_geometry.
            """

            if geometry is None:
                return

            if reset:
                self.flat_geo = []

            ## If iterable, expand recursively.
            try:
                for geo in geometry:
                    if geo is not None:
                        recurse(geometry=geo, reset=False)

            ## Not iterable, do the actual indexing and add.
            except TypeError:
                self.flat_geo.append(geometry)

            return self.flat_geo

        for geo in selected:

            local_results = []
            for geo_obj in recurse(geo.geo):
                try:
                    if type(geo_obj) == Polygon:
                        poly_buf = geo_obj.buffer(-margin)
                    else:
                        poly_buf = Polygon(geo_obj).buffer(-margin)

                    if method == "seed":
                        cp = Geometry.clear_polygon2(poly_buf,
                                                 tooldia, self.app.defaults["geometry_circle_steps"],
                                                 overlap=overlap, contour=contour, connect=connect)
                    elif method == "lines":
                        cp = Geometry.clear_polygon3(poly_buf,
                                                 tooldia, self.app.defaults["geometry_circle_steps"],
                                                 overlap=overlap, contour=contour, connect=connect)

                    else:
                        cp = Geometry.clear_polygon(poly_buf,
                                                tooldia, self.app.defaults["geometry_circle_steps"],
                                                overlap=overlap, contour=contour, connect=connect)

                    if cp is not None:
                        local_results += list(cp.get_objects())
                except Exception as e:
                    log.debug("Could not Paint the polygons. %s" % str(e))
                    self.app.inform.emit(
                        "[error] Could not do Paint. Try a different combination of parameters. "
                        "Or a different method of Paint\n%s" % str(e))
                    return

                # add the result to the results list
                results.append(cascaded_union(local_results))

        # This is a dirty patch:
        for r in results:
            self.add_shape(DrawToolShape(r))
        self.app.inform.emit(
            "[success] Paint done.")
        self.replot()


class FlatCAMExcEditor(QtCore.QObject):

    draw_shape_idx = -1

    def __init__(self, app):
        assert isinstance(app, FlatCAMApp.App), \
            "Expected the app to be a FlatCAMApp.App, got %s" % type(app)

        super(FlatCAMExcEditor, self).__init__()

        self.app = app
        self.canvas = self.app.plotcanvas

        self.exc_edit_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        self.exc_edit_widget.setLayout(layout)

        ## Page Title box (spacing between children)
        self.title_box = QtWidgets.QHBoxLayout()
        layout.addLayout(self.title_box)

        ## Page Title icon
        pixmap = QtGui.QPixmap('share/flatcam_icon32.png')
        self.icon = QtWidgets.QLabel()
        self.icon.setPixmap(pixmap)
        self.title_box.addWidget(self.icon, stretch=0)

        ## Title label
        self.title_label = QtWidgets.QLabel("<font size=5><b>" + 'Excellon Editor' + "</b></font>")
        self.title_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.title_box.addWidget(self.title_label, stretch=1)

        ## Object name
        self.name_box = QtWidgets.QHBoxLayout()
        layout.addLayout(self.name_box)
        name_label = QtWidgets.QLabel("Name:")
        self.name_box.addWidget(name_label)
        self.name_entry = FCEntry()
        self.name_box.addWidget(self.name_entry)

        ## Box box for custom widgets
        # This gets populated in offspring implementations.
        self.custom_box = QtWidgets.QVBoxLayout()
        layout.addLayout(self.custom_box)

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add all the Drills widgets
        # this way I can hide/show the frame
        self.drills_frame = QtWidgets.QFrame()
        self.drills_frame.setContentsMargins(0, 0, 0, 0)
        self.custom_box.addWidget(self.drills_frame)
        self.tools_box = QtWidgets.QVBoxLayout()
        self.tools_box.setContentsMargins(0, 0, 0, 0)
        self.drills_frame.setLayout(self.tools_box)

        #### Tools Drills ####
        self.tools_table_label = QtWidgets.QLabel('<b>Tools Table</b>')
        self.tools_table_label.setToolTip(
            "Tools in this Excellon object\n"
            "when are used for drilling."
        )
        self.tools_box.addWidget(self.tools_table_label)

        self.tools_table_exc = FCTable()
        self.tools_box.addWidget(self.tools_table_exc)

        self.tools_table_exc.setColumnCount(4)
        self.tools_table_exc.setHorizontalHeaderLabels(['#', 'Diameter', 'D', 'S'])
        self.tools_table_exc.setSortingEnabled(False)
        self.tools_table_exc.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.empty_label = QtWidgets.QLabel('')
        self.tools_box.addWidget(self.empty_label)

        #### Add a new Tool ####
        self.addtool_label = QtWidgets.QLabel('<b>Add/Delete Tool</b>')
        self.addtool_label.setToolTip(
            "Add/Delete a tool to the tool list\n"
            "for this Excellon object."
        )
        self.tools_box.addWidget(self.addtool_label)

        grid1 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid1)

        addtool_entry_lbl = QtWidgets.QLabel('Tool Dia:')
        addtool_entry_lbl.setToolTip(
            "Diameter for the new tool"
        )
        grid1.addWidget(addtool_entry_lbl, 0, 0)

        hlay = QtWidgets.QHBoxLayout()
        self.addtool_entry = LengthEntry()
        hlay.addWidget(self.addtool_entry)

        self.addtool_btn = QtWidgets.QPushButton('Add Tool')
        self.addtool_btn.setToolTip(
            "Add a new tool to the tool list\n"
            "with the diameter specified above."
        )
        self.addtool_btn.setFixedWidth(80)
        hlay.addWidget(self.addtool_btn)
        grid1.addLayout(hlay, 0, 1)

        grid2 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid2)

        self.deltool_btn = QtWidgets.QPushButton('Delete Tool')
        self.deltool_btn.setToolTip(
            "Delete a tool in the tool list\n"
            "by selecting a row in the tool table."
        )
        grid2.addWidget(self.deltool_btn, 0, 1)

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add all the Drills widgets
        # this way I can hide/show the frame
        self.resize_frame = QtWidgets.QFrame()
        self.resize_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.resize_frame)
        self.resize_box = QtWidgets.QVBoxLayout()
        self.resize_box.setContentsMargins(0, 0, 0, 0)
        self.resize_frame.setLayout(self.resize_box)

        #### Resize a  drill ####
        self.emptyresize_label = QtWidgets.QLabel('')
        self.resize_box.addWidget(self.emptyresize_label)

        self.drillresize_label = QtWidgets.QLabel('<b>Resize Drill(s)</b>')
        self.drillresize_label.setToolTip(
            "Resize a drill or a selection of drills."
        )
        self.resize_box.addWidget(self.drillresize_label)

        grid3 = QtWidgets.QGridLayout()
        self.resize_box.addLayout(grid3)

        res_entry_lbl = QtWidgets.QLabel('Resize Dia:')
        res_entry_lbl.setToolTip(
            "Diameter to resize to."
        )
        grid3.addWidget(addtool_entry_lbl, 0, 0)

        hlay2 = QtWidgets.QHBoxLayout()
        self.resdrill_entry = LengthEntry()
        hlay2.addWidget(self.resdrill_entry)

        self.resize_btn = QtWidgets.QPushButton('Resize')
        self.resize_btn.setToolTip(
            "Resize drill(s)"
        )
        self.resize_btn.setFixedWidth(80)
        hlay2.addWidget(self.resize_btn)
        grid3.addLayout(hlay2, 0, 1)

        self.resize_frame.hide()

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add
        # all the add drill array  widgets
        # this way I can hide/show the frame
        self.array_frame = QtWidgets.QFrame()
        self.array_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.array_frame)
        self.array_box = QtWidgets.QVBoxLayout()
        self.array_box.setContentsMargins(0, 0, 0, 0)
        self.array_frame.setLayout(self.array_box)

        #### Add DRILL Array ####
        self.emptyarray_label = QtWidgets.QLabel('')
        self.array_box.addWidget(self.emptyarray_label)

        self.drillarray_label = QtWidgets.QLabel('<b>Add Drill Array</b>')
        self.drillarray_label.setToolTip(
            "Add an array of drills (linear or circular array)"
        )
        self.array_box.addWidget(self.drillarray_label)

        self.array_type_combo = FCComboBox()
        self.array_type_combo.setToolTip(
            "Select the type of drills array to create.\n"
            "It can be Linear X(Y) or Circular"
        )
        self.array_type_combo.addItem("Linear")
        self.array_type_combo.addItem("Circular")

        self.array_box.addWidget(self.array_type_combo)

        self.array_form = QtWidgets.QFormLayout()
        self.array_box.addLayout(self.array_form)

        self.drill_array_size_label = QtWidgets.QLabel('Nr of drills:')
        self.drill_array_size_label.setToolTip(
            "Specify how many drills to be in the array."
        )
        self.drill_array_size_label.setFixedWidth(100)

        self.drill_array_size_entry = LengthEntry()
        self.array_form.addRow(self.drill_array_size_label, self.drill_array_size_entry)

        self.array_linear_frame = QtWidgets.QFrame()
        self.array_linear_frame.setContentsMargins(0, 0, 0, 0)
        self.array_box.addWidget(self.array_linear_frame)
        self.linear_box = QtWidgets.QVBoxLayout()
        self.linear_box.setContentsMargins(0, 0, 0, 0)
        self.array_linear_frame.setLayout(self.linear_box)

        self.linear_form = QtWidgets.QFormLayout()
        self.linear_box.addLayout(self.linear_form)

        self.drill_pitch_label = QtWidgets.QLabel('Pitch:')
        self.drill_pitch_label.setToolTip(
            "Pitch = Distance between elements of the array."
        )
        self.drill_pitch_label.setFixedWidth(100)

        self.drill_pitch_entry = LengthEntry()
        self.linear_form.addRow(self.drill_pitch_label, self.drill_pitch_entry)

        self.drill_axis_label = QtWidgets.QLabel('Axis:')
        self.drill_axis_label.setToolTip(
            "Axis on which the linear array is oriented: 'X' or 'Y'."
        )
        self.drill_axis_label.setFixedWidth(100)

        self.drill_axis_radio = RadioSet([{'label': 'X', 'value': 'X'},
                                          {'label': 'Y', 'value': 'Y'}])
        self.drill_axis_radio.set_value('X')
        self.linear_form.addRow(self.drill_axis_label, self.drill_axis_radio)

        self.array_circular_frame = QtWidgets.QFrame()
        self.array_circular_frame.setContentsMargins(0, 0, 0, 0)
        self.array_box.addWidget(self.array_circular_frame)
        self.circular_box = QtWidgets.QVBoxLayout()
        self.circular_box.setContentsMargins(0, 0, 0, 0)
        self.array_circular_frame.setLayout(self.circular_box)

        self.drill_angle_label = QtWidgets.QLabel('Angle:')
        self.drill_angle_label.setToolTip(
            "Angle at which each element in circular array is placed."
        )
        self.drill_angle_label.setFixedWidth(100)

        self.circular_form = QtWidgets.QFormLayout()
        self.circular_box.addLayout(self.circular_form)

        self.drill_angle_entry = LengthEntry()
        self.circular_form.addRow(self.drill_angle_label, self.drill_angle_entry)

        self.drill_direction_label = QtWidgets.QLabel('Direction:')
        self.drill_direction_label.setToolTip(
            "Direction for circular array."
            "Can be CW = clockwise or CCW = counter clockwise."
        )
        self.drill_direction_label.setFixedWidth(100)

        self.drill_direction_radio = RadioSet([{'label': 'CW', 'value': 'CW'},
                                          {'label': 'CCW.', 'value': 'CCW'}])
        self.drill_direction_radio.set_value('CW')
        self.circular_form.addRow(self.drill_direction_label, self.drill_direction_radio)

        self.array_circular_frame.hide()
        self.array_frame.hide()
        self.tools_box.addStretch()

        ## Toolbar events and properties
        self.tools_exc = {
            "select": {"button": self.app.ui.select_drill_btn,
                       "constructor": FCDrillSelect},
            "add": {"button": self.app.ui.add_drill_btn,
                    "constructor": FCDrillAdd},
            "add_array": {"button": self.app.ui.add_drill_array_btn,
                          "constructor": FCDrillArray},
            "resize": {"button": self.app.ui.resize_drill_btn,
                       "constructor": FCDrillResize},
            "copy": {"button": self.app.ui.copy_drill_btn,
                     "constructor": FCDrillCopy},
            "move": {"button": self.app.ui.move_drill_btn,
                     "constructor": FCDrillMove},
        }

        ### Data
        self.active_tool = None

        self.storage_dict = {}
        self.current_storage = []

        # build the data from the Excellon point into a dictionary
        #  {tool_dia: [geometry_in_points]}
        self.points_edit = {}
        self.sorted_diameters =[]

        self.new_drills = []
        self.new_tools = {}
        self.new_slots = {}

        # dictionary to store the tool_row and diameters in Tool_table
        # it will be updated everytime self.build_ui() is called
        self.olddia_newdia = {}

        self.tool2tooldia = {}

        # this will store the value for the last selected tool, for use after clicking on canvas when the selection
        # is cleared but as a side effect also the selected tool is cleared
        self.last_tool_selected = None
        self.utility = []

        # this will flag if the Editor "tools" are launched from key shortcuts (True) or from menu toolbar (False)
        self.launched_from_shortcuts = False

        self.app.ui.delete_drill_btn.triggered.connect(self.on_delete_btn)
        self.name_entry.returnPressed.connect(self.on_name_activate)
        self.addtool_btn.clicked.connect(self.on_tool_add)
        # self.addtool_entry.editingFinished.connect(self.on_tool_add)
        self.deltool_btn.clicked.connect(self.on_tool_delete)
        self.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)
        self.array_type_combo.currentIndexChanged.connect(self.on_array_type_combo)

        self.drill_array_size_entry.set_value(5)
        self.drill_pitch_entry.set_value(2.54)
        self.drill_angle_entry.set_value(12)
        self.drill_direction_radio.set_value('CW')
        self.drill_axis_radio.set_value('X')
        self.exc_obj = None

        # VisPy Visuals
        self.shapes = self.app.plotcanvas.new_shape_collection(layers=1)
        self.tool_shape = self.app.plotcanvas.new_shape_collection(layers=1)
        self.app.pool_recreated.connect(self.pool_recreated)

        # Remove from scene
        self.shapes.enabled = False
        self.tool_shape.enabled = False

        ## List of selected shapes.
        self.selected = []

        self.move_timer = QtCore.QTimer()
        self.move_timer.setSingleShot(True)

        ## Current application units in Upper Case
        self.units = self.app.general_options_form.general_group.units_radio.get_value().upper()

        self.key = None  # Currently pressed key
        self.modifiers = None
        self.x = None  # Current mouse cursor pos
        self.y = None
        # Current snapped mouse pos
        self.snap_x = None
        self.snap_y = None
        self.pos = None

        def make_callback(thetool):
            def f():
                self.on_tool_select(thetool)
            return f

        for tool in self.tools_exc:
            self.tools_exc[tool]["button"].triggered.connect(make_callback(tool))  # Events
            self.tools_exc[tool]["button"].setCheckable(True)  # Checkable

        self.options = {
            "global_gridx": 0.1,
            "global_gridy": 0.1,
            "snap_max": 0.05,
            "grid_snap": True,
            "corner_snap": False,
            "grid_gap_link": True
        }
        self.app.options_read_form()

        for option in self.options:
            if option in self.app.options:
                self.options[option] = self.app.options[option]

        self.rtree_exc_index = rtindex.Index()
        # flag to show if the object was modified
        self.is_modified = False

        self.edited_obj_name = ""

        # variable to store the total amount of drills per job
        self.tot_drill_cnt = 0
        self.tool_row = 0

        # variable to store the total amount of slots per job
        self.tot_slot_cnt = 0
        self.tool_row_slots = 0

        self.tool_row = 0

        # store the status of the editor so the Delete at object level will not work until the edit is finished
        self.editor_active = False

        def entry2option(option, entry):
            self.options[option] = float(entry.text())

        # store the status of the editor so the Delete at object level will not work until the edit is finished
        self.editor_active = False

    def pool_recreated(self, pool):
        self.shapes.pool = pool
        self.tool_shape.pool = pool

    @staticmethod
    def make_storage():

        ## Shape storage.
        storage = FlatCAMRTreeStorage()
        storage.get_points = DrawToolShape.get_pts

        return storage

    def set_ui(self):
        # updated units
        self.units = self.app.general_options_form.general_group.units_radio.get_value().upper()

        self.olddia_newdia.clear()
        self.tool2tooldia.clear()

        # build the self.points_edit dict {dimaters: [point_list]}
        for drill in self.exc_obj.drills:
            if drill['tool'] in self.exc_obj.tools:
                if self.units == 'IN':
                    tool_dia = float('%.3f' % self.exc_obj.tools[drill['tool']]['C'])
                else:
                    tool_dia = float('%.2f' % self.exc_obj.tools[drill['tool']]['C'])

                try:
                    self.points_edit[tool_dia].append(drill['point'])
                except KeyError:
                    self.points_edit[tool_dia] = [drill['point']]
        # update the olddia_newdia dict to make sure we have an updated state of the tool_table
        for key in self.points_edit:
            self.olddia_newdia[key] = key

        sort_temp = []
        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # populate self.intial_table_rows dict with the tool number as keys and tool diameters as values
        for i in range(len(self.sorted_diameters)):
            tt_dia = self.sorted_diameters[i]
            self.tool2tooldia[i + 1] = tt_dia

    def build_ui(self):

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tools_table_exc.itemChanged.disconnect()
        except:
            pass

        # updated units
        self.units = self.app.general_options_form.general_group.units_radio.get_value().upper()

        # make a new name for the new Excellon object (the one with edited content)
        self.edited_obj_name = self.exc_obj.options['name']
        self.name_entry.set_value(self.edited_obj_name)

        if self.units == "IN":
            self.addtool_entry.set_value(0.039)
        else:
            self.addtool_entry.set_value(1)

        sort_temp = []

        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # here, self.sorted_diameters will hold in a oblique way, the number of tools
        n = len(self.sorted_diameters)
        # we have (n+2) rows because there are 'n' tools, each a row, plus the last 2 rows for totals.
        self.tools_table_exc.setRowCount(n + 2)

        self.tot_drill_cnt = 0
        self.tot_slot_cnt = 0

        self.tool_row = 0
        # this variable will serve as the real tool_number
        tool_id = 0

        for tool_no in self.sorted_diameters:
            tool_id += 1
            drill_cnt = 0  # variable to store the nr of drills per tool
            slot_cnt = 0  # variable to store the nr of slots per tool

            # Find no of drills for the current tool
            for tool_dia in self.points_edit:
                if float(tool_dia) == tool_no:
                    drill_cnt = len(self.points_edit[tool_dia])

            self.tot_drill_cnt += drill_cnt

            try:
                # Find no of slots for the current tool
                for slot in self.slots:
                    if slot['tool'] == tool_no:
                        slot_cnt += 1

                self.tot_slot_cnt += slot_cnt
            except AttributeError:
                # log.debug("No slots in the Excellon file")
                # slot editing not implemented
                pass

            id = QtWidgets.QTableWidgetItem('%d' % int(tool_id))
            id.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.tools_table_exc.setItem(self.tool_row, 0, id)  # Tool name/id

            # Make sure that the drill diameter when in MM is with no more than 2 decimals
            # There are no drill bits in MM with more than 3 decimals diameter
            # For INCH the decimals should be no more than 3. There are no drills under 10mils
            if self.units == 'MM':
                dia = QtWidgets.QTableWidgetItem('%.2f' % self.olddia_newdia[tool_no])
            else:
                dia = QtWidgets.QTableWidgetItem('%.3f' % self.olddia_newdia[tool_no])

            dia.setFlags(QtCore.Qt.ItemIsEnabled)

            drill_count = QtWidgets.QTableWidgetItem('%d' % drill_cnt)
            drill_count.setFlags(QtCore.Qt.ItemIsEnabled)

            # if the slot number is zero is better to not clutter the GUI with zero's so we print a space
            if slot_cnt > 0:
                slot_count = QtWidgets.QTableWidgetItem('%d' % slot_cnt)
            else:
                slot_count = QtWidgets.QTableWidgetItem('')
            slot_count.setFlags(QtCore.Qt.ItemIsEnabled)

            self.tools_table_exc.setItem(self.tool_row, 1, dia)  # Diameter
            self.tools_table_exc.setItem(self.tool_row, 2, drill_count)  # Number of drills per tool
            self.tools_table_exc.setItem(self.tool_row, 3, slot_count)  # Number of drills per tool
            self.tool_row += 1

        # make the diameter column editable
        for row in range(self.tool_row):
            self.tools_table_exc.item(row, 1).setFlags(
                QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.tools_table_exc.item(row, 2).setForeground(QtGui.QColor(0, 0, 0))
            self.tools_table_exc.item(row, 3).setForeground(QtGui.QColor(0, 0, 0))

        # add a last row with the Total number of drills
        # HACK: made the text on this cell '9999' such it will always be the one before last when sorting
        # it will have to have the foreground color (font color) white
        empty = QtWidgets.QTableWidgetItem('9998')
        empty.setForeground(QtGui.QColor(255, 255, 255))

        empty.setFlags(empty.flags() ^ QtCore.Qt.ItemIsEnabled)
        empty_b = QtWidgets.QTableWidgetItem('')
        empty_b.setFlags(empty_b.flags() ^ QtCore.Qt.ItemIsEnabled)

        label_tot_drill_count = QtWidgets.QTableWidgetItem('Total Drills')
        tot_drill_count = QtWidgets.QTableWidgetItem('%d' % self.tot_drill_cnt)

        label_tot_drill_count.setFlags(label_tot_drill_count.flags() ^ QtCore.Qt.ItemIsEnabled)
        tot_drill_count.setFlags(tot_drill_count.flags() ^ QtCore.Qt.ItemIsEnabled)

        self.tools_table_exc.setItem(self.tool_row, 0, empty)
        self.tools_table_exc.setItem(self.tool_row, 1, label_tot_drill_count)
        self.tools_table_exc.setItem(self.tool_row, 2, tot_drill_count)  # Total number of drills
        self.tools_table_exc.setItem(self.tool_row, 3, empty_b)

        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)

        for k in [1, 2]:
            self.tools_table_exc.item(self.tool_row, k).setForeground(QtGui.QColor(127, 0, 255))
            self.tools_table_exc.item(self.tool_row, k).setFont(font)

        self.tool_row += 1

        # add a last row with the Total number of slots
        # HACK: made the text on this cell '9999' such it will always be the last when sorting
        # it will have to have the foreground color (font color) white
        empty_2 = QtWidgets.QTableWidgetItem('9999')
        empty_2.setForeground(QtGui.QColor(255, 255, 255))

        empty_2.setFlags(empty_2.flags() ^ QtCore.Qt.ItemIsEnabled)

        empty_3 = QtWidgets.QTableWidgetItem('')
        empty_3.setFlags(empty_3.flags() ^ QtCore.Qt.ItemIsEnabled)

        label_tot_slot_count = QtWidgets.QTableWidgetItem('Total Slots')
        tot_slot_count = QtWidgets.QTableWidgetItem('%d' % self.tot_slot_cnt)
        label_tot_slot_count.setFlags(label_tot_slot_count.flags() ^ QtCore.Qt.ItemIsEnabled)
        tot_slot_count.setFlags(tot_slot_count.flags() ^ QtCore.Qt.ItemIsEnabled)

        self.tools_table_exc.setItem(self.tool_row, 0, empty_2)
        self.tools_table_exc.setItem(self.tool_row, 1, label_tot_slot_count)
        self.tools_table_exc.setItem(self.tool_row, 2, empty_3)
        self.tools_table_exc.setItem(self.tool_row, 3, tot_slot_count)  # Total number of slots

        for kl in [1, 2, 3]:
            self.tools_table_exc.item(self.tool_row, kl).setFont(font)
            self.tools_table_exc.item(self.tool_row, kl).setForeground(QtGui.QColor(0, 70, 255))


        # all the tools are selected by default
        self.tools_table_exc.selectColumn(0)
        #
        self.tools_table_exc.resizeColumnsToContents()
        self.tools_table_exc.resizeRowsToContents()

        vertical_header = self.tools_table_exc.verticalHeader()
        # vertical_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        vertical_header.hide()
        self.tools_table_exc.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        horizontal_header = self.tools_table_exc.horizontalHeader()
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        horizontal_header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        horizontal_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        horizontal_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        # horizontal_header.setStretchLastSection(True)

        self.tools_table_exc.setSortingEnabled(True)
        # sort by tool diameter
        self.tools_table_exc.sortItems(1)

        # After sorting, to display also the number of drills in the right row we need to update self.initial_rows dict
        # with the new order. Of course the last 2 rows in the tool table are just for display therefore we don't
        # use them
        self.tool2tooldia.clear()
        for row in range(self.tools_table_exc.rowCount() - 2):
            tool = int(self.tools_table_exc.item(row, 0).text())
            diameter = float(self.tools_table_exc.item(row, 1).text())
            self.tool2tooldia[tool] = diameter

        self.tools_table_exc.setMinimumHeight(self.tools_table_exc.getHeight())
        self.tools_table_exc.setMaximumHeight(self.tools_table_exc.getHeight())

        # make sure no rows are selected so the user have to click the correct row, meaning selecting the correct tool
        self.tools_table_exc.clearSelection()

        # Remove anything else in the GUI Selected Tab
        self.app.ui.selected_scroll_area.takeWidget()
        # Put ourself in the GUI Selected Tab
        self.app.ui.selected_scroll_area.setWidget(self.exc_edit_widget)
        # Switch notebook to Selected page
        self.app.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)

        # we reactivate the signals after the after the tool adding as we don't need to see the tool been populated
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)

    def on_tool_add(self):
        self.is_modified = True
        tool_dia = float(self.addtool_entry.get_value())

        if tool_dia not in self.olddia_newdia:
            storage_elem = FlatCAMGeoEditor.make_storage()
            self.storage_dict[tool_dia] = storage_elem

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.olddia_newdia[tool_dia] = tool_dia
        else:
            self.app.inform.emit("[warning_notcl]Tool already in the original or actual tool list.\n"
                                 "Save and reedit Excellon if you need to add this tool. ")
            return

        # since we add a new tool, we update also the initial state of the tool_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.tool2tooldia[len(self.olddia_newdia)] = tool_dia

        self.app.inform.emit("[success]Added new tool with dia: %s %s" % (str(tool_dia), str(self.units)))

        self.build_ui()

        # make a quick sort through the tool2tooldia dict so we find which row to select
        row_to_be_selected = None
        for key in sorted(self.tool2tooldia):
            if self.tool2tooldia[key] == tool_dia:
                row_to_be_selected = int(key) - 1
                break

        self.tools_table_exc.selectRow(row_to_be_selected)

    def on_tool_delete(self, dia=None):
        self.is_modified = True
        deleted_tool_dia_list = []

        try:
            if dia is None or dia is False:
                # deleted_tool_dia = float(self.tools_table_exc.item(self.tools_table_exc.currentRow(), 1).text())
                for index in self.tools_table_exc.selectionModel().selectedRows():
                    row = index.row()
                    deleted_tool_dia_list.append(float(self.tools_table_exc.item(row, 1).text()))
            else:
                if isinstance(dia, list):
                    for dd in dia:
                        deleted_tool_dia_list.append(float('%.4f' % dd))
                else:
                    deleted_tool_dia_list.append(float('%.4f' % dia))
        except:
            self.app.inform.emit("[warning_notcl]Select a tool in Tool Table")
            return

        for deleted_tool_dia in deleted_tool_dia_list:

            # delete the storage used for that tool
            storage_elem = FlatCAMGeoEditor.make_storage()
            self.storage_dict[deleted_tool_dia] = storage_elem
            self.storage_dict.pop(deleted_tool_dia, None)

            # I've added this flag_del variable because dictionary don't like
            # having keys deleted while iterating through them
            flag_del = []
            # self.points_edit.pop(deleted_tool_dia, None)
            for deleted_tool in self.tool2tooldia:
                if self.tool2tooldia[deleted_tool] == deleted_tool_dia:
                    flag_del.append(deleted_tool)

            if flag_del:
                for tool_to_be_deleted in flag_del:
                    self.tool2tooldia.pop(tool_to_be_deleted, None)
                    # delete also the drills from points_edit dict just in case we add the tool again, we don't want to show the
                    # number of drills from before was deleter
                    self.points_edit[deleted_tool_dia] = []
                flag_del = []

            self.olddia_newdia.pop(deleted_tool_dia, None)

            self.app.inform.emit("[success]Deleted tool with dia: %s %s" % (str(deleted_tool_dia), str(self.units)))

        self.replot()
        # self.app.inform.emit("Could not delete selected tool")

        self.build_ui()

    def on_tool_edit(self):
        # if connected, disconnect the signal from the slot on item_changed as it creates issues
        self.tools_table_exc.itemChanged.disconnect()
        # self.tools_table_exc.selectionModel().currentChanged.disconnect()

        self.is_modified = True
        geometry = []
        current_table_dia_edited = None

        if self.tools_table_exc.currentItem() is not None:
            current_table_dia_edited = float(self.tools_table_exc.currentItem().text())

        row_of_item_changed = self.tools_table_exc.currentRow()

        # rows start with 0, tools start with 1 so we adjust the value by 1
        key_in_tool2tooldia = row_of_item_changed + 1

        dia_changed = self.tool2tooldia[key_in_tool2tooldia]

        # tool diameter is not used so we create a new tool with the desired diameter
        if current_table_dia_edited not in self.olddia_newdia.values():
            # update the dict that holds as keys our initial diameters and as values the edited diameters
            self.olddia_newdia[dia_changed] = current_table_dia_edited
            # update the dict that holds tool_no as key and tool_dia as value
            self.tool2tooldia[key_in_tool2tooldia] = current_table_dia_edited
            self.replot()
        else:
            # tool diameter is already in use so we move the drills from the prior tool to the new tool
            factor = current_table_dia_edited / dia_changed
            for shape in self.storage_dict[dia_changed].get_objects():
                geometry.append(DrawToolShape(
                    MultiLineString([affinity.scale(subgeo, xfact=factor, yfact=factor) for subgeo in shape.geo])))

                self.points_edit[current_table_dia_edited].append((0, 0))
            self.add_exc_shape(geometry, self.storage_dict[current_table_dia_edited])

            self.on_tool_delete(dia=dia_changed)

        # we reactivate the signals after the after the tool editing
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)
        # self.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)

    def on_name_activate(self):
        self.edited_obj_name = self.name_entry.get_value()

    def activate(self):
        self.connect_canvas_event_handlers()

        # self.app.collection.view.keyPressed.connect(self.on_canvas_key)

        self.shapes.enabled = True
        self.tool_shape.enabled = True
        # self.app.app_cursor.enabled = True
        self.app.ui.snap_max_dist_entry.setDisabled(False)
        self.app.ui.corner_snap_btn.setEnabled(True)
        # Tell the App that the editor is active
        self.editor_active = True

    def deactivate(self):
        self.disconnect_canvas_event_handlers()
        self.clear()
        self.app.ui.exc_edit_toolbar.setDisabled(True)
        self.app.ui.exc_edit_toolbar.setVisible(False)
        self.app.ui.snap_max_dist_entry.setDisabled(True)
        self.app.ui.corner_snap_btn.setEnabled(False)

        # Disable visuals
        self.shapes.enabled = False
        self.tool_shape.enabled = False
        # self.app.app_cursor.enabled = False

        # Tell the app that the editor is no longer active
        self.editor_active = False

        # Show original geometry
        if self.exc_obj:
            self.exc_obj.visible = True

    def connect_canvas_event_handlers(self):
        ## Canvas events

        # make sure that the shortcuts key and mouse events will no longer be linked to the methods from FlatCAMApp
        # but those from FlatCAMGeoEditor
        self.app.plotcanvas.vis_disconnect('key_press', self.app.on_key_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_release', self.app.on_mouse_click_release_over_plot)
        self.app.plotcanvas.vis_disconnect('mouse_double_click', self.app.on_double_click_over_plot)
        self.app.collection.view.keyPressed.disconnect()
        self.app.collection.view.clicked.disconnect()

        self.canvas.vis_connect('mouse_press', self.on_canvas_click)
        self.canvas.vis_connect('mouse_move', self.on_canvas_move)
        self.canvas.vis_connect('mouse_release', self.on_canvas_click_release)
        self.canvas.vis_connect('key_press', self.on_canvas_key)
        self.canvas.vis_connect('key_release', self.on_canvas_key_release)

    def disconnect_canvas_event_handlers(self):

        self.canvas.vis_disconnect('mouse_press', self.on_canvas_click)
        self.canvas.vis_disconnect('mouse_move', self.on_canvas_move)
        self.canvas.vis_disconnect('mouse_release', self.on_canvas_click_release)
        self.canvas.vis_disconnect('key_press', self.on_canvas_key)
        self.canvas.vis_disconnect('key_release', self.on_canvas_key_release)

        # we restore the key and mouse control to FlatCAMApp method
        self.app.plotcanvas.vis_connect('key_press', self.app.on_key_over_plot)
        self.app.plotcanvas.vis_connect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.plotcanvas.vis_connect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.plotcanvas.vis_connect('mouse_release', self.app.on_mouse_click_release_over_plot)
        self.app.plotcanvas.vis_connect('mouse_double_click', self.app.on_double_click_over_plot)
        self.app.collection.view.keyPressed.connect(self.app.collection.on_key)
        self.app.collection.view.clicked.connect(self.app.collection.on_mouse_down)

    def clear(self):
        self.active_tool = None
        # self.shape_buffer = []
        self.selected = []

        self.points_edit = {}
        self.new_tools = {}
        self.new_drills = []

        self.storage_dict = {}

        self.shapes.clear(update=True)
        self.tool_shape.clear(update=True)

        # self.storage = FlatCAMExcEditor.make_storage()
        self.replot()

    def edit_exc_obj(self, exc_obj):
        """
        Imports the geometry from the given FlatCAM Excellon object
        into the editor.

        :param fcgeometry: FlatCAMExcellon
        :return: None
        """

        assert isinstance(exc_obj, Excellon), \
            "Expected an Excellon Object, got %s" % type(exc_obj)

        self.deactivate()
        self.activate()

        # Hide original geometry
        self.exc_obj = exc_obj
        exc_obj.visible = False

        # Set selection tolerance
        # DrawToolShape.tolerance = fc_excellon.drawing_tolerance * 10

        self.select_tool("select")

        self.set_ui()

        # now that we hava data, create the GUI interface and add it to the Tool Tab
        self.build_ui()

        # we activate this after the initial build as we don't need to see the tool been populated
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)

        # build the geometry for each tool-diameter, each drill will be represented by a '+' symbol
        # and then add it to the storage elements (each storage elements is a member of a list
        for tool_dia in self.points_edit:
            storage_elem = FlatCAMGeoEditor.make_storage()
            for point in self.points_edit[tool_dia]:
                # make a '+' sign, the line length is the tool diameter
                start_hor_line = ((point.x - (tool_dia / 2)), point.y)
                stop_hor_line = ((point.x + (tool_dia / 2)), point.y)
                start_vert_line = (point.x, (point.y - (tool_dia / 2)))
                stop_vert_line = (point.x, (point.y + (tool_dia / 2)))
                shape = MultiLineString([(start_hor_line, stop_hor_line),(start_vert_line, stop_vert_line)])
                if shape is not None:
                    self.add_exc_shape(DrawToolShape(shape), storage_elem)
            self.storage_dict[tool_dia] = storage_elem

        self.replot()
        self.app.ui.exc_edit_toolbar.setDisabled(False)
        self.app.ui.exc_edit_toolbar.setVisible(True)
        self.app.ui.snap_toolbar.setDisabled(False)

        # start with GRID toolbar activated
        if self.app.ui.grid_snap_btn.isChecked() is False:
            self.app.ui.grid_snap_btn.trigger()

    def update_exc_obj(self, exc_obj):
        """
        Create a new Excellon object that contain the edited content of the source Excellon object

        :param exc_obj: FlatCAMExcellon
        :return: None
        """

        # this dictionary will contain tooldia's as keys and a list of coordinates tuple as values
        # the values of this dict are coordinates of the holes (drills)
        edited_points = {}
        for storage_tooldia in self.storage_dict:
            for x in self.storage_dict[storage_tooldia].get_objects():

                # all x.geo in self.storage_dict[storage] are MultiLinestring objects
                # each MultiLineString is made out of Linestrings
                # select first Linestring object in the current MultiLineString
                first_linestring = x.geo[0]
                # get it's coordinates
                first_linestring_coords = first_linestring.coords
                x_coord = first_linestring_coords[0][0] + (float(storage_tooldia) / 2)
                y_coord = first_linestring_coords[0][1]

                # create a tuple with the coordinates (x, y) and add it to the list that is the value of the
                # edited_points dictionary
                point = (x_coord, y_coord)
                if not storage_tooldia in edited_points:
                    edited_points[storage_tooldia] = [point]
                else:
                    edited_points[storage_tooldia].append(point)

        # recreate the drills and tools to be added to the new Excellon edited object
        # first, we look in the tool table if one of the tool diameters was changed then
        # append that a tuple formed by (old_dia, edited_dia) to a list
        changed_key = []
        for initial_dia in self.olddia_newdia:
            edited_dia = self.olddia_newdia[initial_dia]
            if edited_dia != initial_dia:
                for old_dia in edited_points:
                    if old_dia == initial_dia:
                        changed_key.append((old_dia, edited_dia))
            # if the initial_dia is not in edited_points it means it is a new tool with no drill points
            # (and we have to add it)
            # because in case we have drill points it will have to be already added in edited_points
            # if initial_dia not in edited_points.keys():
            #     edited_points[initial_dia] = []

        for el in changed_key:
            edited_points[el[1]] = edited_points.pop(el[0])

        # Let's sort the edited_points dictionary by keys (diameters) and store the result in a zipped list
        # ordered_edited_points is a ordered list of tuples;
        # element[0] of the tuple is the diameter and
        # element[1] of the tuple is a list of coordinates (a tuple themselves)
        ordered_edited_points = sorted(zip(edited_points.keys(), edited_points.values()))

        current_tool = 0
        for tool_dia in ordered_edited_points:
            current_tool += 1

            # create the self.tools for the new Excellon object (the one with edited content)
            name = str(current_tool)
            spec = {"C": float(tool_dia[0])}
            self.new_tools[name] = spec

            # create the self.drills for the new Excellon object (the one with edited content)
            for point in tool_dia[1]:
                self.new_drills.append(
                    {
                        'point': Point(point),
                        'tool': str(current_tool)
                    }
                )

        if self.is_modified is True:
            if "_edit" in self.edited_obj_name:
                try:
                    id = int(self.edited_obj_name[-1]) + 1
                    self.edited_obj_name = self.edited_obj_name[:-1] + str(id)
                except ValueError:
                    self.edited_obj_name += "_1"
            else:
                self.edited_obj_name += "_edit"

        self.app.worker_task.emit({'fcn': self.new_edited_excellon,
                                   'params': [self.edited_obj_name]})

        if self.exc_obj.slots:
            self.new_slots = self.exc_obj.slots

        # reset the tool table
        self.tools_table_exc.clear()
        self.tools_table_exc.setHorizontalHeaderLabels(['#', 'Diameter', 'D', 'S'])
        self.last_tool_selected = None

        # delete the edited Excellon object which will be replaced by a new one having the edited content of the first
        self.app.collection.set_active(self.exc_obj.options['name'])
        self.app.collection.delete_active()

        # restore GUI to the Selected TAB
        # Remove anything else in the GUI
        self.app.ui.tool_scroll_area.takeWidget()
        # Switch notebook to Selected page
        self.app.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)

    def new_edited_excellon(self, outname):
        """
        Creates a new Excellon object for the edited Excellon. Thread-safe.

        :param outname: Name of the resulting object. None causes the
            name to be that of the file.
        :type outname: str
        :return: None
        """

        self.app.log.debug("Update the Excellon object with edited content. Source is %s" %
                           self.exc_obj.options['name'])

        # How the object should be initialized
        def obj_init(excellon_obj, app_obj):
            # self.progress.emit(20)
            excellon_obj.drills = self.new_drills
            excellon_obj.tools = self.new_tools
            excellon_obj.slots = self.new_slots

            try:
                excellon_obj.create_geometry()
            except KeyError:
                self.app.inform.emit(
                    "[error_notcl] There are no Tools definitions in the file. Aborting Excellon creation.")
            except:
                msg = "[error] An internal error has ocurred. See shell.\n"
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                raise
                # raise

        with self.app.proc_container.new("Creating Excellon."):

            try:
                self.app.new_object("excellon", outname, obj_init)
            except Exception as e:
                log.error("Error on object creation: %s" % str(e))
                self.app.progress.emit(100)
                return

            self.app.inform.emit("[success]Excellon editing finished.")
            # self.progress.emit(100)

    def on_tool_select(self, tool):
        """
        Behavior of the toolbar. Tool initialization.

        :rtype : None
        """
        current_tool = tool

        self.app.log.debug("on_tool_select('%s')" % tool)

        if self.last_tool_selected is None and current_tool is not 'select':
            # self.draw_app.select_tool('select')
            self.complete = True
            current_tool = 'select'
            self.app.inform.emit("[warning_notcl]Cancelled. There is no Tool/Drill selected")

        # This is to make the group behave as radio group
        if current_tool in self.tools_exc:
            if self.tools_exc[current_tool]["button"].isChecked():
                self.app.log.debug("%s is checked." % current_tool)
                for t in self.tools_exc:
                    if t != current_tool:
                        self.tools_exc[t]["button"].setChecked(False)

                # this is where the Editor toolbar classes (button's) are instantiated
                self.active_tool = self.tools_exc[current_tool]["constructor"](self)
                # self.app.inform.emit(self.active_tool.start_msg)
            else:
                self.app.log.debug("%s is NOT checked." % current_tool)
                for t in self.tools_exc:
                    self.tools_exc[t]["button"].setChecked(False)
                self.active_tool = None

    def on_row_selected(self):
        self.selected = []

        try:
            selected_dia = self.tool2tooldia[self.tools_table_exc.currentRow() + 1]
            self.last_tool_selected = self.tools_table_exc.currentRow() + 1
            for obj in self.storage_dict[selected_dia].get_objects():
                self.selected.append(obj)
        except Exception as e:
            self.app.log.debug(str(e))

        self.replot()

    def toolbar_tool_toggle(self, key):
        self.options[key] = self.sender().isChecked()
        if self.options[key] == True:
            return 1
        else:
            return 0

    def on_canvas_click(self, event):
        """
        event.x and .y have canvas coordinates
        event.xdaya and .ydata have plot coordinates

        :param event: Event object dispatched by Matplotlib
        :return: None
        """

        if event.button is 1:
            self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                                   "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (0, 0))
            self.pos = self.canvas.vispy_canvas.translate_coords(event.pos)

            ### Snap coordinates
            x, y = self.app.geo_editor.snap(self.pos[0], self.pos[1])

            self.pos = (x, y)
            # print(self.active_tool)

            # Selection with left mouse button
            if self.active_tool is not None and event.button is 1:
                # Dispatch event to active_tool
                # msg = self.active_tool.click(self.app.geo_editor.snap(event.xdata, event.ydata))
                msg = self.active_tool.click(self.app.geo_editor.snap(self.pos[0], self.pos[1]))

                # If it is a shape generating tool
                if isinstance(self.active_tool, FCShapeTool) and self.active_tool.complete:
                    if self.current_storage is not None:
                        self.on_exc_shape_complete(self.current_storage)
                        self.build_ui()
                    # MS: always return to the Select Tool
                    self.select_tool("select")
                    return

                if isinstance(self.active_tool, FCDrillSelect):
                    # self.app.log.debug("Replotting after click.")
                    self.replot()
            else:
                self.app.log.debug("No active tool to respond to click!")

    def on_exc_shape_complete(self, storage):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        if type(storage) is list:
            for item_storage in storage:
                self.add_exc_shape(self.active_tool.geometry, item_storage)
        else:
            self.add_exc_shape(self.active_tool.geometry, storage)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def add_exc_shape(self, shape, storage):
        """
        Adds a shape to the shape storage.

        :param shape: Shape to be added.
        :type shape: DrawToolShape
        :return: None
        """
        # List of DrawToolShape?
        if isinstance(shape, list):
            for subshape in shape:
                self.add_exc_shape(subshape, storage)
            return

        assert isinstance(shape, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % str(type(shape))

        assert shape.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shape.geo, list) and len(shape.geo) > 0) or \
               not isinstance(shape.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shape, DrawToolUtilityShape):
            self.utility.append(shape)
        else:
            storage.insert(shape)  # TODO: Check performance

    def add_shape(self, shape):
        """
        Adds a shape to the shape storage.

        :param shape: Shape to be added.
        :type shape: DrawToolShape
        :return: None
        """

        # List of DrawToolShape?
        if isinstance(shape, list):
            for subshape in shape:
                self.add_shape(subshape)
            return

        assert isinstance(shape, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % type(shape)

        assert shape.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shape.geo, list) and len(shape.geo) > 0) or \
               not isinstance(shape.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shape, DrawToolUtilityShape):
            self.utility.append(shape)
        else:
            self.storage.insert(shape)  # TODO: Check performance

    def on_canvas_click_release(self, event):
        pos_canvas = self.canvas.vispy_canvas.translate_coords(event.pos)

        self.modifiers = QtWidgets.QApplication.keyboardModifiers()

        if self.app.grid_status():
            pos = self.app.geo_editor.snap(pos_canvas[0], pos_canvas[1])
        else:
            pos = (pos_canvas[0], pos_canvas[1])

        # if the released mouse button was RMB then test if it was a panning motion or not, if not it was a context
        # canvas menu
        try:
            if event.button == 2:  # right click
                if self.app.panning_action is True:
                    self.app.panning_action = False
                else:
                    self.app.cursor = QtGui.QCursor()
                    self.app.ui.popMenu.popup(self.app.cursor.pos())
        except Exception as e:
            log.warning("Error: %s" % str(e))
            raise

        # if the released mouse button was LMB then test if we had a right-to-left selection or a left-to-right
        # selection and then select a type of selection ("enclosing" or "touching")
        try:
            if event.button == 1:  # left click
                if self.app.selection_type is not None:
                    self.draw_selection_area_handler(self.pos, pos, self.app.selection_type)
                    self.app.selection_type = None
                elif isinstance(self.active_tool, FCDrillSelect):
                    # Dispatch event to active_tool
                    # msg = self.active_tool.click(self.app.geo_editor.snap(event.xdata, event.ydata))
                    # msg = self.active_tool.click_release((self.pos[0], self.pos[1]))
                    # self.app.inform.emit(msg)
                    self.active_tool.click_release((self.pos[0], self.pos[1]))
                    self.replot()
        except Exception as e:
            log.warning("Error: %s" % str(e))
            raise

    def draw_selection_area_handler(self, start_pos, end_pos, sel_type):
        """
        :param start_pos: mouse position when the selection LMB click was done
        :param end_pos: mouse position when the left mouse button is released
        :param sel_type: if True it's a left to right selection (enclosure), if False it's a 'touch' selection
        :type Bool
        :return:
        """
        poly_selection = Polygon([start_pos, (end_pos[0], start_pos[1]), end_pos, (start_pos[0], end_pos[1])])

        self.app.delete_selection_shape()
        for storage in self.storage_dict:
            for obj in self.storage_dict[storage].get_objects():
                if (sel_type is True and poly_selection.contains(obj.geo)) or \
                        (sel_type is False and poly_selection.intersects(obj.geo)):
                    if self.key == self.app.defaults["global_mselect_key"]:
                        if obj in self.selected:
                            self.selected.remove(obj)
                        else:
                            # add the object to the selected shapes
                            self.selected.append(obj)
                    else:
                        self.selected.append(obj)

        # select the diameter of the selected shape in the tool table
        for storage in self.storage_dict:
            for shape_s in self.selected:
                if shape_s in self.storage_dict[storage].get_objects():
                    for key in self.tool2tooldia:
                        if self.tool2tooldia[key] == storage:
                            item = self.tools_table_exc.item((key - 1), 1)
                            self.tools_table_exc.setCurrentItem(item)
                            self.last_tool_selected = key
                            # item.setSelected(True)
                            # self.exc_editor_app.tools_table_exc.selectItem(key - 1)

        self.replot()

    def on_canvas_move(self, event):
        """
        Called on 'mouse_move' event

        event.pos have canvas screen coordinates

        :param event: Event object dispatched by VisPy SceneCavas
        :return: None
        """

        pos = self.canvas.vispy_canvas.translate_coords(event.pos)
        event.xdata, event.ydata = pos[0], pos[1]

        self.x = event.xdata
        self.y = event.ydata

        # Prevent updates on pan
        # if len(event.buttons) > 0:
        #     return

        # if the RMB is clicked and mouse is moving over plot then 'panning_action' is True
        if event.button == 2:
            self.app.panning_action = True
            return
        else:
            self.app.panning_action = False

        try:
            x = float(event.xdata)
            y = float(event.ydata)
        except TypeError:
            return

        if self.active_tool is None:
            return

        ### Snap coordinates
        x, y = self.app.geo_editor.app.geo_editor.snap(x, y)

        self.snap_x = x
        self.snap_y = y

        # update the position label in the infobar since the APP mouse event handlers are disconnected
        self.app.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
                                       "<b>Y</b>: %.4f" % (x, y))

        if self.pos is None:
            self.pos = (0, 0)
        dx = x - self.pos[0]
        dy = y - self.pos[1]

        # update the reference position label in the infobar since the APP mouse event handlers are disconnected
        self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                           "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (dx, dy))

        ### Utility geometry (animated)
        geo = self.active_tool.utility_geometry(data=(x, y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:

            # Remove any previous utility shape
            self.tool_shape.clear(update=True)
            self.draw_utility_geometry(geo=geo)

        ### Selection area on canvas section ###
        dx = pos[0] - self.pos[0]
        if event.is_dragging == 1 and event.button == 1:
            self.app.delete_selection_shape()
            if dx < 0:
                self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x,y),
                     color=self.app.defaults["global_alt_sel_line"],
                     face_color=self.app.defaults['global_alt_sel_fill'])
                self.app.selection_type = False
            else:
                self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x,y))
                self.app.selection_type = True
        else:
            self.app.selection_type = None

        # Update cursor
        self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color='black', size=20)


    def on_canvas_key(self, event):
        """
        event.key has the key.

        :param event:
        :return:
        """
        self.key = event.key.name
        self.modifiers = QtWidgets.QApplication.keyboardModifiers()

        if self.modifiers == Qt.ControlModifier:
            # save (update) the current geometry and return to the App
            if self.key == 'S':
                self.app.editor2object()
                return

            # toggle the measurement tool
            if self.key == 'M':
                self.app.measurement_tool.run()
                return

        # Abort the current action
        if event.key.name == 'Escape':
            # TODO: ...?
            # self.on_tool_select("select")
            self.app.inform.emit("[warning_notcl]Cancelled.")

            self.delete_utility_geometry()

            self.replot()
            # self.select_btn.setChecked(True)
            # self.on_tool_select('select')
            self.select_tool('select')
            return

        # Delete selected object
        if event.key.name == 'Delete':
            self.launched_from_shortcuts = True
            if self.selected:
                self.delete_selected()
                self.replot()
            else:
                self.app.inform.emit("[warning_notcl]Cancelled. Nothing selected to delete.")
            return

        # Add Array of Drill Hole Tool
        if event.key.name == 'A':
            self.launched_from_shortcuts = True
            self.app.inform.emit("Click on target point.")
            self.app.ui.add_drill_array_btn.setChecked(True)
            self.select_tool('add_array')
            return

        # Copy
        if event.key.name == 'C':
            self.launched_from_shortcuts = True
            if self.selected:
                self.app.inform.emit("Click on target point.")
                self.app.ui.copy_drill_btn.setChecked(True)
                self.on_tool_select('copy')
                self.active_tool.set_origin((self.snap_x, self.snap_y))
            else:
                self.app.inform.emit("[warning_notcl]Cancelled. Nothing selected to copy.")
            return

        # Add Drill Hole Tool
        if event.key.name == 'D':
            self.launched_from_shortcuts = True
            self.app.inform.emit("Click on target point.")
            self.app.ui.add_drill_btn.setChecked(True)
            self.select_tool('add')
            return

        # Grid Snap
        if event.key.name == 'G':
            self.launched_from_shortcuts = True
            # make sure that the cursor shape is enabled/disabled, too
            if self.options['grid_snap'] is True:
                self.app.app_cursor.enabled = False
            else:
                self.app.app_cursor.enabled = True
            self.app.ui.grid_snap_btn.trigger()
            return

        # Corner Snap
        if event.key.name == 'K':
            self.launched_from_shortcuts = True
            self.app.ui.corner_snap_btn.trigger()
            return

        # Move
        if event.key.name == 'M':
            self.launched_from_shortcuts = True
            if self.selected:
                self.app.inform.emit("Click on target point.")
                self.app.ui.move_drill_btn.setChecked(True)
                self.on_tool_select('move')
                self.active_tool.set_origin((self.snap_x, self.snap_y))
            else:
                self.app.inform.emit("[warning_notcl]Cancelled. Nothing selected to move.")
            return

        # Resize Tool
        if event.key.name == 'R':
            self.launched_from_shortcuts = True
            self.select_tool('resize')
            return

        # Select Tool
        if event.key.name == 'S':
            self.launched_from_shortcuts = True
            self.select_tool('select')
            return

        # Propagate to tool
        response = None
        if self.active_tool is not None:
            response = self.active_tool.on_key(event.key)
        if response is not None:
            self.app.inform.emit(response)

        # Show Shortcut list
        if event.key.name == '`':
            self.on_shortcut_list()
            return

    def on_shortcut_list(self):
        msg = '''<b>Shortcut list in Geometry Editor</b><br>
<br>
<b>A:</b>       Add an 'Drill Array'<br>
<b>C:</b>       Copy Drill Hole<br>
<b>D:</b>       Add an Drill Hole<br>
<b>G:</b>       Grid Snap On/Off<br>
<b>K:</b>       Corner Snap On/Off<br>
<b>M:</b>       Move Drill Hole<br>
<br>
<b>R:</b>       Resize a 'Drill Hole'<br>
<b>S:</b>       Select Tool Active<br>
<br>
<b>~:</b>       Show Shortcut List<br>
<br>
<b>Enter:</b>   Finish Current Action<br>
<b>Escape:</b>  Abort Current Action<br>
<b>Delete:</b>  Delete Drill Hole'''

        helpbox =QtWidgets.QMessageBox()
        helpbox.setText(msg)
        helpbox.setWindowTitle("Help")
        helpbox.setWindowIcon(QtGui.QIcon('share/help.png'))
        helpbox.setStandardButtons(QtWidgets.QMessageBox.Ok)
        helpbox.setDefaultButton(QtWidgets.QMessageBox.Ok)
        helpbox.exec_()

    def on_canvas_key_release(self, event):
        self.key = None

    def draw_utility_geometry(self, geo):
            # Add the new utility shape
            try:
                # this case is for the Font Parse
                for el in list(geo.geo):
                    if type(el) == MultiPolygon:
                        for poly in el.geoms:
                            self.tool_shape.add(
                                shape=poly,
                                color=(self.app.defaults["global_draw_color"] + '80'),
                                update=False,
                                layer=0,
                                tolerance=None
                            )
                    elif type(el) == MultiLineString:
                        for linestring in el.geoms:
                            self.tool_shape.add(
                                shape=linestring,
                                color=(self.app.defaults["global_draw_color"] + '80'),
                                update=False,
                                layer=0,
                                tolerance=None
                            )
                    else:
                        self.tool_shape.add(
                            shape=el,
                            color=(self.app.defaults["global_draw_color"] + '80'),
                            update=False,
                            layer=0,
                            tolerance=None
                        )
            except TypeError:
                self.tool_shape.add(
                    shape=geo.geo, color=(self.app.defaults["global_draw_color"] + '80'),
                    update=False, layer=0, tolerance=None)

            self.tool_shape.redraw()


    def replot(self):
        self.plot_all()

    def plot_all(self):
        """
        Plots all shapes in the editor.

        :return: None
        :rtype: None
        """
        # self.app.log.debug("plot_all()")
        self.shapes.clear(update=True)

        for storage in self.storage_dict:
            for shape_plus in self.storage_dict[storage].get_objects():
                if shape_plus.geo is None:
                    continue

                if shape_plus in self.selected:
                    self.plot_shape(geometry=shape_plus.geo, color=self.app.defaults['global_sel_draw_color'], linewidth=2)
                    continue
                self.plot_shape(geometry=shape_plus.geo, color=self.app.defaults['global_draw_color'])

        # for shape in self.storage.get_objects():
        #     if shape.geo is None:  # TODO: This shouldn't have happened
        #         continue
        #
        #     if shape in self.selected:
        #         self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_sel_draw_color'], linewidth=2)
        #         continue
        #
        #     self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_draw_color'])



        for shape in self.utility:
            self.plot_shape(geometry=shape.geo, linewidth=1)
            continue

        self.shapes.redraw()

    def plot_shape(self, geometry=None, color='black', linewidth=1):
        """
        Plots a geometric object or list of objects without rendering. Plotted objects
        are returned as a list. This allows for efficient/animated rendering.

        :param geometry: Geometry to be plotted (Any Shapely.geom kind or list of such)
        :param color: Shape color
        :param linewidth: Width of lines in # of pixels.
        :return: List of plotted elements.
        """
        plot_elements = []

        if geometry is None:
            geometry = self.active_tool.geometry

        try:
            for geo in geometry.geoms:
                plot_elements += self.plot_shape(geometry=geo, color=color, linewidth=linewidth)

        ## Non-iterable
        except TypeError:

            ## DrawToolShape
            if isinstance(geometry, DrawToolShape):
                plot_elements += self.plot_shape(geometry=geometry.geo, color=color, linewidth=linewidth)

            ## Polygon: Descend into exterior and each interior.
            if type(geometry) == Polygon:
                plot_elements += self.plot_shape(geometry=geometry.exterior, color=color, linewidth=linewidth)
                plot_elements += self.plot_shape(geometry=geometry.interiors, color=color, linewidth=linewidth)

            if type(geometry) == LineString or type(geometry) == LinearRing:
                plot_elements.append(self.shapes.add(shape=geometry, color=color, layer=0))

            if type(geometry) == Point:
                pass

        return plot_elements

    def on_shape_complete(self):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        self.add_shape(self.active_tool.geometry)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def get_selected(self):
        """
        Returns list of shapes that are selected in the editor.

        :return: List of shapes.
        """
        # return [shape for shape in self.shape_buffer if shape["selected"]]
        return self.selected

    def delete_selected(self):
        temp_ref = [s for s in self.selected]
        for shape_sel in temp_ref:
            self.delete_shape(shape_sel)

        self.selected = []
        self.build_ui()
        self.app.inform.emit("[success]Done. Drill(s) deleted.")

    def delete_shape(self, shape):
        self.is_modified = True

        if shape in self.utility:
            self.utility.remove(shape)
            return

        for storage in self.storage_dict:
            # try:
            #     self.storage_dict[storage].remove(shape)
            # except:
            #     pass
            if shape in self.storage_dict[storage].get_objects():
                self.storage_dict[storage].remove(shape)
                # a hack to make the tool_table display less drills per diameter
                # self.points_edit it's only useful first time when we load the data into the storage
                # but is still used as referecen when building tool_table in self.build_ui()
                # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                # deleting self.points_edit elements (doesn't matter who but just the number) solved the display issue.
                del self.points_edit[storage][0]

        if shape in self.selected:
            self.selected.remove(shape)  # TODO: Check performance

    def delete_utility_geometry(self):
        # for_deletion = [shape for shape in self.shape_buffer if shape.utility]
        # for_deletion = [shape for shape in self.storage.get_objects() if shape.utility]
        for_deletion = [shape for shape in self.utility]
        for shape in for_deletion:
            self.delete_shape(shape)

        self.tool_shape.clear(update=True)
        self.tool_shape.redraw()

    def on_delete_btn(self):
        self.delete_selected()
        self.replot()

    def select_tool(self, toolname):
        """
        Selects a drawing tool. Impacts the object and GUI.

        :param toolname: Name of the tool.
        :return: None
        """
        self.tools_exc[toolname]["button"].setChecked(True)
        self.on_tool_select(toolname)

    def set_selected(self, shape):

        # Remove and add to the end.
        if shape in self.selected:
            self.selected.remove(shape)

        self.selected.append(shape)

    def set_unselected(self, shape):
        if shape in self.selected:
            self.selected.remove(shape)

    def on_array_type_combo(self):
        if self.array_type_combo.currentIndex() == 0:
            self.array_circular_frame.hide()
            self.array_linear_frame.show()
        else:
            self.delete_utility_geometry()
            self.array_circular_frame.show()
            self.array_linear_frame.hide()
            self.app.inform.emit("Click on the circular array Center position")

    def exc_add_drill(self):
        self.select_tool('add')
        return

    def exc_add_drill_array(self):
        self.select_tool('add_array')
        return

    def exc_copy_drills(self):
        self.select_tool('copy')
        return

def distance(pt1, pt2):
    return sqrt((pt1[0] - pt2[0]) ** 2 + (pt1[1] - pt2[1]) ** 2)


def mag(vec):
    return sqrt(vec[0] ** 2 + vec[1] ** 2)


def poly2rings(poly):
    return [poly.exterior] + [interior for interior in poly.interiors]
