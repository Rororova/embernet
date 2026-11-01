import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const V = (v) => new THREE.Vector3(...v);
const TAU = Math.PI * 2;
function setPoints(object, points) {
  const data = new Float32Array(points.length * 3);
  points.forEach((p, i) => {
    data[i * 3] = p.x;
    data[i * 3 + 1] = p.y;
    data[i * 3 + 2] = p.z;
  });
  const current = object.geometry.getAttribute("position");
  if (!current || current.count !== points.length)
    object.geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(data, 3),
    );
  else {
    current.array.set(data);
    current.needsUpdate = true;
  }
  object.geometry.setDrawRange(0, points.length);
  if (points.length) object.geometry.computeBoundingSphere();
}
const ground = (x, y) => -0.7 - 1.1 * Math.sin(x * 0.025) * Math.sin(y * 0.027);

function smokeTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d"),
    g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,0.55)");
  g.addColorStop(0.4, "rgba(255,255,255,0.38)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(canvas);
}

function label(text, color = "#e9eee1") {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const c = canvas.getContext("2d");
  c.font = "600 25px Segoe UI";
  c.textAlign = "center";
  c.fillStyle = "#132b2ddd";
  c.beginPath();
  c.roundRect(12, 7, 232, 46, 8);
  c.fill();
  c.fillStyle = color;
  c.fillText(text, 128, 39);
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map, depthTest: false, transparent: true }),
  );
  sprite.scale.set(17, 4.25, 1);
  sprite.userData.screenLabel = true;
  return sprite;
}

const flameVertex = `uniform float time; varying vec2 vUv; varying float vH;
  void main(){vUv=uv;vH=position.z;vec3 p=position;
  p.x+=sin(time*6.0+position.z*1.8+position.y)*position.z*.11;
  p.y+=cos(time*4.7+position.z*2.2+position.x)*position.z*.09;
  gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`;
const flameFragment = `uniform float time; varying vec2 vUv; varying float vH;
  void main(){float edge=abs(vUv.x-.5)*2.;float h=vUv.y;
  float shape=(1.-edge)*(1.-h);float flicker=.84+.16*sin(h*19.+time*11.+vUv.x*12.);
  float a=smoothstep(.02,.24,shape*flicker)*(1.-smoothstep(.7,1.,h));
  vec3 hot=mix(vec3(1.,.12,.008),vec3(1.,.77,.16),pow(1.-h,1.7));
  hot=mix(hot,vec3(1.,.96,.68),pow(max(0.,(1.-edge)*(1.-h)),3.));
  gl_FragColor=vec4(hot*1.25,a*.88);}`;

