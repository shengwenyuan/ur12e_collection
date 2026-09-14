# Actual printed-board regression fixture

`printed-board.png` is the inspected 1400-pixel-high rendering of the user-supplied
`aprilgrid_Letter_tag36h11_4x6_28mm_actual_size.pdf` (source SHA-256
`8112bee13432c86b77a6914ec7141ded26e3c0604308dac3869f3678d164fe01`).
Its original embedded AprilRobotics license is reproduced in `LICENSE.txt`.

The original PDF, rather than the implementation's own board generator, is the
reference. All 24 tags are rotated 180 degrees relative to OpenCV's generated
markers. Decoded corners correspond to board bottom-right, bottom-left,
top-left, top-right. IDs ascend rightward and then upward from tag zero. This
fixture prevents a self-consistent synthetic generator from concealing a wrong
physical tag-corner convention. It is test data, not a physical accuracy result.
