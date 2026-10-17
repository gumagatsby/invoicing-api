"""Generate the .drawio diagrams for the invoicing API repo (C4 container style)."""
import sys
from html import escape

OUTDIR = sys.argv[1]

C = {"storage": "#7AA116", "integration": "#E7157B", "compute": "#ED7100", "database": "#C925D1",
     "analytics": "#8C4FFF", "management": "#E7157B", "security": "#DD344C", "cost": "#7AA116"}
INK = "#232F3E"
EDGE = "#545B64"
RED = "#D13212"


class Doc:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.cells = []
        self.n = 2
        self.org = {"1": (0, 0)}  # absolute origin of each container; all coordinates passed in are absolute

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    def add(self, value, style, x, y, w, h, parent="1", vertex=True):
        i = self._id()
        value = value.replace("\n", "<br>")
        self.org[i] = (x, y)
        px, py = self.org[parent]
        x, y = x - px, y - py
        self.cells.append(
            f'<mxCell id="{i}" value="{escape(value)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return i

    def group(self, label, kind, x, y, w, h, parent="1", fs=12):
        styles = {
            "cloud": f"grIcon=mxgraph.aws4.group_aws_cloud_alt;strokeColor={INK};fontColor={INK};dashed=0;",
            "region": "grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fontColor=#147EBA;dashed=1;",
            "account": "grIcon=mxgraph.aws4.group_account;strokeColor=#CD2264;fontColor=#CD2264;dashed=0;",
            "office": f"grIcon=mxgraph.aws4.group_corporate_data_center;strokeColor=#7D8998;fontColor={INK};dashed=0;",
            "vpc": "grIcon=mxgraph.aws4.group_vpc;strokeColor=#8C4FFF;fontColor=#8C4FFF;dashed=0;",
            "vpc_off": "grIcon=mxgraph.aws4.group_vpc;strokeColor=#8C4FFF;fontColor=#8C4FFF;dashed=1;",
            "public": "grIcon=mxgraph.aws4.group_security_group;strokeColor=#7AA116;fontColor=#248814;dashed=0;",
            "private": "grIcon=mxgraph.aws4.group_security_group;strokeColor=#00A4A6;fontColor=#147EBA;dashed=0;",
        }
        st = ("points=[];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=%d;fontStyle=1;"
              "container=1;pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;"
              "fillColor=none;verticalAlign=top;align=left;spacingLeft=30;" % fs) + styles[kind]
        return self.add(label, st, x, y, w, h, parent)

    def box(self, label, x, y, w, h, parent="1", color="#879196", fs=12):
        st = (f"fillColor=none;strokeColor={color};dashed=1;verticalAlign=top;fontStyle=1;fontColor={color};"
              f"whiteSpace=wrap;html=1;align=left;spacingLeft=10;spacingTop=4;fontSize={fs};rounded=1;arcSize=3;container=1;collapsible=0;")
        return self.add(label, st, x, y, w, h, parent)

    @staticmethod
    def lab(pos):
        return {"below": "verticalLabelPosition=bottom;verticalAlign=top;align=center;",
                "above": "verticalLabelPosition=top;verticalAlign=bottom;align=center;",
                "right": "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=4;",
                "left": "labelPosition=left;verticalLabelPosition=middle;align=right;verticalAlign=middle;spacingRight=4;"}[pos]

    def res(self, label, icon, cat, x, y, parent="1", s=64, fs=12, pos="below"):
        st = (f"sketch=0;outlineConnect=0;fontColor={INK};gradientColor=none;fillColor={C[cat]};strokeColor=#ffffff;"
              f"dashed=0;html=1;fontSize={fs};" + self.lab(pos) +
              f"aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{icon};")
        return self.add(label, st, x, y, s, s, parent)

    def shape(self, label, shp, color, x, y, w=52, h=52, parent="1", fs=12, pos="below"):
        st = (f"sketch=0;outlineConnect=0;fontColor={INK};gradientColor=none;fillColor={color};strokeColor=none;"
              f"dashed=0;html=1;fontSize={fs};" + self.lab(pos) +
              f"aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.{shp};")
        return self.add(label, st, x, y, w, h, parent)

    def text(self, label, x, y, w, h, fs=12, bold=False, color=INK, align="left", parent="1"):
        st = (f"text;html=1;strokeColor=none;fillColor=none;align={align};verticalAlign=top;whiteSpace=wrap;"
              f"fontSize={fs};fontColor={color};fontStyle={1 if bold else 0};")
        return self.add(label, st, x, y, w, h, parent)

    def badge(self, n, x, y, parent="1", d=24, fs=12):
        st = (f"ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor={INK};strokeColor=none;fontColor=#FFFFFF;"
              f"fontStyle=1;fontSize={fs};")
        return self.add(str(n), st, x, y, d, d, parent)

    def _raw(self, html, st, x, y, w, h):
        i = self._id()
        self.org[i] = (x, y)
        self.cells.append(f'<mxCell id="{i}" value="{escape(html)}" style="{st}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return i

    @staticmethod
    def _label(title, tech, desc, fs):
        return (f"<b>{escape(title)}</b><br><span style='color:#545B64'>[{escape(tech)}]</span>"
                + (f"<br><span style='font-size:{fs - 1}px'>{escape(desc)}</span>" if desc else ""))

    def node(self, title, tech, desc, x, y, w=210, h=96, stroke=INK, dashed=False, fs=12):
        """C4 container: name, [technology], one-line purpose. White fill, 1px border."""
        st = (f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={stroke};strokeWidth=1;"
              f"fontColor={INK};fontSize={fs};verticalAlign=middle;spacing=8;" + ("dashed=1;" if dashed else ""))
        return self._raw(self._label(title, tech, desc, fs), st, x, y, w, h)

    def db(self, title, tech, desc, x, y, w=170, h=100, fs=12):
        st = (f"shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;fillColor=#FFFFFF;strokeColor={INK};"
              f"strokeWidth=1;fontColor={INK};fontSize={fs};")
        return self._raw(self._label(title, tech, desc, fs), st, x, y, w, h)

    def person(self, label, x, y, fs=12):
        st = (f"shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;"
              f"fillColor=#FFFFFF;strokeColor={INK};fontColor={INK};fontSize={fs};")
        return self.add(label, st, x, y, 30, 56)

    def boundary(self, label, x, y, w, h):
        st = ("rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#879196;dashed=1;dashPattern=8 4;"
              "verticalAlign=bottom;align=left;spacingLeft=10;spacingBottom=6;fontColor=#545B64;fontSize=12;fontStyle=1;")
        return self.add(label, st, x, y, w, h)

    def edge(self, src, dst, label="", color=EDGE, dashed=False, w=1.5, ex=None, ey=None, nx=None, ny=None, fs=11, via=None):
        i = self._id()
        st = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor={color};"
              f"strokeWidth={w};fontSize={fs};fontColor={INK};labelBackgroundColor=#FFFFFF;"
              + ("dashed=1;dashPattern=6 4;" if dashed else ""))
        if ex is not None: st += f"exitX={ex};exitY={ey};exitDx=0;exitDy=0;"
        if nx is not None: st += f"entryX={nx};entryY={ny};entryDx=0;entryDy=0;"
        self.cells.append(
            f'<mxCell id="{i}" value="{escape(label.replace(chr(10), "<br>"))}" style="{st}" edge="1" parent="1" source="{src}" target="{dst}">'
            f'<mxGeometry relative="1" as="geometry">'
            + ('<Array as="points">' + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in via) + '</Array>' if via else "")
            + '</mxGeometry></mxCell>')
        return i

    def line(self, x1, y1, x2, y2, label="", dashed=False, color=EDGE, arrow=True, fs=11):
        i = self._id()
        st = (f"html=1;endArrow={'block' if arrow else 'none'};endFill=1;strokeColor={color};strokeWidth=1.5;fontSize={fs};"
              f"fontColor={INK};labelBackgroundColor=#FFFFFF;" + ("dashed=1;dashPattern=6 4;" if dashed else ""))
        self.cells.append(
            f'<mxCell id="{i}" value="{escape(label)}" style="{st}" edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x1}" y="{y1}" as="sourcePoint"/>'
            f'<mxPoint x="{x2}" y="{y2}" as="targetPoint"/></mxGeometry></mxCell>')

    def xml(self):
        return (f'<mxfile host="drawio"><diagram name="{escape(self.name)}">'
                f'<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
                f'fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" background="#FFFFFF" math="0" shadow="0">'
                '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
                + "".join(self.cells) + "</root></mxGraphModel></diagram></mxfile>")


