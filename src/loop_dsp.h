/* Original V2 DSP. Standard oscillation/comb/windowed-delay techniques;
 * no third-party source is incorporated. Fixed state, one FX bus per layer. */
#define FX_SIZE 131072
#define STRING_SIZE 2048
struct LoopDSP { float string[STRING_SIZE],z[8],modes[6],freq,phase2;unsigned cursor,noise; };
struct LoopGrain { float position,step;unsigned age,length; };
struct LoopBus { uint32_t stamps[FX_SIZE],era;float ring[FX_SIZE][2],p[8],low[2],ap[4],phase,phase2,reverse_phase,drop,env;unsigned cursor,grain_clock,noise;int frozen,fade;float last[2],attack,release,cutoff;struct LoopGrain grains[6]; };
static struct LoopDSP lp_dsp[LP_PLAYBACK+16];
static struct LoopBus lp_bus[8];
static _Atomic float lp_fx[8][3];
static float lp_env[8],lp_fx_values[8][3];
float sw_loop_fx(int layer,int metric){return layer>=0&&layer<8&&metric>=0&&metric<3?atomic_load(&lp_fx[layer][metric]):0;}
static float lp_rand(unsigned *seed){*seed=*seed*1664525u+1013904223u;return (float)(*seed>>8)*(1.f/8388608.f)-1.f;}
static float lp_blep(float t,float dt){if(t<dt){t/=dt;return t+t-t*t-1;}if(t>1-dt){t=(t-1)/dt;return t*t+t+t+1;}return 0;}
static float lp_read(struct LoopBus *b,float delay,int channel){
 float pos=(float)b->cursor-delay;while(pos<0)pos+=FX_SIZE;while(pos>=FX_SIZE)pos-=FX_SIZE;
 unsigned index=(unsigned)pos;float frac=pos-index;
 float a=b->stamps[index]==b->era?b->ring[index][channel]:0;unsigned next=(index+1)&(FX_SIZE-1);float c=b->stamps[next]==b->era?b->ring[next][channel]:0;
 return a+(c-a)*frac;
}
static void lp_voice_init(struct LoopVoice *v,int index){
 struct LoopDSP *d=&lp_dsp[index];memset(d,0,sizeof *d);d->freq=(float)(440*pow(2,(v->pitch-69)/12.0));d->noise=(unsigned)(v->id*1234567+76543);
}
/* Seconds-based coefficients; backward Euler differs from exact exponential by
 * <0.15% at the shortest8ms tau, with no transcendental work per sample.
 * Cached per layer every32samples; z[5]/z[6] are unused by all original voices. */
