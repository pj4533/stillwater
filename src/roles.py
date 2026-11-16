"""Stable V2 sound identities. Layer slots never determine role identity."""
ROLE_IDS=('silt','filament','glass','choir','oxide','backwash','spore','prism')
MACROS=(
 ('Bloom','Release','Shade','Hollow','Body','Sub','Rust','Space'),
 ('Pluck','Length','Position','Stiff','Echo','Return','Spread','Mist'),
 ('Ratio','Index','Bloom','Ring','Sweep','Motion','Depth','Phase'),
 ('Vowel','Breath','Throat','Focus','Bloom','Release','Drift','Ensemble'),
 ('Wear','Wow','Flutter','Echo','Return','Dropout','Width','Bloom'),
 ('Strike','Release','Reverse','Window','Seam','Echo','Return','Shade'),
 ('Bow','Tone','Grain','Density','Scatter','Memory','Width','Cloud'),
 ('Strike','Metal','Damping','Glow','Octave','Room','Diffuse','Shade'))
DEFAULTS=((.3,.5,.45,.2,.55,.3,.1,.25),(.6,.55,.3,.25,.2,.2,.4,.2),
 (.25,.3,.35,.6,.3,.2,.25,.25),(.35,.15,.5,.4,.4,.6,.15,.3),
 (.2,.15,.1,.3,.25,.05,.45,.45),(.5,.5,.5,.4,.6,.2,.2,.5),
 (.5,.45,.4,.25,.2,.3,.45,.3),(.5,.5,.6,.35,.2,.35,.45,.5))

# Explicit Push 3 hardware palette entries (bright, medium, dim). Never
# interpolate palette indices. Source: push-hack hardware_palette.go live dump.
ROLE_RGB=dict(zip(ROLE_IDS,((255,155,118),(255,220,59),(128,243,255),(187,170,242),
                          (217,175,113),(49,173,255),(124,221,159),(255,139,176))))
ROLE_PALETTE=dict(zip(ROLE_IDS,((37,65,66),(7,77,78),(46,93,94),(50,107,108),
                              (39,73,74),(16,95,96),(44,91,92),(52,111,112))))
