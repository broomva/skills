// Liquid Midnight · glass plasma orb as a pen.dev shader fill. Port of kit/orb-shaders.js (deck/index.html @187972f
// lines 1470-1488): per-orb attributes became uniforms. The node spans ±1.7 sphere radii: use a SQUARE node whose side is
// 3.4x the sphere radius (non-square nodes draw an ellipse). Output is premultiplied alpha, like the kit's canvas. Colours: A = filaments/caustics (base colour lifted 40% toward cyan), B = body (base x0.8). Defaults = kit colors(--lm-blue).
precision highp float;
/** @resolution */
uniform vec2 u_resolution;
/** @time */
uniform float u_time;
/**
 * @label Filament colour (A)
 * @color
 * @default #5dbbfd
 */
uniform vec3 uA;
/**
 * @label Body colour (B)
 * @color
 * @default #4384d6
 */
uniform vec3 uB;
/**
 * @label Rim violet tint (keep <= .45)
 * @default 0.45
 * @range 0, 1
 */
uniform float uViolet;
/**
 * @label Seed
 * @default 0.3
 * @range 0, 1
 */
uniform float uSeed;
/**
 * @label Speed
 * @default 1
 * @range 0, 3
 */
uniform float u_speed;
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7))+uSeed*13.17)*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<3;i++){s+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return s*1.14;}
float field(vec2 q,float t){float d=length(q),a=atan(q.y,q.x),f=0.;
 for(int k=0;k<2;k++){float fk=float(k);float w=fbm(vec2(a*1.4+fk*3.1,d*2.2-t*(.4+.12*fk))+uSeed*3.);
  float ang=a*(3.+fk*2.)+w*4.+t*(.3-.17*fk)+fk*1.9;f+=pow(1.-abs(sin(ang)),14.+fk*8.)*smoothstep(.05,.3,d)*(.35+.65*smoothstep(1.,.25,d));}
 float rays=pow(1.-abs(sin(a*11.+fbm(vec2(a*2.,t*.3))*3.)),40.)*smoothstep(.15,.6,d)*smoothstep(1.,.7,d)*fbm(vec2(a*5.,d*3.-t*.8))*1.6;
 float caust=smoothstep(.56,.8,fbm(q*2.6+vec2(t*.18,-t*.11)+uSeed))*1.5+smoothstep(.6,.88,fbm(q*5.+vec2(-t*.25,t*.2)))*.9;
 float flare=pow(fbm(vec2(a*2.6,t*.55)+uSeed*2.),3.)*smoothstep(.55,.97,d)*1.6;
 float core=exp(-d*d*26.)*.6+exp(-d*d*4.)*.18;
 vec2 g=q*11.+vec2(t*.12,0.);vec2 cf=fract(g)-.5;float hs=h(floor(g));float sp=step(.9,hs)*exp(-dot(cf,cf)*90.)*(.5+.5*sin(t*3.+hs*40.))*smoothstep(.2,.5,d);
 vec2 g2=q*7.+vec2(0.,-t*.2);vec2 c2=fract(g2)-.5;float hb=h(floor(g2)+7.);float bub=step(.94,hb)*smoothstep(.04,0.,abs(length(c2)-.12-.06*hb))*.35*smoothstep(.35,.6,d);
 return f*.8+rays+caust+flare+core+sp+bub;}
vec3 plasma(vec2 q,float t){float e=field(q,t),d=length(q);
 vec3 base=uB*(.07+.22*fbm(q*2.2+t*.12+uSeed));
 vec3 col=base+mix(uB,uA,clamp(e*.7,0.,1.))*e*.85+vec3(1.)*pow(clamp(e-1.1,0.,2.),2.)*.4;
 return mix(col,col*vec3(.86,.8,1.18),uViolet*smoothstep(.15,1.,d));}
void main(){vec2 p=(gl_FragCoord.xy/u_resolution*2.-1.)*1.7;float r=length(p),t=u_time*u_speed*.6+uSeed*10.;
 float bloom=(exp(-max(r-1.,0.)*5.5)*.5+exp(-max(r-1.,0.)*1.7)*.16)*smoothstep(1.68,1.25,r);vec3 bc=mix(uB,uA,.45);
 if(r>1.){gl_FragColor=vec4(bc*bloom,bloom);return;}
 float z=sqrt(max(1.-r*r,0.));vec3 N=vec3(p,z);float fres=pow(1.-z,3.);
 float k=1.-.4*pow(r,2.4);vec2 q=p*k;
 /* chromatic split only where it is visible (the outer rim): one plasma sample elsewhere */
 vec3 col=plasma(q,t);if(r>.8){float w=smoothstep(.8,.95,r);col=mix(col,vec3(plasma(q*1.025,t).r,col.g,plasma(q*.975,t).b),w);}
 col*=.78+.42*z;
 col+=uA*pow(clamp(-p.y*.95+.05,0.,1.),3.)*smoothstep(.5,1.,r)*.8;
 col+=mix(uA,vec3(1.),.55)*fres*1.15;
 vec2 hp=p-vec2(-.36,.44);col+=vec3(1.)*(exp(-(hp.x*hp.x*16.+hp.y*hp.y*34.))*.5+exp(-dot(hp,hp)*300.)*.85);
 col+=vec3(1.)*smoothstep(.05,0.,abs(r-.93))*pow(max(dot(normalize(p+1e-4),normalize(vec2(.62,-.72))),0.),7.)*.55;
 col=min(col,vec3(1.));float aa=smoothstep(1.,.975,r);
 gl_FragColor=vec4(col*aa+bc*bloom*(1.-aa),aa+bloom*(1.-aa));}