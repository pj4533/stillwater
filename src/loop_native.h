/* Original Stillwater V2 event-loop foundation. Included by engine.c so the
 * existing ALSA/history/limiter remain the single output owner. No RT allocation. */
#define LP_TICKS ((uint64_t)(lp_song.loop_beats?lp_song.loop_beats:4)*96000)
#define LP_ABI 5
int sw_loop_abi(void){return LP_ABI;}
#define LP_EVENTS 256
#define LP_PLAYBACK 64
#define LP_ACKS 64
#define LP_BANKS 3
struct LoopEvent { uint64_t id; uint32_t start_tick,duration_tick; int32_t pitch; float velocity; };
struct LoopLayer { int32_t role,count; float level; int32_t muted,sound_version; float parameters[8]; struct LoopEvent events[LP_EVENTS]; };
struct SongBank { double tempo; float master; int32_t count,loop_beats,retire_mask; struct LoopLayer layers[8]; };
struct LoopTake { uint64_t id,epoch; uint32_t start_tick,duration_tick; int32_t layer,pitch,reason,status; float velocity; };
struct LoopSnapshot { uint64_t sample,origin,phase,cycle,loop_frames,epoch,generation,activity,boundary; double tempo,pending_tempo; int32_t transport,held,pending,captures,rejected,loop_beats,pending_beats; uint64_t op_token,ack_token; int32_t op_status; };
struct LoopCommand { int op,a,b,c,record; uint64_t id,epoch,generation,guard_epoch,guard_activity; float value; };
struct LoopHold { int token,layer,pitch,capture; uint64_t id,epoch,start; uint32_t start_tick; float velocity; };
struct LoopVoice { int active,layer,pitch,held,token,retiring; uint64_t id,deadline,age; double phase; float velocity,gain,pressure,target; };
static struct SongBank lp_song,lp_banks[LP_BANKS];
static _Atomic int lp_bank_state[LP_BANKS]; /* FREE0 WRITING1 READY2 */
static struct LoopCommand lp_commands[QSIZE];static _Atomic unsigned lp_head,lp_tail;
static struct LoopTake lp_takes[LP_ACKS];static _Atomic unsigned lp_take_head,lp_take_tail;
static _Atomic unsigned lp_credits;
static struct LoopHold lp_holds[8];static struct LoopVoice lp_manual[8],lp_manual_tail[8],lp_voices[LP_PLAYBACK];
static uint64_t lp_skip[8][LP_EVENTS];static unsigned lp_skip_count[8];
static uint32_t lp_cursor[8];static uint64_t lp_clock,lp_origin,lp_phase,lp_cycle,lp_length,lp_epoch=1,lp_generation,lp_activity,lp_boundary;
static int lp_enabled,lp_transport,lp_rejected;static double lp_tempo=58,lp_pending_tempo;
static _Atomic unsigned lp_snapshot_version;
static _Atomic uint64_t lp_snapshot_values[9];static _Atomic double lp_snapshot_tempo,lp_snapshot_pending;
static _Atomic int lp_snapshot_ints[8];
static _Atomic uint64_t lp_snapshot_tokens[2];
static struct LoopCommand lp_pending_op;static uint64_t lp_ack_token;static int lp_op_status;
static uint64_t lp_frames_for(double bpm){return (uint64_t)llround(44100.0*60*(lp_song.loop_beats?lp_song.loop_beats:4)/bpm);}
static uint32_t lp_to_tick(uint64_t frame){uint64_t tick=(frame*LP_TICKS+lp_length/2)/lp_length;return (uint32_t)(tick<LP_TICKS?tick:LP_TICKS-1);}
static uint64_t lp_to_frame(uint32_t tick){return ((uint64_t)tick*lp_length+LP_TICKS/2)/LP_TICKS;}
static int lp_enqueue(struct LoopCommand c){
 unsigned h=atomic_load_explicit(&lp_head,memory_order_relaxed),next=(h+1)%QSIZE;
 if(next==atomic_load_explicit(&lp_tail,memory_order_acquire))return -1;
 lp_commands[h]=c;atomic_store_explicit(&lp_head,next,memory_order_release);return 0;
}
/* All cross-thread cells are atomic; version guards coherence, never safety.
 * Publication is once per audio block, with no allocation or UI waiting. */
