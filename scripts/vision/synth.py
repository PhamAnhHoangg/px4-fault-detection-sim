"""Synthetic camera frames with a known horizon, for testing horizon.py without a simulator.
make_frame(roll_deg, horizon_y): sky gradient, textured ground, noise and blur, optional clouds."""
import math
import cv2
import numpy as np


def make_frame(roll_deg, horizon_y, w=320, h=240, seed=0, clouds=True):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.tan(math.radians(roll_deg))
    line = horizon_y * h + a * (xx - w / 2)              # horizon row at each column
    sky = yy < line
    img = np.zeros((h, w, 3), np.float32)
    t = np.clip(yy / h, 0, 1)
    img[..., 0] = np.where(sky, 230 - 60 * t, 60)          # B
    img[..., 1] = np.where(sky, 190 - 40 * t, 110)         # G
    img[..., 2] = np.where(sky, 140 - 40 * t, 80)          # R
    tex = cv2.resize(rng.normal(0, 25, (h // 8, w // 8)).astype(np.float32), (w, h))
    img[~sky] += tex[~sky][:, None]
    if clouds:
        for _ in range(3):
            cx, cy = rng.integers(0, w), rng.integers(0, h)
            cv2.ellipse(img, (int(cx), int(cy)), (int(rng.integers(15, 40)), int(rng.integers(5, 12))), 0, 0, 360, (245, 245, 245), -1)
        img[~sky] = np.clip(img[~sky], 0, 255)             # clouds only matter in the sky
        g = ~sky
        base = np.zeros_like(img); base[..., 0], base[..., 1], base[..., 2] = 60, 110, 80
        img[g] = base[g] + tex[g][:, None]
    img += rng.normal(0, 6, img.shape)
    img = cv2.GaussianBlur(np.clip(img, 0, 255).astype(np.uint8), (3, 3), 0)
    return img
