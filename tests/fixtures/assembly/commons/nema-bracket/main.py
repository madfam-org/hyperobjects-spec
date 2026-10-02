# Assembly-validator fixture. Never rendered: the validator reads only project.json
# and digests this directory (GOC-1 tree_sha256) for the component's instance_id.
import cadquery as cq

result = cq.Workplane("XY").box(42.3, 42.3, plate_thick)  # noqa: F821
