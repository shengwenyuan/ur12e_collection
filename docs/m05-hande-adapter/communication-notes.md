# M05: Hand-E Communication Research

> **Code style requirement: Economical code, exceptional readability, and excellent abstraction design.**

Status: research / transport selection pending. No adapter implementation or
hardware communication acceptance. On 2026-09-10 the user confirmed the UR12e
controller IP `10.18.1.106` and reported `Robotiq_Grippers` in the installed URCaps
list. The [actual unit inventory](../m03-ur-adapter/controller-inventory.md)
records UR Software `5.22.1` and the other pendant version fields. The URCap
version, gripper recognition and communication success remain unverified.
This update changes documentation only.

## Preferred candidate: existing Robotiq URCap bridge

Proposed path: collection PC -> `10.18.1.106:63352` TCP -> Robotiq URCap service
-> serial link -> Hand-E. This lets our client address the gripper service while
keeping the existing pendant integration. It still depends on that service;
Hand-E itself is not being assigned a native Ethernet endpoint. The port is a
candidate from documentation, not a measured fact about this robot.

SDU's ur_rtde documentation describes this as its direct URCap communication
option. It also explains that repeatedly injecting gripper scripts can interrupt
the arm's RTDE control script, making that approach unattractive for concurrent
teleoperation. This is the reasoning for preferring the socket bridge here.
[SDU integration guide](https://sdurobotics.gitlab.io/ur_rtde/pages/core_concepts/guides/use_with_robotiq_gripper.html).

A historical Robotiq-hosted example demonstrates the read query `GET POS` with
a newline terminator, and lists position request echo, status, object detection,
fault and current queries (`PRE`, `STA`, `OBJ`, `FLT`, `COU`). Treat this archived
example as a protocol lead; validate the installed version and response meanings
before adopting its fields. Preserve raw values; do not infer gripper feedback
from UR joint RTDE. [Archived Robotiq example](https://dof.robotiq.com/discussion/2420).

## Alternatives

| Transport | Fit and consequence |
| --- | --- |
| PC USB-to-RS485 -> Hand-E | Bypasses the UR controller, but requires suitable physical cabling and power. A local server can own the serial connection. |
| UR tool RS485 forwarding -> PC Modbus RTU | Retains wrist wiring while moving the protocol owner to the PC; requires a compatible forwarding installation. |

Hand-E's native interface is Modbus RTU over RS485. Documented defaults include
115200 baud, 8 data bits, no parity, one stop bit and device address 9; these can
be changed and must be confirmed on the actual device. Gripper feedback begins
at register 2000 (0x07D0). The manual describes direct USB/RS485 conversion and
optional industrial-protocol controllers. [Hand-E control manual](https://assets.robotiq.com/website-assets/support_documents/document/online/Hand-E_Instruction_Manual_Web_20190329.zip/Hand-E_Instruction_Manual_Web/Content/4.%20Control.htm).

UR documents flange RS485 forwarding and warns about conflicts with the Robotiq
Grippers URCap. Its setup differs between PolyScope 5 and PolyScope X. Do not add
a competing forwarding owner or uninstall the existing URCap during discovery.
[UR tool-communication guide](https://docs.universal-robots.com/Universal_Robots_ROS2_Documentation/doc/ur_robot_driver/ur_robot_driver/doc/setup_tool_communication.html).

## Facts needed before selecting the transport

1. Independently confirm reported UR Software `5.22.1` and installed
   `Robotiq_Grippers`; obtain the still-unknown URCap version and Hand-E firmware.
2. Wiring: short wrist connector, cable to controller USB/RS485, or external box.
3. Whether the installation page recognizes Hand-E, including its device ID.
4. For the preferred candidate, bounded read-only service response and raw field
   mapping. Reachability of `10.18.1.106` alone proves none of these.

The pendant currently reports DHCP and `Not connected to network!` while the
user reports ping reachability. Reconfirm the current address and reconcile
this status discrepancy before treating the candidate endpoint as configured.

Robotiq's e-Series installation manual describes the wrist coupling and the
URCap toolbar/program node. Seeing a gripper item under Program is consistent
with a URCap but does not prove that the package is installed correctly or that
the device is connected. [Robotiq installation](https://assets.robotiq.com/website-assets/support_documents/document/online/Hand-E_Instruction_Manual_e-Series_Web_20190329.zip/Hand-E_Instruction_Manual_e-Series_Web/Content/3.%20Installation.htm).

Current boundary: no robot/gripper connection was opened for this research.
A later read-only probe must exclude activation, reset, calibration, grip/release,
SET commands, program execution and tool-communication reconfiguration. Keep the
runtime Hand-E host/port unconfirmed until the installation is identified and
readback is validated. M05-A01/A02/A03 hardware acceptance remains NOT RUN.
