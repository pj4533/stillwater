#include "../src/engine.c"
#include <assert.h>
int main(void){
 const float p[8][8]={{.72,.78,.86,.72,.12,.22,.015,.70},{.40,.90,.50,.25,.65,.65,.60,.70},{.05,.06,.80,.75,.35,.18,.50,.50},{.08,.06,.12,.20,.80,.80,.25,.70},{.08,.20,.06,.65,.60,0,.55,.80},{.12,.80,.62,.60,.80,.65,.60,.86},{.22,.28,.62,.50,.28,.55,.62,.75},{.12,.10,.25,.38,.20,.70,.70,.86}};
 const float attack[8]={.24828,.0296,.34,.424,.424,.104928,.26294,.077696};
 const float release[8]={.49546,.768,.57,.82,.55,.632,.6,.4875};
 float out[512];
 for(int r=0;r<8;r++){
  sw_reset();struct SongBank b={.loop_beats=4,.tempo=60,.master=.28,.count=1};
  b.layers[0].role=r;b.layers[0].level=.3;b.layers[0].sound_version=2;memcpy(b.layers[0].parameters,p[r],sizeof p[r]);
  assert(!sw_song_publish(&b,1,1));sw_render(out,1);
  assert(!sw_performance_on(0,1,0,62,.6,0,1,1));
  int n=(int)roundf(SR*attack[r]);for(int i=0;i<n;i++)sw_render(out,1);
  assert(fabsf(lp_manual[0].gain-(1-expf(-1)))<.002f);
  assert(!sw_performance_off(0,1));float initial=lp_manual[0].gain;
  n=(int)roundf(SR*release[r]);for(int i=0;i<n;i++)sw_render(out,1);
  assert(fabsf(lp_manual[0].gain/initial-expf(-1))<.002f);
  assert(!sw_loop_transport(0,1,1));for(int i=0;i<80;i++)sw_render(out,256);
  for(int i=0;i<512;i++)assert(out[i]==0);
 }
 return 0;
}