GREY = "#879196"

# =====================================================================
# 1. Container diagram (C4 level 2)
# =====================================================================
d = Doc("Invoicing API: containers", 1760, 1040)
d.add("", "rounded=0;fillColor=#FFFFFF;strokeColor=none;", 0, 0, 1760, 1040)
d.text("Invoicing and payments API", 30, 20, 900, 34, fs=24, bold=True)
d.text("Container diagram (C4 level 2)", 30, 56, 900, 22, fs=14, color="#545B64")

merchant = d.person("Merchant\n(signs in to the dashboard)", 64, 236)
client = d.person("Merchant's own systems\n(call the API directly)", 64, 470)

d.boundary("Invoicing system", 200, 110, 1000, 640)
web = d.node("Dashboard", "React, TypeScript, nginx", "Invoices, payments, ledger", 240, 220, 220, 100)
api = d.node("API", "Python, FastAPI", "Auth, invoices, idempotent payments, double-entry ledger, rate limits",
             560, 210, 260, 120)
worker = d.node("Worker", "Python, arq", "Sends due webhooks every 5 s; retries with backoff, then marks failed",
                560, 560, 260, 110)
pg = d.db("Database", "PostgreSQL 17", "Invoices, payments, ledger, webhook outbox", 960, 170, 190, 120)
rd = d.db("Cache", "Redis 7", "Rate-limit counters; worker scheduling", 960, 420, 190, 110)

