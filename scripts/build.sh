#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p .build
if [ "${1:-}" = device ]; then
  "${ZIG:-zig}" cc -target x86_64-linux-gnu.2.35 -std=c11 -Wall -Wextra -Werror -O2 -shared -fPIC src/engine.c -o .build/engine-device.so -lm -lpthread -ldl
  readelf -V .build/engine-device.so | sed -n '/Version needs section/,$p'
else
  gcc -std=c11 -O2 -Wall -Wextra -Werror -shared -fPIC src/engine.c -o .build/engine.so -lm -lpthread -ldl
fi
