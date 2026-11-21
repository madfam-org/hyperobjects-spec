// A deliberately tiny OpenSCAD cartridge: the integration test's whole job is to prove
// the RUNNER works (command shape, OPENSCADPATH, STL back through the mesh bar), so the
// geometry is the simplest thing that can be watertight and have positive volume.
//
// It dispatches on BOTH the numeric render_mode (what the platform sends for a part
// whose manifest declares one) and the target_part string (what a cartridge that
// dispatches by name reads), because the renderer passes both and a fixture that
// exercises only one would not notice if the other stopped being sent.

block_size = 10;
hole_d = 3;
render_mode = 0;
target_part = "block";

module plain_block() {
    cube([block_size, block_size, block_size], center = true);
}

module drilled_block() {
    difference() {
        plain_block();
        cylinder(h = block_size * 2, d = hole_d, center = true, $fn = 32);
    }
}

if (render_mode == 2 || target_part == "drilled") {
    drilled_block();
} else {
    plain_block();
}
