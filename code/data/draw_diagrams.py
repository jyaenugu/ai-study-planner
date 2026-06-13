#!/usr/bin/env python3
"""Architecture & data-flow diagrams for the AI Planner deck (English, 16:9 PNG)."""
from PIL import Image, ImageDraw, ImageFont

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
def font(sz, bold=True):
    return ImageFont.truetype(FB if bold else FR, sz)

INDIGO=(0x26,0x3A,0x6B); INDIGO2=(0x3B,0x57,0x9E); GOLD=(0xE0,0xA1,0x32)
DARK=(0x1E,0x1E,0x24); GRAY=(0x6A,0x70,0x7E); LIGHT=(0xF1,0xEE,0xE6)
WHITE=(255,255,255); TEAL=(0x2C,0x7A,0x6B); PAPER=(0xFB,0xFA,0xF6)
GREEN=(0x2E,0x7D,0x4F); REDB=(0xB0,0x47,0x3A)

W,H = 1600,900

def center(d, box, text, fnt, fill):
    x0,y0,x1,y1 = box
    tb = d.textbbox((0,0), text, font=fnt)
    tw,th = tb[2]-tb[0], tb[3]-tb[1]
    d.text(((x0+x1)/2 - tw/2, (y0+y1)/2 - th/2 - tb[1]), text, font=fnt, fill=fill)

def box(d, xy, fill, outline, width=3, r=22):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

def label(d, x, y, text, fnt, fill, anchor="la"):
    d.text((x,y), text, font=fnt, fill=fill, anchor=anchor)

def arrow(d, x1,y1,x2,y2, color=INDIGO2, width=5, head=16):
    d.line((x1,y1,x2,y2), fill=color, width=width)
    import math
    ang=math.atan2(y2-y1, x2-x1)
    for s in (-1,1):
        d.line((x2,y2, x2-head*math.cos(ang-s*0.5), y2-head*math.sin(ang-s*0.5)), fill=color, width=width)

# ---------------- Diagram 1: Architecture ----------------
def architecture():
    img=Image.new("RGB",(W,H),PAPER); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,90), fill=INDIGO)
    d.rectangle((0,90,W,96), fill=GOLD)
    label(d, 50, 28, "Architecture — Two Tiers", font(40), WHITE)

    # TIER 1 band (left)
    box(d,(50,150,640,760), LIGHT, GREEN, 3)
    label(d, 70, 168, "TIER 1 · DATA LAYER", font(22), GREEN)
    label(d, 70, 200, "local · $0", font(20,False), GRAY)
    # Vault container
    box(d,(90,250,600,560), WHITE, INDIGO2, 2)
    label(d, 110, 262, "Obsidian Vault", font(22), INDIGO)
    for i,(t) in enumerate(["Journal  (daily log)","Brain  (papers / notes)","Schedule  (calendar)","Goals  (RESEARCH_GOALS)"]):
        y=310+i*58
        box(d,(120,y,570,y+44), PAPER, GOLD, 2, r=12)
        center(d,(120,y,570,y+44), t, font(20,False), DARK)
    # Notion mirror
    box(d,(90,600,600,710), WHITE, TEAL, 2)
    center(d,(90,600,600,655), "Notion mirror  →  phone / web", font(21), TEAL)
    center(d,(90,650,600,705), "(auto every 30 min)", font(17,False), GRAY)

    # TIER 2 band (right top)
    box(d,(720,150,1550,470), LIGHT, GOLD, 3)
    label(d, 740, 168, "TIER 2 · WEEKLY SYNTHESIS", font(22), (0xB0,0x7A,0x1E))
    label(d, 740, 200, "API · ~cents · once a week", font(20,False), GRAY)
    box(d,(760,250,1060,420), WHITE, INDIGO2, 2)
    center(d,(760,250,1060,300),"Saturday 09:00", font(22), INDIGO)
    center(d,(760,295,1060,340),"cron job", font(20,False), DARK)
    arrow(d, 1065,335, 1180,335)
    box(d,(1185,250,1530,420), INDIGO, INDIGO, 2)
    center(d,(1185,250,1530,305),"Claude Sonnet", font(24), WHITE)
    center(d,(1185,300,1530,345),"lightContext", font(19,False), GOLD)
    center(d,(1185,335,1530,380),"+ toolsAllow (6 tools)", font(19,False), GOLD)

    # read arrow Tier1 -> Sonnet
    arrow(d, 600,400, 758,360, color=GREEN, width=5)
    label(d, 610, 405, "weekly read", font(17,False), GREEN)

    # Output
    box(d,(720,560,1550,820), WHITE, INDIGO2, 3)
    label(d, 740, 575, "OUTPUT", font(20), INDIGO2)
    box(d,(760,620,1120,760), PAPER, GOLD, 2)
    center(d,(760,620,1120,690),"Weekly Review", font(26), INDIGO)
    center(d,(760,685,1120,750),"6 sections · grounded", font(18,False), GRAY)
    arrow(d, 1125,690, 1230,660)
    arrow(d, 1125,690, 1230,725)
    box(d,(1235,615,1530,690), PAPER, TEAL, 2, r=14)
    center(d,(1235,615,1530,690),"Telegram", font(22), TEAL)
    box(d,(1235,705,1530,780), PAPER, TEAL, 2, r=14)
    center(d,(1235,705,1530,780),"Obsidian / Notion", font(20), TEAL)
    # Sonnet -> output
    arrow(d, 1357,425, 1357,555, color=INDIGO2)

    label(d, 50, 845, "Expensive part runs once a week. Everything else is free and local.", font(20,False), GRAY)
    img.save("/home/jyaenugu/diagram_architecture.png")
    print("saved diagram_architecture.png")