hook = d.node("Merchant's webhook endpoint", "HTTPS", "Verifies the signature, de-duplicates by event id", 1300, 560, 250, 110, stroke=GREY)

d.boundary("Observability", 200, 790, 1000, 200)
jaeger = d.node("Tracing", "Jaeger, OpenTelemetry", "Every request and SQL statement", 240, 840, 240, 96)
prom = d.node("Metrics", "Prometheus", "Scrapes the API and worker every 5 s", 560, 840, 260, 96)
graf = d.node("Dashboards", "Grafana", "Provisioned from code", 960, 840, 190, 96)

d.edge(merchant, web, "Uses\n[HTTPS]")
d.edge(client, api, "REST calls\n[JWT, Idempotency-Key]", ex=1, ey=0.5, nx=0, ny=0.75, via=[(510, 498), (510, 300)])
d.edge(web, api, "JSON\n[HTTPS]")
d.edge(api, pg, "Reads and writes\n[SQL, row locks]", ex=1, ey=0.3, nx=0, ny=0.5)
d.edge(api, rd, "Counts requests\n[INCR]", ex=1, ey=0.8, nx=0, ny=0.4, via=[(900, 306), (900, 464)])
d.edge(worker, pg, "Reads due\noutbox rows", ex=1, ey=0.3, nx=1, ny=0.5, via=[(1180, 593), (1180, 230)])
d.edge(worker, hook, "POST event\n[HMAC-SHA256 signed]", ex=1, ey=0.6, nx=0, ny=0.6)
d.edge(api, jaeger, "Traces\n[OTLP]", color=GREY, dashed=True, ex=0.2, ey=1, nx=0.5, ny=0, via=[(612, 525), (538, 525), (538, 765), (360, 765)])
d.edge(graf, prom, "Queries", color=GREY, dashed=True)

lx = 1300
d.text("What it guarantees", lx, 120, 420, 22, fs=15, bold=True)
g = [
    "A retried payment never charges twice: idempotency key, unique in the database.",
    "Two payments at once cannot overpay: the invoice row is locked, and a CHECK constraint backs it up.",
    "Every movement of money is an equal debit and credit, append-only.",
    "Webhooks are written in the same transaction as the payment, so none are lost, and each is signed.",
]
y = 152
for s_ in g:
    d.text(s_, lx, y, 420, 50, fs=12)
    y += 54
d.text("Measured", lx, y + 6, 420, 20, fs=13, bold=True)
d.text("k6, 20 users for 60 s, every SQL statement traced: 10,734 requests, 0 errors, payments p95 129 ms. "
       "20 parallel retries of one payment created exactly one.", lx, y + 28, 420, 56, fs=12)
d.text("Legend", lx, 900, 420, 20, fs=13, bold=True)
d.text("Solid: request path\nDashed grey: telemetry\nGrey border: outside the system", lx, 922, 420, 60, fs=12, color="#545B64")
# architecture.drawio is now edited directly in draw.io (AWS reference-architecture style), not generated here.

# =====================================================================
# 2. Payment sequence
# =====================================================================
s = Doc("Payment flow", 1500, 1000)
s.add("", "rounded=0;fillColor=#FFFFFF;strokeColor=none;", 0, 0, 1500, 1000)
s.text("Taking a payment", 30, 20, 900, 34, fs=24, bold=True)
s.text("Idempotent, locked against concurrent overpayment, and recorded in the ledger in one transaction",
       30, 56, 1200, 22, fs=14, color="#545B64")
lanes = [("Client", "app or retrying script"), ("API", "FastAPI"), ("Database", "PostgreSQL"),
         ("Worker", "arq"), ("Merchant endpoint", "HTTPS")]
X = [150, 450, 760, 1060, 1340]
for (n, t), x in zip(lanes, X):
    s._raw(Doc._label(n, t, "", 12), f"rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={INK};"
           f"fontColor={INK};fontSize=12;", x - 90, 100, 180, 56)
    s.line(x, 156, x, 960, dashed=True, arrow=False, color=GREY)