#define LP_PITCHES 73
struct PitchSnapshot { uint64_t epoch,reset; uint32_t enabled; uint64_t onset[8][LP_PITCHES]; uint32_t gate[8][LP_PITCHES]; };
static uint64_t lp_pitch_onset[8][LP_PITCHES],lp_pitch_reset;
static _Atomic uint64_t lp_pitch_epoch_out,lp_pitch_reset_out,lp_pitch_onset_out[8][LP_PITCHES];
static _Atomic uint32_t lp_pitch_enabled_out,lp_pitch_gate_out[8][LP_PITCHES];
static _Atomic unsigned lp_pitch_version;
static void lp_publish_pitches(void){
 uint32_t gates[8][LP_PITCHES]={{0}},enabled=0;
 for(int l=0;l<lp_song.count;l++)if(!lp_song.layers[l].muted&&lp_song.layers[l].level>0)enabled|=1u<<l;
 for(int i=0;i<LP_PLAYBACK;i++){struct LoopVoice *v=&lp_voices[i];if(v->active&&v->held&&!v->retiring&&(enabled&(1u<<v->layer)))gates[v->layer][v->pitch-24]|=2;}
 for(int i=0;i<8;i++){struct LoopVoice *v=&lp_manual[i];if(v->active&&v->held&&!v->retiring&&(enabled&(1u<<v->layer)))gates[v->layer][v->pitch-24]|=1;}
 atomic_fetch_add(&lp_pitch_version,1);
 atomic_store(&lp_pitch_epoch_out,lp_epoch);atomic_store(&lp_pitch_reset_out,lp_pitch_reset);atomic_store(&lp_pitch_enabled_out,enabled);
 for(int l=0;l<8;l++)for(int p=0;p<LP_PITCHES;p++){atomic_store(&lp_pitch_onset_out[l][p],lp_pitch_onset[l][p]);atomic_store(&lp_pitch_gate_out[l][p],gates[l][p]);}
 atomic_fetch_add(&lp_pitch_version,1);
}
int sw_loop_pitches(struct PitchSnapshot *out){
 if(!out)return -2;
 for(int attempt=0;attempt<3;attempt++){
  unsigned v=atomic_load(&lp_pitch_version);if(v&1)continue;
  struct PitchSnapshot s={.epoch=atomic_load(&lp_pitch_epoch_out),.reset=atomic_load(&lp_pitch_reset_out),.enabled=atomic_load(&lp_pitch_enabled_out)};
  for(int l=0;l<8;l++)for(int p=0;p<LP_PITCHES;p++){s.onset[l][p]=atomic_load(&lp_pitch_onset_out[l][p]);s.gate[l][p]=atomic_load(&lp_pitch_gate_out[l][p]);}
  if(v==atomic_load(&lp_pitch_version)){*out=s;return 0;}
 }return -1;
}
static void lp_publish_fx(void);
static void lp_snapshot(void){
 lp_publish_fx();lp_publish_pitches();
 int held=0,pending=0,count=0;
 for(int i=0;i<8;i++){held+=lp_holds[i].token!=0;pending+=lp_holds[i].capture;count+=lp_song.layers[i].count;}
 uint64_t vals[]={lp_clock,lp_origin,lp_phase,lp_cycle,lp_length,lp_epoch,lp_generation,lp_activity,lp_boundary};
 int ints[]={lp_transport,held,pending,count,lp_rejected,lp_song.loop_beats?lp_song.loop_beats:4,lp_pending_op.op?lp_banks[lp_pending_op.a].loop_beats:0,lp_op_status};
 atomic_fetch_add(&lp_snapshot_version,1);
 for(int i=0;i<9;i++)atomic_store(&lp_snapshot_values[i],vals[i]);
 for(int i=0;i<8;i++)atomic_store(&lp_snapshot_ints[i],ints[i]);
 atomic_store(&lp_snapshot_tokens[0],lp_pending_op.id);atomic_store(&lp_snapshot_tokens[1],lp_ack_token);
 atomic_store(&lp_snapshot_tempo,lp_tempo);atomic_store(&lp_snapshot_pending,lp_pending_tempo);
 atomic_fetch_add(&lp_snapshot_version,1);
}
int sw_loop_snapshot(struct LoopSnapshot *out){
 if(!out)return -2;
 for(int attempt=0;attempt<3;attempt++){
  unsigned v=atomic_load(&lp_snapshot_version);if(v&1)continue;
  uint64_t values[9];int ints[8];
  for(int i=0;i<9;i++)values[i]=atomic_load(&lp_snapshot_values[i]);
  for(int i=0;i<8;i++)ints[i]=atomic_load(&lp_snapshot_ints[i]);
  struct LoopSnapshot s={.sample=values[0],.origin=values[1],.phase=values[2],.cycle=values[3],.loop_frames=values[4],.epoch=values[5],.generation=values[6],.activity=values[7],.boundary=values[8],.tempo=atomic_load(&lp_snapshot_tempo),.pending_tempo=atomic_load(&lp_snapshot_pending),.transport=ints[0],.held=ints[1],.pending=ints[2],.captures=ints[3],.rejected=ints[4],.loop_beats=ints[5],.pending_beats=ints[6],.op_status=ints[7],.op_token=atomic_load(&lp_snapshot_tokens[0]),.ack_token=atomic_load(&lp_snapshot_tokens[1])};
  if(v==atomic_load(&lp_snapshot_version)){*out=s;return 0;}
 }return -1;
}
int sw_loop_transport(int action,int overdub,uint64_t epoch){
 if(action<0||action>2||(overdub!=0&&overdub!=1)||!epoch)return -2;
 return lp_enqueue((struct LoopCommand){.op=1,.a=action,.b=overdub,.epoch=epoch});
}
int sw_performance_on(int slot,int token,int layer,int pitch,float velocity,int record,uint64_t epoch,uint64_t id){
 if(slot<0||slot>=8||token<=0||layer<0||layer>=8||pitch<24||pitch>96||!isfinite(velocity)||velocity<=0||velocity>1||(record!=0&&record!=1)||!epoch||!id||id>UINT64_C(9007199254740991))return -2;
 int admitted=record;
 if(record){
  unsigned credits=atomic_load(&lp_credits);
  if(credits>=LP_ACKS-1)admitted=0;
  else {atomic_fetch_add(&lp_credits,1);}
 }
 int result=lp_enqueue((struct LoopCommand){.op=2,.a=slot,.b=token,.c=layer,.value=velocity,.record=record?(admitted?1:2):0,.epoch=epoch,.id=id,.generation=(uint64_t)pitch});
 if(result&&admitted){atomic_fetch_sub(&lp_credits,1);}
 return result?result:(record&&!admitted?1:0); /*1: queued as audition, capture not admitted */
}
int sw_loop_ready(void){
 unsigned h=atomic_load_explicit(&lp_head,memory_order_relaxed),t=atomic_load_explicit(&lp_tail,memory_order_acquire);
 unsigned room=(t+QSIZE-h-1)%QSIZE;int bank=0;
 for(int i=0;i<LP_BANKS;i++)bank|=atomic_load_explicit(&lp_bank_state[i],memory_order_acquire)==0;
 return room>=16&&bank;
}
int sw_performance_off(int slot,int token){if(slot<0||slot>=8||token<=0)return -2;return lp_enqueue((struct LoopCommand){.op=3,.a=slot,.b=token});}
int sw_performance_pressure(int slot,int token,float value){if(slot<0||slot>=8||token<=0||!isfinite(value)||value<0||value>1)return -2;return lp_enqueue((struct LoopCommand){.op=4,.a=slot,.b=token,.value=value});}
int sw_layer_parameter(int layer,int param,float value){
 if(layer<0||layer>=8||param<0||param>9||!isfinite(value)||value<0||value>1)return -2;
 return lp_enqueue((struct LoopCommand){.op=5,.a=layer,.b=param,.value=value}); /*8 level,9 mute */
}
int sw_loop_master(float value){if(!isfinite(value)||value<0||value>1)return -2;return lp_enqueue((struct LoopCommand){.op=8,.value=value});}
int sw_loop_tempo(double value){if(!isfinite(value)||value<30||value>160)return -2;return lp_enqueue((struct LoopCommand){.op=6,.value=(float)value});}
int sw_take_poll(struct LoopTake *out,int capacity){
 if(!out||capacity<1||capacity>LP_ACKS)return -2;
 unsigned t=atomic_load_explicit(&lp_take_tail,memory_order_relaxed),h=atomic_load_explicit(&lp_take_head,memory_order_acquire);int count=0;
 while(t!=h&&count<capacity){out[count++]=lp_takes[t];t=(t+1)%LP_ACKS;}
 atomic_store_explicit(&lp_take_tail,t,memory_order_release);atomic_fetch_sub(&lp_credits,(unsigned)count);return count;
}
static int lp_valid_bank(const struct SongBank *bank){
 if(!bank||!isfinite(bank->tempo)||bank->tempo<30||bank->tempo>160||!isfinite(bank->master)||bank->master<0||bank->master>1||bank->count<1||bank->count>8||bank->loop_beats<4||bank->loop_beats>32||bank->loop_beats%4||bank->retire_mask<0||bank->retire_mask>255)return 0;
 unsigned roles=0;
 for(int l=0;l<bank->count;l++){
  const struct LoopLayer *layer=&bank->layers[l];
  if((layer->sound_version!=1&&layer->sound_version!=2)||layer->role<0||layer->role>7||(roles&(1u<<layer->role))||layer->count<0||layer->count>LP_EVENTS||!isfinite(layer->level)||layer->level<0||layer->level>1||(layer->muted!=0&&layer->muted!=1))return 0;
  roles|=1u<<layer->role;
  for(int p=0;p<8;p++)if(!isfinite(layer->parameters[p])||layer->parameters[p]<0||layer->parameters[p]>1)return 0;
  for(int e=0;e<layer->count;e++){
   const struct LoopEvent *event=&layer->events[e];
   if(!event->id||event->id>UINT64_C(9007199254740991)||event->start_tick>=(uint64_t)bank->loop_beats*96000||!event->duration_tick||event->duration_tick>(uint64_t)bank->loop_beats*96000||event->pitch<24||event->pitch>96||!isfinite(event->velocity)||event->velocity<=0||event->velocity>1)return 0;
   if(e&&(layer->events[e-1].start_tick>event->start_tick||(layer->events[e-1].start_tick==event->start_tick&&layer->events[e-1].id>=event->id)))return 0;
   for(int a=0;a<=l;a++)for(int b=0;b<(a==l?e:bank->layers[a].count);b++)if(bank->layers[a].events[b].id==event->id)return 0;
  }
 }return 1;
}
int sw_song_publish(const struct SongBank *bank,uint64_t generation,uint64_t epoch){
 if(!generation||!epoch||!lp_valid_bank(bank))return -2;
 for(int i=0;i<LP_BANKS;i++){
  int expected=0;
  if(atomic_compare_exchange_strong(&lp_bank_state[i],&expected,1)){
   memcpy(&lp_banks[i],bank,sizeof *bank);atomic_store_explicit(&lp_bank_state[i],2,memory_order_release);
   int result=lp_enqueue((struct LoopCommand){.op=7,.a=i,.generation=generation,.epoch=epoch});
   if(result)atomic_store(&lp_bank_state[i],0);
   return result;
  }
 }return -1;
}
/* Guarded structural bank. Acknowledgment is published with the coherent
 * snapshot; the UI must resolve it before admitting another musical command. */
