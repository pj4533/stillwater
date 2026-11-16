#include "../src/engine.c"
#include <assert.h>
int main(void){
 float out[512];sw_reset();struct SongBank b={.tempo=58,.master=.1,.count=1};b.layers[0].level=.3;
 assert(!sw_song_publish(&b,1,1));sw_render(out,1);assert(!sw_loop_transport(1,1,1));
 for(int i=0;i<8;i++)assert(!sw_performance_on(i,i+1,0,62,.5,1,1,i+1));
 sw_render(out,256);
 b.layers[0].count=256;
 for(int i=0;i<256;i++)b.layers[0].events[i]=(struct LoopEvent){.id=i+1000,.start_tick=i*5000,.duration_tick=10,.pitch=62,.velocity=.5};
 assert(!sw_song_publish(&b,2,1));sw_render(out,1);assert(lp_generation==1);
 b.layers[0].count=248;assert(!sw_song_publish(&b,3,1));sw_render(out,1);assert(lp_generation==3);
 for(int i=0;i<8;i++)assert(!sw_performance_off(i,i+1));
 sw_render(out,1);assert(lp_song.layers[0].count==256);
 struct LoopTake takes[64];assert(sw_take_poll(takes,64)==8);return 0;
}
