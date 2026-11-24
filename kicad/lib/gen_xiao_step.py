"""Write a simple block model of the XIAO ESP32-S3 Plus as a STEP file.

    python3 gen_xiao_step.py   ->  bldc.3dshapes/XIAO-ESP32-S3-Plus.step

Three boxes: the module's PCB, its shield can and the USB-C connector.
It is an envelope for mechanical checks (height, USB overhang), not a
likeness; sizes are approximate. Frame: the footprint's, +X = USB end,
Z = 0 at the carrier board's top surface.
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bldc.3dshapes')
os.makedirs(OUT, exist_ok=True)

BOXES = [       # name, (x0, y0, z0), (x1, y1, z1)   mm
    ('pcb', (-10.5, -8.9, 0.0), (10.5, 8.9, 1.2)),
    ('shield', (-9.0, -6.0, 1.2), (2.5, 6.0, 3.6)),
    ('usb_c', (4.7, -4.47, 1.2), (12.05, 4.47, 4.4)),
]


class Step:
    def __init__(self):
        self.lines = []
        self.n = 100            # ids below 100 are the fixed preamble

    def add(self, text):
        self.n += 1
        self.lines.append(f'#{self.n}={text};')
        return self.n

    def point(self, p):
        return self.add("CARTESIAN_POINT('',(%.4f,%.4f,%.4f))" % p)

    def direction(self, d):
        return self.add("DIRECTION('',(%.1f,%.1f,%.1f))" % d)

    def box(self, name, lo, hi):
        def xyz(i, j, k):
            return (hi[0] if i else lo[0], hi[1] if j else lo[1],
                    hi[2] if k else lo[2])
        corners = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
        pt = {c: self.point(xyz(*c)) for c in corners}
        vx = {c: self.add(f"VERTEX_POINT('',#{pt[c]})") for c in corners}
        edges = {}

        def edge(a, b):
            """Oriented edge a -> b; the underlying curve runs low -> high."""
            lo_c, hi_c = (a, b) if a < b else (b, a)
            if (lo_c, hi_c) not in edges:
                d = tuple(float(h - l) for l, h in zip(lo_c, hi_c))
                length = sum(abs(q - p) for p, q in zip(xyz(*lo_c), xyz(*hi_c)))
                vec = self.add(f"VECTOR('',#{self.direction(d)},{length:.4f})")
                line = self.add(f"LINE('',#{pt[lo_c]},#{vec})")
                edges[(lo_c, hi_c)] = self.add(
                    f"EDGE_CURVE('',#{vx[lo_c]},#{vx[hi_c]},#{line},.T.)")
            sense = '.T.' if a < b else '.F.'
            return self.add(
                f"ORIENTED_EDGE('',*,*,#{edges[(lo_c, hi_c)]},{sense})")

        # each face: outward normal, a reference direction in the plane, and
        # its corners anticlockwise as seen from outside
        faces = [
            ((0, 0, -1), (1, 0, 0), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
            ((0, 0, 1), (1, 0, 0), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
            ((0, -1, 0), (1, 0, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
            ((0, 1, 0), (1, 0, 0), [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)]),
            ((-1, 0, 0), (0, 1, 0), [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)]),
            ((1, 0, 0), (0, 1, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
        ]
        face_ids = []
        for normal, ref, loop in faces:
            oes = [edge(a, b) for a, b in zip(loop, loop[1:] + loop[:1])]
            el = self.add("EDGE_LOOP('',(%s))" % ','.join(f'#{e}' for e in oes))
            bound = self.add(f"FACE_OUTER_BOUND('',#{el},.T.)")
            ax = self.add("AXIS2_PLACEMENT_3D('',#%d,#%d,#%d)" % (
                pt[loop[0]], self.direction(tuple(map(float, normal))),
                self.direction(tuple(map(float, ref)))))
            plane = self.add(f"PLANE('',#{ax})")
            face_ids.append(self.add(
                f"ADVANCED_FACE('',(#{bound}),#{plane},.T.)"))
        shell = self.add("CLOSED_SHELL('',(%s))" %
                         ','.join(f'#{f}' for f in face_ids))
        return self.add(f"MANIFOLD_SOLID_BREP('{name}',#{shell})")


def main():
    s = Step()
    solids = [s.box(name, lo, hi) for name, lo, hi in BOXES]
    items = ','.join(['#11'] + [f'#{b}' for b in solids])
    pre = [
        "#1=APPLICATION_PROTOCOL_DEFINITION('international standard',"
        "'automotive_design',2000,#2);",
        "#2=APPLICATION_CONTEXT('core data for automotive mechanical design processes');",
        '#3=SHAPE_DEFINITION_REPRESENTATION(#4,#10);',
        "#4=PRODUCT_DEFINITION_SHAPE('','',#5);",
        "#5=PRODUCT_DEFINITION('design','',#6,#9);",
        "#6=PRODUCT_DEFINITION_FORMATION('','',#7);",
        "#7=PRODUCT('XIAO-ESP32-S3-Plus','XIAO-ESP32-S3-Plus','',(#8));",
        "#8=PRODUCT_CONTEXT('',#2,'mechanical');",
        "#9=PRODUCT_DEFINITION_CONTEXT('part definition',#2,'design');",
        f"#10=ADVANCED_BREP_SHAPE_REPRESENTATION('',({items}),#15);",
        "#11=AXIS2_PLACEMENT_3D('',#12,#13,#14);",
        "#12=CARTESIAN_POINT('',(0.,0.,0.));",
        "#13=DIRECTION('',(0.,0.,1.));",
        "#14=DIRECTION('',(1.,0.,0.));",
        "#15=(GEOMETRIC_REPRESENTATION_CONTEXT(3)"
        "GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#19))"
        "GLOBAL_UNIT_ASSIGNED_CONTEXT((#16,#17,#18))"
        "REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY'));",
        '#16=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));',
        '#17=(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.));',
        '#18=(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT());',
        "#19=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#16,"
        "'distance_accuracy_value','confusion accuracy');",
        "#20=PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#7));",
    ]
    text = '\n'.join([
        'ISO-10303-21;', 'HEADER;',
        "FILE_DESCRIPTION(('XIAO ESP32-S3 Plus block model'),'2;1');",
        "FILE_NAME('XIAO-ESP32-S3-Plus.step','2026-11-10T00:00:00',(''),(''),"
        "'gen_xiao_step.py','','');",
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));",
        'ENDSEC;', 'DATA;'] + pre + s.lines + ['ENDSEC;', 'END-ISO-10303-21;', ''])
    path = os.path.join(OUT, 'XIAO-ESP32-S3-Plus.step')
    open(path, 'w').write(text)
    print('wrote', path, len(s.lines) + len(pre), 'entities')


if __name__ == '__main__':
    main()