int sw_song_stage(const struct SongBank *bank,uint64_t generation,uint64_t epoch,uint64_t token,uint64_t guard_epoch,uint64_t guard_activity){
 if(!generation||!epoch||!token||!lp_valid_bank(bank))return -2;
 for(int i=0;i<LP_BANKS;i++){
  int expected=0;
  if(atomic_compare_exchange_strong(&lp_bank_state[i],&expected,1)){
   memcpy(&lp_banks[i],bank,sizeof *bank);atomic_store_explicit(&lp_bank_state[i],2,memory_order_release);
   int result=lp_enqueue((struct LoopCommand){.op=9,.a=i,.generation=generation,.epoch=epoch,.id=token,.guard_epoch=guard_epoch,.guard_activity=guard_activity});
   if(result)atomic_store(&lp_bank_state[i],0);
   return result;
  }
 }return -1;
}
int sw_song_cancel(uint64_t token){if(!token)return -2;return lp_enqueue((struct LoopCommand){.op=10,.id=token});}
static void lp_set_cursor(int after){
 for(int l=0;l<8;l++){
  lp_cursor[l]=0;
  while(lp_cursor[l]<(unsigned)lp_song.layers[l].count&&lp_to_frame(lp_song.layers[l].events[lp_cursor[l]].start_tick)<lp_phase+(after?1:0))lp_cursor[l]++;
 }
}
static void lp_finish(int slot,int reason){
 struct LoopHold *hold=&lp_holds[slot];
 if(hold->capture){
  uint64_t age=lp_clock-hold->start;if(!age)age=1;if(age>lp_length)age=lp_length;
  uint32_t duration=(uint32_t)((age*LP_TICKS+lp_length/2)/lp_length);if(!duration)duration=1;
  struct LoopEvent event={hold->id,hold->start_tick,duration,hold->pitch,hold->velocity};
  struct LoopLayer *layer=&lp_song.layers[hold->layer];int index=layer->count;
  /* Publication reserves these slots; fail closed if that invariant breaks. */
  int full=index>=LP_EVENTS;
  if(!full){
  while(index>0&&(layer->events[index-1].start_tick>event.start_tick||(layer->events[index-1].start_tick==event.start_tick&&layer->events[index-1].id>event.id))){layer->events[index]=layer->events[index-1];index--;}
  layer->events[index]=event;layer->count++;
  if(lp_to_frame(event.start_tick)==lp_phase&&lp_skip_count[hold->layer]<LP_EVENTS)lp_skip[hold->layer][lp_skip_count[hold->layer]++]=event.id;
  lp_set_cursor(0);
  }else lp_rejected++;
  unsigned h=atomic_load_explicit(&lp_take_head,memory_order_relaxed);
  lp_takes[h]=(struct LoopTake){.id=hold->id,.epoch=hold->epoch,.start_tick=event.start_tick,.duration_tick=duration,.layer=hold->layer,.pitch=hold->pitch,.reason=reason,.status=full,.velocity=hold->velocity};
  atomic_store_explicit(&lp_take_head,(h+1)%LP_ACKS,memory_order_release);
 }
 lp_activity++;hold->capture=0;hold->token=0;lp_manual[slot].held=0;lp_manual[slot].token=0;
}
static void lp_cancel_holds(void){
 for(int i=0;i<8;i++){
  if(lp_holds[i].capture)atomic_fetch_sub(&lp_credits,1);
  lp_holds[i]=(struct LoopHold){0};lp_manual[i].held=0;lp_manual[i].token=0;
 }
}
static int lp_contains(uint64_t id,int layer){
 if(layer>=lp_song.count)return 0;
 for(int e=0;e<lp_song.layers[layer].count;e++)if(lp_song.layers[layer].events[e].id==id)return 1;
 return 0;
}
/* Same-epoch publication is additive: the audio-owned event set survives even
 * after the UI consumes acknowledgements. Deletion requires a new epoch. The
 * READY mailbox is scratch space; rejection never changes the live song. */
