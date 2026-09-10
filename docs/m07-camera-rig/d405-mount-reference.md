# D405 Mount Reference

The user asked whether D405 can center its stereo view automatically or whether
the adapter should account for a 9 mm lateral offset.

The official D400 datasheet defines the depth X-Y origin at the left imager,
not halfway between the stereo pair. For D405, Table 4-22 specifies 9 mm from
the centerline of the 1/4-20 tripod mounting hole to that imager. Its stereo
baseline is 18 mm. The official D405 ROS description likewise models a nominal
9 mm lateral mount-to-depth offset, an 18 mm stereo separation and zero nominal
color-to-depth translation. Use actual device calibration for camera transforms;
these CAD dimensions do not replace hand-eye calibration.

For a mount intended to place the depth/color optical axis on the gripper's
center plane, compensate this nominal 9 mm mechanically. Choose the direction
from the installed camera orientation and the official drawing, not from the
ambiguous phrase "move left". If using different attachment holes, establish
their relation to the documented tripod-hole datum first. A small adjustment
slot is useful for assembly and framing, subject to maintaining rigid mounting.
The required tilt and clearance remain separate mechanical decisions.

Image alignment, rectification or self-calibration does not physically move the
optical origin to the stereo midpoint. Software can express points in a central
coordinate frame, but that is a coordinate transform; rendering a virtual
central viewpoint requires reprojection and may introduce occlusion holes.
It is unnecessary for the raw collection pipeline. Mechanical centering is a
framing preference, not a prerequisite for valid calibrated RGB-D capture.

Sources checked on 2026-09-10:

- `d400_datasheet_2026_03`, [official D400 datasheet, pp. 65, 89 and 92](https://www.realsenseai.com/wp-content/uploads/2026/03/RealSense-D400-Series-Datasheet-Mar-2026.pdf#page=92), especially Figure 4-9 and Table 4-22.
- `realsense_ros_official`, [official D405 Xacro](https://github.com/realsenseai/realsense-ros/blob/ros2-master/realsense2_description/urdf/_d405.urdf.xacro). The model labels its internal extrinsics nominal; runtime calibrated transforms take precedence.