export class ForestView {
  constructor(canvas, { onSelect, onPlace, onReady, onError } = {}) {
    this.canvas = canvas;
    this.onSelect = onSelect;
    this.onPlace = onPlace;
    this.onReady = onReady;
    this.state = null;
    this.selected = "E02";
    this.tool = null;
    this.mode = "orbit";
    this.drones = new Map();
    this.fires = new Map();
    this.subjects = new Map();
    this.reports = new Map();
    this.loading = true;
    this.clock = new THREE.Clock();
    this.visualTime = 0;
    this.elapsed = 0;
    this.frameCount = 0;
    this.fpsTime = 0;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#a5b5b7");
    this.scene.fog = new THREE.FogExp2("#bacbd0", 0.00075);
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas,
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      });
    } catch (error) {
      onError?.(error);
      return;
    }
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.0));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.95;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    this.renderer.shadowMap.needsUpdate = true;
    this.camera = new THREE.PerspectiveCamera(46, 1, 0.2, 1800);
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(370, -185, 235);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(160, 145, 7);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.minDistance = 7;
    this.controls.maxDistance = 720;
    this.controls.maxPolarAngle = Math.PI * 0.475;
    this.scene.add(new THREE.HemisphereLight("#d9e9ed", "#5d6043", 0.8));
    this.scene.add(new THREE.AmbientLight("#d4dfcf", 0.65));
    const sun = new THREE.DirectionalLight("#fff1df", 2.2);
    sun.position.set(-110, -140, 350);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, {
      left: -280,
      right: 280,
      top: 280,
      bottom: -280,
      near: 1,
      far: 900,
    });
    sun.shadow.normalBias = 0.18;
    sun.shadow.bias = -0.00008;
    sun.target.position.set(160, 150, 0);
    this.scene.add(sun, sun.target);
    this.effects = new THREE.Group();
    this.scene.add(this.effects);
    this.meshLinks = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({
        color: "#b6d9dc",
        transparent: true,
        opacity: 0.21,
      }),
    );
    this.scene.add(this.meshLinks);
    this.sensorRing = new THREE.Mesh(
      new THREE.RingGeometry(50.5, 51, 96),
      new THREE.MeshBasicMaterial({
        color: "#bed8c9",
        transparent: true,
        opacity: 0.45,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    this.scene.add(this.sensorRing);
    this.smokeMap = smokeTexture();
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    this.addSky();
    this.addLake();
    this.addLandmarks();
    this.bindInput();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.resize();
    this.load().catch((error) => onError?.(error));
    this.renderer.setAnimationLoop(() => this.frame());
    canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      onError?.(new Error("3D graphics context lost. Reload the page."));
    });
  }

  addSky() {
    const geometry = new THREE.SphereGeometry(1100, 24, 16);
    const material = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        top: { value: new THREE.Color("#6c9cbc") },
        bottom: { value: new THREE.Color("#d4dfdc") },
      },
      vertexShader:
        "varying vec3 p;void main(){p=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}",
      fragmentShader:
        "uniform vec3 top;uniform vec3 bottom;varying vec3 p;void main(){float h=clamp((p.z+40.)/650.,0.,1.);gl_FragColor=vec4(mix(bottom,top,pow(h,.65)),1.);\n#include <colorspace_fragment>\n}",
    });
    this.scene.add(new THREE.Mesh(geometry, material));
  }

  addLake() {
    const geometry = new THREE.CircleGeometry(25, 80);
    const material = new THREE.MeshPhysicalMaterial({
      color: "#638e91",
      roughness: 0.21,
      metalness: 0.25,
      transparent: true,
      opacity: 0.95,
      clearcoat: 1,
    });
    const lake = new THREE.Mesh(geometry, material);
    lake.position.set(248, 280, -0.45);
    lake.scale.set(1, 0.74, 1);
    this.scene.add(lake);
    this.lake = lake;
    const bank = new THREE.Mesh(
      new THREE.RingGeometry(24, 28, 80),
      new THREE.MeshStandardMaterial({ color: "#9b9b73", roughness: 1 }),
    );
    bank.position.copy(lake.position);
    bank.position.z -= 0.03;
    bank.scale.copy(lake.scale);
    this.scene.add(bank);
  }

  addLandmarks() {
    const border = [];
    for (const p of [
      [0, 0, 0.4],
      [320, 0, 0.4],
      [320, 320, 0.4],
      [0, 320, 0.4],
      [0, 0, 0.4],
    ])
      border.push(...p);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(border, 3));
    const line = new THREE.Line(
      g,
      new THREE.LineDashedMaterial({
        color: "#c6d3b7",
        dashSize: 2,
        gapSize: 5,
        transparent: true,
        opacity: 0.28,
      }),
    );
    line.computeLineDistances();
    this.scene.add(line);
    const sign = label("EMBERNET / FIELD BASE", "#ede5c8");
    sign.userData.screenLabel = false;
    sign.position.set(160, -28, 8);
    sign.scale.set(30, 7.5, 1);
    this.scene.add(sign);
  }

  async load() {
    const loader = new GLTFLoader();
    const [forest, drone, person] = await Promise.all(
      ["/assets/forest.glb", "/assets/drone.glb", "/assets/person.glb"].map(
        (url) => loader.loadAsync(url),
      ),
    );
    forest.scene.traverse((o) => {
      if (o.isMesh) {
        o.receiveShadow = true;
        o.castShadow = true;
        o.material.onBeforeCompile = (shader) => {
          shader.vertexShader = shader.vertexShader
            .replace(
              "#include <common>",
              "#include <common>\nvarying vec3 vSurfacePosition;",
            )
            .replace(
              "#include <begin_vertex>",
              "#include <begin_vertex>\nvSurfacePosition=position;",
            );
          shader.fragmentShader = shader.fragmentShader
            .replace(
              "#include <common>",
              "#include <common>\nvarying vec3 vSurfacePosition;\nfloat surfaceNoise(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}",
            )
            .replace(
              "#include <color_fragment>",
              "#include <color_fragment>\ndiffuseColor.rgb *= .9+.1*surfaceNoise(vSurfacePosition.xy*9.0);",
            );
        };
      }
    });
    this.scene.add(forest.scene);
    this.droneTemplate = drone.scene;
    this.personTemplate = person.scene;
    this.loading = false;
    this.onReady?.();
    if (this.state)
      this.update(this.state, this.selected, this.tool, this.flags);
  }

  bindInput() {
    let down = null;
    this.canvas.addEventListener("pointerdown", (e) => {
      down = [e.clientX, e.clientY];
    });
    this.canvas.addEventListener("pointerup", (e) => {
      if (
        !this.state ||
        !down ||
        Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5
      )
        return;
      const r = this.canvas.getBoundingClientRect();
      this.pointer.set(
        ((e.clientX - r.left) / r.width) * 2 - 1,
        (-(e.clientY - r.top) / r.height) * 2 + 1,
      );
      this.raycaster.setFromCamera(this.pointer, this.camera);
      if (this.tool) {
        const hit = new THREE.Vector3();
        if (
          this.raycaster.ray.intersectPlane(this.plane, hit) &&
          hit.x >= 0 &&
          hit.y >= 0 &&
          hit.x <= 320 &&
          hit.y <= 320
        )
          this.onPlace?.(Math.round(hit.x), Math.round(hit.y));
        return;
      }
      const targets = [...this.drones.values()].map((d) => d.pickTarget);
      const hit = this.raycaster.intersectObjects(targets, false)[0];
      if (hit) this.onSelect?.(hit.object.userData.droneId);
    });
    this.controls.addEventListener("start", () => {
      if (this.mode !== "orbit") {
        this.mode = "orbit";
        this.controls.enabled = true;
        this.onModeChange?.("orbit");
      }
    });
  }

  resize() {
    if (!this.renderer) return;
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.renderer.setSize(r.width, r.height, false);
    this.camera.aspect = r.width / Math.max(1, r.height);
    this.camera.updateProjectionMatrix();
  }

  setMode(mode) {
    this.mode = mode;
    this.controls.enabled = true;
    if (mode === "orbit") {
      this.camera.position.set(370, -185, 235);
      this.controls.target.set(160, 145, 7);
      this.controls.update();
    }
    this.onModeChange?.(mode);
  }

  makeDrone(id) {
    const group = new THREE.Group();
    const body = this.droneTemplate.clone(true);
    group.add(body);
    body.traverse((o) => {
      if (o.isMesh) o.castShadow = true;
    });
    const tag = label(id);
    tag.position.z = 4;
    group.add(tag);
    const pickTarget = new THREE.Mesh(
      new THREE.SphereGeometry(5, 8, 8),
      new THREE.MeshBasicMaterial({ visible: false }),
    );
    pickTarget.userData.droneId = id;
    group.add(pickTarget);
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(3.2, 3.3, 48),
      new THREE.MeshBasicMaterial({
        color: "#f3ba7c",
        transparent: true,
        opacity: 0.8,
        side: THREE.DoubleSide,
      }),
    );
    halo.position.z = -1.3;
    group.add(halo);
    const rotors = [];
    for (const x of [-1.65, 1.65])
      for (const y of [-1.65, 1.65]) {
        const prop = new THREE.Mesh(
          new THREE.CircleGeometry(0.95, 24),
          new THREE.MeshBasicMaterial({
            color: "#b5c4bf",
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.12,
            depthWrite: false,
          }),
        );
        prop.position.set(x, y, 0.68);
        group.add(prop);
        rotors.push(prop);
      }
    const route = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineDashedMaterial({
        color: "#e0c39b",
        dashSize: 1.6,
        gapSize: 2.3,
        transparent: true,
        opacity: 0.65,
      }),
    );
    this.scene.add(route);
    const trail = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({
        color: "#b4cfbd",
        transparent: true,
        opacity: 0.25,
      }),
    );
    this.scene.add(trail);
    const water = new THREE.Line(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({
        color: "#c7eff5",
        transparent: true,
        opacity: 0.85,
      }),
    );
    this.scene.add(water);
    const particles = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({
        color: "#d7f4f4",
        size: 0.35,
        transparent: true,
        opacity: 0.8,
        depthWrite: false,
      }),
    );
    this.scene.add(particles);
    this.scene.add(group);
    return {
      group,
      body,
      tag,
      pickTarget,
      halo,
      rotors,
      route,
      trail,
      water,
      particles,
      target: new THREE.Vector3(),
      previous: new THREE.Vector3(),
      record: null,
    };
  }

  makeFire(f) {
    const group = new THREE.Group();
    group.position.set(f.x, f.y, ground(f.x, f.y) + 0.1);
    this.effects.add(group);
    const material = new THREE.ShaderMaterial({
      uniforms: { time: { value: 0 } },
      vertexShader: flameVertex,
      fragmentShader: flameFragment,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.NormalBlending,
    });
    const flames = [];
    for (let k = 0; k < 24; k++) {
      const geo = new THREE.PlaneGeometry(2.8, 6, 3, 6);
      geo.rotateX(Math.PI / 2);
      geo.translate(0, 0, 3);
      const flame = new THREE.Mesh(geo, material);
      const a = k * 2.39996;
      const rad = Math.sqrt((k + 0.5) / 24) * f.radius * 0.9;
      flame.position.set(Math.cos(a) * rad, Math.sin(a) * rad, 0);
      flame.rotation.z = a;
      flame.scale.set(0.8 + (k % 4) * 0.23, 1, 0.5 + (k % 5) * 0.15);
      group.add(flame);
      flames.push(flame);
    }
    const smoke = [];
    for (let k = 0; k < 28; k++) {
      const cloud = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: this.smokeMap,
          color: "#666c69",
          transparent: true,
          depthWrite: false,
          opacity: 0.25,
        }),
      );
      group.add(cloud);
      smoke.push(cloud);
    }
    const coal = new THREE.Mesh(
      new THREE.CircleGeometry(1, 40),
      new THREE.MeshStandardMaterial({
        color: "#352d23",
        roughness: 1,
        polygonOffset: true,
        polygonOffsetFactor: -1,
      }),
    );
    group.add(coal);
    const glow = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this.smokeMap,
        color: "#ff7e24",
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        opacity: 0.5,
      }),
    );
    glow.scale.set(f.radius * 4, f.radius * 4, 1);
    glow.position.z = 2;
    group.add(glow);
    const tag = label(f.id, "#ffd1a0");
    tag.position.set(0, 0, 12);
    group.add(tag);
    return {
      group,
      flames,
      smoke,
      material,
      coal,
      glow,
      tag,
      radius: f.radius,
      record: f,
    };
  }

  update(state, selected, tool, flags = {}) {
    this.state = state;
    this.selected = selected;
    this.tool = tool;
    this.flags = flags;
    this.renderer.shadowMap.needsUpdate = true;
    this.controls.enabled = !tool;
    if (this.loading) return;
    const living = new Set(state.drones.map((d) => d.id));
    for (const [id, d] of this.drones)
      if (!living.has(id)) {
        this.scene.remove(d.group, d.route, d.trail, d.water, d.particles);
        this.drones.delete(id);
      }
    for (const record of state.drones) {
      if (!this.drones.has(record.id)) {
        const created = this.makeDrone(record.id);
        created.group.position.copy(V(record.position));
        this.drones.set(record.id, created);
      }
      const d = this.drones.get(record.id);
      d.record = record;
      d.target.copy(V(record.position));
      d.halo.visible = record.id === selected;
      d.tag.visible = this.mode !== "pov";
      d.tag.scale.setScalar(record.id === selected ? 1.1 : 0.85);
      d.tag.scale.multiply(new THREE.Vector3(17, 4.25, 1));
      d.route.visible = record.id === selected && !!record.target;
      setPoints(d.route, [
        V(record.position),
        V(record.target || record.position),
      ]);
      d.route.computeLineDistances();
      d.trail.visible = record.id === selected;
      setPoints(d.trail, record.trails.map(V));
      d.water.visible = !!record.discharge;
      d.particles.visible = !!record.discharge;
    }
    const linkPoints = [];
    if (flags.mesh)
      for (const [a, b] of state.mesh.links) {
        linkPoints.push(
          V(state.drones.find((d) => d.id === a).position),
          V(state.drones.find((d) => d.id === b).position),
        );
      }
    setPoints(this.meshLinks, linkPoints);
    this.meshLinks.visible = !!flags.mesh;
    this.sensorRing.visible = !!flags.sensors;
    const chosen = state.drones.find((d) => d.id === selected);
    if (chosen)
      this.sensorRing.position.set(chosen.position[0], chosen.position[1], 0.5);
    const active = new Set();
    for (const f of state.truth.fires) {
      active.add(f.id);
      if (!this.fires.has(f.id)) this.fires.set(f.id, this.makeFire(f));
      const obj = this.fires.get(f.id);
      obj.record = f;
      obj.group.visible = flags.truth !== false;
      obj.coal.scale.setScalar(Math.max(f.radius, f.initial ** 0.5));
    }
    for (const [id, f] of this.fires)
      if (!active.has(id)) {
        this.effects.remove(f.group);
        this.fires.delete(id);
      }
    for (const report of this.reports.values()) report.visible = false;
    if (flags.truth === false) {
      const own = state.drones.find((d) => d.id === selected);
      for (const incident of own?.incidents || []) {
        if (["merged", "cleared"].includes(incident.status)) continue;
        const key = `${selected}:${incident.id}`;
        if (!this.reports.has(key)) {
          const group = new THREE.Group();
          const ring = new THREE.Mesh(
            new THREE.RingGeometry(0.94, 1, 64),
            new THREE.MeshBasicMaterial({
              color: incident.survivor ? "#a1d4ed" : "#e7b477",
              side: THREE.DoubleSide,
              transparent: true,
              opacity: 0.85,
              depthWrite: false,
            }),
          );
          group.add(ring);
          const tag = label(`Report ${incident.id}`, "#e9d7b5");
          tag.position.z = 4;
          group.add(tag);
          group.userData = { ring, tag };
          this.scene.add(group);
          this.reports.set(key, group);
        }
        const group = this.reports.get(key);
        group.visible = true;
        group.position.set(
          incident.position[0],
          incident.position[1],
          ground(...incident.position) + 0.3,
        );
        group.userData.ring.scale.setScalar(Math.max(2, incident.extent));
        group.userData.ring.material.opacity =
          state.time - incident.observed_at > 35 ? 0.35 : 0.85;
      }
    }
    for (const s of state.truth.subjects) {
      if (!this.subjects.has(s.id)) {
        let group;
        if (s.kind === "person") {
          group = this.personTemplate.clone(true);
        } else {
          group = new THREE.Group();
          const fur = new THREE.MeshStandardMaterial({
            color: "#a88d64",
            roughness: 1,
          });
          const body = new THREE.Mesh(
            new THREE.BoxGeometry(1.7, 0.65, 0.8),
            fur,
          );
          body.position.z = 0.9;
          group.add(body);
          for (const x of [-0.65, 0.65])
            for (const y of [-0.25, 0.25]) {
              const leg = new THREE.Mesh(
                new THREE.CylinderGeometry(0.06, 0.08, 0.7, 6),
                fur,
              );
              leg.rotation.x = Math.PI / 2;
              leg.position.set(x, y, 0.35);
              group.add(leg);
            }
          const head = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 0.45, 0.6),
            fur,
          );
          head.position.set(1, 0, 1.3);
          group.add(head);
        }
        group.position.set(s.x, s.y, ground(s.x, s.y));
        group.traverse((o) => {
          if (o.isMesh) o.castShadow = true;
        });
        const tag = label(
          s.kind === "person" ? "Possible person" : "Animal",
          "#cadfe3",
        );
        tag.position.z = 4;
        group.add(tag);
        this.scene.add(group);
        this.subjects.set(s.id, group);
      }
      this.subjects.get(s.id).visible = flags.truth !== false;
    }
  }

  frame() {
    if (!this.renderer) return;
    const dt = Math.min(this.clock.getDelta(), 0.07);
    this.elapsed += dt;
    if (this.state) {
      if (!this.state.paused) this.visualTime += dt * this.state.speed;
      this.visualTime = THREE.MathUtils.lerp(
        this.visualTime,
        this.state.time,
        1 - Math.exp(-dt * 7),
      );
      for (const [id, d] of this.drones) {
        const before = d.group.position.clone();
        d.group.position.lerp(d.target, 1 - Math.exp(-dt * 7));
        const motion = d.group.position.clone().sub(before);
        if (motion.lengthSq() > 0.0001) {
          const heading = Math.atan2(-motion.x, motion.y);
          d.group.rotation.z = THREE.MathUtils.lerp(
            d.group.rotation.z,
            heading,
            0.08,
          );
        }
        const flying = d.record.position[2] > 2;
        d.body.rotation.x = flying
          ? Math.sin(this.visualTime * 2 + Number(id.slice(1))) * 0.018
          : 0;
        d.rotors.forEach((r, k) => {
          r.visible = flying;
          r.rotation.z = this.visualTime * (k % 2 ? 1 : -1) * 34;
        });
        const tagHeight =
          (this.camera.position.distanceTo(d.group.position) *
            2 *
            Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) *
            26) /
          Math.max(1, this.canvas.clientHeight);
        d.tag.scale.set(tagHeight * 4, tagHeight, 1);
        if (d.record.discharge) {
          const target = V(d.record.discharge.target);
          target.z = ground(target.x, target.y) + 0.3;
          const from = d.group.position
            .clone()
            .add(new THREE.Vector3(0, 0, -1.1));
          setPoints(d.water, [from, target]);
          const drops = [];
          for (let k = 0; k < 70; k++) {
            const t = (k / 70 + this.visualTime * 0.6) % 1;
            const p = from.clone().lerp(target, t);
            p.x += Math.sin(k * 17 + this.visualTime * 3) * t * 0.7;
            p.y += Math.cos(k * 13) * t * 0.7;
            drops.push(p);
          }
          setPoints(d.particles, drops);
        }
      }
      for (const f of this.fires.values()) {
        const active = f.record.remaining > 0.2;
        f.material.uniforms.time.value = this.visualTime;
        f.flames.forEach((flame, k) => {
          flame.visible = active;
          const ratio = Math.max(
            0.18,
            Math.min(1.5, f.record.radius / f.radius),
          );
          flame.scale.x = ratio * (0.8 + (k % 4) * 0.23);
          flame.scale.z = (0.6 + f.record.severity * 0.6) * ratio;
          const angle = k * 2.39996,
            radius = Math.sqrt((k + 0.5) / 24) * f.record.radius * 0.9;
          flame.position.x = Math.cos(angle) * radius;
          flame.position.y = Math.sin(angle) * radius;
        });
        f.glow.visible = active;
        f.tag.visible = active;
        f.smoke.forEach((cloud, k) => {
          cloud.visible = active;
          const t = (k / 28 + this.visualTime * 0.035) % 1;
          const angle = k * 2.3999;
          const rad = f.record.radius * (0.2 + t * 0.7);
          cloud.position.set(
            Math.cos(angle) * rad + t * t * 14,
            Math.sin(angle) * rad + t * 4,
            3 + t * 42,
          );
          const size = 5 + t * 17;
          cloud.scale.set(size, size, 1);
          cloud.material.opacity = Math.sin(t * Math.PI) * 0.27;
        });
      }
      const d = this.drones.get(this.selected);
      if (d && this.mode === "follow") {
        const target = d.group.position.clone();
        const offset = new THREE.Vector3(14, -28, 11).applyAxisAngle(
          new THREE.Vector3(0, 0, 1),
          d.group.rotation.z,
        );
        this.camera.position.lerp(
          target.clone().add(offset),
          1 - Math.exp(-dt * 3),
        );
        const aim = target.clone();
        if (d.record.discharge) aim.lerp(V(d.record.discharge.target), 0.45);
        else aim.z -= 2;
        this.controls.target.lerp(aim, 1 - Math.exp(-dt * 5));
        this.camera.lookAt(this.controls.target);
      } else if (d && this.mode === "pov") {
        const p = d.group.position.clone();
        p.z -= 1.4;
        this.camera.position.copy(p);
        let aim = d.record.target
          ? V(d.record.target)
          : p.clone().add(new THREE.Vector3(0, 25, -18));
        if (aim.distanceTo(p) < 6)
          aim = new THREE.Vector3(p.x, p.y, ground(p.x, p.y));
        this.camera.lookAt(aim);
        d.group.visible = false;
      }
      for (const [id, drone] of this.drones)
        drone.group.visible = !(this.mode === "pov" && id === this.selected);
    }
    if (this.mode === "orbit") this.controls.update();
    this.scene.traverse((object) => {
      if (!object.userData.screenLabel) return;
      const position = object.getWorldPosition(new THREE.Vector3());
      const h =
        (this.camera.position.distanceTo(position) *
          2 *
          Math.tan(THREE.MathUtils.degToRad(this.camera.fov) / 2) *
          26) /
        Math.max(1, this.canvas.clientHeight);
      object.scale.set(h * 4, h, 1);
    });
    this.renderer.render(this.scene, this.camera);
    this.frameCount++;
    this.fpsTime += dt;
    if (this.fpsTime > 1) {
      const el = document.getElementById("render-status");
      if (el)
        el.textContent = `${Math.round(this.frameCount / this.fpsTime)} FPS · LIVE 3D`;
      this.frameCount = 0;
      this.fpsTime = 0;
    }
  }
}