static int lp_merge_native(struct SongBank *bank){
 for(int l=0;l<lp_song.count;l++){
  if(l>=bank->count)return 0;
  for(int e=0;e<lp_song.layers[l].count;e++){
   struct LoopEvent event=lp_song.layers[l].events[e];int found=0;
   int lo=0,hi=bank->layers[l].count;
   while(lo<hi){int mid=(lo+hi)/2;struct LoopEvent *candidate=&bank->layers[l].events[mid];
    if(candidate->start_tick<event.start_tick||(candidate->start_tick==event.start_tick&&candidate->id<event.id))lo=mid+1;else hi=mid;
   }
   if(lo<bank->layers[l].count&&bank->layers[l].events[lo].id==event.id){
    if(memcmp(&bank->layers[l].events[lo],&event,sizeof event))return 0;
    found=1;
   }
   if(!found)for(int a=0;a<bank->count;a++)for(int b=0;b<bank->layers[a].count;b++)if(bank->layers[a].events[b].id==event.id)return 0;
   if(!found){
    struct LoopLayer *layer=&bank->layers[l];if(layer->count>=LP_EVENTS)return 0;
    int index=layer->count++;
    while(index>0&&(layer->events[index-1].start_tick>event.start_tick||(layer->events[index-1].start_tick==event.start_tick&&layer->events[index-1].id>event.id))){layer->events[index]=layer->events[index-1];index--;}
    layer->events[index]=event;
   }
  }
 }
 /* Every admitted active capture retains a distinct completion slot. */
 for(int l=0;l<bank->count;l++){
  int used=bank->layers[l].count;
  for(int i=0;i<8;i++)if(lp_holds[i].capture&&lp_holds[i].layer==l){
   for(int a=0;a<bank->count;a++)for(int b=0;b<bank->layers[a].count;b++)if(bank->layers[a].events[b].id==lp_holds[i].id)return 0;
   used++;
  }
  if(used>LP_EVENTS)return 0;
 }
 return 1;
}
#include "loop_dsp.h"
static void lp_publish_fx(void){
 for(int l=0;l<8;l++)for(int m=0;m<3;m++)atomic_store(&lp_fx[l][m],lp_fx_values[l][m]);
 if(lp_enabled)for(int i=0;i<8;i++){
  atomic_fetch_add(&manual_versions[i],1);atomic_store(&manual_tracks[i],lp_manual[i].layer);
  atomic_store(&manual_tokens[i],lp_manual[i].token);atomic_store(&manual_held[i],lp_manual[i].held&&lp_manual[i].active);
  atomic_store(&manual_env[i],lp_manual[i].active?lp_manual[i].gain:0);atomic_store(&manual_pressure[i],lp_manual[i].pressure);atomic_fetch_add(&manual_versions[i],1);
 }
}
static void lp_apply_retire(const struct SongBank *bank);
static int lp_guard(struct LoopCommand c){
 if(c.guard_epoch!=lp_epoch||c.guard_activity!=lp_activity||c.epoch<=lp_epoch||c.generation<=lp_generation||lp_pending_tempo||atomic_load(&lp_credits))return 0;
 for(int i=0;i<8;i++)if(lp_holds[i].token)return 0;
 return 1;
}
static void lp_resolve_op(int apply){
 struct LoopCommand c=lp_pending_op;if(!c.op)return;
 if(apply&&lp_guard(c)){
  memset(lp_pitch_onset,0,sizeof lp_pitch_onset);lp_apply_retire(&lp_banks[c.a]);
  lp_song=lp_banks[c.a];lp_epoch=c.epoch;lp_generation=c.generation;lp_tempo=lp_song.tempo;lp_pending_tempo=0;lp_length=lp_frames_for(lp_tempo);lp_activity++;
  master_target=lp_song.master;
  for(int l=0;l<8;l++)levels[l]=l<lp_song.count&&!lp_song.layers[l].muted?lp_song.layers[l].level:0;
  lp_set_cursor(0);lp_op_status=1;
 }else lp_op_status=-1;
 lp_ack_token=c.id;atomic_store(&lp_bank_state[c.a],0);lp_pending_op=(struct LoopCommand){0};
}
static void lp_retire_layer(int l){
 for(int i=0;i<LP_PLAYBACK;i++)if(lp_voices[i].active&&lp_voices[i].layer==l){lp_voices[i].held=0;lp_voices[i].retiring=441;}
 for(int i=0;i<8;i++){
  if(lp_manual[i].active&&lp_manual[i].layer==l){lp_manual[i].held=0;lp_manual[i].retiring=441;}
  if(lp_manual_tail[i].active&&lp_manual_tail[i].layer==l){lp_manual_tail[i].held=0;lp_manual_tail[i].retiring=441;}
 }
 lp_bus[l].era++;lp_bus[l].frozen=0;lp_bus[l].env=lp_env[l]=0;
 memset(lp_bus[l].grains,0,sizeof lp_bus[l].grains);memset(lp_bus[l].ap,0,sizeof lp_bus[l].ap);memset(lp_bus[l].low,0,sizeof lp_bus[l].low);
 lp_bus[l].fade=441;
}
static void lp_apply_retire(const struct SongBank *bank){
 for(int l=0;l<lp_song.count;l++){
     int changed=(bank->retire_mask&(1<<l))||l>=bank->count||lp_song.layers[l].role!=bank->layers[l].role;
     for(int e=0;e<lp_song.layers[l].count&&!changed;e++){
      struct LoopEvent old=lp_song.layers[l].events[e];int found=0;
      for(int n=0;n<bank->layers[l].count;n++)if(old.id==bank->layers[l].events[n].id&&old.pitch==bank->layers[l].events[n].pitch)found=1;
      if(!found)changed=1;
     }
     if(changed)lp_retire_layer(l);
    }
}
static void lp_process(void){
 unsigned t=atomic_load_explicit(&lp_tail,memory_order_relaxed),h=atomic_load_explicit(&lp_head,memory_order_acquire);
 while(t!=h){
  struct LoopCommand c=lp_commands[t];
  if(c.op==10){if(lp_pending_op.op&&lp_pending_op.id==c.id)lp_resolve_op(0);}
  if(c.op==9){
   if(lp_pending_op.op||!lp_guard(c)){lp_ack_token=c.id;lp_op_status=-1;atomic_store(&lp_bank_state[c.a],0);}
   else {lp_pending_op=c;lp_op_status=0;if(lp_transport!=2)lp_resolve_op(1);}
  }
  if(c.op==7&&atomic_load_explicit(&lp_bank_state[c.a],memory_order_acquire)==2){
   if(c.generation<=lp_generation||c.epoch<lp_epoch){atomic_store(&lp_bank_state[c.a],0);t=(t+1)%QSIZE;continue;}
   if(c.epoch==lp_epoch&&!lp_merge_native(&lp_banks[c.a])){atomic_store(&lp_bank_state[c.a],0);lp_rejected++;t=(t+1)%QSIZE;continue;}
   if(c.epoch!=lp_epoch){
    memset(lp_pitch_onset,0,sizeof lp_pitch_onset);
    lp_cancel_holds();memset(lp_skip_count,0,sizeof lp_skip_count);
    lp_apply_retire(&lp_banks[c.a]);
   }
   for(int l=lp_song.count;l<lp_banks[c.a].count;l++)memcpy(lp_bus[l].p,lp_banks[c.a].layers[l].parameters,sizeof lp_bus[l].p);
   int length_changed=lp_song.loop_beats!=lp_banks[c.a].loop_beats;
   lp_song=lp_banks[c.a];atomic_store(&lp_bank_state[c.a],0);lp_enabled=1;
   lp_epoch=c.epoch;lp_generation=c.generation;lp_activity++;
   if(lp_transport==2)lp_pending_tempo=lp_tempo!=lp_song.tempo?lp_song.tempo:0;
   else {lp_tempo=lp_song.tempo;lp_pending_tempo=0;lp_length=lp_frames_for(lp_tempo);}
   if(length_changed){lp_length=lp_frames_for(lp_tempo);if(lp_phase>=lp_length)lp_phase=0;}
   master_target=lp_song.master;
   for(int l=0;l<8;l++){levels[l]=l<lp_song.count&&!lp_song.layers[l].muted?lp_song.layers[l].level:0;}
   for(int i=0;i<LP_PLAYBACK;i++)if(lp_voices[i].active&&!lp_contains(lp_voices[i].id,lp_voices[i].layer))lp_voices[i].held=0;
   lp_set_cursor(0);
  }
  if(c.op==1){
   if(lp_pending_op.op)lp_resolve_op(0);
   lp_activity++;
   if(c.a==0){lp_pitch_reset++;memset(lp_pitch_onset,0,sizeof lp_pitch_onset);for(int i=0;i<8;i++)if(lp_holds[i].token)lp_finish(i,2);for(int i=0;i<LP_PLAYBACK;i++)lp_voices[i].held=0;lp_transport=0;lp_tempo=lp_song.tempo;lp_pending_tempo=0;lp_length=lp_frames_for(lp_tempo);transport_target=0;stopping=1;}
   else {lp_epoch=c.epoch;lp_transport=c.a;
    if(c.a==1)for(int l=0;l<lp_song.count;l++)if(lp_song.layers[l].count)lp_transport=2;
    lp_origin=lp_clock;lp_phase=lp_cycle=0;lp_boundary=lp_clock;lp_set_cursor(0);transport_target=1;stopping=0;}
  }
  if(c.op==2){
   if(c.epoch!=lp_epoch||c.c>=lp_song.count){
    if(c.record==1)atomic_fetch_sub(&lp_credits,1);
   }else{
    if(lp_holds[c.a].token)lp_finish(c.a,1);
    if(lp_transport==1){lp_transport=2;lp_origin=lp_clock;lp_phase=lp_cycle=0;lp_boundary=lp_clock;lp_set_cursor(0);}
    /* Record intent belongs to this onset, not a stale Play-time mode. */
    int capture=c.record==1&&lp_transport==2;
    int layer_used=lp_song.layers[c.c].count;
    for(int i=0;i<8;i++)if(lp_holds[i].capture&&lp_holds[i].layer==c.c)layer_used++;
    int duplicate=0;
    for(int l=0;l<lp_song.count;l++)if(lp_contains(c.id,l))duplicate=1;
    for(int i=0;i<8;i++)if(lp_holds[i].capture&&lp_holds[i].id==c.id)duplicate=1;
    if(capture&&(layer_used>=LP_EVENTS||duplicate)){
     unsigned next=atomic_load_explicit(&lp_take_head,memory_order_relaxed);
     lp_takes[next]=(struct LoopTake){.id=c.id,.epoch=c.epoch,.layer=c.c,.status=1};
     atomic_store_explicit(&lp_take_head,(next+1)%LP_ACKS,memory_order_release);
     capture=0;lp_rejected++;
    }else if(c.record==1&&!capture)atomic_fetch_sub(&lp_credits,1);
    if(c.record==2)lp_rejected++;
    lp_holds[c.a]=(struct LoopHold){.token=c.b,.layer=c.c,.pitch=(int)c.generation,.capture=capture,.id=c.id,.epoch=c.epoch,.start=lp_clock,.start_tick=lp_to_tick(lp_phase),.velocity=c.value};
    lp_manual_tail[c.a]=lp_manual[c.a];lp_dsp[LP_PLAYBACK+8+c.a]=lp_dsp[LP_PLAYBACK+c.a];lp_manual_tail[c.a].held=0;
    lp_manual[c.a]=(struct LoopVoice){.active=1,.layer=c.c,.pitch=(int)c.generation,.held=1,.token=c.b,.velocity=c.value,.id=c.id};
    if(!lp_song.layers[c.c].muted&&lp_song.layers[c.c].level>0)lp_pitch_onset[c.c][c.generation-24]++;
    lp_voice_init(&lp_manual[c.a],LP_PLAYBACK+c.a);transport_target=1;stopping=0;lp_activity++;atomic_fetch_add(&onsets[c.c],1);
   }
  }
  if(c.op==3&&lp_holds[c.a].token==c.b)lp_finish(c.a,0);
  if(c.op==4&&lp_manual[c.a].token==c.b&&lp_manual[c.a].held)lp_manual[c.a].target=c.value;
  if(c.op==5&&c.a<lp_song.count){
   if(c.b<8)lp_song.layers[c.a].parameters[c.b]=c.value;
   if((c.b==8&&c.value==0)||(c.b==9&&c.value>=.5f)){lp_pitch_reset++;memset(lp_pitch_onset,0,sizeof lp_pitch_onset);}
   if(c.b==8)lp_song.layers[c.a].level=c.value;
   if(c.b==9)lp_song.layers[c.a].muted=c.value>=.5f;
   levels[c.a]=lp_song.layers[c.a].muted?0:lp_song.layers[c.a].level;lp_activity++;
  }
  if(c.op==8){lp_song.master=c.value;master_target=c.value;lp_activity++;}
  if(c.op==6){lp_song.tempo=c.value;if(lp_transport==2)lp_pending_tempo=lp_tempo!=c.value?c.value:0;else{lp_tempo=c.value;lp_pending_tempo=0;lp_length=lp_frames_for(lp_tempo);}lp_activity++;}
  t=(t+1)%QSIZE;
 }atomic_store_explicit(&lp_tail,t,memory_order_release);
}
static void lp_trigger(int layer,const struct LoopEvent *event){
 if(!lp_song.layers[layer].muted&&lp_song.layers[layer].level>0)lp_pitch_onset[layer][event->pitch-24]++;
 int slot=0;
 for(int i=0;i<LP_PLAYBACK;i++){if(!lp_voices[i].active){slot=i;break;}if(lp_voices[i].age>lp_voices[slot].age)slot=i;}
 uint64_t duration=lp_to_frame(event->duration_tick);if(!duration)duration=1;
 lp_voices[slot]=(struct LoopVoice){.active=1,.layer=layer,.pitch=event->pitch,.held=1,.id=event->id,.velocity=event->velocity,.deadline=lp_clock+duration};
 lp_voice_init(&lp_voices[slot],slot);atomic_fetch_add(&onsets[layer],1);
}
static void lp_sample(float *left,float *right){
 if(lp_enabled){
  if(lp_transport==2){
   for(int i=0;i<8;i++)if(lp_holds[i].token&&lp_clock-lp_holds[i].start>=lp_length)lp_finish(i,3);
   if(lp_phase>=lp_length){
    for(int i=0;i<8;i++)if(lp_holds[i].capture&&lp_pending_tempo)lp_finish(i,4);
    lp_phase=0;lp_cycle++;lp_boundary=lp_clock;
    if(lp_pending_op.op)lp_resolve_op(1);
    if(lp_pending_tempo){lp_tempo=lp_pending_tempo;lp_pending_tempo=0;lp_length=lp_frames_for(lp_tempo);}
    lp_set_cursor(0);
   }
   for(int l=0;l<lp_song.count;l++)while(lp_cursor[l]<(unsigned)lp_song.layers[l].count&&lp_to_frame(lp_song.layers[l].events[lp_cursor[l]].start_tick)<=lp_phase){
    const struct LoopEvent *event=&lp_song.layers[l].events[lp_cursor[l]++];int skip=0;
    for(unsigned i=0;i<lp_skip_count[l];i++)if(lp_skip[l][i]==event->id)skip=1;
    if(!skip)lp_trigger(l,event);
   }
   atomic_store(&position,(int)(lp_phase*8/lp_length));
  }
  float buses[8]={0};
  for(int i=0;i<LP_PLAYBACK;i++){if(lp_voices[i].held&&lp_clock>=lp_voices[i].deadline)lp_voices[i].held=0;if(lp_voices[i].active){int retiring=lp_voices[i].retiring;float v=lp_voice_sound(&lp_voices[i],i);if(retiring){*left+=v*track_gain[lp_voices[i].layer];*right+=v*track_gain[lp_voices[i].layer];}else buses[lp_voices[i].layer]+=v;}}
  for(int i=0;i<8;i++){
   if(lp_manual[i].active){int retiring=lp_manual[i].retiring;float v=lp_voice_sound(&lp_manual[i],LP_PLAYBACK+i);if(retiring){*left+=v*track_gain[lp_manual[i].layer];*right+=v*track_gain[lp_manual[i].layer];}else buses[lp_manual[i].layer]+=v;}
   if(lp_manual_tail[i].active){int retiring=lp_manual_tail[i].retiring;float v=lp_voice_sound(&lp_manual_tail[i],LP_PLAYBACK+8+i);if(retiring){*left+=v*track_gain[lp_manual_tail[i].layer];*right+=v*track_gain[lp_manual_tail[i].layer];}else buses[lp_manual_tail[i].layer]+=v;}
  }
  for(int l=0;l<lp_song.count;l++)lp_effect(l,buses[l],left,right);
  if(lp_transport==2)lp_phase++;
 }memset(lp_skip_count,0,sizeof lp_skip_count);lp_clock++;
}
static void lp_reset(void){
 lp_pitch_reset++;memset(lp_pitch_onset,0,sizeof lp_pitch_onset);
 lp_pending_op=(struct LoopCommand){0};lp_ack_token=0;lp_op_status=0;
 lp_dsp_reset();memset(lp_skip_count,0,sizeof lp_skip_count);memset(&lp_song,0,sizeof lp_song);memset(lp_holds,0,sizeof lp_holds);memset(lp_manual,0,sizeof lp_manual);memset(lp_manual_tail,0,sizeof lp_manual_tail);memset(lp_voices,0,sizeof lp_voices);memset(lp_cursor,0,sizeof lp_cursor);
 atomic_store(&lp_head,0);atomic_store(&lp_tail,0);atomic_store(&lp_take_head,0);atomic_store(&lp_take_tail,0);atomic_store(&lp_credits,0);
 for(int i=0;i<LP_BANKS;i++)atomic_store(&lp_bank_state[i],0);
 lp_clock=lp_origin=lp_phase=lp_cycle=lp_generation=lp_activity=lp_boundary=0;lp_epoch=1;lp_tempo=58;lp_length=lp_frames_for(58);lp_pending_tempo=0;lp_enabled=lp_transport=lp_rejected=0;lp_snapshot();
}

static void lp_prepare(void){lp_reset();}
