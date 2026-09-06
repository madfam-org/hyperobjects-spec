// Fixture: the `lever` mode.
//
// `lever_length` stands in for locking-mechanism-hyperobject.lever_length: it is scoped
// to this mode by `visible_in_modes` and it is USED here, so it is alive — even though
// no source of the `stand` mode mentions it. A rule that judged a parameter against
// every mode instead of the modes that list it would call this healthy parameter dead.

lever_length = 30;
render_mode = 1;
target_part = "lever";

module lever() {
    cube([lever_length, 6, 4], center = true);
}

lever();