static void lp_gentle_coefficients(struct LoopBus *b,int role){
 float *p=b->p,a=.02f,r=.5f,c=1000;
 switch(role){
 case 0:a=.015f+.45f*p[0]*p[0];r=.10f+.65f*p[1]*p[1];c=250+10000*(1-p[2])*(1-p[2]);break;
 case 1:a=.008f+.06f*(1-p[0])*(1-p[0]);r=.12f+.80f*p[1]*p[1];c=500+4500*(1-p[3])*(1-p[3])*(1-p[3]);break;
 case 2:a=.020f+.50f*p[2]*p[2];r=.12f+.80f*p[3]*p[3];c=700+6500*p[1]*p[1];break;
 case 3:a=.040f+.60f*p[4]*p[4];r=.18f+p[5]*p[5];c=600+5000*p[3]*p[3];break;
 case 4:a=.040f+.60f*p[7]*p[7];r=.55f;c=600+7500*p[0]*p[0];break;
 case 5:a=.012f+.12f*(1-p[0])*(1-p[0]);r=.12f+.80f*p[1]*p[1];c=400+9000*(1-p[7])*(1-p[7]);break;
 case 6:a=.050f+.35f*(1-p[0])*(1-p[0]);r=.60f;c=500+6000*p[1]*p[1];break;
 case 7:a=.008f+.09f*(1-p[0])*(1-p[0]);r=.15f+.60f*(1-p[2])*(1-p[2]);c=600+10000*(1-p[7])*(1-p[7]);break;
 }
 b->attack=1/(1+SR*a);b->release=1/(1+SR*r);b->cutoff=c;
}
static float lp_voice_sound(struct LoopVoice *v,int index){
 if(!v->active)return 0;
 if(v->retiring){v->gain*=((float)(v->retiring-1)/v->retiring);if(!--v->retiring){v->active=0;return 0;}}
 struct LoopDSP *d=&lp_dsp[index];int role=lp_song.layers[v->layer].role;float *p=lp_bus[v->layer].p;
 int gentle=lp_song.layers[v->layer].sound_version==2;
 if(gentle&&(lp_bus[v->layer].cursor%32==0||!lp_bus[v->layer].attack))lp_gentle_coefficients(&lp_bus[v->layer],role);
 v->pressure+=(v->target-v->pressure)*.00028f;
 float attack=.003f,release=.00008f;
 if(role==0){attack=.00008f+.002f*(1-p[0]);release=.000015f+.0003f*(1-p[1]);}
 if(role==1){attack=.008f;release=.00002f+.0003f*(1-p[1]);}
 if(role==2){attack=.0001f+.004f*(1-p[2]);release=.000015f+.0002f*(1-p[3]);}
 if(role==3){attack=.00004f+.001f*(1-p[4]);release=.00001f+.0002f*(1-p[5]);}
 if(role==4){attack=.00004f+.0008f*(1-p[7]);release=.00006f;}
 if(role==5){attack=.001f+.008f*p[0];release=.00002f+.0004f*(1-p[1]);}
 if(role==6){attack=.00008f+.001f*p[0];release=.00008f;}
 if(role==7){attack=.002f+.01f*p[0];release=.00002f+.0003f*p[2];}
 if(gentle){attack=lp_bus[v->layer].attack;release=lp_bus[v->layer].release;}
 v->gain+=((v->held?1.f:0.f)-v->gain)*(v->held?attack:release);
 if(!v->held&&v->gain<.00001f){v->active=0;return 0;}
 float dt=d->freq/SR,t=(float)(v->phase/TAU),a=(float)sin(v->phase),s=0;
 switch(role){
 case 0:{ /* Band-limited saw/triangle, sub and pressure-sensitive soft rust. */
  float saw=2*t-1-lp_blep(t,dt);float shifted=t+.5f;if(shifted>=1)shifted-=1;
  float square=(t<.5f?1.f:-1.f)+lp_blep(t,dt)-lp_blep(shifted,dt);d->z[0]=dt*square+(1-dt)*d->z[0];
  d->phase2+=dt*.5f;if(d->phase2>=1)d->phase2-=1;
  s=(1-p[4])*(a+sinf(d->phase2*TAU)*p[5])+p[4]*(saw*(1-p[3])+d->z[0]*p[3]*3);
  s=tanhf(s*(1+p[6]*3+v->pressure));break;}
 case 1:{ /* Fractional Karplus string, continuously excited only on attack. */
  float period=fminf(2046,SR/d->freq),read=(float)d->cursor-period;if(read<0)read+=STRING_SIZE;
  unsigned r=(unsigned)read;float f=read-r;
  float old=d->string[r]*(1-f)+d->string[(r+1)&(STRING_SIZE-1)]*f;
  float excite=v->age<(uint64_t)period?lp_rand(&d->noise)*(.2f+p[0])*(.3f+.7f*(float)sin(v->phase*(1+p[2]*3))):0;
  float dispersion=p[3]*.7f,y=-dispersion*old+d->z[1];d->z[1]=old+dispersion*y;
  d->z[0]+=(y-d->z[0])*(.1f+.85f*(1-p[3]));
  s=d->z[0]*(.96f+.039f*p[1])+excite;d->string[d->cursor]=s;
  s-=d->string[(d->cursor+STRING_SIZE-(unsigned)(period*(.05f+.9f*p[2])))&(STRING_SIZE-1)]*.5f;
  d->cursor=(d->cursor+1)&(STRING_SIZE-1);s*=.5f+p[0];break;}
 case 2:{ /* Two-operator harmonic FM. */
  int ratio=1+(int)(p[0]*7);float index=fminf(p[1]*5+v->pressure,fmaxf(0,.45f*SR/d->freq/ratio-1));s=(float)sin(v->phase+(float)sin(v->phase*ratio)*index);break;}
 case 3:{ /* Breath-excited harmonic formants with three moving vowels. */
  float vowel=p[0]*2,breath=lp_rand(&d->noise)*p[1]*.25f;
  for(int h=1;h<=6;h++){float centers[3]={1.5f+vowel,3.3f+vowel*1.7f,5-vowel*.8f};float weight=0;
   for(int f=0;f<3;f++){float distance=h-centers[f]-p[2]*.5f;weight+=1/(1+distance*distance*(1+p[3]*8));}s+=(float)sin(v->phase*h)*weight/(float)h;}
  d->z[0]+=(breath-d->z[0])*.12f;s+=d->z[0];break;}
 case 4:{ /* Detuned, band-limited pad; tape treatment belongs to shared bus. */
  d->phase2+=dt*(1+.004f*p[6]);if(d->phase2>=1)d->phase2-=1;
  s=(2*t-1-lp_blep(t,dt)+2*d->phase2-1-lp_blep(d->phase2,dt))*.5f;
  s+=a*.35f;if(gentle)s=a*(1-p[0]*p[0])+s*p[0]*p[0];break;}
 case 5:{ /* Rounded additive mallet, excitation decays while its gate is held. */
  float age=(float)v->age/SR;float decay=1/(1+age*(1+12*(1-p[1])));
  s=(a+.25f*(float)sin(v->phase*2)+.08f*(float)sin(v->phase*3))*decay;break;}
 case 6:{ /* Bow pressure feeds a tuned comb, plus pitched anchor. */
  unsigned period=(unsigned)fminf(2046,SR/d->freq);unsigned r=(d->cursor+STRING_SIZE-period)&(STRING_SIZE-1);
  float bow=tanhf((a*.08f+v->pressure*.01f-d->string[r])*(.5f+p[0]*2));
  d->z[0]+=(d->string[r]-d->z[0])*(.08f+.8f*p[1]);s=d->z[0]*.985f+bow*.12f;
  d->string[d->cursor]=s;d->cursor=(d->cursor+1)&(STRING_SIZE-1);s=s*2+a*.5f;break;}
 case 7:{ /* Six harmonic modal resonators excited by a decaying strike. */
  float age=(float)v->age/SR;
  for(int h=1;h<=6;h++){float damping=1/(1+age*h*(.1f+4*p[2]));float ratio=h+(h-1)*p[1]*.015f;d->modes[h-1]+=TAU*d->freq*ratio/SR;if(d->modes[h-1]>=TAU)d->modes[h-1]-=TAU;s+=sinf(d->modes[h-1])*damping/(h*h*.6f);}
  break;}
 }
 if(gentle){
  if(!(v->age%32)){float f=fminf(12000,fmaxf(d->freq*1.25f,lp_bus[v->layer].cutoff));d->z[4]=(TAU*f)/(SR+TAU*f);}
  d->z[5]+=(s-d->z[5])*d->z[4];d->z[6]+=(d->z[5]-d->z[6])*d->z[4];d->z[7]=d->z[6];
 }else d->z[7]+=(s-d->z[7])*(.03f+.7f*(1-(role==0?p[2]:role==5?p[7]:role==7?p[7]:.2f)));
 v->phase+=TAU*d->freq/SR;if(v->phase>=TAU)v->phase-=TAU;v->age++;
 static const float trim[8]={1,2,.55f,.85f,.9f,1.8f,1.35f,.75f};
 return (gentle?trim[role]:1)*d->z[7]*(role==1?6:1)*v->velocity*v->gain*.09f*(.8f+.2f*v->pressure);
}
static void lp_effect(int layer,float input,float *left,float *right){
 struct LoopBus *b=&lp_bus[layer];float *p=b->p;int role=lp_song.layers[layer].role;
 for(int i=0;i<8;i++)p[i]+=(lp_song.layers[layer].parameters[i]-p[i])*.0005f;
 b->phase+=.000007f;if(b->phase>=1)b->phase-=1;
 b->phase2+=.000043f;if(b->phase2>=1)b->phase2-=1;
 float slow=sinf(b->phase*TAU),fast=sinf(b->phase2*TAU),l=input,r=input,feedback=.2f,wet=.2f,delayframes=8000,aux=0;
 switch(role){
 case 0:delayframes=1300+p[7]*18000;feedback=.2f+p[7]*.35f;wet=p[7]*.5f;break;
 case 1:delayframes=2400+p[4]*16000;feedback=p[5]*.65f;wet=.1f+p[4]*.55f;r=lp_read(b,delayframes*(1+p[6]*.3f),1)*wet+input;wet+=p[7]*.15f;break;
 case 2:{ /* Four-stage allpass phaser, slow motion with bounded coefficient. */
  float coefficient=.1f+p[4]*.5f+slow*p[5]*.15f;float phased=input;
  for(int i=0;i<4;i++){float y=-coefficient*phased+b->ap[i];b->ap[i]=phased+coefficient*y;phased=y;}
  l=input+phased*p[6]*.6f;r=input+phased*p[7]*.6f;delayframes=3400;wet=.1f;aux=(slow+1)*.5f;break;}
 case 3:delayframes=600+slow*(20+p[6]*160);wet=p[7]*.6f;feedback=.1f;r=input+lp_read(b,700-fast*100*p[6],1)*wet;aux=(slow+1)*.5f;break;
 case 4:{ /* Tape moving heads, quantization and ramped, deterministic dropout. */
  delayframes=1200+p[3]*18000+slow*p[1]*220+fast*p[2]*35;feedback=p[4]*.65f;wet=.15f+p[3]*.5f;
  float target=(slow>.96f-p[5]*.3f&&p[5]>.01f)?1-p[5]*.85f:1;b->drop+=(target-b->drop)*.001f;
  float steps=128+(1-p[0])*12000;if(lp_song.layers[layer].sound_version==2){float quantized=roundf(input*steps)/steps;l=(input+(quantized-input)*p[0]*p[0])*b->drop;}else l=roundf(input*steps)/steps*b->drop;r=l;aux=1-b->drop;break;}
 case 5:{ /* Two overlapping Hann reverse readers, no buffer endpoint jump. */
  float size=3528+p[3]*49392;
  b->reverse_phase+=1/size;if(b->reverse_phase>=1)b->reverse_phase-=1;float phase=b->reverse_phase;
  float w=.5f-.5f*cosf(phase*TAU),q=fmodf(phase+.5f,1),v=.5f-.5f*cosf(q*TAU);
  float reverse=lp_read(b,2*phase*size+1,0)*w+lp_read(b,2*q*size+1,1)*v;
  l=input*(1-p[2]*.7f)+reverse*p[2];r=l+(lp_read(b,size*.5f,1)-l)*p[4]*.2f;
  delayframes=2205+p[5]*12000;wet=p[5]*.4f;feedback=p[6]*.65f;aux=phase;break;}
 case 6:{ /* Six bounded grains over a600ms ring; hysteretic freeze. */
  if(p[5]>.85f)b->frozen=1;
  if(p[5]<.75f)b->frozen=0;
  unsigned interval=(unsigned)(SR/(2+22*p[3]));
  if(++b->grain_clock>=interval){b->grain_clock=0;
   for(int i=0;i<6;i++)if(b->grains[i].age>=b->grains[i].length){b->grains[i]=(struct LoopGrain){.position=100+(lp_rand(&b->noise)+1)*.5f*26000*p[4],.step=1,.length=(unsigned)(882+7056*p[2])};break;}
  }
  float cloud=0;int active=0;
  for(int i=0;i<6;i++){struct LoopGrain *g=&b->grains[i];if(g->age<g->length){float u=(float)g->age/g->length;cloud+=lp_read(b,g->position,0)*(.5f-.5f*cosf(u*TAU));g->age++;active++;}}
  l=input*(1-p[7]*.5f)+cloud*p[7]*.3f;r=l+cloud*p[6]*.15f;delayframes=1800;wet=.1f;feedback=.2f;aux=active/6.f;break;}
 case 7:{ /* Two octave-only moving heads, crossfaded into dark diffusion. */
  float ratio=p[4]<.5f?1:3;float ph=fmodf((float)b->cursor*ratio,4096)/4096,q=fmodf(ph+.5f,1);
  float shimmer=lp_read(b,4096*(1-ph)+1,0)*(.5f-.5f*cosf(ph*TAU))+lp_read(b,4096*(1-q)+1,1)*(.5f-.5f*cosf(q*TAU));
  float diffuse=input,coefficient=.05f+p[6]*.5f;for(int i=0;i<2;i++){float y=-coefficient*diffuse+b->ap[i];b->ap[i]=diffuse+coefficient*y;diffuse=y;}
  l=diffuse+shimmer*p[3]*.4f;r=diffuse+shimmer*p[3]*.4f;delayframes=1400+p[5]*17000;wet=p[5]*.45f;feedback=p[6]*.6f;aux=ph;break;}
 }
 float dl=lp_read(b,delayframes,0),dr=lp_read(b,delayframes+71,1);
 if(lp_song.layers[layer].sound_version==2){
  /* Darken only returned feedback; dry sources and role identities remain. */
  b->low[0]+=(dl-b->low[0])*.254812f;b->low[1]+=(dr-b->low[1])*.254812f;
 }
 if(!b->frozen){
  b->stamps[b->cursor]=b->era;
  if(lp_song.layers[layer].sound_version==2){b->ring[b->cursor][0]=tanhf(l+b->low[1]*feedback);b->ring[b->cursor][1]=tanhf(r+b->low[0]*feedback);}
  else {b->ring[b->cursor][0]=tanhf(l+dr*feedback);b->ring[b->cursor][1]=tanhf(r+dl*feedback);}
 }
 b->cursor=(b->cursor+1)&(FX_SIZE-1);
 l+=dl*wet;r+=dr*wet;
 b->env+=(fabsf(l)+fabsf(r)-b->env)*.003f;lp_env[layer]=fminf(1,b->env*8);
 lp_fx_values[layer][0]=lp_env[layer];lp_fx_values[layer][1]=aux;lp_fx_values[layer][2]=(slow+1)*.5f;
 if(b->fade){float f=(float)b->fade/441;l+=b->last[0]*f;r+=b->last[1]*f;b->fade--;}
 else {b->last[0]=l;b->last[1]=r;}
 *left+=l*track_gain[layer];*right+=r*track_gain[layer];
}
static void lp_dsp_reset(void){memset(lp_dsp,0,sizeof lp_dsp);memset(lp_bus,0,sizeof lp_bus);memset(lp_env,0,sizeof lp_env);memset(lp_fx_values,0,sizeof lp_fx_values);for(int l=0;l<8;l++){lp_bus[l].era=1;lp_bus[l].drop=1;lp_bus[l].noise=l+1;for(int m=0;m<3;m++)atomic_store(&lp_fx[l][m],0);}}

/* O(voices+layers) invalidation, not a multi-megabyte memset on the RT thread. */
static void lp_silenced(void){
 for(int i=0;i<LP_PLAYBACK;i++)lp_voices[i].active=0;
 for(int i=0;i<8;i++){
  lp_manual[i].active=lp_manual_tail[i].active=0;
  struct LoopBus *b=&lp_bus[i];b->era++;b->frozen=0;b->env=lp_env[i]=0;
  memset(b->grains,0,sizeof b->grains);memset(b->ap,0,sizeof b->ap);memset(b->low,0,sizeof b->low);
 }
}
