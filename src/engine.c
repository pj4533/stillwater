#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
/* Stillwater: bounded command queue, sample-clock sequencer, native DSP.
 * ALSA loaded at runtime to keep builds independent of development headers. */
#include <math.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <dlfcn.h>
#include <time.h>
#include <stdio.h>
#include <errno.h>
#define SR 44100
#define TRACKS 8
#define STEPS 8
#define VOICES 48
#define QSIZE 1024
#define MANUAL 8
#ifndef STILLWATER_HISTORY
#define STILLWATER_HISTORY 1
#endif
#define HISTORY_FRAMES (SR*45)
_Static_assert(ATOMIC_LLONG_LOCK_FREE==2 && ATOMIC_INT_LOCK_FREE==2,"history requires lock-free atomics");
_Static_assert(sizeof(float)==4,"history requires32-bit float");
#define CAPTURE_FRAMES (SR*30)
#define TAU 6.283185307179586
struct Command { int op,a,b; float value; int track,note; };
static struct Command queue[QSIZE];
static _Atomic unsigned head,tail;
static _Atomic int running,position;
static _Atomic unsigned long frames,xruns,written;
static _Atomic float peak,envelopes[TRACKS];
static _Atomic unsigned long onsets[TRACKS];
/* Preallocated post-limiter history. All fields atomic: even overwrite racing
 * a reader is data-race-free. Seq-cst publication/data/load ordering prevents
 * an old generation from validating mixed replacement samples. */
struct HistoryFrame { _Atomic uint64_t generation; _Atomic uint32_t left,right; };
static struct HistoryFrame history[HISTORY_FRAMES];
static _Atomic uint64_t history_end,history_epoch=1;
static uint64_t history_next;
static int history_prepared;
static pthread_t thread;
static int started,playing,step=-1;
static float tempo=58,master=.28f,master_target=.28f,space=.35f,space_target=.35f;
static float transport_gain=1,transport_target=1;
static int stopping;
static double until_step;
static float levels[TRACKS]={.6,.36,.28,.4,.24,.28,.25,.22};
static float track_gain[TRACKS];
static float tones[TRACKS]={.5,.5,.5,.5,.5,.5,.5,.5};
static float decays[TRACKS]={.5,.5,.5,.5,.5,.5,.5,.5};
static int patterns[TRACKS][STEPS];
struct Voice { double phase,age,freq; float amp,decay,tone; int kind,active; };
static struct Voice voices[VOICES];
/* Separate manual pool: sequencer allocation and expression can never collide.
 * Each slot has one short stolen-voice tail and a smoothed sum for soft stealing. */
