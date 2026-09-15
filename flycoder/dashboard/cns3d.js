/**
 * Spatial connectome visualization from real MaleCNS soma coordinates.
 * Not neuron morphology. Additive soma cloud + sampled real edges + occupancy shell.
 */
(function (global) {
  const KIND_RGB = [
    [0.62, 0.78, 0.82],
    [0.38, 0.78, 0.95],
    [0.40, 0.74, 0.94],
    [0.42, 0.70, 0.92],
    [0.42, 0.92, 0.62],
    [0.50, 0.96, 0.68],
    [0.92, 0.52, 0.38],
  ];

  const VERT = `
    attribute float aSize;
    varying vec3 vColor;
    varying float vDepth;
    void main() {
      vColor = color;
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vDepth = -mv.z;
      gl_PointSize = clamp(aSize / max(vDepth * 0.9, 0.22), 1.2, 16.0);
      gl_Position = projectionMatrix * mv;
    }
  `;
  const FRAG = `
    varying vec3 vColor;
    varying float vDepth;
    void main() {
      vec2 p = gl_PointCoord - vec2(0.5);
      float d = length(p);
      if (d > 0.5) discard;
      float core = smoothstep(0.5, 0.12, d);
      float fade = exp(-max(vDepth - 0.35, 0.0) * 0.55);
      gl_FragColor = vec4(vColor, core * fade);
    }
  `;

  function pointMat() {
    return new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
  }

  function CNSView(canvas) {
    this.canvas = canvas;
    this.ok = typeof THREE !== "undefined";
    this.recording = true;
    this.orbit = 0;
    this.dragging = false;
    this.lastX = 0;
    this.activity = null;
    this.edgePulse = null;
    this.n = 0;
    this.callout = "";
    this.bridge = 0;
    this.accent = 0;
    this.ids = [];
    if (!this.ok) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030607);
    scene.fog = new THREE.FogExp2(0x030607, 0.22);
    this.scene = scene;
    this.rig = new THREE.Group();
    scene.add(this.rig);

    const camera = new THREE.PerspectiveCamera(36, 1, 0.04, 8);
    this.camera = camera;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance", preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x030607, 1);
    this.renderer = renderer;

    canvas.addEventListener("pointerdown", (e) => {
      if (this.recording) return;
      this.dragging = true;
      this.lastX = e.clientX;
    });
    addEventListener("pointerup", () => { this.dragging = false; });
    addEventListener("pointermove", (e) => {
      if (!this.dragging || this.recording) return;
      this.orbit += (e.clientX - this.lastX) * 0.005;
      this.lastX = e.clientX;
    });
  }

  CNSView.prototype.resize = function () {
    if (!this.ok) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  };

  CNSView.prototype.load = function (S) {
    if (!this.ok || !S || !S.vis || !S.vis.x || !S.vis.x.length) return;
    const vis = S.vis;
    this.n = vis.x.length;
    this.activity = new Float32Array(this.n);
    this.kind = vis.kind || [];
    this.ids = vis.id || [];
    this.edges = vis.edges || [];
    this.edgePulse = new Float32Array(this.edges.length);
    this.labels = S.labels || [];

    while (this.rig.children.length) this.rig.remove(this.rig.children[0]);

    const pos = new Float32Array(this.n * 3);
    const col = new Float32Array(this.n * 3);
    const size = new Float32Array(this.n);
    for (let i = 0; i < this.n; i++) {
      pos[i * 3] = vis.x[i];
      pos[i * 3 + 1] = vis.y[i];
      pos[i * 3 + 2] = vis.z[i] || 0;
      const k = this.kind[i] || 0;
      const rgb = KIND_RGB[k] || KIND_RGB[0];
      const dim = k === 0 ? 0.22 : 0.38;
      col[i * 3] = rgb[0] * dim;
      col[i * 3 + 1] = rgb[1] * dim;
      col[i * 3 + 2] = rgb[2] * dim;
      size[i] = k === 0 ? 4.2 : 6.0;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    geo.setAttribute("aSize", new THREE.BufferAttribute(size, 1));
    geo.computeBoundingSphere();
    this.geo = geo;
    this.rig.add(new THREE.Points(geo, pointMat()));

    if (vis.density && vis.density.length) {
      const dpos = new Float32Array(vis.density.length * 3);
      const dcol = new Float32Array(vis.density.length * 3);
      const dsz = new Float32Array(vis.density.length);
      vis.density.forEach((d, i) => {
        dpos[i * 3] = d[0]; dpos[i * 3 + 1] = d[1]; dpos[i * 3 + 2] = d[2];
        const a = Math.min(1, (d[3] || 4) / 55);
        dcol[i * 3] = 0.18 * a;
        dcol[i * 3 + 1] = 0.38 * a;
        dcol[i * 3 + 2] = 0.42 * a;
        dsz[i] = 7 + a * 6;
      });
      const dgeo = new THREE.BufferGeometry();
      dgeo.setAttribute("position", new THREE.BufferAttribute(dpos, 3));
      dgeo.setAttribute("color", new THREE.BufferAttribute(dcol, 3));
      dgeo.setAttribute("aSize", new THREE.BufferAttribute(dsz, 1));
      this.rig.add(new THREE.Points(dgeo, pointMat()));
    }

    if (this.edges.length) {
      const epos = new Float32Array(this.edges.length * 6);
      const ecol = new Float32Array(this.edges.length * 6);
      this.edges.forEach((e, i) => {
        const a = e[0], b = e[1];
        epos[i * 6] = vis.x[a]; epos[i * 6 + 1] = vis.y[a]; epos[i * 6 + 2] = vis.z[a] || 0;
        epos[i * 6 + 3] = vis.x[b]; epos[i * 6 + 4] = vis.y[b]; epos[i * 6 + 5] = vis.z[b] || 0;
        ecol[i * 6] = 0.12; ecol[i * 6 + 1] = 0.28; ecol[i * 6 + 2] = 0.32;
        ecol[i * 6 + 3] = 0.12; ecol[i * 6 + 4] = 0.28; ecol[i * 6 + 5] = 0.32;
      });
      const egeo = new THREE.BufferGeometry();
      egeo.setAttribute("position", new THREE.BufferAttribute(epos, 3));
      egeo.setAttribute("color", new THREE.BufferAttribute(ecol, 3));
      this.edgeGeo = egeo;
      this.rig.add(new THREE.LineSegments(egeo, new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.28,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        fog: true,
      })));
    }

    this.rig.rotation.set(Math.PI / 2, 0, 0);
    const bs = geo.boundingSphere;
    this.viewRadius = bs && bs.radius ? bs.radius : 0.55;
    this.viewCenter = bs && bs.center ? bs.center.clone() : new THREE.Vector3();
  };

  CNSView.prototype.ingest = function (d, activity, edgePulse) {
    this.activity = activity;
    this.edgePulse = edgePulse;
    const kind = d.present_kind || "";
    let text = "";
    this.accent = 0;
    if (kind === "INPUT" || kind === "PROPAGATE") {
      const sn = d.sensory_norm || {};
      const bits = [];
      if ((sn.lc10aR || 0) > (sn.lc10aL || 0) && sn.lc10aR > 0.08) bits.push("LC10a-R ↑");
      else if ((sn.lc10aL || 0) > 0.08) bits.push("LC10a-L ↑");
      if ((sn.lplc1R || 0) > 0.08) bits.push("LPLC1 ↑");
      if ((sn.lc4 || 0) > 0.08) bits.push("LC4 / LPLC2 ↑");
      text = bits.length ? `SENSORY  ${bits.slice(0, 2).join("  ")}` : "";
    } else if (kind === "READOUT" || kind === "CURSOR_MOVE") {
      const c = d.control || {};
      text = c.steer > 0.04 ? "DESCENDING  DNa02-R" : (c.steer < -0.04 ? "DESCENDING  DNa02-L" : "DESCENDING  DNa02");
      this.bridge = 1;
    } else if (kind === "COMMIT" || kind === "ACTION") {
      if (d.pulse === "reject") {
        text = "DESCENDING  MDN REJECT";
        this.accent = 2;
      } else {
        text = "DESCENDING  DNp01 COMMIT";
        this.accent = 1;
      }
      this.bridge = 1;
    } else if (kind === "SUCCESS") {
      text = "TARGET CENTERED";
      this.bridge = 1;
      this.accent = 1;
    }
    this.callout = text;
    const el = document.getElementById("cns-callout");
    if (el) {
      el.hidden = !text;
      el.textContent = text;
    }
  };

  CNSView.prototype.tick = function (now) {
    if (!this.ok || !this.geo) return;
    const col = this.geo.getAttribute("color");
    const sz = this.geo.getAttribute("aSize");
    const act = this.activity;
    if (act && col && sz) {
      for (let i = 0; i < this.n; i++) {
        const a = act[i] || 0;
        const k = this.kind[i] || 0;
        const rgb = KIND_RGB[k] || KIND_RGB[0];
        let g = (k === 0 ? 0.20 : 0.32) + a * 0.95;
        if (this.accent === 1 && (k === 5 || k === 4)) g += 0.25;
        if (this.accent === 2 && k === 6) g += 0.35;
        col.setXYZ(i, rgb[0] * g, rgb[1] * g, rgb[2] * g);
        sz.setX(i, (k === 0 ? 4.0 : 5.8) + a * 8.0);
      }
      col.needsUpdate = true;
      sz.needsUpdate = true;
    }
    if (this.edgeGeo && this.edges && this.edgePulse) {
      const ec = this.edgeGeo.getAttribute("color");
      for (let i = 0; i < this.edges.length; i++) {
        const p = this.edgePulse[i] || 0;
        const e = this.edges[i];
        const ga = 0.10 + (act && act[e[0]] || 0) * 0.45 + p * 0.7;
        const gb = 0.10 + (act && act[e[1]] || 0) * 0.45 + p * 0.7;
        const r = this.accent === 2 ? 0.85 : 0.35;
        const gch = this.accent === 2 ? 0.38 : 0.85;
        const bch = this.accent === 2 ? 0.28 : 0.92;
        ec.setXYZ(i * 2, r * ga, gch * ga, bch * ga);
        ec.setXYZ(i * 2 + 1, r * gb, gch * gb, bch * gb);
      }
      ec.needsUpdate = true;
    }
    if (this.bridge > 0.02) {
      this.bridge *= 0.94;
      const br = document.getElementById("cns-bridge");
      if (br) {
        br.classList.toggle("on", this.bridge > 0.12);
        br.style.opacity = String(this.bridge);
      }
    } else {
      const br = document.getElementById("cns-bridge");
      if (br && br.classList.contains("on")) {
        br.classList.remove("on");
        br.style.opacity = "0";
      }
    }

    const yaw = this.recording ? 0.38 : (0.38 + this.orbit);
    const r = Math.max(1.05, (this.viewRadius || 0.55) * 2.35);
    this.camera.position.set(Math.sin(yaw) * r, 0.22, Math.cos(yaw) * r);
    this.camera.lookAt(0, 0.02, 0);
    this.renderer.render(this.scene, this.camera);
  };

  global.CNSView = CNSView;
})(window);
