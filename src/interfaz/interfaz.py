
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import threading
import json
import math
import logging

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.patches import Polygon as MplPolygon
import matplotlib.patches as mpatches

# ── Ruta raíz del proyecto ─────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _p in [
    os.path.join(ROOT, "src"),
    os.path.join(ROOT, "src", "config"),
    os.path.join(ROOT, "src", "moldes"),
    os.path.join(ROOT, "src", "nesting"),
    os.path.join(ROOT, "src", "metricas"),
    os.path.join(ROOT, "src", "validacion"),
    os.path.join(ROOT, "src", "exportacion"),
    os.path.join(ROOT, "src", "utils"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from logger_config import configurar_logging
configurar_logging("DEBUG")

from validador     import validar_molde, validar_parametros_tela
from gestor_moldes import (registrar_molde, listar_moldes, obtener_molde,
                            editar_molde, eliminar_molde)
from motor_nesting import ejecutar_nesting
from metricas      import calcular_metricas, comparar_manual_vs_optimizado
from exportador    import (exportar_json, exportar_csv, exportar_imagen,
                            guardar_simulacion, listar_simulaciones)

logger = logging.getLogger("nesting.interfaz")

# ══════════════════════════════════════════════════════════════════
#  PALETA DE COLORES
# ══════════════════════════════════════════════════════════════════
BG        = "#0f1117"
SURFACE   = "#1a1d27"
SURFACE2  = "#22263a"
BORDER    = "#2e3250"
ACCENT    = "#6c8ef5"
ACCENT2   = "#a78bfa"
SUCCESS   = "#34d399"
DANGER    = "#f87171"
WARN      = "#fbbf24"
TEXT      = "#e2e8f0"
TEXT2     = "#94a3b8"
CANVAS_BG = "#141824"
GRID_COL  = "#1e2236"

COLORES_PIEZA = [
    "#6c8ef5","#a78bfa","#34d399","#fbbf24","#f87171",
    "#38bdf8","#fb923c","#a3e635","#e879f9","#22d3ee",
    "#facc15","#4ade80","#fb7185","#818cf8","#2dd4bf",
]

FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_LABEL = ("Segoe UI", 9)
FONT_SMALL = ("Segoe UI", 8)
FONT_MONO  = ("Consolas", 8)
FONT_BTN   = ("Segoe UI", 9, "bold")


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════
def _frame(parent, **kw):
    return tk.Frame(parent, bg=kw.pop("bg", BG), **kw)

def _label(parent, text, font=FONT_LABEL, color=TEXT, bg=SURFACE, **kw):
    return tk.Label(parent, text=text, font=font, fg=color, bg=bg, **kw)

def _lighten(hex_color, factor=0.18):
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        r = min(255, int(r + (255-r)*factor))
        g = min(255, int(g + (255-g)*factor))
        b = min(255, int(b + (255-b)*factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color

def _btn(parent, text, command, color=ACCENT, text_color="white",
         width=None, padx=12, pady=5):
    kw = dict(text=text, command=command,
              bg=color, fg=text_color, activebackground=_lighten(color),
              activeforeground=text_color, font=FONT_BTN,
              relief="flat", cursor="hand2",
              padx=padx, pady=pady, bd=0)
    if width:
        kw["width"] = width
    return tk.Button(parent, **kw)

def _separator(parent, color=BORDER):
    tk.Frame(parent, bg=color, height=1).pack(fill="x", pady=5)


# ══════════════════════════════════════════════════════════════════
#  UTILIDADES GEOMÉTRICAS
# ══════════════════════════════════════════════════════════════════
def _bezier_puntos(p0, ctrl, p1, pasos=24):
    """
    Genera 'pasos' puntos a lo largo de una curva Bézier cuadrática.
    p0, ctrl, p1 son tuplas (x, y) en cm.
    """
    pts = []
    for i in range(pasos + 1):
        t  = i / pasos
        t2 = 1 - t
        x  = t2*t2*p0[0] + 2*t2*t*ctrl[0] + t*t*p1[0]
        y  = t2*t2*p0[1] + 2*t2*t*ctrl[1] + t*t*p1[1]
        pts.append((x, y))
    return pts

def _expandir_segmentos(segmentos):
    """
    Convierte lista de segmentos en lista plana de puntos para guardar.
    Segmento recto: {"tipo": "linea",  "p0": ..., "p1": ...}
    Segmento curvo: {"tipo": "bezier", "p0": ..., "ctrl": ..., "p1": ...}
    Retorna lista de (x,y) muestreados (sin duplicar puntos de unión).
    """
    if not segmentos:
        return []
    todos = []
    for i, seg in enumerate(segmentos):
        if seg["tipo"] == "linea":
            if i == 0:
                todos.append(seg["p0"])
            todos.append(seg["p1"])
        else:  # bezier
            pts_curva = _bezier_puntos(seg["p0"], seg["ctrl"], seg["p1"])
            if i == 0:
                todos.extend(pts_curva)
            else:
                todos.extend(pts_curva[1:])
    return todos


# ══════════════════════════════════════════════════════════════════
#  EDITOR VISUAL DE MOLDES
# ══════════════════════════════════════════════════════════════════
class EditorMolde(tk.Toplevel):
    """
    Editor visual tipo CAD para crear moldes textiles.

    Herramientas:
      - Polígono (líneas rectas): clic para añadir vértice.
      - Curva Bézier: clic para definir inicio y fin, luego arrastra control.
      - Rectángulo: arrastra para definir área.
      - Elipse: arrastra para definir forma.
    """

    GRID_SIZE   = 20   # px por cm
    POINT_R     = 5    # radio vértices
    CTRL_R      = 4    # radio puntos de control

    def __init__(self, master, datos_existentes=None, on_guardar=None):
        super().__init__(master)
        self.title("Editor de Molde")
        self.configure(bg=BG)
        self.grab_set()
        self.resizable(True, True)
        self.minsize(960, 660)

        self.on_guardar  = on_guardar
        self.resultado   = None
        self._datos      = datos_existentes or {}

        # ── Estado del editor ──────────────────────────────────────
        self._puntos = []      # Lista de puntos (x,y) para modo polígono
        self._segmentos = []   # Lista de segmentos para modo curvas
        self._cerrado = False
        self._modo_curvas = False  # True = usar segmentos, False = usar puntos

        # Arrastre
        self._drag_what = None   # ("vertice", idx) | ("ctrl", idx)
        self._drag_offset = None
        self._last_click_time = 0

        # Para herramienta bezier
        self._bezier_p0 = None
        self._bezier_waiting_ctrl = False

        # Para herramienta rect/ellipse
        self._rect_start = None
        self._preview_shape_id = None

        self._tool = tk.StringVar(value="poly")
        self._snap = tk.BooleanVar(value=True)
        self._offset_x = 40
        self._offset_y = 30

        # Cargar datos existentes si los hay
        if self._datos.get("coordenadas"):
            pts = [tuple(p) for p in self._datos["coordenadas"]]
            self._puntos = pts
            self._cerrado = False  # Inicialmente no cerrado

        self._build()
        self.canvas.after(100, self._draw_all)

    # ══════════════════════════════════════════════════════════════
    #  PROPIEDADES DERIVADAS
    # ══════════════════════════════════════════════════════════════
    def _vertices(self):
        """Lista de vértices principales."""
        if self._modo_curvas:
            if not self._segmentos:
                return []
            pts = [self._segmentos[0]["p0"]]
            for seg in self._segmentos:
                pts.append(seg["p1"])
            return pts
        else:
            return self._puntos.copy()

    def _puntos_para_guardar(self):
        """Expande todos los segmentos/puntos en puntos para guardar."""
        if self._modo_curvas and self._segmentos:
            return _expandir_segmentos(self._segmentos)
        elif self._puntos:
            pts = self._puntos.copy()
            if self._cerrado and len(pts) >= 3:
                pts.append(pts[0])
            return pts
        return []

    def _ultimo_punto(self):
        """Retorna el último punto colocado."""
        if self._modo_curvas and self._segmentos:
            return self._segmentos[-1]["p1"]
        elif self._puntos:
            return self._puntos[-1] if self._puntos else None
        return None

    def _primer_punto(self):
        if self._modo_curvas and self._segmentos:
            return self._segmentos[0]["p0"]
        elif self._puntos:
            return self._puntos[0] if self._puntos else None
        return None

    # ══════════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN UI
    # ══════════════════════════════════════════════════════════════
    def _build(self):
        hdr = _frame(self, bg=SURFACE)
        hdr.pack(fill="x")
        _label(hdr, "  ✏  Editor de Molde",
               font=FONT_TITLE, bg=SURFACE, color=ACCENT).pack(side="left", pady=10, padx=4)
        self._lbl_hint = _label(
            hdr, "Herramienta: Polígono  •  Clic para agregar vértice  •  Ctrl+Z para deshacer",
            font=FONT_SMALL, bg=SURFACE, color=TEXT2)
        self._lbl_hint.pack(side="left", padx=10)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = _frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        left = _frame(body, bg=SURFACE, width=235)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_sidebar(left)

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        right = _frame(body, bg=CANVAS_BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_canvas(right)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        foot = _frame(self, bg=SURFACE)
        foot.pack(fill="x")
        _btn(foot, "✔  Guardar Molde", self._guardar,
             color=SUCCESS, text_color="#0a0a0a", padx=22).pack(side="right", pady=8, padx=10)
        _btn(foot, "✖  Cancelar", self.destroy,
             color=SURFACE2, text_color=TEXT, padx=16).pack(side="right", pady=8, padx=4)
        self._lbl_status = _label(foot, "Sin puntos aún",
                                   font=FONT_SMALL, bg=SURFACE, color=TEXT2)
        self._lbl_status.pack(side="left", padx=14)

    def _build_sidebar(self, parent):
        # DATOS DEL MOLDE
        self._sec_title(parent, "DATOS DEL MOLDE")
        for label, attr, key in [
            ("Nombre",     "_e_nombre", "nombre"),
            ("Descripción","_e_desc",   "descripcion"),
            ("Cantidad",   "_e_cant",   "cantidad"),
        ]:
            _label(parent, label, font=FONT_SMALL, bg=SURFACE,
                   color=TEXT2).pack(anchor="w", fill="x", padx=12, pady=(4,0))
            default = str(self._datos.get(key, 1 if key == "cantidad" else ""))
            e = tk.Entry(parent, font=FONT_LABEL, bg=SURFACE2, fg=TEXT,
                         relief="flat", bd=0, insertbackground=ACCENT,
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=BORDER)
            e.insert(0, default)
            e.pack(fill="x", padx=12, pady=(1,4), ipady=5)
            setattr(self, attr, e)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=6)

        # HERRAMIENTAS
        self._sec_title(parent, "HERRAMIENTA DE DIBUJO")
        tools = [
            ("poly",    "✏  Polígono (líneas rectas)"),
            ("bezier",  "〜  Curva Bézier"),
            ("rect",    "▭  Rectángulo"),
            ("ellipse", "○  Elipse / Óvalo"),
        ]
        for key, label in tools:
            tk.Radiobutton(
                parent, text=label, variable=self._tool, value=key,
                bg=SURFACE, fg=TEXT, selectcolor=ACCENT,
                activebackground=SURFACE, activeforeground=ACCENT,
                font=FONT_LABEL, cursor="hand2", indicatoron=True, relief="flat",
                command=lambda k=key: self._on_tool_change(k)
            ).pack(anchor="w", padx=14, pady=1)

        tk.Checkbutton(
            parent, text="⊞ Ajustar a grilla (0.5 cm)",
            variable=self._snap, bg=SURFACE, fg=TEXT2,
            selectcolor=ACCENT, activebackground=SURFACE,
            font=FONT_SMALL, cursor="hand2", relief="flat"
        ).pack(anchor="w", padx=14, pady=(8,0))

        # Leyenda de colores
        frm_leyenda = _frame(parent, bg=SURFACE)
        frm_leyenda.pack(fill="x", padx=14, pady=(6,0))
        for col, txt in [(SUCCESS,"Primer vértice"),(ACCENT,"Vértice"),(WARN,"Control curva")]:
            row = _frame(frm_leyenda, bg=SURFACE)
            row.pack(fill="x", pady=1)
            tk.Canvas(row, width=10, height=10, bg=col,
                      highlightthickness=0, bd=0).pack(side="left", padx=(0,4))
            _label(row, txt, font=("Segoe UI",7), bg=SURFACE,
                   color=TEXT2).pack(side="left")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=6)

        # ACCIONES
        self._sec_title(parent, "ACCIONES")
        _btn(parent, "↩  Deshacer  (Ctrl+Z)", self._undo, color=SURFACE2,
             text_color=TEXT, pady=4).pack(fill="x", padx=12, pady=2)
        _btn(parent, "⊙  Cerrar forma", self._cerrar_forma, color=SURFACE2,
             text_color=ACCENT2, pady=4).pack(fill="x", padx=12, pady=2)
        _btn(parent, "🗑  Limpiar todo", self._clear, color=DANGER,
             text_color="white", pady=4).pack(fill="x", padx=12, pady=2)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=6)

        # PLANTILLAS
        self._sec_title(parent, "PLANTILLAS")
        frm = _frame(parent, bg=SURFACE)
        frm.pack(fill="x", padx=12)
        ejemplos = [
            ("Manga",     self._ej_manga),
            ("Pantalón",  self._ej_pantalon),
            ("Pechera",   self._ej_pechera),
            ("Falda",     self._ej_falda),
            ("Triángulo", self._ej_triangulo),
            ("Trapecio",  self._ej_trapecio),
        ]
        for i, (nom, fn) in enumerate(ejemplos):
            b = tk.Button(frm, text=nom, command=fn,
                          bg=SURFACE2, fg=ACCENT2, font=FONT_SMALL,
                          relief="flat", cursor="hand2", pady=3, bd=0)
            b.grid(row=i//2, column=i%2, padx=2, pady=2, sticky="ew")
            b.bind("<Enter>", lambda e, w=b: w.config(bg=ACCENT2, fg=BG))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=SURFACE2, fg=ACCENT2))
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=6)

        # IMPORTAR / EXPORTAR
        self._sec_title(parent, "IMPORTAR / EXPORTAR")
        _btn(parent, "📂  Importar .json", self._importar,
             color=SURFACE2, text_color=ACCENT, pady=4).pack(fill="x", padx=12, pady=2)
        _btn(parent, "💾  Exportar .json", self._exportar,
             color=SURFACE2, text_color=SUCCESS, pady=4).pack(fill="x", padx=12, pady=2)

    def _sec_title(self, parent, text):
        _label(parent, f"  {text}", font=("Segoe UI",7,"bold"),
               bg=SURFACE, color=TEXT2).pack(anchor="w", pady=(4,0))

    def _build_canvas(self, parent):
        bar = _frame(parent, bg=CANVAS_BG)
        bar.pack(fill="x")
        self._lbl_mouse = _label(bar, "  x: —  y: —",
                                  font=FONT_MONO, bg=CANVAS_BG, color=TEXT2)
        self._lbl_mouse.pack(side="left", pady=4)

        self.canvas = tk.Canvas(parent, bg=CANVAS_BG, cursor="crosshair",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # ── Bindings ──────────────────────────────────────────────
        self.canvas.bind("<Button-1>",       self._on_btn1_press)
        self.canvas.bind("<B1-Motion>",      self._on_drag)
        self.canvas.bind("<ButtonRelease-1>",self._on_release)
        self.canvas.bind("<Motion>",         self._on_motion)
        self.canvas.bind("<Configure>",      lambda e: self._draw_all())

        # Ctrl+Z global en la ventana
        self.bind("<Control-z>", lambda e: self._undo())
        self.bind("<Control-Z>", lambda e: self._undo())

    # ══════════════════════════════════════════════════════════════
    #  CONVERSIONES
    # ══════════════════════════════════════════════════════════════
    def _px2cm(self, px, py):
        return ((px - self._offset_x) / self.GRID_SIZE,
                (py - self._offset_y) / self.GRID_SIZE)

    def _cm2px(self, cx, cy):
        return (cx * self.GRID_SIZE + self._offset_x,
                cy * self.GRID_SIZE + self._offset_y)

    def _snap_pt(self, cx, cy):
        if self._snap.get():
            return round(cx * 2) / 2, round(cy * 2) / 2
        return cx, cy

    # ══════════════════════════════════════════════════════════════
    #  DIBUJO
    # ══════════════════════════════════════════════════════════════
    def _draw_all(self, mouse_px=None):
        """Redibuja todo el canvas."""
        c = self.canvas
        c.delete("all")
        W = c.winfo_width() or 700
        H = c.winfo_height() or 560

        # Grilla
        for xi in range(0, W, self.GRID_SIZE):
            c.create_line(xi, 0, xi, H, fill=GRID_COL, width=1)
        for yi in range(0, H, self.GRID_SIZE):
            c.create_line(0, yi, W, yi, fill=GRID_COL, width=1)

        # Ejes
        ox, oy = self._offset_x, self._offset_y
        c.create_line(ox, 0, ox, H, fill=BORDER, width=1, dash=(4,3))
        c.create_line(0, oy, W, oy, fill=BORDER, width=1, dash=(4,3))
        c.create_text(ox+4, oy-8, text="0,0", fill=TEXT2,
                      font=FONT_SMALL, anchor="w")
        
        # Regla
        for i in range(0, int((W-ox)/self.GRID_SIZE)+1):
            px = ox + i*self.GRID_SIZE
            if 0 < px < W:
                c.create_text(px, oy-5, text=str(i), fill=TEXT2,
                              font=("Consolas",6), anchor="s")

        # Dibujar forma según el modo
        if self._modo_curvas and self._segmentos:
            self._draw_curves(c)
        elif self._puntos:
            self._draw_polygon(c)
        else:
            # Mostrar hint si no hay puntos
            tool = self._tool.get()
            hints = {
                "poly": "Clic para agregar el primer vértice",
                "bezier": "Clic para colocar punto de inicio de la curva",
                "rect": "Arrastra para definir el rectángulo",
                "ellipse": "Arrastra para definir la elipse"
            }
            c.create_text(W//2, H//2, text=hints.get(tool, "Selecciona una herramienta"),
                          fill=BORDER, font=("Segoe UI",12))

        # Dibujar preview de bezier en curso
        if self._bezier_p0 and mouse_px and self._tool.get() == "bezier":
            bx, by = self._cm2px(*self._bezier_p0)
            c.create_line(bx, by, mouse_px[0], mouse_px[1],
                          fill=ACCENT2, width=2, dash=(4,2))

        # Preview de rect/ellipse
        if self._rect_start and self._tool.get() in ("rect", "ellipse") and not self._preview_shape_id:
            if mouse_px:
                cx, cy = self._px2cm(mouse_px[0], mouse_px[1])
                cx, cy = self._snap_pt(cx, cy)
                pts = self._shape_pts(self._rect_start, (cx, cy), self._tool.get())
                if len(pts) >= 3:
                    px_flat = []
                    for (qx, qy) in pts:
                        ppx, ppy = self._cm2px(qx, qy)
                        px_flat += [ppx, ppy]
                    self._preview_shape_id = c.create_polygon(
                        px_flat, outline=ACCENT2, fill=ACCENT2+"22", 
                        width=2, dash=(4,2))

        # Actualizar estado
        self._update_status()

    def _draw_polygon(self, canvas):
        """Dibuja polígono desde lista de puntos - versión CORREGIDA."""
        verts = self._puntos
        if not verts:
            return

        # Dibujar líneas entre puntos consecutivos
        for i in range(len(verts) - 1):
            x1, y1 = self._cm2px(*verts[i])
            x2, y2 = self._cm2px(*verts[i+1])
            canvas.create_line(x1, y1, x2, y2, fill=ACCENT, width=2)

        # Si está cerrado y hay al menos 3 puntos, dibujar línea de cierre
        if self._cerrado and len(verts) >= 3:
            x1, y1 = self._cm2px(*verts[-1])
            x2, y2 = self._cm2px(*verts[0])
            canvas.create_line(x1, y1, x2, y2, fill=ACCENT, width=2)
            
            # Dibujar relleno SOLO si está cerrado y hay al menos 3 puntos
            px_flat = []
            for cx, cy in verts:
                ppx, ppy = self._cm2px(cx, cy)
                px_flat += [ppx, ppy]
            # Cerrar el polígono para el relleno
            px_flat.extend([px_flat[0], px_flat[1]])
            canvas.create_polygon(px_flat, fill=ACCENT+"18", outline="", smooth=False)

        # Dibujar todos los vértices (SIEMPRE se muestran)
        r = self.POINT_R
        for i, (cx, cy) in enumerate(verts):
            ppx, ppy = self._cm2px(cx, cy)
            col = SUCCESS if i == 0 else ACCENT
            canvas.create_oval(ppx-r, ppy-r, ppx+r, ppy+r,
                               fill=col, outline="white", width=1.5,
                               tags=f"vert_{i}")
            canvas.create_text(ppx+8, ppy-8,
                               text=f"({cx:.1f},{cy:.1f})",
                               fill=TEXT2, font=("Consolas",6), anchor="w")

    def _draw_curves(self, canvas):
        """Dibuja curvas desde segmentos."""
        # Relleno solo si está cerrado
        if self._cerrado:
            todos_pts = self._puntos_para_guardar()
            if len(todos_pts) >= 3:
                px_flat = []
                for cx, cy in todos_pts:
                    ppx, ppy = self._cm2px(cx, cy)
                    px_flat += [ppx, ppy]
                canvas.create_polygon(px_flat, fill=ACCENT+"18", outline="", smooth=False)

        # Dibujar cada segmento
        for idx, seg in enumerate(self._segmentos):
            if seg["tipo"] == "linea":
                x1, y1 = self._cm2px(*seg["p0"])
                x2, y2 = self._cm2px(*seg["p1"])
                canvas.create_line(x1, y1, x2, y2, fill=ACCENT, width=2)
            else:  # bezier
                pts = _bezier_puntos(seg["p0"], seg["ctrl"], seg["p1"])
                coords = []
                for (cx, cy) in pts:
                    ppx, ppy = self._cm2px(cx, cy)
                    coords += [ppx, ppy]
                for i in range(len(coords)//2 - 1):
                    canvas.create_line(
                        coords[i*2], coords[i*2+1],
                        coords[i*2+2], coords[i*2+3],
                        fill=ACCENT, width=2)
                
                # Línea punteada al punto de control
                cx0, cy0 = self._cm2px(*seg["p0"])
                cxc, cyc = self._cm2px(*seg["ctrl"])
                cx1, cy1 = self._cm2px(*seg["p1"])
                canvas.create_line(cx0, cy0, cxc, cyc, fill=WARN, width=1, dash=(3,3))
                canvas.create_line(cxc, cyc, cx1, cy1, fill=WARN, width=1, dash=(3,3))
                
                # Punto de control
                r = self.CTRL_R
                canvas.create_rectangle(cxc-r, cyc-r, cxc+r, cyc+r,
                                        fill=WARN, outline="white", width=1.5,
                                        tags=f"ctrl_{idx}")

        # Dibujar vértices
        verts = self._vertices()
        r = self.POINT_R
        for i, (cx, cy) in enumerate(verts):
            ppx, ppy = self._cm2px(cx, cy)
            col = SUCCESS if i == 0 else ACCENT
            canvas.create_oval(ppx-r, ppy-r, ppx+r, ppy+r,
                               fill=col, outline="white", width=1.5,
                               tags=f"vert_{i}")
            canvas.create_text(ppx+8, ppy-8,
                               text=f"({cx:.1f},{cy:.1f})",
                               fill=TEXT2, font=("Consolas",6), anchor="w")

        # Línea de cierre si está cerrado
        if self._cerrado and len(verts) >= 3:
            x1, y1 = self._cm2px(*verts[-1])
            x2, y2 = self._cm2px(*verts[0])
            canvas.create_line(x1, y1, x2, y2, fill=ACCENT2, width=1, dash=(5,3))

    def _update_status(self):
        """Actualiza la barra de estado."""
        verts = self._vertices()
        n_verts = len(verts)
        
        if n_verts < 3:
            self._lbl_status.config(text=f"{n_verts} vértice(s) — necesitas al menos 3")
        else:
            pts = self._puntos_para_guardar()
            if pts:
                n = len(pts)
                # Calcular área solo si está cerrado
                if self._cerrado:
                    area = abs(sum(
                        pts[i][0]*pts[(i+1)%n][1] - pts[(i+1)%n][0]*pts[i][1]
                        for i in range(n)
                    )) / 2
                else:
                    area = 0
                cerr = "  •  ✓ Cerrado" if self._cerrado else "  •  ✗ Abierto"
                self._lbl_status.config(
                    text=f"{n_verts} vértices  •  Área ≈ {area:.1f} cm²{cerr}")

    # ══════════════════════════════════════════════════════════════
    #  DETECCIÓN DE ELEMENTOS CERCANOS
    # ══════════════════════════════════════════════════════════════
    def _find_near(self, px, py, thresh=12):
        """Busca el elemento más cercano al cursor."""
        best_d = thresh ** 2
        result = None

        # Vértices
        for i, (cx, cy) in enumerate(self._vertices()):
            qx, qy = self._cm2px(cx, cy)
            d = (px-qx)**2 + (py-qy)**2
            if d < best_d:
                best_d, result = d, ("vertice", i)

        # Puntos de control de curvas
        if self._modo_curvas:
            for i, seg in enumerate(self._segmentos):
                if seg["tipo"] == "bezier":
                    qx, qy = self._cm2px(*seg["ctrl"])
                    d = (px-qx)**2 + (py-qy)**2
                    if d < best_d:
                        best_d, result = d, ("ctrl", i)

        return result

    # ══════════════════════════════════════════════════════════════
    #  EVENTOS DEL CANVAS
    # ══════════════════════════════════════════════════════════════
    def _on_btn1_press(self, event):
        import time
        px, py = event.x, event.y

        # Detección de doble clic
        now = time.time()
        is_dbl = (now - self._last_click_time) < 0.35
        self._last_click_time = now

        if is_dbl:
            self._handle_double_click(px, py)
            return

        # Verificar si estamos sobre un elemento arrastrable
        hit = self._find_near(px, py)
        if hit is not None:
            self._drag_what = hit
            # Guardar offset para arrastre suave
            if hit[0] == "vertice":
                cx, cy = self._vertices()[hit[1]]
                qx, qy = self._cm2px(cx, cy)
                self._drag_offset = (px - qx, py - qy)
            elif hit[0] == "ctrl":
                ctrl = self._segmentos[hit[1]]["ctrl"]
                qx, qy = self._cm2px(*ctrl)
                self._drag_offset = (px - qx, py - qy)
            return

        # Acción según herramienta
        tool = self._tool.get()
        cx, cy = self._snap_pt(*self._px2cm(px, py))
        cx, cy = max(0.0, cx), max(0.0, cy)

        if tool == "poly":
            self._poly_add_point(cx, cy)
        elif tool == "bezier":
            self._bezier_click(cx, cy, px, py)
        elif tool in ("rect", "ellipse"):
            self._rect_start = (cx, cy)
            self._preview_shape_id = None

    def _handle_double_click(self, px, py):
        """Cierra la forma conectando último con primer vértice."""
        if self._cerrado:
            return
        verts = self._vertices()
        if len(verts) >= 3:
            self._cerrado = True
            self._draw_all()
            self._lbl_hint.config(text="Forma cerrada • Puedes seguir añadiendo puntos")

    def _poly_add_point(self, cx, cy):
        """Añade un punto al polígono - CORREGIDO."""
        if self._modo_curvas:
            # Cambiar a modo puntos
            self._modo_curvas = False
            self._segmentos = []
        
        self._puntos.append((cx, cy))
        self._draw_all()  # Redibujar inmediatamente para mostrar el nuevo punto

    def _bezier_click(self, cx, cy, px, py):
        """Maneja clic en modo bezier."""
        if self._bezier_p0 is None:
            # Primer clic: definir inicio
            if not self._modo_curvas and self._puntos:
                # Convertir puntos existentes a segmentos
                self._convertir_puntos_a_segmentos()
            
            self._modo_curvas = True
            ultimo = self._ultimo_punto()
            if ultimo is not None:
                self._bezier_p0 = ultimo
            else:
                self._bezier_p0 = (cx, cy)
                # Añadir como primer punto también
                self._segmentos = []
            self._draw_all(mouse_px=(px, py))
        else:
            # Segundo clic: definir fin y crear curva
            p1 = (cx, cy)
            ctrl = ((self._bezier_p0[0] + p1[0]) / 2, 
                    (self._bezier_p0[1] + p1[1]) / 2)
            
            self._segmentos.append({
                "tipo": "bezier",
                "p0": self._bezier_p0,
                "ctrl": ctrl,
                "p1": p1
            })
            self._bezier_p0 = None
            self._draw_all()
            self._lbl_hint.config(
                text="Curva añadida  •  Arrastra el punto naranja ◆ para cambiar la curvatura")

    def _convertir_puntos_a_segmentos(self):
        """Convierte puntos existentes a segmentos de línea."""
        if len(self._puntos) >= 2:
            for i in range(len(self._puntos) - 1):
                self._segmentos.append({
                    "tipo": "linea",
                    "p0": self._puntos[i],
                    "p1": self._puntos[i+1]
                })
            self._puntos = []

    def _on_drag(self, event):
        px, py = event.x, event.y
        
        # Arrastre de vértice o control
        if self._drag_what is not None:
            kind, idx = self._drag_what
            # Ajustar por offset
            if self._drag_offset:
                qx = px - self._drag_offset[0]
                qy = py - self._drag_offset[1]
            else:
                qx, qy = px, py
            
            cx, cy = self._snap_pt(*self._px2cm(qx, qy))
            cx, cy = max(0.0, cx), max(0.0, cy)
            
            if kind == "vertice":
                self._move_vertex(idx, (cx, cy))
            elif kind == "ctrl":
                self._segmentos[idx]["ctrl"] = (cx, cy)
            self._draw_all()
            return

        # Preview para rect/ellipse
        tool = self._tool.get()
        if tool in ("rect", "ellipse") and self._rect_start:
            if self._preview_shape_id:
                self.canvas.delete(self._preview_shape_id)
                self._preview_shape_id = None
            
            cx, cy = self._snap_pt(*self._px2cm(event.x, event.y))
            pts = self._shape_pts(self._rect_start, (cx, cy), tool)
            if len(pts) >= 3:
                px_flat = []
                for (qx, qy) in pts:
                    ppx, ppy = self._cm2px(qx, qy)
                    px_flat += [ppx, ppy]
                self._preview_shape_id = self.canvas.create_polygon(
                    px_flat, outline=ACCENT2, fill=ACCENT2+"22",
                    width=2, dash=(4,2))

        # Preview de bezier
        if tool == "bezier" and self._bezier_p0:
            self._draw_all(mouse_px=(event.x, event.y))

    def _on_release(self, event):
        if self._drag_what is not None:
            self._drag_what = None
            self._drag_offset = None
            self._draw_all()
            return

        tool = self._tool.get()
        if tool in ("rect", "ellipse") and self._rect_start:
            if self._preview_shape_id:
                self.canvas.delete(self._preview_shape_id)
                self._preview_shape_id = None
            
            cx, cy = self._snap_pt(*self._px2cm(event.x, event.y))
            pts = self._shape_pts(self._rect_start, (cx, cy), tool)
            
            if len(pts) >= 3:
                if not self._modo_curvas and self._puntos:
                    self._puntos = []
                self._modo_curvas = True
                self._segmentos = []
                
                for i in range(len(pts)):
                    p0 = pts[i]
                    p1 = pts[(i+1) % len(pts)]
                    self._segmentos.append({"tipo": "linea", "p0": p0, "p1": p1})
                self._cerrado = True
            
            self._rect_start = None
            self._draw_all()

    def _on_motion(self, event):
        cx, cy = self._snap_pt(*self._px2cm(event.x, event.y))
        self._lbl_mouse.config(text=f"  x: {cx:.1f} cm   y: {cy:.1f} cm")

        # Actualizar preview
        tool = self._tool.get()
        if tool == "bezier" and self._bezier_p0:
            self._draw_all(mouse_px=(event.x, event.y))

    def _move_vertex(self, idx, new_pt):
        """Mueve un vértice y actualiza todos los segmentos que lo usan."""
        if self._modo_curvas:
            # Actualizar en segmentos
            if idx < len(self._segmentos):
                self._segmentos[idx]["p0"] = new_pt
            if idx > 0:
                self._segmentos[idx-1]["p1"] = new_pt
            if self._cerrado and idx == len(self._segmentos):
                self._segmentos[-1]["p1"] = new_pt
        else:
            # Actualizar en lista de puntos
            if 0 <= idx < len(self._puntos):
                self._puntos[idx] = new_pt

    def _shape_pts(self, start, end, tool):
        """Genera puntos para rectángulo o elipse."""
        if start is None or end is None:
            return []
        
        x1, y1 = min(start[0], end[0]), min(start[1], end[1])
        x2, y2 = max(start[0], end[0]), max(start[1], end[1])
        
        if x2 <= x1 or y2 <= y1:
            return []
        
        if tool == "rect":
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        else:  # ellipse
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            rx, ry = (x2 - x1) / 2, (y2 - y1) / 2
            n = 24
            return [(cx + rx * math.cos(2 * math.pi * i / n),
                     cy + ry * math.sin(2 * math.pi * i / n)) 
                    for i in range(n)]

    # ══════════════════════════════════════════════════════════════
    #  HERRAMIENTAS — cambio de modo
    # ══════════════════════════════════════════════════════════════
    def _on_tool_change(self, key):
        cursors = {
            "poly": "crosshair",
            "bezier": "crosshair",
            "rect": "sizing",
            "ellipse": "sizing"
        }
        self.canvas.config(cursor=cursors.get(key, "crosshair"))
        self._bezier_p0 = None
        self._rect_start = None
        
        hints = {
            "poly": "Polígono  •  Clic para agregar vértice  •  Doble clic para cerrar",
            "bezier": "Curva Bézier  •  1er clic: inicio  •  2do clic: fin  •  Arrastra ◆ para curvar",
            "rect": "Rectángulo  •  Mantén presionado y arrastra para definir el área",
            "ellipse": "Elipse  •  Mantén presionado y arrastra para definir la forma",
        }
        self._lbl_hint.config(text=hints.get(key, ""))
        self._draw_all()

    # ══════════════════════════════════════════════════════════════
    #  ACCIONES
    # ══════════════════════════════════════════════════════════════
    def _undo(self):
        """Deshace la última acción."""
        if self._bezier_p0 is not None:
            self._bezier_p0 = None
        elif self._modo_curvas and self._segmentos:
            self._segmentos.pop()
            if not self._segmentos:
                self._modo_curvas = False
        elif not self._modo_curvas and self._puntos:
            self._puntos.pop()
        self._cerrado = False
        self._draw_all()

    def _cerrar_forma(self):
        """Cierra la forma conectando el último vértice con el primero."""
        if self._cerrado:
            messagebox.showinfo("Ya cerrado", "La forma ya está cerrada.", parent=self)
            return
        
        verts = self._vertices()
        if len(verts) < 3:
            messagebox.showwarning("Pocos vértices",
                "Necesitas al menos 3 vértices para cerrar la forma.", parent=self)
            return
        
        self._cerrado = True
        self._draw_all()

    def _clear(self):
        """Limpia todos los puntos y segmentos."""
        if (self._puntos or self._segmentos) and messagebox.askyesno(
                "Limpiar", "¿Borrar toda la forma?", parent=self):
            self._puntos = []
            self._segmentos = []
            self._cerrado = False
            self._modo_curvas = False
            self._bezier_p0 = None
            self._rect_start = None
            self._draw_all()

    def _load_pts(self, pts, nombre="", desc=""):
        """Carga una lista de puntos como polígono."""
        self._puntos = [(float(p[0]), float(p[1])) for p in pts]
        self._segmentos = []
        self._cerrado = False
        self._modo_curvas = False
        self._bezier_p0 = None
        
        if nombre:
            self._e_nombre.delete(0, "end")
            self._e_nombre.insert(0, nombre)
        if desc:
            self._e_desc.delete(0, "end")
            self._e_desc.insert(0, desc)
        
        self._draw_all()

    # ── Plantillas ─────────────────────────────────────────────────
    def _ej_manga(self):
        self._load_pts([(0,0),(25,0),(28,5),(26,30),(20,35),(8,33),(0,25)],
                       "manga_caporal","Manga traje caporal")
    
    def _ej_pantalon(self):
        self._load_pts([(0,0),(40,0),(42,10),(38,60),(30,65),(10,63),(2,55)],
                       "pantalon_caporal","Pantalón traje caporal")
    
    def _ej_pechera(self):
        self._load_pts([(5,0),(35,0),(38,8),(35,25),(20,28),(5,25),(2,8)],
                       "pechera_caporal","Pechera traje caporal")
    
    def _ej_falda(self):
        self._load_pts([(0,5),(15,0),(45,0),(60,5),(58,50),(30,55),(2,50)],
                       "falda_caporal","Falda traje caporal")
    
    def _ej_triangulo(self):
        self._load_pts([(0,0),(30,0),(15,25)],
                       "triangulo","Triángulo")
    
    def _ej_trapecio(self):
        self._load_pts([(5,0),(35,0),(40,20),(0,20)],
                       "trapecio","Trapecio")

    # ── Importar / Exportar ────────────────────────────────────────
    def _importar(self):
        ruta = filedialog.askopenfilename(
            title="Importar molde", parent=self,
            filetypes=[("Molde JSON","*.json"),("Todos","*.*")])
        if not ruta: 
            return
        
        try:
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
            
            coords = d.get("coordenadas", [])
            if len(coords) < 3:
                messagebox.showerror("Error",
                    "El archivo no tiene vértices suficientes (mín. 3).", parent=self)
                return
            
            pts = [tuple(p) for p in coords]
            self._load_pts(pts,
                          d.get("nombre", ""),
                          d.get("descripcion", ""))
            
            if d.get("cantidad"):
                self._e_cant.delete(0, "end")
                self._e_cant.insert(0, str(d["cantidad"]))
            
            messagebox.showinfo("Importado",
                f"Molde '{d.get('nombre', '')}' cargado con {len(pts)} puntos.",
                parent=self)
        except Exception as exc:
            messagebox.showerror("Error al importar", str(exc), parent=self)

    def _exportar(self):
        pts = self._puntos_para_guardar()
        if len(pts) < 3:
            messagebox.showwarning("Sin forma",
                "Dibuja al menos 3 puntos primero.", parent=self)
            return
        
        nombre = self._e_nombre.get().strip() or "molde"
        ruta = filedialog.asksaveasfilename(
            title="Exportar molde", parent=self,
            defaultextension=".json", initialfile=f"{nombre}.json",
            filetypes=[("Molde JSON","*.json")])
        
        if not ruta: 
            return
        
        datos = {
            "nombre": nombre,
            "descripcion": self._e_desc.get().strip(),
            "cantidad": int(self._e_cant.get().strip() or "1"),
            "coordenadas": [list(p) for p in pts],
            "cerrado": self._cerrado
        }
        
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        
        messagebox.showinfo("Exportado", f"Molde guardado en:\n{ruta}", parent=self)

    # ── Guardar al sistema ─────────────────────────────────────────
    def _guardar(self):
        nombre = self._e_nombre.get().strip().replace(" ", "_")
        if not nombre:
            messagebox.showerror("Error", "El nombre es obligatorio.", parent=self)
            return
        
        try:
            cantidad = int(self._e_cant.get().strip())
        except ValueError:
            messagebox.showerror("Error", "La cantidad debe ser un número entero.", parent=self)
            return

        pts = self._puntos_para_guardar()
        if len(pts) < 3:
            messagebox.showerror("Error",
                "El molde necesita al menos 3 puntos.\n"
                "Dibuja la forma en el canvas.", parent=self)
            return

        valido, msg = validar_molde(pts)
        if not valido:
            messagebox.showerror("Molde inválido", msg, parent=self)
            return

        self.resultado = {
            "nombre": nombre,
            "coordenadas": pts,
            "cantidad": cantidad,
            "descripcion": self._e_desc.get().strip(),
            "cerrado": self._cerrado
        }
        
        self.destroy()
        if self.on_guardar:
            self.on_guardar(self.resultado)


# ══════════════════════════════════════════════════════════════════
#  VENTANA COMPARACIÓN
# ══════════════════════════════════════════════════════════════════
class VentanaComparacion(tk.Toplevel):
    def __init__(self, master, resultado_nesting):
        super().__init__(master)
        self.title("Comparación Manual vs Sistema")
        self.configure(bg=BG)
        self.grab_set()
        self.resizable(False, False)
        self._res = resultado_nesting
        self._build()

    def _build(self):
        frm = _frame(self, bg=SURFACE)
        frm.pack(fill="both", expand=True, padx=2, pady=2)

        _label(frm, "Manual vs Sistema Optimizado",
               font=FONT_TITLE, bg=SURFACE, color=ACCENT).pack(pady=(18,4))

        m   = self._res.get("metricas",{})
        pct = m.get("porcentaje_uso",0)
        _label(frm, f"Aprovechamiento del sistema: {pct:.1f}%",
               font=("Segoe UI",10,"bold"), bg=SURFACE, color=SUCCESS).pack()

        tk.Frame(frm, bg=BORDER, height=1).pack(fill="x", padx=20, pady=12)

        _label(frm, "Porcentaje de aprovechamiento manual (%):",
               font=FONT_LABEL, bg=SURFACE, color=TEXT2).pack()
        self.e = tk.Entry(frm, font=FONT_LABEL, bg=SURFACE2, fg=TEXT,
                          width=12, relief="flat", bd=0,
                          insertbackground=ACCENT,
                          highlightthickness=1, highlightcolor=ACCENT,
                          highlightbackground=BORDER)
        self.e.insert(0,"65.0")
        self.e.pack(ipady=6, pady=4)

        self.lbl = _label(frm,"",font=("Segoe UI",9), bg=SURFACE,
                           color=TEXT, justify="left", wraplength=360)
        self.lbl.pack(pady=8, padx=20)

        _btn(frm,"Calcular",self._calc,color=ACCENT).pack(pady=4)
        _btn(frm,"Cerrar",self.destroy,color=SURFACE2,text_color=TEXT).pack(pady=(2,18))

    def _calc(self):
        try:
            pm = float(self.e.get())
            if not 0<=pm<=100: raise ValueError
        except ValueError:
            messagebox.showerror("Error","Ingrese un % válido (0–100).",parent=self)
            return
        m = self._res.get("metricas",{})
        c = comparar_manual_vs_optimizado(pm, m.get("porcentaje_uso",0),
                                           m.get("area_tela_cm2",1))
        d = c["diferencial_pct"]
        s = "+" if d>0 else ""
        col = SUCCESS if d>0 else (DANGER if d<0 else TEXT)
        self.lbl.config(fg=col, text=(
            f"Distribución manual:   {c['porcentaje_manual']:.1f}%\n"
            f"Distribución sistema:  {c['porcentaje_optimizado']:.1f}%\n"
            f"Diferencial:           {s}{d:.1f}%\n"
            f"Área adicional:        {c['ahorro_area_cm2']:.1f} cm²\n\n"
            f"📌 {c['recomendacion']}"))


# ══════════════════════════════════════════════════════════════════
#  APLICACIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════
class AppNesting:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NestingPro  •  BordArte Paz  •  EISPDM 2026")
        self.root.configure(bg=BG)
        self.root.geometry("1360x820")
        self.root.minsize(1100, 660)

        self._resultado_actual = None
        self._fig = None
        self._canvas_mpl = None

        self._build_ui()
        self._refresh_moldes()

    def _build_ui(self):
        self._build_topbar()
        main = _frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=(0,8))

        self.frm_left = _frame(main, bg=SURFACE, width=295)
        self.frm_left.pack(side="left", fill="y", padx=(0,8))
        self.frm_left.pack_propagate(False)

        self.frm_right = _frame(main, bg=BG)
        self.frm_right.pack(side="left", fill="both", expand=True)

        self._build_panel_moldes()
        self._build_panel_params()
        self._build_panel_actions()
        self._build_panel_metrics()
        self._build_panel_viz()

    def _build_topbar(self):
        bar = _frame(self.root, bg=SURFACE)
        bar.pack(fill="x")
        lf = _frame(bar, bg=SURFACE)
        lf.pack(side="left", padx=16, pady=10)
        tk.Label(lf, text="⬡  NestingPro",
                 font=("Segoe UI",15,"bold"), bg=SURFACE, fg=ACCENT).pack(side="left")
        tk.Label(lf, text="  Sistema de Optimización de Corte Textil",
                 font=("Segoe UI",10), bg=SURFACE, fg=TEXT2).pack(side="left", padx=8)
        tk.Label(bar,
                 text="EISPDM  •  Carrera Informática Industrial  •  La Paz, Bolivia",
                 font=FONT_SMALL, bg=SURFACE, fg=TEXT2).pack(side="right", padx=16)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

    def _sec_hdr(self, parent, title):
        h = _frame(parent, bg=SURFACE2)
        h.pack(fill="x")
        _label(h, f"  {title}", font=("Segoe UI",8,"bold"),
               bg=SURFACE2, color=TEXT2).pack(side="left", pady=5)
        f = _frame(parent, bg=SURFACE)
        f.pack(fill="x", padx=10, pady=6)
        return f

    def _build_panel_moldes(self):
        sec = self._sec_hdr(self.frm_left, "MOLDES")

        fl = _frame(sec, bg=SURFACE)
        fl.pack(fill="x")
        sc = tk.Scrollbar(fl, bg=SURFACE2)
        sc.pack(side="right", fill="y")
        self.lista_moldes = tk.Listbox(
            fl, height=7, bg=CANVAS_BG, fg=TEXT,
            selectbackground=ACCENT, selectforeground="white",
            font=FONT_MONO, activestyle="none",
            yscrollcommand=sc.set, relief="flat", bd=0,
            highlightthickness=0)
        self.lista_moldes.pack(fill="x")
        sc.config(command=self.lista_moldes.yview)

        fb = _frame(sec, bg=SURFACE)
        fb.pack(fill="x", pady=(6,0))
        for txt, cmd, col in [
            ("＋ Nuevo",  self._nuevo_molde,    ACCENT),
            ("✏ Editar", self._editar_molde,   ACCENT2),
            ("🗑 Borrar", self._eliminar_molde, DANGER),
        ]:
            _btn(fb, txt, cmd, color=col, padx=4, pady=3
                 ).pack(side="left", padx=2, expand=True, fill="x")

        _btn(sec, "📂  Importar molde (.json)",
             self._importar_molde_directo,
             color=SURFACE2, text_color=ACCENT, pady=4
             ).pack(fill="x", pady=(6,0))

    def _build_panel_params(self):
        sec = self._sec_hdr(self.frm_left, "PARÁMETROS DE TELA")
        self._entradas = {}
        campos = [
            ("Ancho tela (cm)","150"),
            ("Largo tela (cm)","300"),
            ("Margen piezas (cm)","0.5"),
            ("Paso rotación (°)","15"),
            ("Resolución grid (cm)","2.0"),
        ]
        for label, default in campos:
            row = _frame(sec, bg=SURFACE)
            row.pack(fill="x", pady=2)
            _label(row, label, font=FONT_SMALL, bg=SURFACE, color=TEXT2).pack(side="left")
            e = tk.Entry(row, font=FONT_MONO, bg=SURFACE2, fg=TEXT,
                         width=9, relief="flat", bd=0,
                         insertbackground=ACCENT,
                         highlightthickness=1, highlightcolor=ACCENT,
                         highlightbackground=BORDER)
            e.insert(0, default)
            e.pack(side="right", ipady=4, padx=(4,0))
            self._entradas[label] = e

    def _build_panel_actions(self):
        sec = self._sec_hdr(self.frm_left, "ACCIONES")
        _btn(sec,"🚀  Ejecutar Optimización", self._run_nesting,
             color=ACCENT).pack(fill="x", pady=2)
        _btn(sec,"📊  Comparar Manual / Auto",self._open_comp,
             color=ACCENT2).pack(fill="x", pady=2)
        tk.Frame(sec, bg=BORDER, height=1).pack(fill="x", pady=4)
        for txt, cmd, tc in [
            ("💾  Exportar JSON", self._exp_json, SUCCESS),
            ("📄  Exportar CSV",  self._exp_csv,  SUCCESS),
            ("🖼   Guardar imagen",self._exp_img,  ACCENT2),
        ]:
            _btn(sec,txt,cmd,color=SURFACE2,text_color=tc,pady=3
                 ).pack(fill="x", pady=1)
        tk.Frame(sec, bg=BORDER, height=1).pack(fill="x", pady=4)
        _btn(sec,"📂  Historial de simulaciones",self._historial,
             color=SURFACE2,text_color=TEXT2,pady=3).pack(fill="x")

    def _build_panel_metrics(self):
        sec = self._sec_hdr(self.frm_left, "MÉTRICAS")
        self.lbl_metricas = _label(
            sec,"Ejecute la optimización para ver las métricas.",
            font=FONT_SMALL,bg=SURFACE,color=TEXT2,
            justify="left",wraplength=255)
        self.lbl_metricas.pack(anchor="w")

    def _build_panel_viz(self):
        hdr = _frame(self.frm_right, bg=BG)
        hdr.pack(fill="x", pady=(0,4))
        _label(hdr,"Visualización — Distribución Optimizada",
               font=FONT_TITLE,bg=BG,color=TEXT).pack(side="left")
        self.lbl_estado = _label(hdr,"",font=("Segoe UI",9,"italic"),
                                  bg=BG,color=ACCENT)
        self.lbl_estado.pack(side="right")

        self.frm_canvas = _frame(self.frm_right, bg=CANVAS_BG)
        self.frm_canvas.pack(fill="both", expand=True)
        self._placeholder()

    def _placeholder(self):
        for w in self.frm_canvas.winfo_children():
            w.destroy()
        tk.Label(self.frm_canvas,
                 text=("Agrega moldes  →  Configura los parámetros de tela\n"
                       "→  Ejecuta la optimización\n\n"
                       "El resultado aparecerá aquí"),
                 font=("Segoe UI",12), bg=CANVAS_BG, fg=BORDER,
                 justify="center").place(relx=0.5,rely=0.5,anchor="center")

    # ── Gestión moldes ────────────────────────────────────────────
    def _refresh_moldes(self):
        self.lista_moldes.delete(0,"end")
        moldes = listar_moldes()
        for m in moldes:
            self.lista_moldes.insert("end",
                f"  [{m.get('cantidad',1):>2}×]  {m['nombre']}")
        if not moldes:
            self.lista_moldes.insert("end","  (sin moldes registrados)")

    def _nuevo_molde(self):
        EditorMolde(self.root, on_guardar=self._save_new)

    def _save_new(self, r):
        ok,msg = registrar_molde(r["nombre"],r["coordenadas"],
                                  r["cantidad"],r["descripcion"])
        if ok: messagebox.showinfo("Molde guardado", msg)
        else:  messagebox.showerror("Error", msg)
        self._refresh_moldes()

    def _selected(self):
        sel = self.lista_moldes.curselection()
        if not sel:
            messagebox.showwarning("Sin selección","Seleccione un molde.")
            return None
        txt = self.lista_moldes.get(sel[0])
        if "sin moldes" in txt: return None
        try: return txt.split("×]")[1].strip()
        except Exception: return None

    def _editar_molde(self):
        nombre = self._selected()
        if not nombre: return
        datos = obtener_molde(nombre)
        if not datos:
            messagebox.showerror("Error",f"No se encontró '{nombre}'.")
            return
        def on_save(r):
            ok,msg = editar_molde(nombre,
                nuevas_coordenadas=r["coordenadas"],
                nueva_cantidad=r["cantidad"],
                nueva_descripcion=r["descripcion"])
            if ok: messagebox.showinfo("Actualizado",msg)
            else:  messagebox.showerror("Error",msg)
            self._refresh_moldes()
        EditorMolde(self.root, datos_existentes=datos, on_guardar=on_save)

    def _eliminar_molde(self):
        nombre = self._selected()
        if not nombre: return
        if not messagebox.askyesno("Confirmar",
                f"¿Eliminar '{nombre}'?\n(se creará respaldo automático)"):
            return
        ok,msg = eliminar_molde(nombre)
        if ok: messagebox.showinfo("Eliminado",msg)
        else:  messagebox.showerror("Error",msg)
        self._refresh_moldes()

    def _importar_molde_directo(self):
        ruta = filedialog.askopenfilename(
            title="Importar molde",
            filetypes=[("Molde JSON","*.json"),("Todos","*.*")])
        if not ruta: return
        try:
            with open(ruta,encoding="utf-8") as f:
                d = json.load(f)
            coords = d.get("coordenadas",[])
            nombre = d.get("nombre","") or os.path.splitext(os.path.basename(ruta))[0]
            if len(coords) < 3:
                messagebox.showerror("Error","El archivo no tiene coordenadas válidas.")
                return
            ok,msg = registrar_molde(nombre,coords,
                d.get("cantidad",1),d.get("descripcion",""))
            if ok:
                messagebox.showinfo("Molde importado",msg)
            elif "Ya existe" in msg:
                if messagebox.askyesno("Ya existe",
                        f"El molde '{nombre}' ya existe.\n¿Reemplazar?"):
                    editar_molde(nombre,nuevas_coordenadas=coords,
                        nueva_cantidad=d.get("cantidad",1),
                        nueva_descripcion=d.get("descripcion",""))
                    messagebox.showinfo("Actualizado",f"Molde '{nombre}' actualizado.")
            else:
                messagebox.showerror("Error",msg)
            self._refresh_moldes()
        except Exception as exc:
            messagebox.showerror("Error al importar",str(exc))

    # ── Parámetros ────────────────────────────────────────────────
    def _read_params(self):
        try:
            ancho  = float(self._entradas["Ancho tela (cm)"].get())
            largo  = float(self._entradas["Largo tela (cm)"].get())
            margen = float(self._entradas["Margen piezas (cm)"].get())
            paso   = int(float(self._entradas["Paso rotación (°)"].get()))
            grid   = float(self._entradas["Resolución grid (cm)"].get())
        except ValueError:
            messagebox.showerror("Parámetro inválido",
                "Todos los parámetros deben ser numéricos.")
            return None
        ok,msg = validar_parametros_tela(ancho,largo,margen)
        if not ok:
            messagebox.showerror("Parámetros inválidos",msg)
            return None
        return {"ancho":ancho,"largo":largo,"margen":margen,
                "angulo_paso":paso,"paso_grid":grid}

    # ── Nesting ───────────────────────────────────────────────────
    def _run_nesting(self):
        moldes = listar_moldes()
        if not moldes:
            messagebox.showwarning("Sin moldes",
                "Registre al menos un molde antes de optimizar.")
            return
        params = self._read_params()
        if not params: return
        self.lbl_estado.config(text="⏳ Optimizando…", fg=WARN)
        self.root.update_idletasks()

        def worker():
            try:
                res = ejecutar_nesting(
                    moldes=moldes,
                    ancho_tela=params["ancho"],
                    largo_tela=params["largo"],
                    margen=params["margen"],
                    angulo_paso=params["angulo_paso"],
                    paso_grid=params["paso_grid"],
                )
                self._resultado_actual = res
                guardar_simulacion(res)
                self.root.after(0, self._post_nesting)
            except Exception as exc:
                logger.exception("Error nesting")
                self.root.after(0, lambda: messagebox.showerror("Error",str(exc)))
                self.root.after(0, lambda: self.lbl_estado.config(text="",fg=TEXT))

        threading.Thread(target=worker, daemon=True).start()

    def _post_nesting(self):
        if not self._resultado_actual: return
        res = self._resultado_actual
        m   = calcular_metricas(res)
        no_col = res.get("no_colocadas",[])
        aviso  = f"\n⚠ No colocadas: {', '.join(no_col)}" if no_col else ""
        self.lbl_metricas.config(fg=TEXT, text=(
            f"Área tela:        {m.get('area_tela_cm2',0):.1f} cm²\n"
            f"Área utilizada:   {m.get('area_usada_cm2',0):.1f} cm²\n"
            f"Área residual:    {m.get('area_residual_cm2',0):.1f} cm²\n"
            f"Aprovechamiento:  {m.get('porcentaje_uso',0):.1f}%\n"
            f"Nivel:            {m.get('nivel_aprovechamiento','')}\n"
            f"Piezas:           {m.get('piezas_colocadas',0)}/{m.get('piezas_totales',0)}\n"
            f"Tiempo:           {m.get('tiempo_s',0):.2f} s{aviso}"
        ))
        pct = m.get("porcentaje_uso",0)
        self.lbl_estado.config(text=f"✅  {pct:.1f}% aprovechamiento", fg=SUCCESS)
        self._draw_result()

    def _draw_result(self):
        if not self._resultado_actual: return
        for w in self.frm_canvas.winfo_children():
            w.destroy()

        res       = self._resultado_actual
        params    = res.get("parametros",{})
        metricas  = res.get("metricas",{})
        colocadas = res.get("colocadas",[])
        ancho = params.get("ancho_tela",150)
        largo = params.get("largo_tela",300)

        fig, ax = plt.subplots(figsize=(8, max(5, largo/ancho*5.5)))
        fig.patch.set_facecolor("#141824")
        ax.set_facecolor("#f8f5f0")
        ax.set_xlim(0,ancho); ax.set_ylim(0,largo)
        ax.set_aspect("equal")

        from matplotlib.patches import Rectangle
        ax.add_patch(Rectangle((0,0),ancho,largo,
                               lw=1.5,edgecolor="#6c8ef5",facecolor="none",zorder=0))

        handles = []
        for i, pieza in enumerate(colocadas):
            coords = pieza.get("coordenadas",[])
            if len(coords) < 3: continue
            col   = COLORES_PIEZA[i % len(COLORES_PIEZA)]
            pts   = list(coords)
            patch = MplPolygon(pts, closed=True, facecolor=col,
                               edgecolor="white", lw=0.8, alpha=0.85, zorder=2)
            ax.add_patch(patch)
            cx = sum(p[0] for p in pts)/len(pts)
            cy = sum(p[1] for p in pts)/len(pts)
            ax.text(cx,cy,pieza["nombre"][:10],ha="center",va="center",
                    fontsize=5,color="white",fontweight="bold",zorder=3)
            handles.append(mpatches.Patch(color=col,label=pieza["nombre"]))

        if handles:
            ax.legend(handles=handles[:14],loc="upper right",fontsize=5.5,
                      framealpha=0.85,facecolor="#1a1d27",labelcolor="white",
                      title="Piezas",title_fontsize=6)

        pct = metricas.get("porcentaje_uso",0)
        ax.set_title(
            f"Aprovechamiento: {pct:.1f}%   |   "
            f"Piezas: {metricas.get('piezas_colocadas',0)}/{metricas.get('piezas_totales',0)}   |   "
            f"Tela: {ancho}×{largo} cm",
            fontsize=7.5, color="#e2e8f0", pad=8)
        ax.set_xlabel("Ancho (cm)",fontsize=7,color="#94a3b8")
        ax.set_ylabel("Largo (cm)",fontsize=7,color="#94a3b8")
        ax.tick_params(colors="#94a3b8",labelsize=6)
        ax.grid(True,ls="--",lw=0.3,color="#aaaaaa",alpha=0.35)
        for sp in ax.spines.values(): sp.set_edgecolor("#2e3250")
        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.frm_canvas)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both",expand=True)
        tbf = _frame(self.frm_canvas, bg="#141824")
        tbf.pack(fill="x")
        tb = NavigationToolbar2Tk(canvas,tbf)
        tb.config(bg="#141824")
        tb.update()
        self._fig = fig
        self._canvas_mpl = canvas

    # ── Exportaciones ─────────────────────────────────────────────
    def _check(self):
        if not self._resultado_actual:
            messagebox.showwarning("Sin resultado","Ejecute primero la optimización.")
            return False
        return True

    def _exp_json(self):
        if not self._check(): return
        r = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")],title="Exportar JSON")
        if r:
            ok,msg = exportar_json(self._resultado_actual,r)
            messagebox.showinfo("Exportado",f"Guardado:\n{r}") if ok else messagebox.showerror("Error",msg)

    def _exp_csv(self):
        if not self._check(): return
        r = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV","*.csv")],title="Exportar CSV")
        if r:
            ok,msg = exportar_csv(self._resultado_actual,r)
            messagebox.showinfo("Exportado",f"Guardado:\n{r}") if ok else messagebox.showerror("Error",msg)

    def _exp_img(self):
        if not self._check(): return
        r = filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG","*.png")],title="Guardar imagen")
        if r:
            ok,msg = exportar_imagen(self._resultado_actual,r)
            messagebox.showinfo("Imagen guardada",f"Guardada:\n{r}") if ok else messagebox.showerror("Error",msg)

    def _open_comp(self):
        if not self._check(): return
        VentanaComparacion(self.root, self._resultado_actual)

    # ── Historial ─────────────────────────────────────────────────
    def _historial(self):
        sims = listar_simulaciones()
        win = tk.Toplevel(self.root)
        win.title("Historial de Simulaciones")
        win.configure(bg=BG)
        win.geometry("720x440")

        _label(win,"Historial de Simulaciones",
               font=FONT_TITLE,bg=BG,color=ACCENT).pack(pady=12)

        frm = _frame(win,bg=BG)
        frm.pack(fill="both",expand=True,padx=12)

        cols = ("Fecha","Aprovechamiento","Piezas","Tela (cm)")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("D.Treeview",
            background=CANVAS_BG,foreground=TEXT,
            fieldbackground=CANVAS_BG,rowheight=24,font=FONT_SMALL)
        style.configure("D.Treeview.Heading",
            background=SURFACE2,foreground=TEXT2,
            font=("Segoe UI",8,"bold"),relief="flat")

        tree = ttk.Treeview(frm,columns=cols,show="headings",
                             style="D.Treeview",height=14)
        for col in cols:
            tree.heading(col,text=col)
            tree.column(col,width=165,anchor="center")
        sc = ttk.Scrollbar(frm,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=sc.set)
        tree.pack(side="left",fill="both",expand=True)
        sc.pack(side="right",fill="y")

        for sim in sims[:60]:
            m = sim.get("metricas",{})
            p = sim.get("parametros",{})
            tree.insert("","end",values=(
                sim.get("timestamp","")[:16].replace("T"," "),
                f"{m.get('porcentaje_uso',0):.1f}%",
                f"{m.get('piezas_colocadas',0)}/{m.get('piezas_totales',0)}",
                f"{p.get('ancho_tela',0)}×{p.get('largo_tela',0)}",
            ))
        if not sims:
            _label(win,"No hay simulaciones guardadas.",
                   font=FONT_LABEL,bg=BG,color=TEXT2).pack(pady=8)

        _btn(win,"Cerrar",win.destroy,color=SURFACE2,text_color=TEXT).pack(pady=10)

    def ejecutar(self):
        logger.info("Aplicación iniciada.")
        self.root.mainloop()
        logger.info("Aplicación cerrada.")


if __name__ == "__main__":
    app = AppNesting()
    app.ejecutar()