def msg(a, b, y, text_, dashed=False, n=None):
    """Arrow with its label above it, starting after the step number, so the label never covers the arrow."""
    s.line(X[a], y, X[b], y, "", dashed=dashed)
    left = min(X[a], X[b])
    span = abs(X[b] - X[a])
    if n:
        s.badge(n, left + 8, y - 25, d=20, fs=10)
    s.add(text_, f"text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=bottom;whiteSpace=wrap;"
             f"fontSize=11;fontColor={INK};", left + 34, y - 46, span - 40, 42)

def note(x, y, w, text_):
    s.text(text_, x, y, w, 40, fs=11, color="#545B64")

msg(0, 1, 210, "POST /invoices/{id}/payments [Idempotency-Key: k]", n=1)
msg(1, 2, 270, "BEGIN; SELECT invoice ... FOR UPDATE", n=2)
note(774, 280, 270, "Concurrent payments for this invoice wait here")
msg(1, 2, 340, "SELECT payment WHERE key = k (none)", n=3)
note(476, 350, 280, "Check currency, status, amount <= outstanding")
msg(1, 2, 430, "INSERT payment, 2 ledger rows, webhook outbox rows; UPDATE invoice; COMMIT", n=4)
msg(1, 0, 480, "201 Created", dashed=True, n=5)
s.text("Retry after a dropped response", 20, 512, 400, 20, fs=12, bold=True)
msg(0, 1, 570, "POST again, same key k, same body", n=6)
msg(1, 2, 630, "SELECT payment WHERE key = k (found, same request hash)", n=7)
msg(1, 0, 690, "200 OK, Idempotent-Replayed: true, same payment", dashed=True, n=8)
note(176, 700, 270, "Same key with a different body: 409 Conflict")
s.text("Every 5 seconds", 20, 742, 400, 20, fs=12, bold=True)
msg(3, 2, 800, "SELECT due deliveries FOR UPDATE SKIP LOCKED", n=9)
msg(3, 4, 860, "POST event [Invoicing-Signature: t=..., v1=HMAC]", n=10)
msg(4, 3, 920, "2xx: delivered", dashed=True, n=11)
note(1076, 930, 400, "Otherwise retry after 1, 2, 4, 8, 16 minutes; failed after 6 attempts")
open(f"{OUTDIR}/payment-flow.drawio", "w").write(s.xml())

# =====================================================================
# 3. LinkedIn: 540x675 page, exported at 2x = 1080x1350
# =====================================================================
L = Doc("LinkedIn", 540, 675)
L.add("", "rounded=0;fillColor=#FFFFFF;strokeColor=none;", 0, 0, 540, 675)
L.text("Invoicing and payments API", 22, 20, 500, 30, fs=22, bold=True)
L.text("Python, FastAPI, PostgreSQL, Redis, React and TypeScript", 22, 52, 500, 20, fs=13, color="#545B64")
lw = L.node("Dashboard", "React, TypeScript", "", 22, 100, 150, 56, fs=11)
la = L.node("API", "Python, FastAPI", "", 210, 100, 140, 56, fs=11)
lr = L.db("Cache", "Redis", "", 392, 96, 126, 64, fs=11)
lp = L.db("Database", "PostgreSQL", "", 392, 196, 126, 72, fs=11)
lk = L.node("Worker", "Python, arq", "", 210, 204, 140, 56, fs=11)
lh = L.node("Webhook endpoint", "HTTPS, signed", "", 22, 204, 150, 56, stroke=GREY, fs=11)
L.edge(lw, la)
L.edge(la, lr)
L.edge(la, lp, ex=0.85, ey=1, nx=0.5, ny=0, via=[(329, 180), (455, 180)])
L.edge(lk, lp)
L.edge(lk, lh)
L.text("What it guarantees", 22, 300, 500, 20, fs=13, bold=True)
items = ["A retried payment never charges twice", "Two payments at once cannot overpay an invoice",
         "Every payment is a balanced debit and credit", "Webhooks are never lost, and are signed"]
for n, s_ in enumerate(items):
    L.text(s_, 22, 326 + n * 22, 500, 20, fs=12)
L.text("Measured with k6 (20 users, 60 s, full tracing)", 22, 430, 500, 20, fs=13, bold=True)
for n, s_ in enumerate(["10,734 requests, 0 errors", "Payments p95: 129 ms",
                        "20 parallel retries of one payment: exactly 1 created",
                        "Ledger after the run: debits minus credits = 0"]):
    L.text(s_, 22, 456 + n * 22, 500, 20, fs=12)
L.text("Tests run against real PostgreSQL and Redis in CI. Traces, metrics and dashboards included.", 22, 570, 500, 36, fs=12)
L.text("github.com/gumagatsby/invoicing-api", 22, 646, 500, 18, fs=11, color="#545B64")
open(f"{OUTDIR}/linkedin-architecture.drawio", "w").write(L.xml())
print("ok")
