"""Dependency-free Studio integration check. Synthetic frames, not a robot benchmark."""
import argparse
import json
import os
from pathlib import Path
import struct
import time
import zlib


def frame(x):
    width, height = 320, 240
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for col in range(width):
            pixels.extend((80, 180, 240) if (col-x)**2+(y-120)**2 < 144 else (24, 30, 38))
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(pixels))+chunk(b'IEND', b'')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=8)
    parser.add_argument('--delay', type=float, default=1)
    args = parser.parse_args()
    output = Path(os.environ['LINKMIND_RUN_OUTPUT'])
    output.mkdir(parents=True, exist_ok=False)
    print('Studio 接入自检：合成画面，不是机器人评测', flush=True)
    for step in range(args.steps):
        temporary = output/'frame.tmp'
        temporary.write_bytes(frame(30+(step*17)%260))
        temporary.replace(output/'frame.png')
        print(f'frame {step+1}/{args.steps}', flush=True)
        time.sleep(args.delay)
    (output/'result.json').write_text(json.dumps({'kind':'studio-integration-check', 'frames':args.steps, 'benchmark':False}, indent=2))
    print('Finished; original JSON result saved.', flush=True)


if __name__ == '__main__':
    main()
