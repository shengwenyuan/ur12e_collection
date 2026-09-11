import * as THREE from './three.module.min.js';
import {frames} from './kinematics.js';

const viewport = document.querySelector('#viewport');
const status = document.querySelector('#status');
const notice = document.querySelector('#notice');
const details = document.querySelector('#details');
const names = ['Base', 'Shoulder', 'Elbow', 'Wrist 1', 'Wrist 2', 'Wrist 3'];
document.querySelector('#joints').innerHTML = names.map((name, i) =>
  `<div class="row"><span>J${i + 1} · ${name}</span><b id="q${i}">—</b></div>`).join('');

const scene = new THREE.Scene();
scene.background = new THREE.Color('#101923');
const camera = new THREE.PerspectiveCamera(42, 1, 0.02, 30);
camera.up.set(0, 0, 1);
const renderer = new THREE.WebGLRenderer({antialias: true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
viewport.append(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xd6edff, 0x40556b, 2.8));
const light = new THREE.DirectionalLight(0xffffff, 3.2);
light.position.set(2, -3, 5); scene.add(light);
const grid = new THREE.GridHelper(4, 40, 0x526477, 0x253647);
grid.rotation.x = Math.PI / 2; scene.add(grid);
scene.add(new THREE.AxesHelper(0.35));
const material = color => new THREE.MeshStandardMaterial({color, roughness:0.42, metalness:0.3});
const silver = material(0xbbcbd7), blue = material(0x54a8ce), dark = material(0x354b5f);
const robot = new THREE.Group(); scene.add(robot); robot.visible = false;
const mesh = (geometry, surface, parent = robot) => {
  const value = new THREE.Mesh(geometry, surface); parent.add(value); return value;
};
const base = mesh(new THREE.CylinderGeometry(0.1, 0.115, 0.06, 40), dark);
base.rotation.x = Math.PI / 2; base.position.z = 0.03;
const links = Array.from({length:6}, (_, i) =>
  mesh(new THREE.CylinderGeometry(i < 3 ? 0.042 : 0.031, i < 3 ? 0.042 : 0.031, 1, 24), silver));
const joints = Array.from({length:6}, (_, i) =>
  mesh(new THREE.SphereGeometry(i < 3 ? 0.069 : 0.049, 24, 16), blue));
const flange = new THREE.Group(); robot.add(flange); flange.matrixAutoUpdate = false;
const plate = mesh(new THREE.BoxGeometry(0.12, 0.065, 0.028), dark, flange);
plate.position.z = 0.014;
const stripe = mesh(new THREE.BoxGeometry(0.023, 0.063, 0.031), material(0xf4b963), flange);
stripe.position.set(0.043, 0, 0.017);
flange.add(new THREE.AxesHelper(0.18));
const unitY = new THREE.Vector3(0, 1, 0);
function showPose(q) {
  const transforms = frames(q);
  const points = transforms.map(t => new THREE.Vector3(t[3], t[7], t[11]));
  links.forEach((link, i) => {
    const delta = points[i + 1].clone().sub(points[i]);
    link.position.copy(points[i]).add(points[i + 1]).multiplyScalar(0.5);
    link.scale.y = delta.length();
    if (delta.lengthSq() > 0) link.quaternion.setFromUnitVectors(unitY, delta.normalize());
    joints[i].position.copy(points[i]);
    document.querySelector(`#q${i}`).textContent = (q[i] * 180 / Math.PI).toFixed(1) + '°';
  });
  flange.matrix.set(...transforms.at(-1));
  robot.visible = true;
}

const focus = new THREE.Vector3(0.2, 0, 0.58);
let yaw = -1.02, elevation = 0.38, distance = 3.0, pointer = null;
function placeCamera() {
  camera.position.set(
    distance * Math.cos(elevation) * Math.cos(yaw),
    distance * Math.cos(elevation) * Math.sin(yaw),
    distance * Math.sin(elevation),
  ).add(focus);
  camera.lookAt(focus);
}
renderer.domElement.addEventListener('pointerdown', event => {
  pointer = [event.clientX, event.clientY]; renderer.domElement.setPointerCapture(event.pointerId);
});
renderer.domElement.addEventListener('pointermove', event => {
  if (!pointer) return;
  yaw -= (event.clientX - pointer[0]) * 0.007;
  elevation = THREE.MathUtils.clamp(elevation + (event.clientY - pointer[1]) * 0.007, -0.15, 1.55);
  pointer = [event.clientX, event.clientY]; placeCamera();
});
for (const kind of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  renderer.domElement.addEventListener(kind, () => {pointer = null;});
}
renderer.domElement.addEventListener('wheel', event => {
  event.preventDefault(); distance = THREE.MathUtils.clamp(distance * Math.exp(event.deltaY * 0.001), 0.6, 9); placeCamera();
}, {passive:false});
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  const view = button.dataset.view;
  yaw = view === 'orbit' ? -1.02 : -Math.PI / 2;
  elevation = view === 'top' ? 1.55 : view === 'front' ? 0.04 : 0.38;
  distance = 3; placeCamera();
}));
placeCamera();
function resize() {
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
}
addEventListener('resize', resize); resize();
let lastResponse = 0;
function unavailable(message) {
  status.textContent = 'STALE · Last measured pose'; status.className = '';
  notice.textContent = message;
}
async function poll() {
  try {
    const response = await fetch('/state', {cache:'no-store', signal:AbortSignal.timeout(1500)});
    if (!response.ok) throw new Error('Observer unavailable');
    const state = await response.json(); lastResponse = performance.now();
    if (state.actual_q) showPose(state.actual_q);
    if (state.fresh) {
      status.textContent = 'LIVE · Actual feedback'; status.className = 'live'; notice.textContent = '';
    } else unavailable(state.error || 'Waiting for actual state');
    details.textContent = state.actual_q
      ? `Controller ${state.timestamp_s.toFixed(3)} s · Age ${state.age_ms} ms · 30 Hz observer`
      : robot.visible ? 'Waiting for reader; last measured pose retained.'
      : 'No measured pose received. Robot model is hidden.';
  } catch (error) { unavailable(`Observer disconnected: ${error.message}`); }
  setTimeout(poll, 50);
}
poll();
renderer.setAnimationLoop(() => {
  if (lastResponse && performance.now() - lastResponse > 1500) unavailable('No recent observer response');
  renderer.render(scene, camera);
});
