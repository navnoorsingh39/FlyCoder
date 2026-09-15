/**
 * Procedural adult Drosophila for FlyCoder.
 * Original Three.js primitives — not a third-party mesh, not biomechanics.
 * Wing taps visualize real COMMIT / REJECT / RUN events.
 */
(function (global) {
  const TILES = [
    { id: "DISPLAY_BLOCK", label: "BLOCK" },
    { id: "DISPLAY_FLEX", label: "FLEX" },
    { id: "TEXT_ALIGN_CENTER", label: "TEXT ALIGN" },
    { id: "MARGIN_AUTO", label: "MARGIN AUTO" },
    { id: "JUSTIFY_CENTER", label: "JUSTIFY CENTER" },
    { id: "ALIGN_CENTER", label: "ALIGN CENTER" },
    { id: "DELETE_LAST", label: "DELETE" },
    { id: "RUN", label: "RUN" },
  ];
  const WING_FOR = {
    DISPLAY_BLOCK: "L", DISPLAY_FLEX: "L", TEXT_ALIGN_CENTER: "L",
    MARGIN_AUTO: "R", JUSTIFY_CENTER: "R", ALIGN_CENTER: "R",
    DELETE_LAST: "L", RUN: "both",
  };

  function damp(cur, tgt, k) {
    return cur + (tgt - cur) * k;
  }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function ease(t) {
    t = clamp(t, 0, 1);
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  }
  function envelope(u) {
    if (u < 0.42) return ease(u / 0.42);
    if (u < 0.58) return 1;
    return 1 - ease((u - 0.58) / 0.42);
  }

  function mat(color, opts) {
    return new THREE.MeshStandardMaterial(Object.assign({
      color, roughness: 0.62, metalness: 0.08,
    }, opts || {}));
  }

  function ellipsoid(rx, ry, rz, material, segs) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1, segs || 18, segs || 14), material);
    m.scale.set(rx, ry, rz);
    m.castShadow = true;
    m.receiveShadow = true;
    return m;
  }

  function cyl(rTop, rBot, h, material, segs) {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBot, h, segs || 8), material);
    m.castShadow = true;
    return m;
  }

  function keyTexture(label, hot) {
    const c = document.createElement("canvas");
    c.width = 256;
    c.height = 96;
    const g = c.getContext("2d");
    g.fillStyle = hot ? "#244a38" : "#161e1b";
    g.fillRect(0, 0, 256, 96);
    g.strokeStyle = hot ? "#8ef0ad" : "#3d5348";
    g.lineWidth = 6;
    g.strokeRect(4, 4, 248, 88);
    g.fillStyle = hot ? "#8ef0ad" : "#d5e4dc";
    g.font = "bold 26px ui-monospace, Consolas, monospace";
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText(label, 128, 50);
    const tex = new THREE.CanvasTexture(c);
    tex.anisotropy = 4;
    return tex;
  }

  function makeLeg(side, lengthScale, materials) {
    const root = new THREE.Group();
    const coxa = new THREE.Group();
    const femur = cyl(0.028, 0.022, 0.22 * lengthScale, materials.leg);
    femur.position.y = -0.11 * lengthScale;
    const knee = new THREE.Group();
    knee.position.y = -0.22 * lengthScale;
    const tibia = cyl(0.018, 0.012, 0.2 * lengthScale, materials.leg);
    tibia.position.y = -0.1 * lengthScale;
    const tarsusG = new THREE.Group();
    tarsusG.position.y = -0.2 * lengthScale;
    const tarsus = cyl(0.01, 0.006, 0.12 * lengthScale, materials.leg);
    tarsus.position.y = -0.06 * lengthScale;
    tarsusG.add(tarsus);
    knee.add(tibia, tarsusG);
    coxa.add(femur, knee);
    root.add(coxa);
    root.userData = { coxa, knee, tarsusG, side };
    return root;
  }

  function makeWing(sign, materials) {
    const root = new THREE.Group();
    const shape = new THREE.Shape();
    shape.moveTo(0, 0);
    shape.quadraticCurveTo(0.2, 0.05, 0.62, 0.02);
    shape.quadraticCurveTo(0.7, -0.08, 0.42, -0.17);
    shape.quadraticCurveTo(0.14, -0.12, 0, 0);
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), materials.wing);
    mesh.rotation.x = -Math.PI / 2;
    mesh.scale.x = sign;
    root.add(mesh);
    root.userData = { mesh, sign };
    return root;
  }

  function buildFly(materials) {
    const root = new THREE.Group();
    const body = new THREE.Group();
    root.add(body);

    const thorax = ellipsoid(0.22, 0.18, 0.26, materials.thorax, 22);
    thorax.position.set(0, 0.16, 0);
    body.add(thorax);
    const scutellum = ellipsoid(0.12, 0.08, 0.1, materials.body, 12);
    scutellum.position.set(0, 0.28, -0.06);
    body.add(scutellum);

    const head = new THREE.Group();
    head.position.set(0, 0.18, 0.28);
    head.add(ellipsoid(0.16, 0.14, 0.16, materials.head, 20));
    const eyeGeo = new THREE.SphereGeometry(0.11, 18, 14, 0, Math.PI);
    const eyeL = new THREE.Mesh(eyeGeo, materials.eye);
    eyeL.position.set(-0.12, 0.02, 0.04);
    eyeL.rotation.y = Math.PI * 0.55;
    const eyeR = eyeL.clone();
    eyeR.position.x = 0.12;
    eyeR.rotation.y = -Math.PI * 0.55;
    head.add(eyeL, eyeR);
    const glowL = new THREE.PointLight(0x66d0c8, 0, 0.55);
    glowL.position.set(-0.16, 0.04, 0.12);
    const glowR = new THREE.PointLight(0x66d0c8, 0, 0.55);
    glowR.position.set(0.16, 0.04, 0.12);
    head.add(glowL, glowR);
    const antL = new THREE.Group();
    antL.position.set(-0.05, 0.12, 0.1);
    const antLa = cyl(0.008, 0.006, 0.16, materials.leg, 6);
    antLa.position.y = 0.08;
    antL.add(antLa);
    const antR = antL.clone();
    antR.position.x = 0.05;
    head.add(antL, antR);
    body.add(head);

    const abdomen = new THREE.Group();
    abdomen.position.set(0, 0.12, -0.22);
    for (let i = 0; i < 5; i++) {
      const s = 1 - i * 0.12;
      const seg = ellipsoid(0.16 * s, 0.13 * s, 0.1, i % 2 ? materials.stripe : materials.body, 14);
      seg.position.z = -0.14 * i;
      abdomen.add(seg);
    }
    body.add(abdomen);

    const wingL = makeWing(-1, materials);
    wingL.position.set(-0.07, 0.3, 0.04);
    const wingR = makeWing(1, materials);
    wingR.position.set(0.07, 0.3, 0.04);
    body.add(wingL, wingR);

    const legs = {};
    [
      ["LF", -1, 0.12, 0.12, 0.95],
      ["RF", 1, 0.12, 0.12, 0.95],
      ["LM", -1, 0.02, -0.02, 1.05],
      ["RM", 1, 0.02, -0.02, 1.05],
      ["LR", -1, -0.04, -0.16, 1.15],
      ["RR", 1, -0.04, -0.16, 1.15],
    ].forEach(([id, side, y, z, len]) => {
      const leg = makeLeg(side, len, materials);
      leg.position.set(side * 0.14, y, z);
      body.add(leg);
      legs[id] = leg;
    });

    root.userData = { body, head, abdomen, wingL, wingR, antL, antR, legs, glowL, glowR, eyeL, eyeR };
    return root;
  }

  function buildArena(scene) {
    const grid = new THREE.GridHelper(5.5, 22, 0x1c2824, 0x141a18);
    scene.add(grid);
    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(2.8, 48),
      new THREE.MeshStandardMaterial({ color: 0x0c100e, roughness: 0.92, metalness: 0.04 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const target = new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0x8cff66, emissive: 0x3a8a30, emissiveIntensity: 0.7, roughness: 0.4 })
    );
    target.add(new THREE.PointLight(0x8cff66, 0.55, 1.8));
    scene.add(target);

    const consoleG = new THREE.Group();
    consoleG.position.set(0, 0.46, 0.56);
    consoleG.rotation.x = -0.52;
    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(1.72, 0.04, 0.48),
      new THREE.MeshStandardMaterial({ color: 0x121816, roughness: 0.48, metalness: 0.12 })
    );
    consoleG.add(plate);
    const tiles = [];
    TILES.forEach((meta, i) => {
      const col = i % 4;
      const row = Math.floor(i / 4);
      const tex = keyTexture(meta.label, false);
      const tile = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.045, 0.2),
        new THREE.MeshStandardMaterial({ color: 0x161e1b, roughness: 0.45, emissive: 0x08140e, emissiveIntensity: 0.2 })
      );
      const face = new THREE.Mesh(
        new THREE.PlaneGeometry(0.38, 0.18),
        new THREE.MeshBasicMaterial({ map: tex, transparent: false })
      );
      face.rotation.x = -Math.PI / 2;
      face.position.y = 0.024;
      tile.add(face);
      tile.position.set(-0.66 + col * 0.44, 0.05, 0.1 - row * 0.22);
      tile.userData = { restY: 0.05, texOff: tex, texOn: keyTexture(meta.label, true), face, label: meta.label, id: meta.id };
      consoleG.add(tile);
      tiles.push(tile);
    });
    scene.add(consoleG);
    return { target, tiles, consoleG };
  }

  function FlyView(canvas) {
    this.canvas = canvas;
    this.ok = typeof THREE !== "undefined";
    this.pose = null;
    this.cur = {};
    this.recording = false;
    this.orbit = 0;
    this.dragging = false;
    this.lastX = 0;
    this.gesture = null;
    this.queued = null;
    this.onContact = null;
    if (!this.ok) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0e10);
    scene.fog = new THREE.Fog(0x0b0e10, 4.5, 9);
    this.scene = scene;

    const camera = new THREE.PerspectiveCamera(34, 1, 0.05, 30);
    camera.position.set(1.35, 1.58, 1.72);
    camera.lookAt(0, 0.32, 0.28);
    this.camera = camera;
    this.camHome = camera.position.clone();
    this.camTarget = new THREE.Vector3(0, 0.32, 0.28);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = false;
    this.renderer = renderer;

    const key = new THREE.DirectionalLight(0xf0e6d0, 1.1);
    key.position.set(2.2, 3.2, 1.4);
    key.castShadow = false;
    scene.add(key);
    scene.add(new THREE.AmbientLight(0x4a5852, 0.48));
    const fill = new THREE.DirectionalLight(0x6a90a8, 0.32);
    fill.position.set(-2, 1.2, -1);
    scene.add(fill);
    const rim = new THREE.DirectionalLight(0x88c8c0, 0.26);
    rim.position.set(0.2, 1.4, -2.2);
    scene.add(rim);

    this.materials = {
      body: mat(0x3a2418),
      thorax: mat(0x4a2c18, { roughness: 0.55 }),
      head: mat(0x2a1a12),
      stripe: mat(0x6b3a18),
      eye: mat(0x6a1212, { roughness: 0.25, metalness: 0.15 }),
      wing: new THREE.MeshPhysicalMaterial({
        color: 0xc8ddd4, transparent: true, opacity: 0.32,
        roughness: 0.18, metalness: 0.04, side: THREE.DoubleSide, depthWrite: false,
      }),
      leg: mat(0x1a120e, { roughness: 0.7 }),
    };

    this.fly = buildFly(this.materials);
    this.fly.position.y = 0.4;
    scene.add(this.fly);
    const arena = buildArena(scene);
    this.target = arena.target;
    this.tiles = arena.tiles;

    canvas.addEventListener("pointerdown", (e) => {
      if (this.recording) return;
      this.dragging = true;
      this.lastX = e.clientX;
    });
    addEventListener("pointerup", () => { this.dragging = false; });
    addEventListener("pointermove", (e) => {
      if (!this.dragging || this.recording) return;
      this.orbit += (e.clientX - this.lastX) * 0.006;
      this.lastX = e.clientX;
    });
  }

  FlyView.prototype.resize = function () {
    if (!this.ok) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  FlyView.prototype.applyState = function (state, recording) {
    this.recording = !!recording;
    this.pose = global.FlyMotion.computeFlyPose(state, performance.now() / 1000);
  };

  FlyView.prototype.resetPose = function () {
    this.gesture = null;
    this.queued = null;
    this.onContact = null;
    this.pose = global.FlyMotion.computeFlyPose({ running: false, finished: false, control: { mode: "SCANNING" } }, 0);
  };

  FlyView.prototype.playGesture = function (kind, index, action, onContact) {
    if (this.gesture && kind === "flutter" && this.gesture.kind !== "flutter") {
      this.queued = { kind, index, action, onContact: null };
      return;
    }
    if (this.gesture && this.onContact && !this.gesture.contacted) this.onContact();
    const wing = WING_FOR[action] || ((index % 4) < 2 ? "L" : "R");
    this.gesture = {
      kind: kind || "press",
      index: index || 0,
      action: action || "",
      wing,
      t0: performance.now(),
      dur: kind === "flutter" ? 420 : (kind === "run" ? 560 : 480),
      contacted: false,
    };
    this.onContact = onContact || null;
  };

  FlyView.prototype.tick = function (now) {
    if (!this.ok) return;
    const t = now / 1000;
    const pose = this.pose || global.FlyMotion.computeFlyPose({}, t);
    const k = pose.paused ? 0.04 : 0.14;
    const u = this.fly.userData;
    const c = this.cur;
    const set = (key, val) => { c[key] = damp(c[key] || 0, val, k); return c[key]; };

    let lean = 0;
    let back = 0;
    let wL = pose.wingL;
    let wR = pose.wingR;
    let rL = pose.wingReachL || 0.12;
    let rR = pose.wingReachR || 0.12;
    let pressI = -1;
    let gAmt = 0;

    if (this.gesture) {
      const g = this.gesture;
      const u01 = (now - g.t0) / g.dur;
      if (u01 >= 1) {
        if (!g.contacted && this.onContact) this.onContact();
        this.gesture = null;
        this.onContact = null;
        if (this.queued) {
          const q = this.queued;
          this.queued = null;
          this.playGesture(q.kind, q.index, q.action, q.onContact);
        }
      } else {
        gAmt = envelope(u01);
        if (!g.contacted && u01 >= 0.4) {
          g.contacted = true;
          if (this.onContact) this.onContact();
        }
        if (g.kind === "reject") {
          back = gAmt * 0.12;
          wL -= gAmt * 0.55;
          rL -= gAmt * 0.4;
          pressI = 6;
        } else if (g.kind === "flutter") {
          const fl = Math.sin(u01 * Math.PI * 8) * (1 - u01) * 0.28;
          wL += fl;
          wR -= fl;
        } else if (g.kind === "run") {
          const a = envelope(u01);
          const b = envelope(clamp((u01 - 0.12) / 0.88, 0, 1));
          wL += a * 0.55;
          wR -= b * 0.55;
          rL += a * 0.7;
          rR += b * 0.7;
          lean = Math.max(a, b) * 0.18;
          pressI = 7;
        } else {
          lean = gAmt * 0.2;
          if (g.wing === "L" || g.wing === "both") {
            wL += gAmt * 0.5;
            rL += gAmt * 0.85;
          }
          if (g.wing === "R" || g.wing === "both") {
            wR -= gAmt * 0.5;
            rR += gAmt * 0.85;
          }
          pressI = g.index;
        }
      }
    }

    this.fly.position.x = set("x", pose.x - back);
    this.fly.position.z = set("z", pose.z + lean * 0.08);
    u.body.rotation.y = set("yaw", pose.yaw);
    u.body.rotation.x = set("pitch", pose.pitch + lean * 0.35);
    u.body.rotation.z = set("roll", pose.roll);
    u.head.rotation.y = set("headYaw", pose.headYaw);
    u.head.rotation.x = set("headPitch", pose.headPitch + lean * 0.25);
    u.abdomen.rotation.x = set("abdomen", pose.abdomen);
    u.wingL.rotation.z = set("wingL", wL);
    u.wingR.rotation.z = set("wingR", wR);
    u.wingL.rotation.x = set("reachL", rL);
    u.wingR.rotation.x = set("reachR", rR);
    u.antL.rotation.z = set("antL", pose.antennaL);
    u.antR.rotation.z = set("antR", pose.antennaR);

    Object.keys(pose.legs || {}).forEach((id) => {
      const spec = pose.legs[id];
      const leg = u.legs[id];
      if (!leg) return;
      const d = leg.userData;
      d.coxa.rotation.z = damp(d.coxa.rotation.z, spec.yaw, k);
      d.coxa.rotation.x = damp(d.coxa.rotation.x, spec.lift, k);
      d.knee.rotation.x = damp(d.knee.rotation.x, spec.bend, k);
    });

    u.glowL.intensity = 0.15 + pose.eyeL * 1.4;
    u.glowR.intensity = 0.15 + pose.eyeR * 1.4;
    this.materials.eye.emissiveIntensity = 0.15 + Math.max(pose.eyeL, pose.eyeR) * 0.5;

    if (this.target && pose.target) {
      this.target.position.x = damp(this.target.position.x, pose.target.x, 0.08);
      this.target.position.y = damp(this.target.position.y, 0.52 + pose.target.y, 0.08);
      this.target.position.z = damp(this.target.position.z, pose.target.z, 0.08);
    }

    this.tiles.forEach((tile, i) => {
      const on = i === pose.selected;
      const down = (i === pressI) && gAmt > 0.35;
      const reject = down && this.gesture && this.gesture.kind === "reject";
      const wantY = tile.userData.restY - (down && !reject ? 0.028 : 0);
      tile.position.y = damp(tile.position.y, wantY, 0.28);
      tile.material.emissive.setHex(reject ? 0xaa4433 : 0x08140e);
      tile.material.emissiveIntensity = on || down ? (reject ? 1.1 : 0.95) : 0.16;
      const tex = on || down ? tile.userData.texOn : tile.userData.texOff;
      if (tile.userData.face && tile.userData.face.material.map !== tex) {
        tile.userData.face.material.map = tex;
        tile.userData.face.material.needsUpdate = true;
      }
    });

    const orbit = this.recording ? 0 : this.orbit;
    this.camera.position.x = this.camHome.x * Math.cos(orbit) + this.camHome.z * Math.sin(orbit);
    this.camera.position.z = this.camHome.z * Math.cos(orbit) - this.camHome.x * Math.sin(orbit);
    this.camera.lookAt(this.camTarget);
    this.renderer.render(this.scene, this.camera);
  };

  global.FlyView = FlyView;
})(window);
