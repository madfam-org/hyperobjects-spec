// The OpenSCAD half of a dual-engine fixture. Its whole job is to model EXACTLY the
// same solid as block.py so the parity pass has a pair that genuinely agrees — a
// centred cube, no curves, so the two kernels produce the same AABB and the same
// volume with no chord error to explain away.
//
// Both `render_mode` (what the platform sends for a part whose manifest declares one)
// and `target_part` (what a cartridge dispatching by name reads) are honoured, as in
// the scad-block fixture, because the renderer passes both.

block_size = 10;
plate_h = 2;
render_mode = 0;
target_part = "block";

module plain_block() {
    cube([block_size, block_size, block_size], center = true);
}

module plate() {
    cube([block_size * 2, block_size * 2, plate_h], center = true);
}

if (render_mode == 2 || target_part == "plate") {
    plate();
} else {
    plain_block();
}
