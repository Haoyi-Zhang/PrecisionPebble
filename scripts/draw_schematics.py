"""Vector drawing primitives; copied into each independent project generator."""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)

NAMES=('separation','valley')
def draw_all(out):
    out.mkdir(parents=True,exist_ok=True)
    d=Drawing((-1.2,-1.2,9.2,5.2))
    for n,x,label in [('sa',0,r'$4x-t$'),('sb1',2,r'$x$'),('sb2',4,r'$2x$'),('sc1',6,r'$x$'),('sc2',8,r'$x+t$')]:d.box(n,x,0,1.5,.65,label)
    for n,x,y,label in [('A',0,1.5,r'$A\ (t)$'),('b',3,1.5,r'$b\ (x)$'),('c',7,1.5,r'$c\ (x)$'),('d',5,3,r'$d\ (t)$'),('z',2.5,4.5,r'$z\ (r)$')]:d.box(n,x,y,1.5,.65,label)
    for a,b in [('sa','A'),('sb1','b'),('sb2','b'),('sc1','c'),('sc2','c'),('c','d'),('A','z'),('d','z')]:d.edge(a,b,'n','s')
    d.edge('b','d','n','s',dashed=True);d.text(3.25,2.6,'store/load',size=8.5)
    d.text(4,-.8,r'Source allocations; $B=4x$, $x\geq2t$, $1\leq r\leq t$');d.save(out,'separation')
    d=Drawing((-.6,-1.1,8.6,4.8))
    for i,x in [(1,1.8),(2,6.2)]:
        for prefix,y,label in [('s',0,'source 16'),('m',1.3,'middle 1'),('f',2.6,'final 8')]:d.box(prefix+str(i),x,y,1.7,.6,label)
        d.edge('s'+str(i),'m'+str(i),'n','s');d.edge('m'+str(i),'f'+str(i),'n','s')
        xlab=.35 if i==1 else 7.65;d.text(xlab,.65,'shrink');d.text(xlab,1.95,'expand')
    d.box('z',4,4,1.5,.6,'root 1');d.edge('f1','z','n','s');d.edge('f2','z','n','s')
    d.line([d.point('m1','e'),d.point('m2','w')],dashed=True);d.text(4,1.75,'both one-unit\nvalleys coexist',size=8.5)
    d.text(4,-.8,r'$B=18$; optimum I/O $=16+16+1=33$');d.save(out,'valley')

def main():
    import tempfile
    ap=argparse.ArgumentParser(description='Direct Python vector drawings of the manuscript relationships.')
    ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'figures');ap.add_argument('--check',action='store_true');a=ap.parse_args()
    if a.check:
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);draw_all(out)
            for name in NAMES:
                p=a.output/(name+'.pdf')
                if not p.is_file() or p.read_bytes()!=(out/(name+'.pdf')).read_bytes():raise SystemExit('Missing/stale schematic: '+name)
        print('All schematics reproduce byte-for-byte.')
    else:draw_all(a.output)
if __name__=='__main__':main()

