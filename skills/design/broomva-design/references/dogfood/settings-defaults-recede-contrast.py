"""WCAG 2.x contrast for the settings defaults-recede specimen (BRO-2537).
OKLCH token values from DESIGN.md / broomva-foundation.css -> linear sRGB (clipped),
translucent fills composited in gamma-encoded sRGB. Run: python3 settings-defaults-recede-contrast.py"""
import math
def oklch_to_srgb(L,C,h):
    a=C*math.cos(math.radians(h)); b=C*math.sin(math.radians(h))
    l_=L+0.3963377774*a+0.2158037573*b; m_=L-0.1055613458*a-0.0638541728*b; s_=L-0.0894841775*a-1.2914855480*b
    l,m,s=l_**3,m_**3,s_**3
    r=4.0767416621*l-3.3077115913*m+0.2309699292*s; g=-1.2684380046*l+2.6097574011*m-0.3413193965*s; bb=-0.0041960863*l-0.7034186147*m+1.7076147010*s
    return [min(1,max(0,x)) for x in (r,g,bb)]  # linear sRGB, clipped
def enc(x): return 12.92*x if x<=0.0031308 else 1.055*x**(1/2.4)-0.055
def dec(x): return x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4
def over(fg,a,bg): return [dec(a*enc(f)+(1-a)*enc(b)) for f,b in zip(fg,bg)]  # composite in gamma-encoded sRGB, as browsers do
def lum(lin): return 0.2126*lin[0]+0.7152*lin[1]+0.0722*lin[2]
def cr(x,y):
    a,b=sorted([lum(x),lum(y)],reverse=True); return (a+0.05)/(b+0.05)
O=oklch_to_srgb
W=O(1,0,0)
light=dict(card=W, secondary=O(0.966,0.003,265), ink=O(0.175,0.022,265), muted=O(0.50,0.015,265), placeholder=O(0.68,0.010,265), blue=O(0.60,0.12,260), accentfg=O(0.38,0.020,265))
light['accent_bg']=over(light['blue'],0.09,light['card'])
dark=dict(card=O(0.175,0.025,272), secondary=O(0.165,0.022,272), fg=O(0.965,0.004,265), muted=O(0.62,0.020,270), blue=O(0.60,0.12,260), accentfg=O(0.88,0.012,268))
dark['accent_bg']=over(dark['blue'],0.13,dark['card'])
rows=[
("light default value: ink on secondary chip", light['ink'], light['secondary']),
("light default value: muted-foreground on secondary", light['muted'], light['secondary']),
("light faded default: placeholder mist on secondary", light['placeholder'], light['secondary']),
("light changed value: blue text on accent fill", light['blue'], light['accent_bg']),
("light changed value: ink text on accent fill", light['ink'], light['accent_bg']),
("light default label: blue on card", light['blue'], light['card']),
("light default label as rendered: muted-foreground on card", light['muted'], light['card']),
("light chip edge: blue vs card (non-text, 3:1)", light['blue'], light['card']),
("dark default value: fg on secondary chip", dark['fg'], dark['secondary']),
("dark default value: muted-foreground on secondary", dark['muted'], dark['secondary']),
("dark changed value: blue text on accent fill", dark['blue'], dark['accent_bg']),
("dark changed value: fg text on accent fill", dark['fg'], dark['accent_bg']),
("dark default label: blue on card", dark['blue'], dark['card']),
("dark default label as rendered: muted-foreground on card", dark['muted'], dark['card']),
("dark chip edge: blue vs card (non-text, 3:1)", dark['blue'], dark['card']),
]
for n,f,b in rows: print(f"{cr(f,b):5.2f}:1  {'PASS' if cr(f,b)>=4.5 else ('3:1 ok' if cr(f,b)>=3 else 'FAIL')}  {n}")