struct Manual { struct Voice voice,tail; int token,held; float pressure,target,release,tail_release,smooth; };
static struct Manual manual[MANUAL];
static _Atomic unsigned manual_versions[MANUAL];
static _Atomic int manual_tokens[MANUAL],manual_held[MANUAL],manual_tracks[MANUAL];
static _Atomic float manual_env[MANUAL],manual_pressure[MANUAL];
static float delay[SR*2][2];
static unsigned delaypos;
static void *pcm,*alsa;
static int (*pcm_open)(void**,const char*,int,int);
static int (*pcm_params)(void*,int,int,unsigned,unsigned,int,unsigned);
static long (*pcm_write)(void*,const void*,unsigned long);
static int (*pcm_prepare)(void*),(*pcm_close)(void*),(*pcm_nonblock)(void*,int);
static void lp_prepare(void);
int sw_history_prepare(void){
 if(started)return -1;
 if(!history_prepared){
  lp_prepare();
  for(unsigned i=0;i<HISTORY_FRAMES;i++){
   atomic_store(&history[i].generation,0);atomic_store(&history[i].left,0);atomic_store(&history[i].right,0);
  }history_prepared=1;
 }return 0;
}
uint64_t sw_history_end(void){return atomic_load(&history_end);}
uint64_t sw_history_epoch(void){return atomic_load(&history_epoch);}
int sw_history_copy(uint64_t epoch,uint64_t start,int count,int16_t *out){
 uint64_t end=atomic_load(&history_end);
 if(count<=0||count>CAPTURE_FRAMES||start>end||((uint64_t)count)>end-start||end-start>HISTORY_FRAMES||epoch!=atomic_load(&history_epoch))return -1;
 for(int i=0;i<count;i++){
  uint64_t index=start+(uint64_t)i;struct HistoryFrame *f=&history[index%HISTORY_FRAMES];
  if(atomic_load(&f->generation)!=index+1)return -2;
  uint32_t l=atomic_load(&f->left),r=atomic_load(&f->right);
  if(atomic_load(&f->generation)!=index+1)return -2;
  float left,right;memcpy(&left,&l,4);memcpy(&right,&r,4);
  out[i*2]=(int16_t)lrintf(left*32767);out[i*2+1]=(int16_t)lrintf(right*32767);
 }
 return epoch==atomic_load(&history_epoch)?0:-2;
}
static void trigger(int track,int note,float vel){
 transport_target=1;stopping=0;atomic_fetch_add(&onsets[track],1);
 int i; for(i=0;i<VOICES;i++)if(!voices[i].active)break;
 if(i==VOICES){i=0;for(int j=1;j<VOICES;j++)if(voices[j].age>voices[i].age)i=j;}
 struct Voice *v=&voices[i]; *v=(struct Voice){.freq=440*pow(2,(note-69)/12.0),.amp=vel*.16f,.decay=decays[track],.tone=tones[track],.kind=track,.active=1};
}
/* Single producer (UI/IPC dispatcher), single consumer (audio render). */
static int enqueue(struct Command command){
 unsigned h=atomic_load_explicit(&head,memory_order_relaxed),next=(h+1)%QSIZE;
 if(next==atomic_load_explicit(&tail,memory_order_acquire))return -1;
 queue[h]=command;atomic_store_explicit(&head,next,memory_order_release);return 0;
}
int sw_command(int op,int a,int b,float value){return enqueue((struct Command){.op=op,.a=a,.b=b,.value=value});}
int sw_manual_on(int slot,int token,int track,int note,float velocity){
 if(slot<0||slot>=MANUAL||token<=0||track<0||track>=TRACKS||note<24||note>96||!isfinite(velocity)||velocity<=0||velocity>1)return -2;
 return enqueue((struct Command){.op=8,.a=slot,.b=token,.track=track,.note=note,.value=velocity});
}
static void commands(void){
 unsigned t=atomic_load_explicit(&tail,memory_order_relaxed),h=atomic_load_explicit(&head,memory_order_acquire);
 while(t!=h){struct Command c=queue[t];
  if(c.op==1&&c.value>=30&&c.value<=160)tempo=c.value;
  if(c.op==2){
   playing=c.a!=0;
   if(playing){until_step=0;step=-1;transport_target=1;stopping=0;}
   else{
    transport_target=0;stopping=1;
    /* Retire held identities now, independently of the cancellable master fade.
     * A new note/Play may reopen transport while these old voices fade out. */
    for(int i=0;i<MANUAL;i++){manual[i].token=0;manual[i].held=0;manual[i].target=0;}
   }
  }
  if(c.op==3&&c.a>=0&&c.a<8&&c.b>=0&&c.b<STEPS&&c.value>=0&&c.value<=127)patterns[c.a][c.b]=(int)c.value;
  if(c.op==4&&c.a>=0&&c.a<8&&c.value>=0&&c.value<=1){if(c.b==0)levels[c.a]=c.value;if(c.b==1)tones[c.a]=c.value;if(c.b==2)decays[c.a]=c.value;}
  if(c.op==5&&c.a>=0&&c.a<8&&c.b>=24&&c.b<=96&&c.value>=0&&c.value<=1)trigger(c.a,c.b,c.value);
  if(c.op==6&&c.value>=0&&c.value<=1.f)master_target=c.value;
  if(c.op==7&&c.value>=0&&c.value<=.8f)space_target=c.value;
  if(c.op==8&&c.a>=0&&c.a<MANUAL){
   struct Manual *m=&manual[c.a];m->tail=m->voice;m->tail_release=m->release;
   m->voice=(struct Voice){.freq=440*pow(2,(c.note-69)/12.0),.amp=c.value*.16f,.decay=decays[c.track],.tone=tones[c.track],.kind=c.track,.active=1};
   m->token=c.b;m->held=1;m->pressure=m->target=m->release=0;
   transport_target=1;stopping=0;atomic_fetch_add(&onsets[c.track],1);
  }
  if((c.op==9||c.op==10)&&c.a>=0&&c.a<MANUAL&&manual[c.a].token==c.b){
   if(c.op==9&&manual[c.a].held&&isfinite(c.value)&&c.value>=0&&c.value<=1)manual[c.a].target=c.value;
   if(c.op==10)manual[c.a].held=0;
  }
  t=(t+1)%QSIZE;
 }atomic_store_explicit(&tail,t,memory_order_release);
}
#include "loop_native.h"
void sw_render(float *out,int count){
 commands();lp_process();float max=0;
 for(int n=0;n<count;n++){
  if(!lp_enabled&&playing&&until_step<=0){step=(step+1)%STEPS;atomic_store(&position,step);for(int t=0;t<8;t++)if(patterns[t][step])trigger(t,patterns[t][step],.8f);until_step+=SR*60.0/tempo/4;}
  if(playing)until_step-=1;
  float left=0,right=0,activity[TRACKS]={0};
  for(int t=0;t<TRACKS;t++)track_gain[t]+=(levels[t]-track_gain[t])*.001f; /* ~23ms track faders, including existing tails */
  for(int i=0;i<VOICES;i++)if(voices[i].active){struct Voice *v=&voices[i];
   double age=v->age,env,sig,seconds=.8+v->decay*5.2;
   /* Every voice is a soft, band-limited ambient tone. No drum/noise path. */
   double attack=.07+v->kind*.035;
   env=(1-exp(-age/attack))*exp(-age/seconds);
   sig=sin(v->phase)+v->tone*.18*sin(v->phase*2.001)+v->tone*.06*sin(v->phase*3.003);
   activity[v->kind]+=(float)env*v->amp*track_gain[v->kind]*master*transport_gain;
   float s=(float)(sig*env)*v->amp*track_gain[v->kind];float pan=(v->kind%3-1)*.22f;left+=s*(1-pan);right+=s*(1+pan);
   v->phase+=TAU*v->freq/SR; if(v->phase>TAU)v->phase-=TAU;v->age+=1.0/SR;if(env<.0003&&age>.1)v->active=0;
  }
  for(int i=0;i<MANUAL;i++){
   struct Manual *m=&manual[i];float sum=0,env_current=0;
   m->pressure+=(m->target-m->pressure)*.00028f; /* ~81ms pressure smoothing */
   for(int part=0;part<2;part++){
    struct Voice *v=part?&m->tail:&m->voice;if(!v->active)continue;
    float *release=part?&m->tail_release:&m->release;
    if(part||!m->held)*release+=1.f/SR;
    double env=(1-exp(-v->age/(.07+v->kind*.035)))*(.65+.35*exp(-v->age/(.8+v->decay*5.2)));
    env*=exp(-*release/(part?.10:(.15+v->decay*.35)));
    float pressure=part?0:m->pressure;
    double tone=fmin(1,v->tone+pressure*.18);
    double sig=sin(v->phase)+tone*.18*sin(v->phase*2.001)+tone*.06*sin(v->phase*3.003);
    float amp=v->amp*track_gain[v->kind]*(.8f+.2f*pressure);
    sum+=(float)(sig*env)*amp;
    activity[v->kind]+=(float)env*amp*master*transport_gain;
    if(!part)env_current=(float)env*amp*master*transport_gain;
    v->phase+=TAU*v->freq/SR;if(v->phase>TAU)v->phase-=TAU;v->age+=1.0/SR;
    if(*release>0&&env<.0003){v->active=0;if(!part)env_current=0;}
   }
   /* Removes discontinuity even if rapid stealing replaces an older tail. */
   m->smooth+=(sum-m->smooth)*.05f;
   float pan=(m->voice.kind%3-1)*.22f;left+=m->smooth*(1-pan);right+=m->smooth*(1+pan);
   if(n==count-1){
    atomic_fetch_add(&manual_versions[i],1);
    atomic_store(&manual_tracks[i],m->voice.kind);atomic_store(&manual_tokens[i],m->token);atomic_store(&manual_held[i],m->held&&m->voice.active);
    atomic_store(&manual_env[i],stopping||transport_gain==0?0:fminf(1,env_current*24));
    atomic_store(&manual_pressure[i],m->pressure);atomic_fetch_add(&manual_versions[i],1);
   }
  }
  lp_sample(&left,&right);
  unsigned read=(delaypos+SR*2-22050)% (SR*2);float dl=lp_enabled?0:delay[read][0],dr=lp_enabled?0:delay[read][1];
  delay[delaypos][0]=left+dr*.47f;delay[delaypos][1]=right+dl*.47f;delaypos=(delaypos+1)%(SR*2);
  master+=(master_target-master)*.002f;space+=(space_target-space)*.002f;
  transport_gain+=(transport_target-transport_gain)*.002f;
  if(stopping&&transport_gain<.0001f){lp_silenced();memset(voices,0,sizeof voices);memset(manual,0,sizeof manual);memset(delay,0,sizeof delay);transport_gain=0;stopping=0;}
  left=.25f*tanhf((left+dl*space)*master*4)*transport_gain;right=.25f*tanhf((right+dr*space)*master*4)*transport_gain;
  if(n==count-1)for(int t=0;t<TRACKS;t++)atomic_store(&envelopes[t],stopping||transport_gain==0?0:fminf(1,activity[t]*24+lp_env[t]));
#if STILLWATER_HISTORY
  struct HistoryFrame *f=&history[history_next%HISTORY_FRAMES];uint32_t l,r;
  memcpy(&l,&left,4);memcpy(&r,&right,4);
  atomic_store(&f->generation,0);atomic_store(&f->left,l);atomic_store(&f->right,r);
  atomic_store(&f->generation,history_next+1);history_next++;
#endif
  out[n*2]=left;out[n*2+1]=right;float p=fmaxf(fabsf(left),fabsf(right));if(p>max)max=p;
 }atomic_store(&history_end,history_next);atomic_store(&peak,max);atomic_fetch_add(&frames,count);lp_snapshot();
}
static void *audio_loop(void *unused){
 (void)unused;struct sched_param sp={.sched_priority=30};pthread_setschedparam(pthread_self(),SCHED_FIFO,&sp);
 float stereo[256*2];unsigned char packed[256*16*3];
 while(atomic_load(&running)){
  sw_render(stereo,256);memset(packed,0,sizeof packed);
  for(int n=0;n<256;n++)for(int ch=0;ch<4;ch++){int32_t v=(int32_t)(stereo[n*2+(ch%2)]*8388607.f);unsigned off=(n*16+ch)*3;packed[off]=v;packed[off+1]=v>>8;packed[off+2]=v>>16;}
  int done=0;while(done<256&&atomic_load(&running)){
   long n=pcm_write(pcm,packed+done*48,256-done);
   if(n==-EAGAIN||n==0){struct timespec pause={.tv_sec=0,.tv_nsec=1000000};nanosleep(&pause,NULL);}
   else if(n==-EPIPE){atomic_fetch_add(&xruns,1);if(pcm_prepare(pcm)<0)atomic_store(&running,0);}
   else if(n<0){atomic_fetch_add(&xruns,1);atomic_store(&running,0);}
   else{done+=(int)n;atomic_fetch_add(&written,(unsigned long)n);}
  }
 }return NULL;
}
int sw_start(const char *device){
 if(started)return -1;
 alsa=dlopen("libasound.so.2",RTLD_NOW);if(!alsa)return -2;
 #define LOAD(name,target) *(void **)(&target)=dlsym(alsa,name);if(!target)return -3
 LOAD("snd_pcm_open",pcm_open);LOAD("snd_pcm_set_params",pcm_params);LOAD("snd_pcm_writei",pcm_write);LOAD("snd_pcm_prepare",pcm_prepare);LOAD("snd_pcm_nonblock",pcm_nonblock);LOAD("snd_pcm_close",pcm_close);
 int e=pcm_open(&pcm,device,0,1);if(e<0)return e;
 /* S24_3LE=32, RW_INTERLEAVED=3. All CV/ADAT outputs remain zero. */
 e=pcm_params(pcm,32,3,16,SR,0,17415);if(e<0){pcm_close(pcm);pcm=NULL;return e;}
 e=pcm_nonblock(pcm,1);if(e<0){pcm_close(pcm);pcm=NULL;return e;}
 atomic_store(&running,1);if(pthread_create(&thread,NULL,audio_loop,NULL)){atomic_store(&running,0);pcm_close(pcm);return -4;}started=1;return 0;
}
int sw_stop(void){
 if(!started)return 0;
 sw_command(2,0,0,0);struct timespec fade={.tv_sec=0,.tv_nsec=100000000};nanosleep(&fade,NULL);
 atomic_store(&running,0);
 struct timespec deadline;clock_gettime(CLOCK_REALTIME,&deadline);deadline.tv_sec+=2;
 if(pthread_timedjoin_np(thread,NULL,&deadline))return -1;
 pcm_close(pcm);pcm=NULL;started=0;return 0;
}
unsigned long sw_frames(void){return atomic_load(&frames);}
unsigned long sw_written(void){return atomic_load(&written);}
unsigned long sw_xruns(void){return atomic_load(&xruns);}
int sw_position(void){return atomic_load(&position);}
int sw_alive(void){return atomic_load(&running);}
float sw_envelope(int track){return track>=0&&track<TRACKS?atomic_load(&envelopes[track]):0;}
unsigned long sw_onsets(int track){return track>=0&&track<TRACKS?atomic_load(&onsets[track]):0;}
/* Bounded coherent UI snapshot; it cannot wait on the audio publisher. */
int sw_manual_snapshot(int slot,int *token,int *held,int *track,float *env,float *pressure){
 if(slot<0||slot>=MANUAL)return 0;
 for(int attempt=0;attempt<3;attempt++){
  unsigned version=atomic_load(&manual_versions[slot]);if(version&1)continue;
  int t=atomic_load(&manual_tokens[slot]),h=atomic_load(&manual_held[slot]),k=atomic_load(&manual_tracks[slot]);
  float e=atomic_load(&manual_env[slot]),p=atomic_load(&manual_pressure[slot]);
  if(version==atomic_load(&manual_versions[slot])){*token=t;*held=h;*track=k;*env=e;*pressure=p;return 1;}
 }return 0;
}
int sw_manual_token(int slot){return slot>=0&&slot<MANUAL?atomic_load(&manual_tokens[slot]):0;}
int sw_manual_track(int slot){return slot>=0&&slot<MANUAL?atomic_load(&manual_tracks[slot]):0;}
int sw_manual_held(int slot){return slot>=0&&slot<MANUAL?atomic_load(&manual_held[slot]):0;}
float sw_manual_envelope(int slot){return slot>=0&&slot<MANUAL?atomic_load(&manual_env[slot]):0;}
float sw_manual_pressure(int slot){return slot>=0&&slot<MANUAL?atomic_load(&manual_pressure[slot]):0;}
float sw_peak(void){return atomic_load(&peak);}
void sw_reset(void){if(started)return;lp_reset();atomic_store(&history_end,0);atomic_fetch_add(&history_epoch,1);history_next=0;memset(voices,0,sizeof voices);memset(manual,0,sizeof manual);for(int i=0;i<MANUAL;i++){atomic_store(&manual_versions[i],0);atomic_store(&manual_tracks[i],0);atomic_store(&manual_tokens[i],0);atomic_store(&manual_held[i],0);atomic_store(&manual_env[i],0);atomic_store(&manual_pressure[i],0);}memset(patterns,0,sizeof patterns);memset(delay,0,sizeof delay);atomic_store(&head,0);atomic_store(&tail,0);atomic_store(&frames,0);atomic_store(&xruns,0);atomic_store(&written,0);playing=0;step=-1;until_step=0;tempo=58;master=master_target=.28f;space=space_target=.35f;transport_gain=transport_target=1;stopping=0;delaypos=0;for(int t=0;t<TRACKS;t++){track_gain[t]=levels[t];atomic_store(&envelopes[t],0);atomic_store(&onsets[t],0);}}
