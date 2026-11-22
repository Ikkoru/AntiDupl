"""A folder of many small distinct pictures, so that a search's keypoint
estimate at the highest level exceeds the free memory.

    py -3 many_images.py <folder> <count>
"""
import os
import random
import sys

from PIL import Image

folder, count = sys.argv[1], int(sys.argv[2])
os.makedirs(folder, exist_ok=True)
rng = random.Random(1)
for i in range(count):
    path = os.path.join(folder, f"{i:05d}.png")
    if os.path.exists(path):
        continue
    im = Image.new("L", (48, 48))
    im.putdata([rng.randrange(256) for _ in range(48 * 48)])
    im.save(path)
