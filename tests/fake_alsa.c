/* Fault-injection ALSA shim: verifies nonblocking mode and bounded shutdown. */
#include <stdlib.h>
#include <unistd.h>
static int nonblocking;
int snd_pcm_open(void **p,const char *d,int s,int flags){(void)d;(void)s;*p=(void*)1;nonblocking=flags&1;return 0;}
int snd_pcm_set_params(void *p,int f,int a,unsigned c,unsigned r,int b,unsigned t){(void)p;(void)f;(void)a;(void)c;(void)r;(void)b;(void)t;return 0;}
int snd_pcm_nonblock(void *p,int on){(void)p;nonblocking=on;return 0;}
long snd_pcm_writei(void *p,const void *b,unsigned long n){
 (void)p;(void)b;(void)n;
 if(!nonblocking)abort();
 if(getenv("SW_TEST_BLOCK_FOREVER")){for(;;)sleep(10);}
 return -11;
}
int snd_pcm_prepare(void *p){(void)p;return 0;}
int snd_pcm_close(void *p){(void)p;return 0;}
