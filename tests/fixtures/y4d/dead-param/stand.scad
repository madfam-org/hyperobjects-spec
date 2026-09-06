// Fixture: the OpenSCAD half of the `stand` mode.
//
// Every parameter the platform passes arrives as `-D name=value`, which OVERRIDES the
// declaration below. OpenSCAD accepts a `-D` for a name the file never mentions in
// silence, so a declaration with no corresponding USE is a slider that moves nothing —
// which is exactly what `phone_angle` is here, standing in for portacosas.

base_w = 40;        // ALIVE: declared here, used in the module below.
phone_angle = 65;   // DEAD: portacosas.phone_angle — this line and nowhere else.
mat_width = 50;     // DEAD: framing-hyperobject.mat_width — and absent from stand.py.
render_mode = 0;
target_part = "stand";

module stand() {
    // `base_w` is read here: that is what makes it a reference and not a declaration.
    cube([base_w, base_w, 4], center = true);
}

stand();