# ---------------- Diagram 2: Data-flow / Privacy ----------------
def dataflow():
    img=Image.new("RGB",(W,H),PAPER); d=ImageDraw.Draw(img)
    d.rectangle((0,0,W,90), fill=INDIGO); d.rectangle((0,90,W,96), fill=GOLD)
    label(d, 50, 28, "Data Flow & Privacy", font(40), WHITE)

    # Local machine boundary
    d.rounded_rectangle((50,150,900,820), radius=26, fill=(0xEC,0xF2,0xEC), outline=GREEN, width=4)
    label(d, 80, 170, "YOUR MACHINE  (local, self-hosted)", font(24), GREEN)

    # Vault (raw data) inside
    box(d,(100,240,560,560), WHITE, INDIGO2, 2)
    label(d, 120, 255, "Obsidian Vault — raw data", font(21), INDIGO)
    for i,t in enumerate(["Journal / daily logs","Brain / papers & notes","Schedule / Goals"]):
        y=300+i*70
        box(d,(130,y,530,y+54), PAPER, GOLD, 2, r=12)
        center(d,(130,y,530,y+54), t, font(20,False), DARK)
    d.ellipse((100,581,116,597), fill=GREEN)
    label(d, 126, 575, "raw notes never leave the machine", font(20), GREEN)

    # OpenClaw gateway inside
    box(d,(100,640,560,770), WHITE, INDIGO2, 2)
    center(d,(100,640,560,700),"OpenClaw gateway", font(22), INDIGO)
    center(d,(100,695,560,760),"(builds weekly digest)", font(18,False), GRAY)

    # API outside
    box(d,(1080,330,1520,560), INDIGO, INDIGO, 3)
    center(d,(1080,330,1520,400),"Anthropic API", font(26), WHITE)
    center(d,(1080,390,1520,450),"Claude Sonnet", font(21,False), GOLD)
    center(d,(1080,450,1520,520),"(no data stored by us)", font(17,False), (0xC8,0xD0,0xE6))

    # crossing arrows
    label(d, 600, 338, "weekly DIGEST text only", font(20), REDB)
    label(d, 600, 370, "(1× per week, ~a few KB)", font(17,False), GRAY)
    arrow(d, 565,430, 1075,415, color=REDB, width=6)
    arrow(d, 1075,505, 565,695, color=INDIGO2, width=5)
    label(d, 660, 590, "review text back", font(19,False), INDIGO2)

    # outputs
    box(d,(1080,620,1340,720), PAPER, TEAL, 2, r=14)
    center(d,(1080,620,1340,720),"Telegram", font(22), TEAL)
    box(d,(1360,620,1520,720), PAPER, TEAL, 2, r=14)
    center(d,(1360,620,1520,720),"Notion\n(phone)", font(18), TEAL)
    arrow(d, 565,735, 1075,665, color=TEAL, width=4)
    label(d, 640, 700, "deliver", font(17,False), TEAL)

    label(d, 50, 845, "Only a once-a-week summary crosses the boundary. Everything raw stays local.", font(20,False), GRAY)
    img.save("/home/jyaenugu/diagram_dataflow.png")
    print("saved diagram_dataflow.png")

architecture()
dataflow()
print("done")
